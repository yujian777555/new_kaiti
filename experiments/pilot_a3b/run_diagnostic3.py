"""D-062 diagnostic round 3: WAIT-SLA contract, B-new, Safety Gate.

Fresh scenario seeds (2026110900 base) -- the D-061 validation set is NOT
reused. DIAGNOSTIC ONLY; formal A-3b remains HOLD.

Arms (8): Hand / NSGA-II / A / A+Fixed-WAIT / A+WAIT-SLA / B-new / A+B-new /
A+B-new+Gate. All evolutionary arms share: identical init pool per seed,
identical train scenarios, identical evaluation budget (safety-battery
rollouts counted), identical stopping.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from a3_bridge import (
    StatefulFSM, evaluate_controller, hand_fsm, run_episode_fsm, scenario_verdict,
)
from ea import run_evolution, safety_battery_pass, validator_illegal_ratio
from pilot_a3 import ALL_COMPOSITIONS, TASKS, make_fault_vector

SEEDS = [111, 222, 333]
SEED_BASE = 2026110900
REPEATS = 3
POP = 48
GENS = 60
TRAIN_TASKS = ("inventory_order_payment", "calendar_order_ledger",
               "customer_order_shipment", "inventory_calendar_order")
VAL_TASKS = ("return_refund_restock", "subscription_ledger_notification")


def build_scenarios():
    train, val = [], []
    idx = 0
    for task in TRAIN_TASKS:
        for comp in ALL_COMPOSITIONS:
            for rep in range(REPEATS):
                seed = SEED_BASE + idx * 13 + rep
                train.append({
                    "scenario_id": f"t3train|{task}|{comp}|{rep}",
                    "split": "train", "task": task, "composition": comp,
                    "seed": seed, "tools": TASKS[task],
                    "faults": make_fault_vector(task, comp, seed),
                })
                idx += 1
    for task in VAL_TASKS:
        for comp in ALL_COMPOSITIONS:
            for rep in range(REPEATS):
                seed = SEED_BASE + 90000 + idx * 13 + rep
                val.append({
                    "scenario_id": f"t3val|{task}|{comp}|{rep}",
                    "split": "validation", "task": task, "composition": comp,
                    "seed": seed, "tools": TASKS[task],
                    "faults": make_fault_vector(task, comp, seed),
                })
                idx += 1
    return train, val


def build_battery():
    """Fixed safety battery: critical ambiguity scenarios from TRAIN families.
    Gate rejects candidates producing duplicates or SLA violations here."""
    specs = [("inventory_order_payment", "single_timeout"),
             ("inventory_order_payment", "timeout_then_rate_limit"),
             ("inventory_order_payment", "partial_then_delay"),
             ("calendar_order_ledger", "single_timeout"),
             ("customer_order_shipment", "timeout_then_rate_limit"),
             ("inventory_calendar_order", "partial_then_delay")]
    bat = []
    for i, (task, comp) in enumerate(specs):
        seed = SEED_BASE + 777777 + i * 17
        bat.append({
            "scenario_id": f"battery|{task}|{comp}|{i}",
            "split": "battery", "task": task, "composition": comp,
            "seed": seed, "tools": TASKS[task],
            "faults": make_fault_vector(task, comp, seed),
        })
    return bat


def sensible_random_fsm(rng):
    import a3_bridge as ab
    fsm = ab.random_fsm(rng)
    skeleton = {
        ab.OBS_START: ab.ACT_RETRY, ab.OBS_TIMEOUT: ab.ACT_WAIT,
        ab.OBS_WAITED: ab.ACT_VERIFY, ab.OBS_NOT_COMMITTED: ab.ACT_RETRY,
        ab.OBS_RATE_LIMIT: ab.ACT_WAIT, ab.OBS_SCHEMA: ab.ACT_REPAIR,
        ab.OBS_PERMISSION: ab.ACT_ESCALATE, ab.OBS_PARTIAL: ab.ACT_COMPENSATE,
    }
    if rng.random() < 0.5:
        for gene in fsm.genes_list():
            if gene.att_bucket == 0 and not gene.stack and gene.error in skeleton:
                gene.action = skeleton[gene.error]
    return fsm


def apply_flags(pool, sla_aware=False, fixed_wait=False):
    for fsm in pool:
        fsm.sla_aware = sla_aware
        fsm.fixed_wait = fixed_wait
    return pool


def pack_rows(scenarios, res, seed, split_tag):
    out = []
    for sc, r in zip(scenarios, res["rows"]):
        out.append({
            "scenario_id": sc["scenario_id"], "split": split_tag,
            "task": sc["task"], "composition": sc["composition"], "seed": seed,
            "label": r["label"], "class_success": r["class_success"],
            "task_success": r["task_success"],
            "invariant_violation": r["invariant_violation"],
            "downstream_violation": r["downstream_violation"],
            "sla_violation": r["sla_violation"],
            "duplicate": r["duplicate"],
            "avoidable_harm": r["avoidable_harm"],
            "policy_selected_escalation": r["policy_selected_escalation"],
            "decision_count": r["decision_count"],
            "active_effects": r["active_effects"],
        })
    return out


def main():
    out_dir = Path(__file__).parent
    train, val = build_scenarios()
    battery = build_battery()
    vtrain = {s["scenario_id"]: scenario_verdict(s) for s in train}
    vval = {s["scenario_id"]: scenario_verdict(s) for s in val}
    vbat = {s["scenario_id"]: scenario_verdict(s) for s in battery}
    label_counts = defaultdict(int)
    for v in vtrain.values():
        label_counts[v["class"]] += 1

    g = hand_fsm()
    t0 = time.time()
    n = 0
    while time.time() - t0 < 1.5:
        run_episode_fsm(g, train[0])
        n += 1
    eps = n / (time.time() - t0)
    budget = POP * (GENS + 1) * len(train) + POP * GENS * len(battery)
    print(f"train={len(train)} val={len(val)} battery={len(battery)} labels={dict(label_counts)}")
    print(f"throughput={eps:.0f} eps/s; budget/method/seed={budget}")

    methods = ["hand", "nsga2", "A", "AwaitFixed", "AwaitSLA", "B", "AB", "ABG"]
    runs = []
    for seed in SEEDS:
        rng = random.Random(seed * 7919 + 29)
        base_pool = [sensible_random_fsm(rng) for _ in range(60)]
        for method in methods:
            t0 = time.time()
            if method == "hand":
                fsm = hand_fsm()
                res_tr = evaluate_controller(fsm, train, vtrain)
                res_va = evaluate_controller(fsm, val, vval)
                episodes = len(train) + len(val)
                illegal = validator_illegal_ratio([fsm])
                hist = []
                gate_pass = None
            else:
                if method == "AwaitFixed":
                    pool = apply_flags([f.clone() for f in base_pool], fixed_wait=True)
                    algo = "A"
                elif method == "AwaitSLA":
                    pool = apply_flags([f.clone() for f in base_pool], sla_aware=True)
                    algo = "A"
                else:
                    pool = [f.clone() for f in base_pool]
                    algo = method
                out = run_evolution(algo, pool, train, vtrain,
                                    pop_size=POP, generations=GENS,
                                    eval_budget=budget * 2, seed=seed,
                                    safety_battery=(battery if method == "ABG" else None),
                                    battery_verdicts=vbat)
                fsm = out["best"]
                res_tr = out["best_result"]
                res_va = evaluate_controller(fsm, val, vval)
                episodes = out["episodes"] + len(val)
                illegal = validator_illegal_ratio(out["final_population"])
                hist = out["history"]
                gate_pass = None
                if method == "ABG":
                    gate_pass = safety_battery_pass(fsm, battery, vbat)
            runs.append({
                "method": method, "seed": seed, "episodes": episodes,
                "wall": round(time.time() - t0, 2),
                "validator_illegal_ratio": illegal,
                "battery_pass": gate_pass,
                "train_metrics": {k: res_tr[k] for k in res_tr if k != "rows"},
                "val_metrics": {k: res_va[k] for k in res_va if k != "rows"},
                "rules": [[k[0], k[1], k[2], gm.action, gm.wait_n]
                          for k, gm in sorted(fsm.genes.items())],
                "fsm_flags": {"sla_aware": fsm.sla_aware, "fixed_wait": fsm.fixed_wait},
                "history": hist,
                "rows": pack_rows(train, res_tr, seed, "train")
                       + pack_rows(val, res_va, seed, "validation"),
            })
            print(f"seed={seed} {method:10s} train={res_tr['cond_rec']:.3f} val={res_va['cond_rec']:.3f} "
                  f"sla_viol={res_tr['sla_viol']:.3f} dup={res_tr['dup']:.3f} "
                  f"behav={res_tr['behavioral_violation']:.3f} illegal={illegal:.2f} eps={episodes}")

    payload = {
        "kind": "DIAGNOSTIC_ROUND3_D062_NOT_CONFIRMATORY",
        "seed_base": SEED_BASE,
        "methods": methods, "seeds": SEEDS,
        "n_train": len(train), "n_val": len(val), "n_battery": len(battery),
        "label_counts_train": dict(label_counts),
        "throughput_eps_per_s": round(eps, 1),
        "pop": POP, "generations": GENS,
        "budget_episodes_per_method_seed": budget,
        "runs": runs,
    }
    payload["manifest_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()
    (out_dir / "diagnostic3_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote diagnostic3_results.json", payload["manifest_sha256"][:16])


if __name__ == "__main__":
    main()
