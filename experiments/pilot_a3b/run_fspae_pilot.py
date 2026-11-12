#!/usr/bin/env python3
"""Run the bounded D-079 Train-only FSPAE mechanism-discovery pilot."""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from a3_bridge import evaluator_verdict_from_scenario, hand_fsm
from d079_challenge_generator import build_challenge_manifest, validate_challenge_manifest, validate_manifest_lock
from fspae_runner import run_fspae_evolution
from sbcg import evaluate_sbcg_candidate, make_shared_initial_pool, select_train_diagnostic_candidate
from sbcg_experiment import reflection_proxy_fsm, rule_based_fsm
from sbcg_runner import run_sbcg_evolution
from split_access import validate_evaluation_scenarios, validate_evolution_scenarios

SEEDS = (411, 522, 633)
POP_SIZE = 8
GENERATIONS = 5
ARCHIVE_CAPACITY = 4
EXPECTED_MANIFEST_SHA256 = "09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca"


def _rows_for_diagnostic(record, scenarios, seed, method):
    if record is None:
        return []
    metadata = {item["scenario_id"]: item for item in scenarios}
    rows = []
    for row in record.metrics["rows"]:
        scenario = metadata[row["scenario_id"]]
        rows.append({
            "method": method, "seed": seed,
            "scenario_id": row["scenario_id"],
            "task": scenario["task_family_id"],
            "composition": scenario["difficulty_stratum"],
            "cluster_id": scenario["cluster_id"],
            "label": row["label"],
            "class_success": row["class_success"],
            "avoidable_harm": row["avoidable_harm"],
            "duplicate": row["duplicate"],
            "sla_violation": row["sla_violation"],
            "invariant_violation": row["invariant_violation"],
            "policy_selected_escalation": row["policy_selected_escalation"],
            "decision_count": row["decision_count"],
        })
    return rows


def _mean(values):
    return sum(float(value) for value in values) / len(values) if values else None


def _summarize_rows(rows):
    if not rows:
        return {
            "status": "NO_FEASIBLE_SELECTED_CANDIDATE", "n": 0,
            "cond_rec_r1_r2": None, "correct_escalation_r3": None,
            "damage_containment_r4": None, "macro_class_success": None,
            "avoidable_harm_mean": None, "duplicate_rate": None,
            "sla_violation_rate": None, "invariant_violation_rate": None,
            "mean_recovery_decisions": None, "worst_cluster_success": None,
            "hard_safety_gate": "HOLD",
        }
    r12 = [row for row in rows if row["label"] in ("R1", "R2")]
    r3 = [row for row in rows if row["label"] == "R3"]
    r4 = [row for row in rows if row["label"] == "R4"]
    cond = _mean([row["class_success"] for row in r12])
    esc = _mean([row["class_success"] for row in r3])
    containment = _mean([row["class_success"] for row in r4])
    class_rates = [value for value in (cond, esc, containment) if value is not None]
    by_cluster = defaultdict(list)
    for row in rows:
        by_cluster[row["cluster_id"]].append(float(row["class_success"]))
    duplicates = sum(int(row["duplicate"]) for row in rows)
    sla = sum(int(row["sla_violation"]) for row in rows)
    invariants = sum(int(row["invariant_violation"]) for row in rows)
    return {
        "status": "EVALUATED", "n": len(rows),
        "cond_rec_r1_r2": cond, "correct_escalation_r3": esc,
        "damage_containment_r4": containment,
        "macro_class_success": _mean(class_rates),
        "avoidable_harm_mean": _mean([row["avoidable_harm"] for row in rows]),
        "duplicate_rate": duplicates / len(rows),
        "sla_violation_rate": sla / len(rows),
        "invariant_violation_rate": invariants / len(rows),
        "mean_recovery_decisions": _mean([row["decision_count"] for row in rows]),
        "worst_cluster_success": min(_mean(values) for values in by_cluster.values()),
        "hard_safety_gate": "PASS" if duplicates + sla + invariants == 0 else "FAIL",
        "hard_violation_counts": {
            "duplicate": duplicates, "sla_violation": sla, "invariant_violation": invariants,
        },
    }


def _paired_cluster_bootstrap(rows_a, rows_b, field, reps=4000, seed=2026111201):
    """Descriptive paired bootstrap over family × fault-stratum clusters."""
    by_a, by_b, metadata = defaultdict(dict), defaultdict(dict), {}
    for row in rows_a:
        value = row.get(field)
        if value is not None:
            by_a[row["scenario_id"]][row["seed"]] = float(value)
            metadata[row["scenario_id"]] = (row["task"], row["composition"])
    for row in rows_b:
        value = row.get(field)
        if value is not None:
            by_b[row["scenario_id"]][row["seed"]] = float(value)
    per_scenario = {}
    for scenario_id, seed_values in by_a.items():
        differences = [
            value - by_b.get(scenario_id, {}).get(algorithm_seed)
            for algorithm_seed, value in seed_values.items()
            if algorithm_seed in by_b.get(scenario_id, {})
        ]
        if differences:
            per_scenario[scenario_id] = sum(differences) / len(differences)
    by_cluster = defaultdict(list)
    for scenario_id, difference in per_scenario.items():
        by_cluster[metadata[scenario_id]].append(difference)
    keys = sorted(by_cluster)
    if not keys:
        return None
    cluster_means = {key: _mean(values) for key, values in by_cluster.items()}
    estimate = _mean(list(cluster_means.values()))
    rng = random.Random(seed)
    samples = []
    for _ in range(reps):
        chosen = [rng.choice(keys) for _ in keys]
        samples.append(_mean([cluster_means[key] for key in chosen]))
    samples.sort()
    return {
        "field": field,
        "mean_cluster_difference": estimate,
        "descriptive_cluster_bootstrap_95_ci": [
            samples[int(0.025 * (len(samples) - 1))],
            samples[int(0.975 * (len(samples) - 1))],
        ],
        "clusters": len(keys),
        "paired_scenarios": len(per_scenario),
        "algorithm_seeds": list(SEEDS),
        "confirmatory_p_value": None,
    }


def _run_evolutionary_arm(method, pool, search, diagnostic, verdicts, seed, budget):
    start = time.perf_counter()
    if method == "matched_nsga3":
        out = run_sbcg_evolution(
            pool, search, verdicts, pop_size=POP_SIZE, generations=GENERATIONS,
            eval_budget=budget, seed=seed, use_five_objectives=True,
            use_stratified_counterexamples=False, use_elite_archive=False,
            remove_hand_from_pool=False, optimizer="nsga3",
        )
    elif method == "sbcg_nsga3":
        out = run_sbcg_evolution(
            pool, search, verdicts, pop_size=POP_SIZE, generations=GENERATIONS,
            eval_budget=budget, seed=seed, use_five_objectives=True,
            use_stratified_counterexamples=True, use_elite_archive=True,
            remove_hand_from_pool=False, optimizer="nsga3",
        )
    elif method in (
        "fspae", "fspae_uniform", "fspae_r2",
        "fspae_r2_global_mut", "fspae_r2_uniform", "fspae_r2_uniform_global_mut",
        "fspae_r2_legacy_scheduler", "fspae_r3_block",
    ):
        settings = {
            "fspae": ("deficit", "local_a_global_b", "global"),
            "fspae_uniform": ("uniform", "local_a_global_b", "global"),
            "fspae_r2": ("performance_deficit", "local_pair", "target_cluster"),
            "fspae_r2_global_mut": ("performance_deficit", "local_pair", "global"),
            "fspae_r2_uniform": ("uniform", "local_pair", "target_cluster"),
            "fspae_r2_uniform_global_mut": ("uniform", "local_pair", "global"),
            "fspae_r2_legacy_scheduler": ("legacy_deficit", "local_pair", "target_cluster"),
            "fspae_r3_block": ("uniform", "global_anchor_local_block", "target_cluster_block"),
        }
        target_mode, parent_mode, variation_mode = settings[method]
        out = run_fspae_evolution(
            pool, search, verdicts, pop_size=POP_SIZE, generations=GENERATIONS,
            eval_budget=budget, seed=seed, archive_capacity=ARCHIVE_CAPACITY,
            target_mode=target_mode, parent_mode=parent_mode,
            variation_mode=variation_mode,
        )
    else:
        raise ValueError("unknown evolutionary arm: " + method)

    candidate_records = out.get("train_candidate_records", [])
    selection = select_train_diagnostic_candidate(candidate_records)
    selected = selection.get("candidate")
    diagnostic_record = (
        evaluate_sbcg_candidate(selected.fsm, diagnostic, verdicts, use_five_objectives=True)
        if selected is not None else None
    )
    diagnostic_rows = _rows_for_diagnostic(diagnostic_record, diagnostic, seed, method)
    return {
        "method": method, "seed": seed,
        "wall_seconds": time.perf_counter() - start,
        "search": {
            "episodes": out["episodes"], "eval_budget": out["eval_budget"],
            "unique_evaluations": out["unique_evaluations"],
            "cache_hits": out["cache_hits"], "evaluation_calls": out["evaluation_calls"],
            "initial_pool_sha256": out["initial_pool_sha256"],
            "history": out["history"],
            "feasible_candidate_count": len(candidate_records),
            "selected_candidate": selected.fingerprint if selected is not None else None,
            "selection_status": selection["status"],
            "archive_stats": out.get("archive_stats", []),
            "target_selection_counts": out.get("target_selection_counts", {}),
            "algorithm_config": out.get("config", {}),
            "mutation_audit": out.get("mutation_audit", []),
        },
        "diagnostic": _summarize_rows(diagnostic_rows),
        "diagnostic_rows": diagnostic_rows,
    }


def run_pilot():
    manifest = build_challenge_manifest()
    challenge_gate = validate_challenge_manifest(manifest)
    if not challenge_gate["ok"]:
        raise RuntimeError("D-079 challenge gate failed: " + "; ".join(challenge_gate["problems"]))
    lock_gate = validate_manifest_lock(manifest)
    if not lock_gate["ok"]:
        raise RuntimeError("committed D-079 v2 lock failed: " + "; ".join(lock_gate["problems"]))
    if manifest["manifest_sha256"] != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("D-079 regenerated manifest SHA differs from frozen v2 SHA")

    scenarios = manifest["scenarios"]
    if len(scenarios) != 288 or any(row.get("split") != "train" for row in scenarios):
        raise RuntimeError("FSPAE pilot requires exactly 288 Train-only scenarios")
    search = [row for row in scenarios if row["evaluation_role"] == "search"]
    diagnostic = [row for row in scenarios if row["evaluation_role"] == "diagnostic"]
    if len(search) != 144 or len(diagnostic) != 144:
        raise RuntimeError("D-079 search/diagnostic role counts changed")
    if {row["scenario_id"] for row in search} & {row["scenario_id"] for row in diagnostic}:
        raise RuntimeError("search and diagnostic scenario IDs overlap")
    validate_evolution_scenarios(search)
    validate_evaluation_scenarios(diagnostic)
    verdicts = {
        row["scenario_id"]: evaluator_verdict_from_scenario(row)
        for row in scenarios
    }
    clusters = {row["cluster_id"] for row in search}
    if len(clusters) != 48 or any(
        sum(row["cluster_id"] == cluster for row in search) != 3
        for cluster in clusters
    ):
        raise RuntimeError("D-079 search role must contain 48 clusters × 3 replicates")

    budget = POP_SIZE * (GENERATIONS + 1) * len(search)
    results = []
    for seed in SEEDS:
        shared_pool = make_shared_initial_pool(seed, size=60, include_hand=False)
        for method in ("matched_nsga3", "sbcg_nsga3", "fspae", "fspae_uniform"):
            results.append(_run_evolutionary_arm(
                method, shared_pool, search, diagnostic, verdicts, seed, budget
            ))

    fixed_baselines = []
    for method, policy in (
        ("hand_fsm", hand_fsm()),
        ("rule_based", rule_based_fsm()),
        ("reflection_proxy", reflection_proxy_fsm()),
    ):
        record = evaluate_sbcg_candidate(policy, diagnostic, verdicts, use_five_objectives=True)
        rows = _rows_for_diagnostic(record, diagnostic, 0, method)
        fixed_baselines.append({
            "method": method, "seed": None,
            "diagnostic": _summarize_rows(rows), "diagnostic_rows": rows,
        })

    rows_by_method = defaultdict(list)
    for result in results:
        rows_by_method[result["method"]].extend(result["diagnostic_rows"])
    for result in fixed_baselines:
        rows_by_method[result["method"]].extend(result["diagnostic_rows"])

    comparisons = {}
    for comparator in ("sbcg_nsga3", "matched_nsga3"):
        comparisons[f"fspae_vs_{comparator}"] = {
            field: _paired_cluster_bootstrap(
                rows_by_method["fspae"], rows_by_method[comparator], field,
                seed=2026111201 + len(comparisons),
            )
            for field in (
                "class_success", "avoidable_harm", "duplicate",
                "sla_violation", "invariant_violation", "decision_count",
            )
        }

    aggregate = {}
    for method, rows in rows_by_method.items():
        if method in ("hand_fsm", "rule_based", "reflection_proxy"):
            aggregate[method] = _summarize_rows(rows)
            continue
        per_seed = []
        for seed in SEEDS:
            seed_rows = [row for row in rows if row["seed"] == seed]
            per_seed.append({"seed": seed, **_summarize_rows(seed_rows)})
        available = [item for item in per_seed if item["n"]]
        aggregate[method] = {
            "per_seed": per_seed,
            "mean_macro_class_success": _mean([item["macro_class_success"] for item in available]),
            "mean_cond_rec_r1_r2": _mean([item["cond_rec_r1_r2"] for item in available]),
            "mean_correct_escalation_r3": _mean([item["correct_escalation_r3"] for item in available]),
            "mean_damage_containment_r4": _mean([item["damage_containment_r4"] for item in available]),
            "mean_avoidable_harm": _mean([item["avoidable_harm_mean"] for item in available]),
            "all_seeds_hard_safety_pass": bool(available) and all(
                item["hard_safety_gate"] == "PASS" for item in available
            ),
        }

    return {
        "schema_version": 1,
        "experiment": "D079_FSPAE_TRAIN_ONLY_EXPLORATORY",
        "status": "EXECUTED_EXPLORATORY_NO_HELDOUT_CLAIM",
        "authorization_scope": (
            "User requested faster experiment progress on 2026-11-11; interpreted narrowly "
            "as approval for the locked D-079 Train-only synthetic diagnostic."
        ),
        "manifest": {
            "generator_version": manifest["generator_version"],
            "manifest_sha256": manifest["manifest_sha256"],
            "scenario_count": manifest["scenario_count"],
            "cluster_count": manifest["cluster_count"],
            "search_scenario_count": len(search),
            "diagnostic_scenario_count": len(diagnostic),
            "label_counts_by_role": manifest["label_counts_by_role"],
            "committed_lock_gate": lock_gate,
        },
        "scope": {
            "search_split": "train", "diagnostic_split": "train",
            "search_role": "search", "diagnostic_role": "diagnostic",
            "validation_scenarios_constructed": False,
            "test_scenarios_constructed": False, "test_outcomes_read": False,
            "llm_inference": False, "api_calls": False,
            "gpu_or_optimizer_service": False, "foundation_model_training": False,
        },
        "protocol": {
            "seeds": list(SEEDS), "population": POP_SIZE, "generations": GENERATIONS,
            "per_arm_seed_search_episode_budget": budget,
            "archive_capacity_per_stratum": ARCHIVE_CAPACITY,
            "arms": ["matched_nsga3", "sbcg_nsga3", "fspae", "fspae_uniform"],
            "fixed_diagnostic_baselines": ["hand_fsm", "rule_based", "reflection_proxy"],
            "candidate_selection": (
                "common Train-search feasible Pareto / family coverage / worst-family "
                "CondRecSucc selector; diagnostic role evaluated once"
            ),
        },
        "results": results, "fixed_baselines": fixed_baselines,
        "aggregate": aggregate, "paired_cluster_bootstrap": comparisons,
        "interpretation": (
            "Exploratory mechanism-discovery evidence only. No confirmatory p-values, "
            "held-out generalization, formal A-3b readiness, or paper-level uplift claim."
        ),
    }


def write_outputs(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "d079_fspae_pilot.json"
    report_path = output_dir / "d079_fspae_pilot.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# D-079 Train-only FSPAE exploratory pilot", "",
        f"- Status: **{result['status']}**",
        f"- Manifest SHA-256: {result['manifest']['manifest_sha256']}",
        "- Scope: Train/search for optimization; disjoint Train/diagnostic for post-search evaluation",
        f"- Seeds: {result['protocol']['seeds']}",
        f"- Population / generations: {result['protocol']['population']} / {result['protocol']['generations']}",
        f"- Search budget per evolutionary arm/seed: {result['protocol']['per_arm_seed_search_episode_budget']}",
        "- Validation/Test payloads: not constructed or accessed",
        "- LLM/API/A800/vLLM/model training: not used", "",
        "## Diagnostic results", "",
        "| Method | Mean macro class success | R1/R2 CondRec | R3 CorrectEscalation | R4 DamageContainment | Avoidable harm | Hard safety |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for method in (
        "matched_nsga3", "sbcg_nsga3", "fspae", "fspae_uniform",
        "hand_fsm", "rule_based", "reflection_proxy",
    ):
        summary = result["aggregate"].get(method, {})
        if "per_seed" in summary:
            values = (
                summary.get("mean_macro_class_success"),
                summary.get("mean_cond_rec_r1_r2"),
                summary.get("mean_correct_escalation_r3"),
                summary.get("mean_damage_containment_r4"),
                summary.get("mean_avoidable_harm"),
                "PASS" if summary.get("all_seeds_hard_safety_pass") else "HOLD/FAIL",
            )
        else:
            values = (
                summary.get("macro_class_success"), summary.get("cond_rec_r1_r2"),
                summary.get("correct_escalation_r3"), summary.get("damage_containment_r4"),
                summary.get("avoidable_harm_mean"), summary.get("hard_safety_gate"),
            )
        def fmt(value):
            if value is None:
                return "NA"
            return f"{float(value):.4f}" if isinstance(value, (int, float)) else str(value)
        lines.append("| " + method + " | " + " | ".join(fmt(value) for value in values) + " |")

    lines.extend(["", "## FSPAE paired descriptive contrasts", ""])
    for comparator, fields in result["paired_cluster_bootstrap"].items():
        lines.extend([
            f"### {comparator}", "",
            "| Endpoint | Mean cluster difference | Descriptive 95% cluster-bootstrap interval | Clusters |",
            "|---|---:|---:|---:|",
        ])
        for field, stats in fields.items():
            if stats is None:
                lines.append(f"| {field} | NA | NA | 0 |")
            else:
                ci = stats["descriptive_cluster_bootstrap_95_ci"]
                lines.append(
                    f"| {field} | {stats['mean_cluster_difference']:.4f} | "
                    f"[{ci[0]:.4f}, {ci[1]:.4f}] | {stats['clusters']} |"
                )
        lines.extend(["", "No confirmatory p-values are reported.", ""])
    lines.extend([
        "## Research interpretation", "",
        "This is a Train-only mechanism-discovery experiment. The diagnostic role consists of independent parameter-seed replicates within the same Train family/stratum domain; it is not external generalization.",
        "The earlier D-079 report with manifest SHA cafdc52e... is not reused because it does not match the currently committed v2 lock (09df6bab...).",
        "",
        "A positive contrast only justifies designing a new locked Validation/Test protocol. A null/negative contrast requires revising or rejecting FSPAE. No result here alone supports a paper-level uplift claim.", "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, report_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_pilot()
    json_path, report_path = write_outputs(result, args.output_dir)
    print(json.dumps({
        "status": result["status"],
        "manifest_sha256": result["manifest"]["manifest_sha256"],
        "aggregate": result["aggregate"],
        "comparisons": result["paired_cluster_bootstrap"],
        "json": str(json_path), "report": str(report_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
