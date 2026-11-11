"""Typed semantic contracts for the formal synthetic-saga task families.

The task unit is deliberately an ABSTRACT three-step side-effecting workflow:
each tool consumes a typed workflow context and, after step zero, the prior
step's committed EffectReceipt. This validates ordered saga semantics and
contract compatibility; it does NOT claim that arbitrary sequences are
real-world business processes.
"""
from __future__ import annotations

import itertools
import sys
from collections import Counter
from pathlib import Path

PILOT_DIR = Path(__file__).resolve().parents[1] / "pilot_a_recovery"
if str(PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(PILOT_DIR))

from pilot_a3 import TASKS as LEGACY_TASKS, TOOLS  # noqa: E402

SEMANTIC_CONTRACT_VERSION = "synthetic-saga-contract-v1"
WORKFLOW_TEMPLATE = "ordered-three-step-side-effect-saga"
STEP_COUNT = 3

TOOL_OPERATIONS = {
    "inventory": "execute_inventory_side_effect",
    "calendar": "execute_calendar_side_effect",
    "order": "execute_order_side_effect",
    "payment": "execute_payment_side_effect",
    "ledger": "execute_ledger_side_effect",
    "customer": "execute_customer_side_effect",
    "shipment": "execute_shipment_side_effect",
    "refund": "execute_refund_side_effect",
    "subscription": "execute_subscription_side_effect",
    "notification": "execute_notification_side_effect",
}


def family_id_for(tools):
    return "tf_" + "__".join(tools)


def profile_key(tools):
    return tuple(
        (bool(TOOLS[t]["idempotent"]), bool(TOOLS[t]["compensatable"]))
        for t in tools
    )


def profile_id(tools):
    return "|".join(
        ("I" if TOOLS[t]["idempotent"] else "N")
        + ("C" if TOOLS[t]["compensatable"] else "U")
        for t in tools
    )


def build_task_family(tools, family_id=None, legacy=False):
    tools = tuple(tools)
    if len(tools) != STEP_COUNT:
        raise ValueError("a task family must contain exactly three tools")
    unknown = [t for t in tools if t not in TOOLS]
    if unknown:
        raise ValueError("unknown tools: " + ", ".join(unknown))

    fid = family_id or family_id_for(tools)
    payload_types = [t.title() + "Payload" for t in tools]
    steps = []
    for idx, tool in enumerate(tools):
        inputs = {
            "workflow_context": {"type": "WorkflowContext", "source": "initial_context"},
            "tool_payload": {"type": payload_types[idx], "source": "initial_context"},
        }
        preconditions = ["workflow_open", "tool_payload_valid"]
        if idx == 0:
            predecessor = None
        else:
            predecessor = {
                "type": "EffectReceipt",
                "producer": tools[idx - 1],
                "step_index": idx - 1,
                "commit_status": "COMMITTED",
            }
            inputs["previous_receipt"] = predecessor
            preconditions.extend([
                "previous_step_committed",
                "previous_receipt_matches_workflow",
            ])
        steps.append({
            "step_index": idx,
            "tool": tool,
            "operation": TOOL_OPERATIONS[tool],
            "inputs": inputs,
            "required_predecessor": predecessor,
            "preconditions": preconditions,
            "outputs": {
                "type": "EffectReceipt",
                "producer": tool,
                "step_index": idx,
                "commit_status": "COMMITTED",
            },
            "postconditions": ["side_effect_recorded", "receipt_emitted"],
            "tool_contract": {
                "idempotent": bool(TOOLS[tool]["idempotent"]),
                "compensatable": bool(TOOLS[tool]["compensatable"]),
                "visibility_bound": int(TOOLS[tool]["visibility_bound"]),
            },
        })

    return {
        "schema_version": SEMANTIC_CONTRACT_VERSION,
        "family_id": fid,
        "template": WORKFLOW_TEMPLATE,
        "semantic_scope": "abstract_synthetic_saga_not_domain_business_semantics",
        "legacy_task_family": bool(legacy),
        "tools": list(tools),
        "initial_context": {
            "workflow_id": "workflow::" + fid,
            "workflow_open": True,
            "payload_types": payload_types,
        },
        "steps": steps,
        "goal": {
            "predicate": "all_steps_committed_in_order",
            "required_step_count": STEP_COUNT,
            "terminal_receipt": {
                "type": "EffectReceipt",
                "producer": tools[-1],
                "step_index": STEP_COUNT - 1,
                "commit_status": "COMMITTED",
            },
        },
        "compensation_order": "reverse_commit_order",
    }


def validate_task_family(spec, require_primary_support=False):
    """Independent structural/semantic validator; returns all findings."""
    errors = []
    if not isinstance(spec, dict):
        return {"ok": False, "errors": ["task family must be a mapping"]}

    if spec.get("schema_version") != SEMANTIC_CONTRACT_VERSION:
        errors.append("unsupported semantic schema version")
    if spec.get("template") != WORKFLOW_TEMPLATE:
        errors.append("unsupported workflow template")

    tools = tuple(spec.get("tools", ()))
    if len(tools) != STEP_COUNT:
        errors.append("exactly three ordered tool steps are required")
    if len(set(tools)) != len(tools):
        errors.append("a tool may occur at most once in a family")
    unknown = [t for t in tools if t not in TOOLS]
    if unknown:
        errors.append("unknown tools: " + ", ".join(unknown))

    expected_id = family_id_for(tools) if len(tools) == STEP_COUNT and not unknown else None
    family_id = spec.get("family_id")
    if expected_id and family_id != expected_id:
        legacy_match = (
            family_id in LEGACY_TASKS
            and tuple(LEGACY_TASKS[family_id]) == tools
            and bool(spec.get("legacy_task_family"))
        )
        if not legacy_match:
            errors.append("family_id does not match the ordered tool sequence")

    context = spec.get("initial_context", {})
    if not context.get("workflow_id") or context.get("workflow_open") is not True:
        errors.append("initial context must provide an open workflow_id")
    expected_payloads = [t.title() + "Payload" for t in tools if t in TOOLS]
    if context.get("payload_types") != expected_payloads:
        errors.append("initial context payload types do not match the ordered tools")

    steps = spec.get("steps", [])
    if len(steps) != STEP_COUNT:
        errors.append("exactly three step contracts are required")
    for idx, step in enumerate(steps[:STEP_COUNT]):
        if idx >= len(tools):
            break
        tool = tools[idx]
        if step.get("step_index") != idx:
            errors.append(f"step {idx}: non-contiguous step index")
        if step.get("tool") != tool:
            errors.append(f"step {idx}: tool order mismatch")
        if step.get("operation") != TOOL_OPERATIONS.get(tool):
            errors.append(f"step {idx}: operation does not match tool")
        expected_contract = {
            "idempotent": bool(TOOLS[tool]["idempotent"]),
            "compensatable": bool(TOOLS[tool]["compensatable"]),
            "visibility_bound": int(TOOLS[tool]["visibility_bound"]),
        }
        if step.get("tool_contract") != expected_contract:
            errors.append(f"step {idx}: tool contract mismatch")

        inputs = step.get("inputs", {})
        if inputs.get("workflow_context", {}).get("type") != "WorkflowContext":
            errors.append(f"step {idx}: missing typed WorkflowContext")
        if inputs.get("tool_payload", {}).get("type") != tool.title() + "Payload":
            errors.append(f"step {idx}: missing matching typed tool payload")

        pre = set(step.get("preconditions", []))
        post = set(step.get("postconditions", []))
        if not {"workflow_open", "tool_payload_valid"}.issubset(pre):
            errors.append(f"step {idx}: missing common preconditions")
        if not {"side_effect_recorded", "receipt_emitted"}.issubset(post):
            errors.append(f"step {idx}: missing postconditions")

        output = step.get("outputs", {})
        expected_output = {
            "type": "EffectReceipt",
            "producer": tool,
            "step_index": idx,
            "commit_status": "COMMITTED",
        }
        if output != expected_output:
            errors.append(f"step {idx}: invalid EffectReceipt output")

        if idx == 0:
            if step.get("required_predecessor") is not None or "previous_receipt" in inputs:
                errors.append("step 0 must consume the initial request, not a predecessor")
        else:
            expected_predecessor = {
                "type": "EffectReceipt",
                "producer": tools[idx - 1],
                "step_index": idx - 1,
                "commit_status": "COMMITTED",
            }
            if step.get("required_predecessor") != expected_predecessor:
                errors.append(f"step {idx}: predecessor contract mismatch")
            if inputs.get("previous_receipt") != expected_predecessor:
                errors.append(f"step {idx}: previous receipt input mismatch")
            if not {
                "previous_step_committed",
                "previous_receipt_matches_workflow",
            }.issubset(pre):
                errors.append(f"step {idx}: missing predecessor preconditions")

    if len(tools) == STEP_COUNT and all(t in TOOLS for t in tools):
        expected_goal = {
            "predicate": "all_steps_committed_in_order",
            "required_step_count": STEP_COUNT,
            "terminal_receipt": {
                "type": "EffectReceipt",
                "producer": tools[-1],
                "step_index": STEP_COUNT - 1,
                "commit_status": "COMMITTED",
            },
        }
        if spec.get("goal") != expected_goal:
            errors.append("task goal does not match the terminal receipt")
    if spec.get("compensation_order") != "reverse_commit_order":
        errors.append("compensation must follow reverse commit order")

    if require_primary_support and len(tools) == STEP_COUNT and all(t in TOOLS for t in tools):
        if not TOOLS[tools[0]]["compensatable"]:
            errors.append("primary-compatible families require a compensatable first step")
        if not any(not TOOLS[t]["compensatable"] for t in tools):
            errors.append("primary-compatible families require at least one uncompensatable step")

    return {"ok": not errors, "errors": errors}


def enumerate_primary_compatible_sequences():
    """Contract-compatible expansion pool used by the frozen formal split."""
    out = []
    names = list(TOOLS)
    for seq in itertools.permutations(names, STEP_COUNT):
        spec = build_task_family(seq)
        if validate_task_family(spec, require_primary_support=True)["ok"]:
            out.append(tuple(seq))
    return out


def _greedy_select(pool, count, selected_global, selected_in_split):
    pool = list(pool)
    chosen = []
    while len(chosen) < count:
        if not pool:
            raise ValueError("candidate pool exhausted during split selection")

        def score(seq):
            prof_count = sum(
                1 for other in selected_in_split + chosen
                if profile_key(other) == profile_key(seq)
            )
            overlaps = [
                len(set(seq) & set(other))
                for other in selected_global + chosen
            ]
            max_overlap = max(overlaps, default=0)
            total_overlap = sum(overlaps)
            usage = Counter(
                tool for family in selected_global + chosen for tool in family
            )
            imbalance = sum(
                (usage[t] + (1 if t in seq else 0)) ** 2 for t in TOOLS
            )
            return (prof_count, max_overlap, total_overlap, imbalance, seq)

        best = min(pool, key=score)
        chosen.append(best)
        pool.remove(best)
    return chosen, pool


def build_split_catalog():
    """Return the deterministic 8/4/40 family split (test families stay undisclosed)."""
    legacy_sequences = [tuple(v) for v in LEGACY_TASKS.values()]
    legacy_specs = [
        build_task_family(seq, family_id=name, legacy=True)
        for name, seq in LEGACY_TASKS.items()
    ]
    candidate_pool = [
        seq for seq in enumerate_primary_compatible_sequences()
        if seq not in legacy_sequences
    ]

    train_add, candidate_pool = _greedy_select(
        candidate_pool, 2, legacy_sequences, legacy_sequences
    )
    selected_global = legacy_sequences + train_add
    validation, candidate_pool = _greedy_select(
        candidate_pool, 4, selected_global, []
    )
    selected_global += validation
    test, candidate_pool = _greedy_select(
        candidate_pool, 40, selected_global, []
    )

    train_specs = legacy_specs + [build_task_family(seq) for seq in train_add]
    validation_specs = [build_task_family(seq) for seq in validation]
    test_specs = [build_task_family(seq) for seq in test]
    return {
        "train": train_specs,
        "validation": validation_specs,
        "test": test_specs,
        "candidate_pool_size": len(enumerate_primary_compatible_sequences()),
    }


def audit_split_catalog(catalog):
    problems = []
    expected = {"train": 8, "validation": 4, "test": 40}
    ids = {}
    sequences = {}
    for split, n_expected in expected.items():
        families = catalog.get(split, [])
        if len(families) != n_expected:
            problems.append(f"{split}: expected {n_expected} families, got {len(families)}")
        ids[split] = {f["family_id"] for f in families}
        sequences[split] = {tuple(f["tools"]) for f in families}
        for family in families:
            result = validate_task_family(
                family,
                require_primary_support=(not family.get("legacy_task_family")),
            )
            if not result["ok"]:
                problems.extend(f"{split}/{family.get('family_id')}: {e}" for e in result["errors"])

    if ids["train"] & ids["validation"] or ids["train"] & ids["test"] or ids["validation"] & ids["test"]:
        problems.append("task-family IDs overlap across splits")
    if (sequences["train"] & sequences["validation"]
            or sequences["train"] & sequences["test"]
            or sequences["validation"] & sequences["test"]):
        problems.append("ordered tool sequences overlap across splits")

    test_profiles = Counter(profile_id(f["tools"]) for f in catalog.get("test", []))
    if len(test_profiles) != 10 or set(test_profiles.values()) != {4}:
        problems.append("test profile coverage must be 10 profiles x 4 families each")

    return {
        "ok": not problems,
        "problems": problems,
        "candidate_pool_size": catalog.get("candidate_pool_size", 0),
        "profile_counts_test": dict(sorted(test_profiles.items())),
    }
