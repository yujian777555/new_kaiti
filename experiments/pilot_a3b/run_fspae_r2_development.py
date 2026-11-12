#!/usr/bin/env python3
"""Development-only R2 mechanism experiment on the locked D-079 Train domain.

The diagnostic role was already inspected in the earlier R1 pilot. This runner
reuses it only for iterative mechanism development and never labels it held-out
or confirmatory. All optimization fitness remains Train/search-only.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from a3_bridge import evaluator_verdict_from_scenario, hand_fsm
from d079_challenge_generator import (
    build_challenge_manifest, validate_challenge_manifest, validate_manifest_lock,
)
from run_fspae_pilot import (
    ARCHIVE_CAPACITY, EXPECTED_MANIFEST_SHA256, GENERATIONS, POP_SIZE, SEEDS,
    _mean, _paired_cluster_bootstrap, _rows_for_diagnostic, _run_evolutionary_arm,
    _summarize_rows,
)
from sbcg import evaluate_sbcg_candidate, make_shared_initial_pool
from sbcg_experiment import reflection_proxy_fsm, rule_based_fsm
from split_access import validate_evaluation_scenarios, validate_evolution_scenarios

ARMS = (
    "matched_nsga3",
    "sbcg_nsga3",
    "fspae",
    "fspae_uniform",
    "fspae_r2",
    "fspae_r2_global_mut",
    "fspae_r2_uniform",
    "fspae_r2_uniform_global_mut",
    "fspae_r2_legacy_scheduler",
)
COMPARATORS = {
    "matched_nsga3": "matched_nsga3",
    "sbcg_nsga3": "sbcg_nsga3",
    "fspae_r1": "fspae",
    "r2_global_mutation_ablation": "fspae_r2_global_mut",
    "r2_uniform_target_ablation": "fspae_r2_uniform",
    "r2_uniform_global_mutation_factorial_cell": "fspae_r2_uniform_global_mut",
    "r2_legacy_scheduler_ablation": "fspae_r2_legacy_scheduler",
}
FIELDS = (
    "class_success", "avoidable_harm", "duplicate",
    "sla_violation", "invariant_violation", "decision_count",
)


def _mechanism_audit(results):
    grouped = defaultdict(list)
    for result in results:
        if not result["method"].startswith("fspae_r2"):
            continue
        audit = result["search"].get("mutation_audit", [])
        grouped[result["method"]].append({
            "seed": result["seed"],
            "offspring_count": len(audit),
            "local_parent_pair_count": sum(
                item.get("parent_a_source") == "target_archive"
                and item.get("parent_b_source") == "target_archive"
                for item in audit
            ),
            "targeted_mutation_count": sum(
                item.get("selected_cluster") is not None for item in audit
            ),
            "target_match_count": sum(
                item.get("selected_cluster") is not None
                and item.get("selected_cluster") == item.get("target_cluster")
                for item in audit
            ),
            "cross_target_mutation_count": sum(
                item.get("selected_cluster") is not None
                and item.get("selected_cluster") != item.get("target_cluster")
                for item in audit
            ),
            "no_target_counterexample_fallbacks": sum(
                item.get("fallback") == "standard_mutation_no_target_counterexamples"
                for item in audit
            ),
            "target_selection_counts": result["search"].get("target_selection_counts", {}),
        })
    return {
        method: {
            "per_seed": rows,
            "offspring_count": sum(row["offspring_count"] for row in rows),
            "local_parent_pair_count": sum(row["local_parent_pair_count"] for row in rows),
            "targeted_mutation_count": sum(row["targeted_mutation_count"] for row in rows),
            "target_match_count": sum(row["target_match_count"] for row in rows),
            "cross_target_mutation_count": sum(row["cross_target_mutation_count"] for row in rows),
            "no_target_counterexample_fallbacks": sum(
                row["no_target_counterexample_fallbacks"] for row in rows
            ),
        }
        for method, rows in grouped.items()
    }


def run_development_experiment():
    manifest = build_challenge_manifest()
    challenge_gate = validate_challenge_manifest(manifest)
    if not challenge_gate["ok"]:
        raise RuntimeError("D-079 challenge gate failed: " + "; ".join(challenge_gate["problems"]))
    lock_gate = validate_manifest_lock(manifest)
    if not lock_gate["ok"]:
        raise RuntimeError("D-079 v2 lock failed: " + "; ".join(lock_gate["problems"]))
    if manifest["manifest_sha256"] != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("D-079 manifest SHA differs from the committed v2 lock")

    scenarios = manifest["scenarios"]
    if len(scenarios) != 288 or any(row.get("split") != "train" for row in scenarios):
        raise RuntimeError("R2 development requires exactly 288 Train-only scenarios")
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
        for method in ARMS:
            results.append(_run_evolutionary_arm(
                method, shared_pool, search, diagnostic, verdicts, seed, budget
            ))

    fixed_baselines = []
    for method, policy in (
        ("hand_fsm", hand_fsm()),
        ("rule_based", rule_based_fsm()),
        ("reflection_proxy", reflection_proxy_fsm()),
    ):
        record = evaluate_sbcg_candidate(
            policy, diagnostic, verdicts, use_five_objectives=True
        )
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
    for label, comparator in COMPARATORS.items():
        comparisons[f"fspae_r2_vs_{label}"] = {
            field: _paired_cluster_bootstrap(
                rows_by_method["fspae_r2"], rows_by_method[comparator], field,
                seed=2026111301 + len(comparisons),
            )
            for field in FIELDS
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
            "mean_macro_class_success": _mean(
                [item["macro_class_success"] for item in available]
            ),
            "mean_cond_rec_r1_r2": _mean(
                [item["cond_rec_r1_r2"] for item in available]
            ),
            "mean_correct_escalation_r3": _mean(
                [item["correct_escalation_r3"] for item in available]
            ),
            "mean_damage_containment_r4": _mean(
                [item["damage_containment_r4"] for item in available]
            ),
            "mean_avoidable_harm": _mean(
                [item["avoidable_harm_mean"] for item in available]
            ),
            "mean_recovery_decisions": _mean(
                [item["mean_recovery_decisions"] for item in available]
            ),
            "all_seeds_hard_safety_pass": bool(available) and all(
                item["hard_safety_gate"] == "PASS" for item in available
            ),
        }

    return {
        "schema_version": 1,
        "experiment": "D079_FSPAE_R2_3_CONTEXT_CONDITIONED_DEVELOPMENT_DIAGNOSTIC",
        "status": "EXECUTED_DEVELOPMENT_ONLY_DIAGNOSTIC_REUSED",
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
            "search_split": "train",
            "diagnostic_split": "train",
            "optimization_role": "search",
            "candidate_diagnostic_role": "diagnostic",
            "diagnostic_role_reused_from_prior_R1_study": True,
            "diagnostic_is_fresh_heldout": False,
            "validation_scenarios_constructed": False,
            "test_scenarios_constructed": False,
            "test_outcomes_read": False,
            "llm_inference": False,
            "api_calls": False,
            "gpu_or_optimizer_service": False,
            "foundation_model_training": False,
        },
        "protocol": {
            "seeds": list(SEEDS),
            "population": POP_SIZE,
            "generations": GENERATIONS,
            "per_arm_seed_search_episode_budget": budget,
            "total_evolutionary_arm_seed_runs": len(ARMS) * len(SEEDS),
            "arms": list(ARMS),
            "fixed_diagnostic_baselines": [
                "hand_fsm", "rule_based", "reflection_proxy"
            ],
            "candidate_selection": (
                "common Train-search feasible Pareto / family coverage / "
                "worst-family CondRecSucc selector"
            ),
            "diagnostic_reuse_notice": (
                "The D-079 diagnostic role was already inspected in the R1 study. "
                "This run is development-only and is not a fresh held-out evaluation."
            ),
        },
        "results": results,
        "fixed_baselines": fixed_baselines,
        "aggregate": aggregate,
        "paired_cluster_bootstrap": comparisons,
        "mechanism_audit": _mechanism_audit(results),
        "interpretation": (
            "Use this run to decide whether target-conditioned search deserves a "
            "freshly generated and locked diagnostic protocol. It is not confirmatory "
            "evidence and does not authorize Validation/Test access."
        ),
    }


def write_outputs(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "d079_fspae_r2_development.json"
    report_path = output_dir / "d079_fspae_r2_development.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# D-079 FSPAE-R2.3 context-conditioned development experiment",
        "",
        f"- Status: **{result['status']}**",
        f"- Manifest SHA-256: {result['manifest']['manifest_sha256']}",
        f"- Seeds: {result['protocol']['seeds']}",
        f"- Population / generations: {result['protocol']['population']} / {result['protocol']['generations']}",
        f"- Search budget per arm/seed: {result['protocol']['per_arm_seed_search_episode_budget']}",
        f"- Evolutionary runs: {result['protocol']['total_evolutionary_arm_seed_runs']}",
        "- Optimization fitness: Train/search only",
        "- Diagnostic: previously inspected D-079 Train/diagnostic role; development use only",
        "- Validation/Test, LLM API, GPU and model training: not used",
        "",
        "## Diagnostic metrics",
        "",
        "| Method | Macro success | Mean decisions | R1/R2 CondRec | R3 escalation | R4 containment | Avoidable harm | Hard safety |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    order = list(ARMS) + ["hand_fsm", "rule_based", "reflection_proxy"]
    for method in order:
        summary = result["aggregate"].get(method, {})
        if "per_seed" in summary:
            values = (
                summary.get("mean_macro_class_success"),
                summary.get("mean_recovery_decisions"),
                summary.get("mean_cond_rec_r1_r2"),
                summary.get("mean_correct_escalation_r3"),
                summary.get("mean_damage_containment_r4"),
                summary.get("mean_avoidable_harm"),
                "PASS" if summary.get("all_seeds_hard_safety_pass") else "FAIL/HOLD",
            )
        else:
            values = (
                summary.get("macro_class_success"),
                summary.get("mean_recovery_decisions"),
                summary.get("cond_rec_r1_r2"),
                summary.get("correct_escalation_r3"),
                summary.get("damage_containment_r4"),
                summary.get("avoidable_harm_mean"),
                summary.get("hard_safety_gate"),
            )
        def fmt(value):
            if value is None:
                return "NA"
            return f"{float(value):.4f}" if isinstance(value, (int, float)) else str(value)
        lines.append("| " + method + " | " + " | ".join(fmt(x) for x in values) + " |")

    lines.extend(["", "## Paired descriptive contrasts for FSPAE-R2", ""])
    for label, fields in result["paired_cluster_bootstrap"].items():
        lines.extend([
            f"### {label}", "",
            "| Endpoint | Mean cluster difference | 95% descriptive cluster-bootstrap interval | Clusters |",
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

    lines.extend(["", "## Mechanism dataflow audit", ""])
    lines.append(
        "| Arm | Offspring | Local parent pairs | Targeted mutations | Exact target matches | Cross-target mutations | No-target fallbacks |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for method, item in result["mechanism_audit"].items():
        lines.append(
            f"| {method} | {item['offspring_count']} | {item['local_parent_pair_count']} | "
            f"{item['targeted_mutation_count']} | {item['target_match_count']} | "
            f"{item['cross_target_mutation_count']} | {item['no_target_counterexample_fallbacks']} |"
        )
    lines.extend([
        "",
        "## 2×2 scheduler × mutation factorial",
        "",
        "The four local-parent cells are performance-deficit/exact-target, performance-deficit/global, uniform/exact-target, and uniform/global. Compare the missing uniform/global cell with the three existing cells using the same paired diagnostic rows and per-seed summaries.",
        "",
        "## Advancement rule",
        "",
        "Advance to a fresh locked diagnostic only if the mechanism gates pass, hard safety remains at zero, cross-target mutation count is zero, and class-conditional development metrics improve consistently over matched NSGA-III and R1 FSPAE.",
        "",
        "This report reuses a diagnostic role that was previously inspected. All contrasts are development evidence; no held-out, confirmatory, or generalization claim is made.",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, report_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_development_experiment()
    json_path, report_path = write_outputs(result, args.output_dir)
    print(json.dumps({
        "status": result["status"],
        "manifest_sha256": result["manifest"]["manifest_sha256"],
        "aggregate": result["aggregate"],
        "mechanism_audit": result["mechanism_audit"],
        "json": str(json_path),
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
