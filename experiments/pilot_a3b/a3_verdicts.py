"""Exhaustive verdict provenance for A-3 scenarios (57 F5).

Two independent paths are cross-checked over the FULL pattern space:
1. `a3_bridge.scenario_verdict` -- analytic prover rules;
2. `reachability.classify` on an explicit EpisodeSpec mirroring A-3 per-step
   semantics: one-shot faults (on_nth_call=1), delayed visibility with SLA,
   idempotent/compensatable contracts, compensation availability as hidden
   theta, and PUBLIC error-code observations.

Every A-3 scenario maps to a (contracts, fault pattern, comp-availability)
key; the cross-check enumerates the pattern space and records per-pattern
class + status. Mismatch rate is reported (not silently ignored).
"""
from __future__ import annotations

import itertools
from collections import Counter

from reachability import (
    CLS_R1, CLS_R2, CLS_R3, CLS_R4, CLS_UNKNOWN,
    AugState, EpisodeSpec, classify,
)
from a3_bridge import scenario_verdict

ACTIONS = ("CALL", "RETRY", "VERIFY", "WAIT", "REPAIR", "COMPENSATE", "ROLLBACK", "ESCALATE", "STOP_SAFE")
VIS_BOUND = 4

# hidden = (states, comps, delays, waitc, spent, last_obs, stopped, done)
# states per step: 0 NONE, 1 COMMITTED_INVISIBLE, 2 COMMITTED_VISIBLE, 3 PARTIAL, 4 COMPENSATED
# spent: fault already fired (one-shot, matches on_nth_call=1)


def make_pattern_spec(name, faults, idempotent, compensatable, comp_available, horizon=12, start_at_first_fault=False):
    n = len(faults)
    if isinstance(comp_available, (list, tuple)) and len(comp_available) != n:
        raise ValueError("comp_available sequence must match the fault vector length")
    comp_opts = []
    for i, f in enumerate(faults):
        if f in ("partial_commit", "timeout_after", "delayed_visibility") and compensatable[i]:
            available = comp_available[i] if isinstance(comp_available, (list, tuple)) else comp_available
            comp_opts.append((True, False) if available is None else (bool(available),))
        else:
            comp_opts.append((True,))
    delay_opts = []
    for f in faults:
        if f in ("timeout_after", "delayed_visibility"):
            delay_opts.append(tuple(range(1, VIS_BOUND + 1)))
        else:
            delay_opts.append((0,))
    variants = []
    first_fault = next((i for i, f in enumerate(faults) if f is not None), None)
    for comps in itertools.product(*comp_opts):
        for delays in itertools.product(*delay_opts):
            states = [0] * n
            waitc = [0] * n
            spent = [0] * n
            last_obs = "START"
            if start_at_first_fault and first_fault is not None:
                # The recovery controller is invoked after the first public fault
                # observation; every earlier step is already committed.
                for j in range(first_fault):
                    states[j] = 2
                fault = faults[first_fault]
                if fault == "timeout_before":
                    spent[first_fault] = 1
                    last_obs = "TIMEOUT"
                elif fault in ("timeout_after", "delayed_visibility"):
                    states[first_fault] = 1
                    spent[first_fault] = 1
                    last_obs = "TIMEOUT"
                elif fault == "partial_commit":
                    states[first_fault] = 3
                    spent[first_fault] = 1
                    last_obs = "PARTIAL"
                elif fault == "schema_drift":
                    spent[first_fault] = 1
                    last_obs = "SCHEMA"
                elif fault == "rate_limit":
                    last_obs = "RATE_LIMIT"
                elif fault == "permission_denied":
                    last_obs = "PERMISSION"
            variants.append((
                tuple(states), comps, delays, tuple(waitc), tuple(spent),
                last_obs, 0, 0
            ))

    def pack(states, comps, delays, waitc, spent, last_obs, stopped, done):
        return (tuple(states), tuple(comps), tuple(delays), tuple(waitc), tuple(spent), last_obs, stopped, done)

    def trans(h, a):
        states, comps, delays, waitc, spent, last_obs, stopped, done = h
        states, waitc, spent = list(states), list(waitc), list(spent)
        if stopped or done:
            return h, "ALREADY", 0
        # current step = first not fully committed
        cur = None
        for i, s in enumerate(states):
            if s != 2:
                cur = i
                break
        if cur is None:
            return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 1), "COMMITTED", 0
        fault = faults[cur] or "none"
        s = states[cur]
        harm = 0

        if a in ("CALL", "RETRY"):
            if s == 2:
                return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 0), "COMMITTED", 0
            if s in (1, 3):
                if idempotent[cur]:
                    if s == 3:
                        return pack(states, comps, delays, waitc, spent, "PARTIAL", 0, 0), "PARTIAL", 0
                    return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 0), "COMMITTED", 0
                return pack(states, comps, delays, waitc, spent, "DUPLICATE", 0, 0), "DUPLICATE", 1
            # fresh attempt at step (s == 0)
            if fault == "permission_denied":
                # persistent denial (pilot_a3 semantics)
                return pack(states, comps, delays, waitc, spent, "PERMISSION", 0, 0), "PERMISSION", 0
            if fault == "schema_drift" and not spent[cur]:
                spent[cur] = 1  # 'unrepaired' marker reused as drift-active
                return pack(states, comps, delays, waitc, spent, "SCHEMA", 0, 0), "SCHEMA", 0
            if fault == "schema_drift" and spent[cur] == 1:
                return pack(states, comps, delays, waitc, spent, "SCHEMA", 0, 0), "SCHEMA", 0
            if fault == "rate_limit" and waitc[cur] < 1:
                return pack(states, comps, delays, waitc, spent, "RATE_LIMIT", 0, 0), "RATE_LIMIT", 0
            if not spent[cur] and fault in ("timeout_before", "timeout_after",
                                            "delayed_visibility", "partial_commit"):
                spent[cur] = 1
                if fault == "timeout_before":
                    return pack(states, comps, delays, waitc, spent, "TIMEOUT", 0, 0), "TIMEOUT", 0
                if fault in ("timeout_after", "delayed_visibility"):
                    states[cur] = 1
                    return pack(states, comps, delays, waitc, spent, "TIMEOUT", 0, 0), "TIMEOUT", 0
                states[cur] = 3
                return pack(states, comps, delays, waitc, spent, "PARTIAL", 0, 0), "PARTIAL", 0
            # clean step or one-shot fault already spent: commit
            states[cur] = 2
            return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 0), "COMMITTED", 0

        if a == "REPAIR":
            if fault == "schema_drift":
                spent[cur] = 2  # repaired
                states[cur] = 2
                return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 0), "COMMITTED", 0
            return pack(states, comps, delays, waitc, spent, "NOOP", 0, 0), "NOOP", 0

        if a == "VERIFY":
            if s == 2 or (s == 1 and waitc[cur] >= delays[cur] and delays[cur] == 0):
                states[cur] = 2
                return pack(states, comps, delays, waitc, spent, "COMMITTED", 0, 0), "COMMITTED", 0
            if s == 1:
                return pack(states, comps, delays, waitc, spent, "NOT_COMMITTED", 0, 0), "NOT_COMMITTED", 0
            if s == 3:
                return pack(states, comps, delays, waitc, spent, "PARTIAL", 0, 0), "PARTIAL", 0
            return pack(states, comps, delays, waitc, spent, "NOT_COMMITTED", 0, 0), "NOT_COMMITTED", 0

        if a == "WAIT":
            # Waiting advances only a live visibility delay or rate-limit window.
            # Counters saturate at the corresponding bound; otherwise WAIT is a
            # state-neutral self-loop so the finite-state solver can prove loss.
            wait_limit = delays[cur]
            if fault == "rate_limit":
                wait_limit = max(wait_limit, 1)
            if wait_limit > 0:
                waitc[cur] = min(waitc[cur] + 1, wait_limit)
            if s == 1 and waitc[cur] >= delays[cur]:
                states[cur] = 2
            return pack(states, comps, delays, waitc, spent, "WAITED", 0, 0), "WAITED", 0

        if a == "COMPENSATE":
            if s in (1, 2, 3):
                if compensatable[cur] and comps[cur]:
                    states[cur] = 4
                    return pack(states, comps, delays, waitc, spent, "COMPENSATED", 0, 0), "COMPENSATED", 0
                return pack(states, comps, delays, waitc, spent, "COMP_FAILED", 0, 0), "COMP_FAILED", 0
            return pack(states, comps, delays, waitc, spent, "COMPENSATED", 0, 0), "COMPENSATED", 0

        if a == "ROLLBACK":
            changed = False
            for i in range(cur - 1, -1, -1):
                if states[i] in (1, 2, 3):
                    if compensatable[i] and comps[i]:
                        states[i] = 4
                        changed = True
            return pack(states, comps, delays, waitc, spent,
                        "COMPENSATED" if changed else "COMP_FAILED", 0, 0), \
                   ("COMPENSATED" if changed else "COMP_FAILED"), 0

        if a in ("ESCALATE", "STOP_SAFE"):
            return pack(states, comps, delays, waitc, spent, "ESCALATED", 1, 0), "ESCALATED", 0
        return pack(states, comps, delays, waitc, spent, "NOOP", 0, 0), "NOOP", 0

    def obs_key(aug: AugState):
        h = aug.hidden
        states, _c, _d, _w, _sp, last_obs, stopped, done = h
        pub = tuple(2 if s == 2 else (3 if s == 3 else 0) for s in states)
        return (last_obs, pub, stopped, done, aug.used_escalate)

    def terminal(aug: AugState):
        h = aug.hidden
        return bool(h[6] or h[7])

    def goal_task(aug: AugState):
        h = aug.hidden
        return all(s == 2 for s in h[0])

    def goal_zero(aug: AugState):
        h = aug.hidden
        residual = sum(1 for s in h[0] if s in (1, 2, 3))
        return bool(h[6]) and residual == 0 and aug.harm == 0

    return EpisodeSpec(
        name=name,
        initial_hidden=variants,
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_key,
        terminal=terminal,
        goal_task=goal_task,
        goal_zero_residual=goal_zero,
        min_reachable_harm=0,
    )


def _sc(faults, compensatable, comp_available):
    tools = []
    fault_specs = []
    for i, f in enumerate(faults):
        if compensatable[i]:
            tools.append("calendar" if i % 2 == 0 else "inventory")
        else:
            tools.append("ledger" if i % 2 == 0 else "shipment")
        fault_specs.append({
            "fault": f or "none",
            "delay": 0,
            "retry_after": 0,
            "compensation_available": bool(comp_available) if compensatable[i] else False,
        })
    return {"tools": tuple(tools), "faults": fault_specs}


def crosscheck_all_patterns():
    from pilot_a3 import TOOLS as A3_TOOLS  # noqa: F401  (contract table reference)
    fault_types = [None, "timeout_before", "timeout_after", "delayed_visibility",
                   "partial_commit", "rate_limit", "schema_drift", "permission_denied"]
    profiles = [
        ("idem_comp", [True, True, True], [True, True, True]),
        ("nonidem_comp", [False, False, False], [True, True, True]),
        ("mixed", [True, False, False], [True, True, False]),
    ]
    rows = []
    for prof_name, idem, comp in profiles:
        for f0, f1 in itertools.product(fault_types, repeat=2):
            faults = [f0, f1, None]
            has_hidden_comp = any(
                f in ("partial_commit", "timeout_after", "delayed_visibility") and comp[i]
                for i, f in enumerate(faults)
            )
            for cf in ([True, False] if has_hidden_comp else [True]):
                sc = _sc(faults, comp, cf)
                analytic = scenario_verdict(sc)["class"]
                spec = make_pattern_spec(f"pat|{prof_name}|{f0}|{f1}|{cf}", faults, idem, comp, cf)
                checked = classify(spec, horizon=12).label
                rows.append({
                    "profile": prof_name,
                    "faults": [str(f) for f in faults],
                    "comp_available": cf,
                    "analytic": analytic,
                    "checker": checked,
                    "match": analytic == checked,
                })
    return rows


if __name__ == "__main__":
    rows = crosscheck_all_patterns()
    mismatch = [r for r in rows if not r["match"]]
    print("patterns checked:", len(rows))
    print("analytic:", dict(Counter(r["analytic"] for r in rows)))
    print("checker :", dict(Counter(r["checker"] for r in rows)))
    print("mismatch:", len(mismatch), f"({len(mismatch)/len(rows):.1%})")
    agree = Counter((r["analytic"], r["checker"]) for r in rows)
    for (a, c), n in sorted(agree.items(), key=lambda kv: -kv[1]):
        print(f"  analytic={a:8s} checker={c:8s} n={n}")


# ---------------------------------------------------------------------------
# Scenario-level robust labels for the D-064-C formal generator
# ---------------------------------------------------------------------------
from functools import lru_cache

from pilot_a3 import TOOLS as TOOL_CONTRACTS


@lru_cache(maxsize=50000)
def _classify_pattern_cached(faults, idempotent, compensatable,
                             comp_available, horizon, max_nodes):
    """Cache labels by public fault pattern and contract profile, never policy output."""
    name = "formal|" + "|".join(str(x or "none") for x in faults)
    name += "|" + "|".join(
        ("1" if i else "0") + ("1" if c else "0")
        for i, c in zip(idempotent, compensatable)
    )
    spec = make_pattern_spec(
        name, faults, idempotent, compensatable, comp_available,
        horizon=horizon, start_at_first_fault=True,
    )
    result = classify(spec, horizon=horizon, max_nodes=max_nodes)
    return result.label, result.evidence


def classify_scenario(scenario, horizon=24, max_nodes=500000):
    """Return robust R1-R4/UNKNOWN label plus an analytic cross-check.

    The recovery decision begins immediately after the first fault has been
    observed; all earlier workflow steps are initialized as committed. This
    prevents trivial pre-execution escalation from turning every hard scenario
    into R3. Compensation availability is fixed by the evaluator-side fault
    plan. For partial_comp_failure, the ground-truth availability is false but
    remains hidden from the policy until it receives COMP_FAILED. This is one
    fixed scenario state, not a mixture of mutually exclusive fault plans. No
    tested policy or outcome is used to generate the label.
    """
    tools = tuple(scenario["tools"])
    fault_specs = scenario["faults"]
    if len(tools) != len(fault_specs):
        raise ValueError("tools/faults length mismatch")

    faults = tuple(
        None if spec["fault"] in (None, "none") else spec["fault"]
        for spec in fault_specs
    )
    idempotent = tuple(bool(TOOL_CONTRACTS[t]["idempotent"]) for t in tools)
    compensatable = tuple(bool(TOOL_CONTRACTS[t]["compensatable"]) for t in tools)
    comp_options = []
    for i, spec in enumerate(fault_specs):
        comp_options.append(bool(spec.get("compensation_available", False)))
    comp_options = tuple(comp_options)

    label, evidence = _classify_pattern_cached(
        faults, idempotent, compensatable, comp_options, int(horizon), int(max_nodes)
    )
    analytic = scenario_verdict(scenario)["class"]
    return {
        "class": label,
        "evidence": evidence,
        "analytic_class": analytic,
        "agreement": label == analytic,
    }
