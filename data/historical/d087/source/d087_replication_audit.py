"""Independent raw-ledger audit for D-087; no policy execution or search."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

OUTDIR = Path(__file__).resolve().parent / "results" / "d087_replication"
SEEDS = [711, 822, 933, 1044, 1155]
BASELINES = ("Hand", "FixedPrefix", "FixedPrefixForward", "RuleBased", "Greedy", "AdaptiveProbe", "CostAware", "Random")


def _mean(values):
    return sum(values) / len(values) if values else None


def _metrics(rows):
    family_values = []
    for family in sorted({row["task_family_id"] for row in rows}):
        group = [row for row in rows if row["task_family_id"] == family]
        r1 = [row for row in group if row["label"] == "R1"]
        r2 = [row for row in group if row["label"] == "R2"]
        r3 = [row for row in group if row["label"] == "R3"]
        r4 = [row for row in group if row["label"] == "R4"]
        family_values.append({
            "task_family_id": family,
            "r3_success": _mean([row["correct_escalation"] for row in r3]),
            "r4_success": _mean([row["class_success"] for row in r4]),
            "condrec": (_mean([row["conditional_recovery_success"] for row in r1]) + _mean([row["conditional_recovery_success"] for row in r2])) / 2,
            "prefix_compensation_success": _mean([row["prefix_compensation_success"] for row in r3]),
            "residual": _mean([row["residual_side_effects"] for row in group]),
            "avoid_harm": _mean([row["avoidable_harm"] for row in group]),
            "r3_cost": _mean([row["recovery_cost"] for row in r3]),
            "action_cost": _mean([row["action_cost"] for row in group]),
            "constraint_count": sum(row["constraint_violation"] for row in group),
            "duplicate_count": sum(row["duplicate_compensation"] for row in group),
            "pending_count": sum(row["pending_compensation"] for row in group),
        })
    return {
        "r3_success": _mean([item["r3_success"] for item in family_values]),
        "r4_success": _mean([item["r4_success"] for item in family_values]),
        "condrec": _mean([item["condrec"] for item in family_values]),
        "prefix_compensation_success": _mean([item["prefix_compensation_success"] for item in family_values]),
        "residual": _mean([item["residual"] for item in family_values]),
        "avoid_harm": _mean([item["avoid_harm"] for item in family_values]),
        "r3_cost": _mean([item["r3_cost"] for item in family_values]),
        "action_cost": _mean([item["action_cost"] for item in family_values]),
        "constraint_count": sum(item["constraint_count"] for item in family_values),
        "duplicate_count": sum(item["duplicate_count"] for item in family_values),
        "pending_count": sum(item["pending_count"] for item in family_values),
    }, family_values


def audit_replication(outdir=OUTDIR):
    outdir = Path(outdir)
    summary = json.loads((outdir / "d087_replication_summary.json").read_text(encoding="utf-8"))
    raw = json.loads((outdir / "d087_replication_rows.json").read_text(encoding="utf-8"))
    frozen = json.loads((outdir / "frozen_candidates.json").read_text(encoding="utf-8"))
    manifest = json.loads((outdir / "replication_manifest.json").read_text(encoding="utf-8"))
    with (outdir / "d087_replication_rows.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    checks = {}
    checks["raw_json_csv_exact"] = len(raw) == len(csv_rows) == 1040 and all(
        all(
            ("" if value is None else str(value)) == csv_row[key]
            for key, value in row.items() if key != "trace"
        )
        and json.loads(csv_row["trace_json"]) == row["trace"]
        for row, csv_row in zip(raw, csv_rows)
    )
    checks["one_evaluation_per_pair"] = len({
        (row["method"], row["optimizer_seed"], row["scenario_id"], row["scenario_seed"])
        for row in raw
    }) == 1040
    checks["validation_only"] = all(row["split"] == "validation" for row in raw)
    checks["scenario_ids_match_manifest"] = {row["scenario_id"] for row in raw} == {row["scenario_id"] for row in manifest["scenarios"]}
    checks["candidate_count"] = len([row for row in raw if row["method"] == "FrozenNSGA-III"]) == 400
    checks["all_baselines_present"] = all(
        len([row for row in raw if row["method"] == method]) == 80 for method in BASELINES
    )
    checks["frozen_seed_mapping"] = all(
        len([row for row in raw if row["method"] == "FrozenNSGA-III" and row["optimizer_seed"] == seed]) == 80
        for seed in SEEDS
    )
    checks["frozen_genome_unchanged"] = all(
        row["genome_fingerprint"] == item["genome_fingerprint"]
        for item in frozen["candidates"] for row in raw
        if row["method"] == "FrozenNSGA-III" and row["optimizer_seed"] == item["seed"]
    )
    checks["candidate_integrity"] = _canonical_frozen(frozen) == frozen["frozen_candidates_sha256"]
    checks["source_config_unchanged"] = frozen["source_config_sha256"] == hashlib.sha256(Path("experiments/pilot_a3b/d086_experiment_config.json").read_bytes()).hexdigest()
    checks["source_runs_unchanged"] = frozen["source_runs_sha256"] == hashlib.sha256(Path("experiments/pilot_a3b/results/d086_evolution/d086_experiment_runs.json").read_bytes()).hexdigest()
    checks["budget"] = summary["evaluation_calls"] == 1040 and summary["cache_hits"] == 0 and summary["unique_episode_equivalent"] == 1040
    checks["no_train_search"] = summary["train_search_performed"] is False
    checks["no_test"] = summary["test_accessed"] is False and manifest["test_included"] is False
    mismatches = []
    summary_by_method = {
        (item["method"], item["seed"]): item
        for item in summary["candidates"] + list(summary["baselines"].values())
    }
    for (method, seed), rows in _groups(raw).items():
        recomputed, family_values = _metrics(rows)
        expected = summary_by_method[(method, seed)]
        for key, value in recomputed.items():
            if value != expected[key]:
                mismatches.append({"method": method, "seed": seed, "metric": key, "expected": expected[key], "actual": value})
        if method != "FrozenNSGA-III":
            continue
        for family_item in family_values:
            expected_family = next(
                item for item in summary["per_family"]
                if item["seed"] == seed and item["task_family_id"] == family_item["task_family_id"]
            )
            for key, value in family_item.items():
                if value != expected_family[key]:
                    mismatches.append({
                        "method": method, "seed": seed,
                        "family": family_item["task_family_id"],
                        "metric": key, "expected": expected_family[key], "actual": value,
                    })
    checks["metrics_recomputed"] = not mismatches
    candidate_checks = []
    greedy_cost = summary["baselines"]["Greedy"]["r3_cost"]
    for item in summary["candidates"]:
        family = [row for row in summary["per_family"] if row["seed"] == item["seed"]]
        candidate_checks.append(
            item["r3_success"] == 1.0 and item["r4_success"] == 1.0
            and item["condrec"] == 1.0 and item["constraint_count"] == 0
            and item["r3_cost"] < greedy_cost
            and all(row["r3_success"] == 1.0 and row["r4_success"] == 1.0
                    and row["condrec"] == 1.0 and row["constraint_count"] == 0 for row in family)
        )
    any_hard = any(item["constraint_count"] > 0 for item in summary["candidates"])
    passed = sum(candidate_checks)
    if passed >= 4 and not any_hard:
        status = "REPLICATION_SUPPORTED"
    elif not any_hard and any(item["r3_success"] == 1.0 and item["r4_success"] == 1.0 and item["condrec"] == 1.0 and item["constraint_count"] == 0 for item in summary["candidates"]):
        status = "PARTIAL_REPLICATION"
    else:
        status = "REPLICATION_FAILED"
    checks["decision_recomputed"] = status == summary["decision"] and summary["decision_detail"]["candidate_pass_count"] == passed
    artifact = json.loads((outdir / "d087_artifact_manifest.json").read_text(encoding="utf-8"))
    checks["artifact_hashes"] = all(
        hashlib.sha256(b"\n".join((outdir / filename).read_bytes().splitlines())).hexdigest() == digest
        for filename, digest in artifact["files"].items()
    )
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "metric_mismatches": mismatches,
        "candidate_pass_count": passed,
        "decision": status,
        "raw_row_count": len(raw),
        "cache_hits": summary["cache_hits"],
        "train_search_performed": False,
        "test_accessed": False,
        "optimizer_runs": 0,
    }


def _groups(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["optimizer_seed"])].append(row)
    return groups


def _canonical_frozen(frozen):
    return hashlib.sha256(json.dumps({key: value for key, value in frozen.items() if key != "frozen_candidates_sha256"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(OUTDIR))
    args = parser.parse_args()
    report = audit_replication(args.outdir)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path = Path(args.outdir) / "d087_independent_audit.json"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FileExistsError("refusing to overwrite different independent audit")
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
