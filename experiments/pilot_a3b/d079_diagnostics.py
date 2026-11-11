"""Independent, outcome-blind audit of the D-078 Train/Validation artifact.

Reads only the disclosed D-078 Validation rows and reconstructs their four
Validation families. It never builds or reads Test.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from formal_scenario_generator import _build_cluster
from task_semantics import build_task_family


def parse_scenario_id(scenario_id):
    parts = str(scenario_id).split("|")
    if len(parts) != 4 or parts[0] != "validation":
        raise ValueError("unexpected D-078 scenario_id: " + str(scenario_id))
    return parts[1], parts[2], parts[3]


def reconstruct_validation_labels(scenario_ids):
    """Rebuild robust and analytic labels without constructing Test."""
    families = {}
    compositions = set()
    for scenario_id in scenario_ids:
        family_id, composition, _repeat = parse_scenario_id(scenario_id)
        families.setdefault(
            family_id,
            build_task_family(
                tuple(family_id.removeprefix("tf_").split("__")),
                family_id=family_id,
            ),
        )
        compositions.add(composition)

    labels = {}
    disagreements = []
    for family_id, family in sorted(families.items()):
        for composition in sorted(compositions):
            cluster, scenarios, problems = _build_cluster(
                family, "validation", composition
            )
            if problems:
                raise RuntimeError(
                    "Validation label reconstruction failed for "
                    + family_id + "/" + composition + ": "
                    + "; ".join(problems)
                )
            for scenario in scenarios:
                labels[scenario["scenario_id"]] = {
                    "robust_label": scenario["label"],
                    "analytic_label": scenario["analytic_label"],
                    "label_evidence_sha256": scenario["label_evidence_sha256"],
                    "cluster_id": scenario["cluster_id"],
                }
                if scenario["label"] != scenario["analytic_label"]:
                    disagreements.append({
                        "scenario_id": scenario["scenario_id"],
                        "robust_label": scenario["label"],
                        "analytic_label": scenario["analytic_label"],
                        "reason": scenario.get("analytic_disagreement_reason"),
                    })
    expected = set(scenario_ids)
    if set(labels) != expected:
        missing = sorted(expected - set(labels))
        extra = sorted(set(labels) - expected)
        raise RuntimeError(
            "reconstructed Validation IDs differ; missing="
            + repr(missing[:5]) + " extra=" + repr(extra[:5])
        )
    return labels, disagreements


def corrected_row_score(row, robust_label):
    """Re-score stored raw fields under corrected intended-effect semantics."""
    task_success = int(row.get("task_success", 0))
    residual = 0 if task_success else int(row.get("active_effects", 0))
    duplicates = int(row.get("duplicate_count", row.get("duplicate", 0)))
    minimum_harm = int(row.get("unavoidable_residual", 0))
    actual_harm = duplicates + residual
    avoidable_harm = max(0, actual_harm - minimum_harm)
    explicit_escalation = int(row.get("policy_selected_escalation", 0)) == 1

    if robust_label in ("R1", "R2"):
        success = task_success
    elif robust_label == "R3":
        success = int(explicit_escalation and residual == 0 and not task_success)
    elif robust_label == "R4":
        success = int(
            explicit_escalation
            and int(row.get("duplicate", duplicates > 0)) == 0
            and avoidable_harm == 0
        )
    else:
        success = None
    return {
        "robust_label": robust_label,
        "class_success": success,
        "actual_harm_corrected": actual_harm,
        "avoidable_harm_corrected": avoidable_harm,
        "residual_effects_corrected": residual,
    }


def _aggregate_add(target, row, scored):
    target["n"] += 1
    target["success_n"] += int(scored["class_success"] == 1)
    target["success_den"] += int(scored["class_success"] is not None)
    target["actual_harm"] += scored["actual_harm_corrected"]
    target["avoidable_harm"] += scored["avoidable_harm_corrected"]
    target["actions"] += int(row.get("action_count", 0))
    target["duplicates"] += int(row.get("duplicate_count", 0))
    target["sla_violations"] += int(row.get("sla_violation", 0))
    target["invariant_violations"] += int(row.get("invariant_violation", 0))


def audit_matrix(matrix):
    if matrix.get("matrix_version") != "sbcg-14-arm-train-validation-v1":
        raise ValueError("unexpected D-078 matrix version")
    policy = matrix.get("test_policy", {})
    if policy.get("test_outcomes_read") is not False:
        raise ValueError("D-078 artifact does not certify Test outcome isolation")
    if policy.get("test_scenarios_passed_to_runner") is not False:
        raise ValueError("D-078 artifact does not certify Test runner isolation")
    if matrix.get("run_count") != 42 or len(matrix.get("results", [])) != 42:
        raise ValueError("D-078 must contain exactly 42 registered runs")
    scenario_ids = sorted({
        row["scenario_id"]
        for run in matrix["results"]
        for row in (run.get("best_result") or {}).get("rows", [])
    })
    if len(scenario_ids) != 108:
        raise ValueError("D-078 Validation must contain exactly 108 scenario IDs")
    labels, disagreements = reconstruct_validation_labels(scenario_ids)

    hand_by_seed = {
        run["seed"]: run["best_fsm"]["fingerprint"]
        for run in matrix["results"]
        if run["algorithm"] == "Hand FSM" and run.get("best_fsm")
    }
    if len(hand_by_seed) != 3:
        raise ValueError("missing Hand FSM fingerprint for one or more seeds")

    scenario_rows = []
    family_buckets = defaultdict(lambda: {
        "n": 0, "success_n": 0, "success_den": 0,
        "actual_harm": 0, "avoidable_harm": 0, "actions": 0,
        "duplicates": 0, "sla_violations": 0, "invariant_violations": 0,
    })
    arm_buckets = defaultdict(lambda: {
        "runs": 0, "selected_hand": 0, "hand_in_pareto": 0,
        "fingerprints": set(), "n": 0, "success_n": 0, "success_den": 0,
        "actual_harm": 0, "avoidable_harm": 0, "actions": 0,
        "duplicates": 0, "sla_violations": 0, "invariant_violations": 0,
    })
    run_summaries = []

    for run in matrix["results"]:
        algorithm, seed = run["algorithm"], run["seed"]
        bucket = arm_buckets[algorithm]
        bucket["runs"] += 1
        best_fsm = run.get("best_fsm")
        fingerprint = best_fsm.get("fingerprint") if best_fsm else None
        if fingerprint:
            bucket["fingerprints"].add(fingerprint)
        selected_hand = bool(fingerprint and fingerprint == hand_by_seed[seed])
        bucket["selected_hand"] += int(selected_hand)
        front = (run.get("validation_report") or {}).get("pareto_front", [])
        hand_in_front = any(
            item.get("fingerprint") == hand_by_seed[seed] for item in front
        )
        bucket["hand_in_pareto"] += int(hand_in_front)

        metrics = run.get("best_result") or {}
        rows = metrics.get("rows", [])
        run_success = defaultdict(lambda: [0, 0])
        run_labels = Counter()
        for row in rows:
            scenario_id = row["scenario_id"]
            info = labels[scenario_id]
            robust_label, analytic_label = info["robust_label"], info["analytic_label"]
            scored = corrected_row_score(row, robust_label)
            family_id, composition, repeat = parse_scenario_id(scenario_id)
            run_labels[robust_label] += 1
            scenario_rows.append({
                "algorithm": algorithm,
                "seed": seed,
                "scenario_id": scenario_id,
                "family_id": family_id,
                "composition": composition,
                "repeat": repeat,
                "robust_label": robust_label,
                "analytic_label": analytic_label,
                "label_disagrees": robust_label != analytic_label,
                "selected_fsm_is_hand": selected_hand,
                "task_success": int(row.get("task_success", 0)),
                "class_success_corrected": scored["class_success"],
                "active_effects": int(row.get("active_effects", 0)),
                "residual_effects_corrected": scored["residual_effects_corrected"],
                "original_avoidable_harm": float(row.get("avoidable_harm", 0.0)),
                "actual_harm_corrected": scored["actual_harm_corrected"],
                "avoidable_harm_corrected": scored["avoidable_harm_corrected"],
                "policy_selected_escalation": int(row.get("policy_selected_escalation", 0)),
                "duplicate_count": int(row.get("duplicate_count", 0)),
                "sla_violation": int(row.get("sla_violation", 0)),
                "invariant_violation": int(row.get("invariant_violation", 0)),
                "action_count": int(row.get("action_count", 0)),
            })
            run_success[robust_label][0] += int(scored["class_success"] == 1)
            run_success[robust_label][1] += int(scored["class_success"] is not None)
            _aggregate_add(
                family_buckets[(algorithm, seed, family_id, composition, robust_label)],
                row, scored,
            )
            _aggregate_add(bucket, row, scored)

        run_summaries.append({
            "algorithm": algorithm,
            "seed": seed,
            "selected_fsm_fingerprint": fingerprint,
            "selected_fsm_is_hand": selected_hand,
            "hand_present_in_validation_pareto_front": hand_in_front,
            "pareto_candidate_count": len(front),
            "validation_rows": len(rows),
            "robust_label_counts": dict(sorted(run_labels.items())),
            "selected_validation_metrics_original": {
                name: metrics.get(name)
                for name in (
                    "cond_rec", "corr_esc", "containment",
                    "avoid_resid", "unnec_actions_r12",
                    "dup", "sla_viol", "violations",
                )
            },
            "corrected_class_success": {
                label: (value[0] / value[1] if value[1] else None)
                for label, value in sorted(run_success.items())
            },
        })

    arms = {}
    for algorithm, b in sorted(arm_buckets.items()):
        arms[algorithm] = {
            "runs": b["runs"],
            "selected_hand_count": b["selected_hand"],
            "hand_in_pareto_front_count": b["hand_in_pareto"],
            "unique_selected_fingerprints": len(b["fingerprints"]),
            "corrected_class_success": b["success_n"] / b["success_den"] if b["success_den"] else None,
            "corrected_avoidable_harm_per_scenario": b["avoidable_harm"] / b["n"] if b["n"] else None,
            "corrected_actual_harm_per_scenario": b["actual_harm"] / b["n"] if b["n"] else None,
            "mean_action_count": b["actions"] / b["n"] if b["n"] else None,
            "duplicate_rate": b["duplicates"] / b["n"] if b["n"] else None,
            "sla_violation_rate": b["sla_violations"] / b["n"] if b["n"] else None,
            "invariant_violation_rate": b["invariant_violations"] / b["n"] if b["n"] else None,
        }

    family_output = []
    for (algorithm, seed, family_id, composition, label), b in sorted(family_buckets.items()):
        family_output.append({
            "algorithm": algorithm,
            "seed": seed,
            "family_id": family_id,
            "composition": composition,
            "robust_label": label,
            "n": b["n"],
            "class_success": b["success_n"] / b["success_den"] if b["success_den"] else None,
            "mean_avoidable_harm_corrected": b["avoidable_harm"] / b["n"],
            "mean_actual_harm_corrected": b["actual_harm"] / b["n"],
            "mean_action_count": b["actions"] / b["n"],
            "duplicate_rate": b["duplicates"] / b["n"],
            "sla_violation_rate": b["sla_violations"] / b["n"],
            "invariant_violation_rate": b["invariant_violations"] / b["n"],
        })

    hand_rows = [row for row in scenario_rows if row["algorithm"] == "Hand FSM"]
    hand_primary = [row for row in hand_rows if row["robust_label"] in ("R1", "R2")]
    hand_r3 = [row for row in hand_rows if row["robust_label"] == "R3"]
    hand_r4 = [row for row in hand_rows if row["robust_label"] == "R4"]
    summary = {
        "status": "D078_INDEPENDENT_DIAGNOSTIC_COMPLETE",
        "matrix_version": matrix["matrix_version"],
        "git_head": matrix.get("git_head"),
        "manifest_sha256": matrix.get("manifest_sha256"),
        "algorithm_count": matrix["algorithm_count"],
        "run_count": matrix["run_count"],
        "seed_count": len(matrix["seeds"]),
        "validation_scenario_count": len(scenario_ids),
        "validation_family_count": len({parse_scenario_id(sid)[0] for sid in scenario_ids}),
        "robust_vs_analytic_label_disagreements": len(disagreements),
        "label_disagreements": disagreements,
        "selected_hand_fsm_runs": sum(x["selected_fsm_is_hand"] for x in run_summaries),
        "runs_with_hand_in_validation_pareto_front": sum(
            x["hand_present_in_validation_pareto_front"] for x in run_summaries
        ),
        "hand_primary_success": (
            sum(row["class_success_corrected"] == 1 for row in hand_primary) / len(hand_primary)
            if hand_primary else None
        ),
        "hand_primary_scenario_count": len(hand_primary),
        "hand_r3_correct_escalation": (
            sum(row["class_success_corrected"] == 1 for row in hand_r3) / len(hand_r3)
            if hand_r3 else None
        ),
        "hand_r3_scenario_count": len(hand_r3),
        "hand_r4_damage_containment": (
            sum(row["class_success_corrected"] == 1 for row in hand_r4) / len(hand_r4)
            if hand_r4 else None
        ),
        "hand_r4_scenario_count": len(hand_r4),
        "arms": arms,
        "run_summaries": run_summaries,
    }
    return summary, scenario_rows, family_output


def write_outputs(summary, scenario_rows, family_rows, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "d079_d078_audit.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for filename, rows in (
        ("d078_scenario_diagnostics.csv", scenario_rows),
        ("d078_family_composition_diagnostics.csv", family_rows),
    ):
        if rows:
            with (outdir / filename).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    lines = [
        "# D-079 independent diagnostics of D-078",
        "",
        "- Scope: D-078 disclosed Validation rows only; no Test scenarios or outcomes are reconstructed.",
        "- Robust labels are reconstructed from the four disclosed Validation families.",
        "- Corrected harm excludes intended active effects after successful completion; duplicates remain harmful.",
        "",
        f"- Runs: {summary['run_count']} across {summary['algorithm_count']} arms and {summary['seed_count']} seeds.",
        f"- Validation scenarios: {summary['validation_scenario_count']} across {summary['validation_family_count']} families.",
        f"- Robust/analytic label disagreements: {summary['robust_vs_analytic_label_disagreements']}.",
        f"- Selected FSMs exactly equal to Hand FSM: {summary['selected_hand_fsm_runs']}/{summary['run_count']}.",
        f"- Runs whose Validation Pareto front contains Hand FSM: {summary['runs_with_hand_in_validation_pareto_front']}/{summary['run_count']}.",
        "",
        "## Per-arm results",
        "",
        "| Arm | Hand selected / runs | Hand in Pareto / runs | Unique selected FSMs | Corrected avoidable harm / scenario | Duplicate rate | SLA violation rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    def fmt(value):
        return "n/a" if value is None else f"{value:.4f}"

    for algorithm, arm in summary["arms"].items():
        lines.append(
            f"| {algorithm} | {arm['selected_hand_count']}/{arm['runs']} | "
            f"{arm['hand_in_pareto_front_count']}/{arm['runs']} | "
            f"{arm['unique_selected_fingerprints']} | "
            f"{fmt(arm['corrected_avoidable_harm_per_scenario'])} | "
            f"{fmt(arm['duplicate_rate'])} | {fmt(arm['sla_violation_rate'])} |"
        )
    lines.extend([
        "",
        "## Hand FSM class-conditional diagnostics",
        "",
        f"- R1/R2 CondRecSucc: {summary['hand_primary_success']:.4f} over {summary['hand_primary_scenario_count']} scenarios.",
        f"- R3 CorrectEscalation: {summary['hand_r3_correct_escalation']:.4f} over {summary['hand_r3_scenario_count']} scenarios.",
        f"- R4 DamageContainment: {summary['hand_r4_damage_containment']:.4f} over {summary['hand_r4_scenario_count']} scenarios.",
        "",
        "## Interpretation limits",
        "",
        "- Exact Hand selections are selection outcomes, not proof that all optimizers converged to the Hand genome.",
        "- Validation is used for candidate selection in D-078; its metrics remain selection-biased.",
        "- Corrected harm is a post-hoc re-score of stored fields, not a rerun.",
        "- This audit does not establish EC uplift, formal A-3b readiness, or generalization to locked Test.",
        "",
    ])
    (outdir / "d079_d078_audit_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(
            Path(__file__).resolve().parent
            / "results" / "d078_train_validation_pilot" / "matrix_results.json"
        ),
    )
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    matrix = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary, scenario_rows, family_rows = audit_matrix(matrix)
    write_outputs(summary, scenario_rows, family_rows, args.outdir)
    print(json.dumps({
        "status": summary["status"],
        "run_count": summary["run_count"],
        "selected_hand_fsm_runs": summary["selected_hand_fsm_runs"],
        "label_disagreements": summary["robust_vs_analytic_label_disagreements"],
        "hand_primary_success": summary["hand_primary_success"],
        "hand_r3_correct_escalation": summary["hand_r3_correct_escalation"],
        "hand_r4_damage_containment": summary["hand_r4_damage_containment"],
        "outdir": args.outdir,
    }, indent=2))


if __name__ == "__main__":
    main()
