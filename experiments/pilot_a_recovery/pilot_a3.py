"""Pilot A-3: independent per-tool faults and cross-step saga recovery.

Exploratory deterministic simulator. Policies only receive public errors,
tool contracts and verification results. Latent fault labels are retained
for offline audit and the privileged diagnostic oracle only.
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

POLICIES = (
    "blind_retry",
    "verify_then_retry",
    "fixed_wait_verify",
    "conservative_escalation",
    "contract_aware",
    "saga_aware",
    "oracle_diagnostic",
)

TOOLS = {
    "inventory": {"idempotent": False, "compensatable": True, "visibility_bound": 4},
    "calendar": {"idempotent": True, "compensatable": True, "visibility_bound": 4},
    "order": {"idempotent": False, "compensatable": True, "visibility_bound": 4},
    "payment": {"idempotent": False, "compensatable": True, "visibility_bound": 4},
    "ledger": {"idempotent": False, "compensatable": False, "visibility_bound": 4},
    "customer": {"idempotent": True, "compensatable": True, "visibility_bound": 4},
    "shipment": {"idempotent": False, "compensatable": False, "visibility_bound": 4},
    "refund": {"idempotent": False, "compensatable": False, "visibility_bound": 4},
    "subscription": {"idempotent": True, "compensatable": True, "visibility_bound": 4},
    "notification": {"idempotent": False, "compensatable": False, "visibility_bound": 4},
}

TASKS = {
    "inventory_order_payment": ("inventory", "order", "payment"),
    "calendar_order_ledger": ("calendar", "order", "ledger"),
    "customer_order_shipment": ("customer", "order", "shipment"),
    "inventory_calendar_order": ("inventory", "calendar", "order"),
    "return_refund_restock": ("order", "refund", "inventory"),
    "subscription_ledger_notification": ("subscription", "ledger", "notification"),
}
TRAIN_TASKS = (
    "inventory_order_payment",
    "calendar_order_ledger",
    "customer_order_shipment",
)
VALIDATION_TASKS = ("inventory_calendar_order",)
HELDOUT_TASKS = ("return_refund_restock", "subscription_ledger_notification")

TRAIN_COMPOSITIONS = (
    "single_timeout",
    "timeout_then_rate_limit",
    "partial_then_delay",
    "schema_then_timeout",
)
VALIDATION_COMPOSITIONS = (
    "independent_mixed_val",
    "partial_then_timeout_val",
)
HELDOUT_COMPOSITIONS = (
    "partial_comp_failure",
    "delay_rate_permission",
    "triple_mixed",
)

ALL_TASKS = tuple(TASKS)
ALL_COMPOSITIONS = TRAIN_COMPOSITIONS + VALIDATION_COMPOSITIONS + HELDOUT_COMPOSITIONS
MAX_PUBLIC_WAIT = 4


def make_fault_vector(task_name, composition, seed):
    """Create a per-step fault vector; never broadcast one fault to all tools."""
    rng = random.Random(seed)
    steps = TASKS[task_name]
    faults = []
    for tool_name in steps:
        can_compensate = TOOLS[tool_name]["compensatable"]
        faults.append({
            "fault": "none",
            "delay": 0,
            "retry_after": 0,
            "compensation_available": bool(can_compensate and rng.random() < 0.90),
        })

    def assign(index, fault, compensation_available=None):
        tool_name = steps[index]
        can_compensate = TOOLS[tool_name]["compensatable"]
        if compensation_available is None:
            compensation_available = bool(can_compensate and rng.random() < 0.90)
        faults[index] = {
            "fault": fault,
            "delay": rng.randint(1, 4) if fault in ("timeout_after", "delayed_visibility") else 0,
            "retry_after": rng.randint(1, 3) if fault == "rate_limit" else 0,
            "compensation_available": bool(compensation_available and can_compensate),
        }

    n = len(steps)
    if composition == "single_timeout":
        assign(rng.randrange(n), rng.choice(("timeout_before", "timeout_after", "delayed_visibility")))
    elif composition == "timeout_then_rate_limit":
        assign(0, "timeout_after")
        assign(1, "rate_limit")
    elif composition == "partial_then_delay":
        assign(0, "partial_commit")
        assign(1, "delayed_visibility")
    elif composition == "schema_then_timeout":
        assign(0, "schema_drift")
        assign(1, "timeout_before")
    elif composition == "independent_mixed_val":
        choices = ("none", "timeout_before", "timeout_after", "delayed_visibility",
                   "partial_commit", "rate_limit", "schema_drift", "permission_denied")
        for i in range(n):
            assign(i, rng.choice(choices))
    elif composition == "partial_then_timeout_val":
        assign(0, "partial_commit")
        assign(1, "timeout_after")
    elif composition == "partial_comp_failure":
        idx = next((i for i, name in enumerate(steps) if TOOLS[name]["compensatable"]), 0)
        assign(idx, "partial_commit", compensation_available=False)
        if n > 1:
            assign((idx + 1) % n, "timeout_after")
    elif composition == "delay_rate_permission":
        assign(0, "delayed_visibility")
        if n > 1:
            assign(1, "rate_limit")
        if n > 2:
            assign(2, "permission_denied")
    elif composition == "triple_mixed":
        choices = ("none", "timeout_before", "timeout_after", "delayed_visibility",
                   "partial_commit", "rate_limit", "schema_drift", "permission_denied")
        for i in range(n):
            assign(i, rng.choice(choices))
    else:
        raise ValueError("unknown composition: " + composition)
    return faults


def build_scenarios():
    scenarios = []

    def add(split, task_names, compositions, repeats):
        for task_name in task_names:
            for composition in compositions:
                task_index = ALL_TASKS.index(task_name)
                composition_index = ALL_COMPOSITIONS.index(composition)
                for rep in range(repeats):
                    seed = 20261105 + task_index * 100000 + composition_index * 1000 + rep
                    scenario_id = "{}|{}|{}".format(task_name, composition, rep)
                    scenarios.append({
                        "scenario_id": scenario_id,
                        "split": split,
                        "task": task_name,
                        "composition": composition,
                        "seed": seed,
                        "tools": TASKS[task_name],
                        "faults": make_fault_vector(task_name, composition, seed),
                    })

    add("train", TRAIN_TASKS, TRAIN_COMPOSITIONS, 12)
    add("validation_task_shift", VALIDATION_TASKS, TRAIN_COMPOSITIONS, 12)
    add("validation_fault_shift", TRAIN_TASKS, VALIDATION_COMPOSITIONS, 12)
    add("heldout_task_shift", HELDOUT_TASKS, TRAIN_COMPOSITIONS, 30)
    add("heldout_fault_shift", TRAIN_TASKS, HELDOUT_COMPOSITIONS, 30)
    add("heldout_joint_shift", HELDOUT_TASKS, HELDOUT_COMPOSITIONS, 30)
    return scenarios


class ToolRuntime:
    def __init__(self, name, fault_spec):
        self.name = name
        self.contract = dict(TOOLS[name])
        self.fault = fault_spec["fault"]
        self.delay = fault_spec["delay"]
        self.retry_after = fault_spec["retry_after"]
        self.compensation_available = fault_spec["compensation_available"]
        self.tick = 0
        self.state = "NOT_COMMITTED"
        self.visible_at = 0
        self.active_effects = 0
        self.attempts = 0
        self.schema_repaired = False
        self.action_count = 0
        self.duplicate_count = 0
        self.violation_count = 0
        self.compensation_failures = 0
        self.compensation_attempted = False
        self.last_compensation_result = None

    def _commit(self, partial=False):
        self.state = "PARTIAL" if partial else "COMMITTED"
        self.active_effects += 1
        self.visible_at = self.tick + self.delay

    def execute(self):
        self.action_count += 1
        if self.fault == "permission_denied":
            return "PERMISSION"
        if self.fault == "schema_drift" and not self.schema_repaired:
            return "SCHEMA"
        if self.fault == "rate_limit" and self.tick < self.retry_after:
            return "RATE_LIMIT"

        if self.attempts == 0:
            self.attempts += 1
            if self.fault == "timeout_before":
                return "TIMEOUT"
            if self.fault in ("timeout_after", "delayed_visibility"):
                self._commit()
                return "TIMEOUT"
            if self.fault == "partial_commit":
                self._commit(partial=True)
                return "PARTIAL"

        if self.state in ("COMMITTED", "PARTIAL"):
            if self.contract["idempotent"]:
                return "IDEMPOTENT_REPLAY" if self.state == "COMMITTED" else "PARTIAL_REPLAY"
            self.active_effects += 1
            self.duplicate_count += 1
            self.violation_count += 1
            return "DUPLICATE"

        self.attempts += 1
        self._commit()
        return "COMMITTED"

    def retry(self):
        return self.execute()

    def verify(self):
        self.action_count += 1
        if self.state == "PARTIAL":
            return "PARTIAL"
        if self.state == "COMMITTED" and self.tick >= self.visible_at:
            return "COMMITTED"
        return "NOT_COMMITTED"

    def wait(self):
        self.action_count += 1
        self.tick += 1
        return "WAITED"

    def repair_schema(self):
        self.action_count += 1
        self.schema_repaired = True
        return "REPAIRED"

    def compensate(self):
        if self.active_effects == 0:
            self.last_compensation_result = "NO_EFFECT"
            return self.last_compensation_result
        if not self.contract["compensatable"]:
            self.action_count += 1
            self.last_compensation_result = "CONTRACT_BLOCKED"
            return self.last_compensation_result
        if self.compensation_attempted:
            return self.last_compensation_result
        self.action_count += 1
        self.compensation_attempted = True
        if not self.compensation_available:
            self.compensation_failures += 1
            self.last_compensation_result = "FAILED"
            return self.last_compensation_result
        self.active_effects = 0
        self.state = "COMPENSATED"
        self.last_compensation_result = "COMPENSATED"
        return self.last_compensation_result


class PublicToolView:
    """Restricted policy interface; latent simulator fields stay in ToolRuntime."""
    __slots__ = ("__runtime", "contract", "retry_after")

    def __init__(self, runtime):
        self.__runtime = runtime
        self.contract = dict(runtime.contract)
        self.retry_after = runtime.retry_after

    def retry(self):
        return self.__runtime.retry()

    def verify(self):
        return self.__runtime.verify()

    def wait(self):
        return self.__runtime.wait()

    def repair_schema(self):
        return self.__runtime.repair_schema()

    def compensate(self):
        return self.__runtime.compensate()


def accepted(result):
    return result in ("COMMITTED", "IDEMPOTENT_REPLAY")


def compensate_then_retry(tool):
    if not tool.contract["compensatable"]:
        return False
    if tool.compensate() != "COMPENSATED":
        return False
    return accepted(tool.retry())


def recover_tool(policy, tool, initial_error):
    """Implementable policies receive only the public error and public contract."""
    if policy == "blind_retry":
        return accepted(tool.retry())

    if policy == "verify_then_retry":
        state = tool.verify()
        if state == "COMMITTED":
            return True
        if state == "PARTIAL":
            return compensate_then_retry(tool)
        return accepted(tool.retry())

    if policy == "fixed_wait_verify":
        for _ in range(2):
            tool.wait()
        state = tool.verify()
        if state == "COMMITTED":
            return True
        if state == "PARTIAL":
            return compensate_then_retry(tool)
        return accepted(tool.retry())

    if policy == "conservative_escalation":
        if initial_error in ("TIMEOUT", "PARTIAL", "PERMISSION"):
            return False
        if initial_error == "RATE_LIMIT":
            # The public view has no runtime clock; the policy counts its own waits.
            for _ in range(tool.retry_after):
                tool.wait()
            return accepted(tool.retry())
        if initial_error == "SCHEMA":
            tool.repair_schema()
            return accepted(tool.retry())
        return False

    if policy in ("contract_aware", "saga_aware"):
        if initial_error == "PERMISSION":
            return False
        if initial_error == "SCHEMA":
            tool.repair_schema()
            return accepted(tool.retry())
        if initial_error == "RATE_LIMIT":
            # The public view has no runtime clock; the policy counts its own waits.
            for _ in range(tool.retry_after):
                tool.wait()
            return accepted(tool.retry())
        if initial_error == "PARTIAL":
            return compensate_then_retry(tool)
        if initial_error == "TIMEOUT":
            for _ in range(tool.contract["visibility_bound"]):
                tool.wait()
                if tool.verify() == "COMMITTED":
                    return True
            state = tool.verify()
            if state == "PARTIAL":
                return compensate_then_retry(tool)
            # The public visibility SLA has elapsed; a non-commit can now be retried.
            return accepted(tool.retry())
        return False

    raise ValueError("unknown implementable policy: " + policy)


def oracle_recover(tool, initial_error):
    """Privileged diagnostic: sees latent current-step state and exact visibility time."""
    if initial_error == "TIMEOUT":
        if tool.state == "COMMITTED":
            while tool.tick < tool.visible_at:
                tool.wait()
            return tool.verify() == "COMMITTED"
        return accepted(tool.retry())
    if initial_error == "PARTIAL":
        return compensate_then_retry(tool)
    if initial_error == "RATE_LIMIT":
        for _ in range(max(0, tool.retry_after - tool.tick)):
            tool.wait()
        return accepted(tool.retry())
    if initial_error == "SCHEMA":
        tool.repair_schema()
        return accepted(tool.retry())
    if initial_error == "PERMISSION":
        return False
    return False


def rollback(tools, rollback_order):
    for tool in reversed(tools):
        if tool.active_effects <= 0:
            continue
        if not tool.contract["compensatable"]:
            rollback_order.append(tool.name + ":BLOCKED")
            continue
        result = tool.compensate()
        rollback_order.append(tool.name if result == "COMPENSATED" else tool.name + ":FAILED")


def run_episode(policy, scenario):
    tools = [ToolRuntime(name, spec) for name, spec in zip(scenario["tools"], scenario["faults"])]
    failed = False
    escalated = False
    rollback_order = []
    downstream_violation = 0

    for index, tool in enumerate(tools):
        if index and any(previous.state != "COMMITTED" for previous in tools[:index]):
            downstream_violation += 1
            failed = True
            escalated = True
            break

        first_result = tool.execute()
        if accepted(first_result):
            continue

        if policy == "oracle_diagnostic":
            recovered = oracle_recover(tool, first_result)
        else:
            recovered = recover_tool(policy, PublicToolView(tool), first_result)

        if recovered and tool.state == "COMMITTED":
            continue

        failed = True
        escalated = True
        if policy in ("saga_aware", "oracle_diagnostic"):
            rollback(tools[:index + 1], rollback_order)
        break

    violation_count = downstream_violation + sum(t.violation_count for t in tools)
    task_success = int(
        not failed
        and all(t.state == "COMMITTED" for t in tools)
        and violation_count == 0
    )
    active_effects = sum(t.active_effects for t in tools)
    safe_resolution = int(task_success or active_effects == 0)
    duplicate = int(any(t.duplicate_count > 0 for t in tools))
    compensation_failures = sum(t.compensation_failures for t in tools)
    actions = sum(t.action_count for t in tools) + int(escalated)

    return {
        "scenario_id": scenario["scenario_id"],
        "split": scenario["split"],
        "task_family": scenario["task"],
        "fault_composition": scenario["composition"],
        "seed": scenario["seed"],
        "policy": policy,
        "task_success": task_success,
        "safe_resolution": safe_resolution,
        "safe": int(violation_count == 0),
        "invariant_violation": int(violation_count > 0),
        "duplicate_side_effect": duplicate,
        "unresolved": int(not task_success and active_effects > 0),
        "escalated": int(escalated),
        "compensation_failure": int(compensation_failures > 0),
        "compensation_failures": compensation_failures,
        "active_effects": active_effects,
        "steps_committed": sum(t.state == "COMMITTED" for t in tools),
        "steps_attempted": sum(t.action_count > 0 for t in tools),
        "action_count": actions,
        "rollback_order": ">".join(rollback_order),
        "tool_action_counts": "|".join(str(t.action_count) for t in tools),
        "tool_vector": "|".join(scenario["tools"]),
        "fault_vector": "|".join(
            "{}:comp={}".format(f["fault"], int(f["compensation_available"]))
            for f in scenario["faults"]
        ),
    }


def metric_summary(rows):
    if not rows:
        return {"episodes": 0}
    n = len(rows)
    return {
        "episodes": n,
        "task_success": round(sum(r["task_success"] for r in rows) / n, 4),
        "safe_resolution": round(sum(r["safe_resolution"] for r in rows) / n, 4),
        "safe": round(sum(r["safe"] for r in rows) / n, 4),
        "invariant_violation": round(sum(r["invariant_violation"] for r in rows) / n, 4),
        "duplicate_side_effect": round(sum(r["duplicate_side_effect"] for r in rows) / n, 4),
        "unresolved": round(sum(r["unresolved"] for r in rows) / n, 4),
        "escalated": round(sum(r["escalated"] for r in rows) / n, 4),
        "compensation_failure": round(sum(r["compensation_failure"] for r in rows) / n, 4),
        "mean_action_count": round(sum(r["action_count"] for r in rows) / n, 4),
        "mean_active_effects": round(sum(r["active_effects"] for r in rows) / n, 4),
        "mean_steps_committed": round(sum(r["steps_committed"] for r in rows) / n, 4),
    }


def paired_cluster_bootstrap(rows, policy_a, policy_b, metric="task_success", reps=2000):
    """Cluster bootstrap over task-family × fault-composition groups."""
    by_scenario = defaultdict(dict)
    scenario_meta = {}
    for row in rows:
        by_scenario[row["scenario_id"]][row["policy"]] = row[metric]
        scenario_meta[row["scenario_id"]] = (row["task_family"], row["fault_composition"])
    clusters = defaultdict(list)
    for scenario_id, values in by_scenario.items():
        if policy_a in values and policy_b in values:
            diff = values[policy_a] - values[policy_b]
            clusters[scenario_meta[scenario_id]].append(diff)
    keys = sorted(clusters)
    if not keys:
        return {"mean_difference": None, "ci95": [None, None], "clusters": 0}
    all_values = [v for key in keys for v in clusters[key]]
    mean_difference = sum(all_values) / len(all_values)
    rng = random.Random(20261105)
    estimates = []
    for _ in range(reps):
        sampled_keys = [rng.choice(keys) for _ in keys]
        sample = [v for key in sampled_keys for v in clusters[key]]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return {
        "mean_difference": round(mean_difference, 6),
        "ci95": [round(low, 6), round(high, 6)],
        "clusters": len(keys),
        "bootstrap_reps": reps,
    }



def decide_gate(summaries, oracle_gap):
    saga_metrics = summaries["saga_aware"]["heldout_all"]
    oracle_metrics = summaries["oracle_diagnostic"]["heldout_all"]
    heldout_slices = [
        value for key, value in summaries["saga_aware"].items()
        if key.startswith("heldout_") and key != "heldout_all"
    ]
    zero_violation_all_slices = bool(heldout_slices) and all(
        value["invariant_violation"] == 0 for value in heldout_slices
    )
    success_gap = oracle_metrics["task_success"] - saga_metrics["task_success"]
    action_gap = (
        (saga_metrics["mean_action_count"] - oracle_metrics["mean_action_count"])
        / max(oracle_metrics["mean_action_count"], 1e-9)
    )
    ci_low = oracle_gap["ci95"][0] if oracle_gap.get("ci95") else None

    if not zero_violation_all_slices:
        gate = "HOLD_SAFETY_FAILURE"
    elif success_gap >= 0.05 and ci_low is not None and ci_low > 0:
        gate = "CONDITIONAL_GO_PILOT_B"
    elif success_gap <= 0.02 and action_gap <= 0.10:
        gate = "NO_GO_INSUFFICIENT_OPTIMIZATION_HEADROOM"
    else:
        gate = "HOLD_REVIEW_FAILURE_BOUNDARIES"

    return gate, success_gap, action_gap, zero_violation_all_slices


def run_experiment():
    scenarios = build_scenarios()
    rows = [run_episode(policy, scenario) for scenario in scenarios for policy in POLICIES]

    by_policy_split = defaultdict(list)
    by_policy = defaultdict(list)
    for row in rows:
        by_policy_split[(row["policy"], row["split"])].append(row)
        by_policy[row["policy"]].append(row)

    summaries = {}
    for policy in POLICIES:
        summaries[policy] = {
            split: metric_summary(group)
            for (p, split), group in by_policy_split.items() if p == policy
        }
        heldout = [r for r in by_policy[policy] if r["split"].startswith("heldout_")]
        summaries[policy]["heldout_all"] = metric_summary(heldout)

    heldout_rows = [r for r in rows if r["split"].startswith("heldout_")]
    oracle_gap = paired_cluster_bootstrap(
        heldout_rows, "oracle_diagnostic", "saga_aware", "task_success"
    )
    gate, success_gap, action_gap, zero_violation_all_slices = decide_gate(
        summaries, oracle_gap
    )

    worst_groups = {}
    group_rows = defaultdict(list)
    for row in heldout_rows:
        group_rows[(row["policy"], row["task_family"], row["fault_composition"])].append(row)
    for (policy, task, composition), group in sorted(group_rows.items()):
        worst_groups["{}|{}|{}".format(policy, task, composition)] = metric_summary(group)

    payload = {
        "status": "EXPLORATORY_PILOT_A3",
        "design": {
            "tasks": len(TASKS),
            "tool_steps_per_task": 3,
            "fault_compositions": len(ALL_COMPOSITIONS),
            "policies": len(POLICIES),
            "episodes_per_policy": len(scenarios),
            "total_policy_episodes": len(rows),
            "train_episodes_per_policy": sum(s["split"] == "train" for s in scenarios),
            "validation_episodes_per_policy": sum(s["split"].startswith("validation") for s in scenarios),
            "heldout_episodes_per_policy": sum(s["split"].startswith("heldout_") for s in scenarios),
            "same_scenario_ids_across_policies": True,
            "per_tool_fault_vector": True,
            "policy_access": "public errors, tool contracts, VERIFY/WAIT results only",
            "oracle_access": "privileged current-step latent state; diagnostic only",
            "task_splits": {
                "train": list(TRAIN_TASKS),
                "validation": list(VALIDATION_TASKS),
                "heldout": list(HELDOUT_TASKS),
            },
            "composition_splits": {
                "train": list(TRAIN_COMPOSITIONS),
                "validation": list(VALIDATION_COMPOSITIONS),
                "heldout": list(HELDOUT_COMPOSITIONS),
            },
        },
        "summary": summaries,
        "heldout_worst_groups": worst_groups,
        "paired_bootstrap_oracle_minus_saga_success": oracle_gap,
        "gate": {
            "decision": gate,
            "oracle_minus_saga_success": round(success_gap, 6),
            "saga_minus_oracle_action_cost_relative": round(action_gap, 6),
            "saga_zero_violation_all_heldout_slices": zero_violation_all_slices,
            "rule": (
                "Pilot B GO requires zero saga_aware held-out invariant violations, "
                "oracle-success gap >= 0.05, and cluster-bootstrap CI lower bound > 0. "
                "Action-cost-only gaps do not pass."
            ),
        },
        "limitations": [
            "Deterministic simulator, not a real tool environment or LLM Agent evaluation.",
            "Oracle diagnostic has privileged current-step latent state and is not deployable.",
            "A3 is a policy-headroom gate only; no random search, GA/GP or EA has been run.",
            "No statistical claim of algorithmic improvement is made.",
        ],
    }

    root = Path(__file__).parent
    (root / "pilot_a3_results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fields = list(rows[0].keys()) if rows else []
    with (root / "pilot_a3_episodes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    run_experiment()
