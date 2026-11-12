"""D-087 evaluation of frozen candidates only; no search or Test access."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from d087_challenge import LOCK_PATH, MANIFEST_PATH, build_manifest, validate_lock, validate_manifest
from dependency_genome import GenomePolicy, RecoveryGenome
from dependency_policies import make_policy
from dependency_recovery import run_episode

HERE = Path(__file__).resolve().parent
OUTDIR = HERE / "results" / "d087_replication"
FROZEN_PATH = OUTDIR / "frozen_candidates.json"
SEEDS = [711, 822, 933, 1044, 1155]
BASELINES = ("Hand", "FixedPrefix", "FixedPrefixForward", "RuleBased", "Greedy", "AdaptiveProbe", "CostAware", "Random")
RANDOM_SEED = 20261122
SOURCE_RUNS = HERE / "results" / "d086_evolution" / "d086_experiment_runs.json"
SOURCE_CONFIG = HERE / "d086_experiment_config.json"
SOURCE_MANIFEST = HERE / "results" / "d086_dependency_challenge" / "dependency_manifest.json"
SOURCE_ASSESSMENT = HERE / "results" / "d086_evolution" / "nsga3_candidate_assessment.json"
SOURCE_COMMIT = "5210d1c40fbb41b39a51e2ef7ef544e582dc4af5"
ALGORITHM_FILES = (
    "dependency_genome.py", "dependency_policies.py", "dependency_recovery.py",
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_file_sha(path):
    return hashlib.sha256(b"\n".join(Path(path).read_bytes().splitlines())).hexdigest()


def _write_once(path, text, newline=None):
    path = Path(path)
    if path.exists():
        with path.open("r", encoding="utf-8", newline=newline) as handle:
            if handle.read() != text:
                raise FileExistsError("refusing to overwrite different D-087 evidence: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)


def freeze_candidates():
    runs = json.loads(SOURCE_RUNS.read_text(encoding="utf-8"))
    config = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    assessment = json.loads(SOURCE_ASSESSMENT.read_text(encoding="utf-8"))
    selected = [run for run in runs if run["arm"] == "NSGA-III"]
    if [run["seed"] for run in selected] != SEEDS or not all(assessment["criteria"].values()):
        raise ValueError("D-086 frozen candidate source is invalid")
    if manifest["test_included"] or manifest["test_outcomes_read"]:
        raise ValueError("D-086 source manifest violates Test isolation")
    candidates = []
    for run in selected:
        if run["selection"]["status"] != "SELECTED" or run["budget_exhausted"]:
            raise ValueError("frozen candidate was not validly selected")
        genome = run["selection"]["genome"]
        if not any(record["genome"] == genome for record in run["archive"]):
            raise ValueError("selected genome is absent from the original archive")
        candidate = RecoveryGenome(**genome)
        fp = repr(sorted(candidate.fingerprint().items()))
        candidates.append({
            "seed": run["seed"],
            "genome": genome,
            "genome_fingerprint": fp,
            "genome_sha256": hashlib.sha256(fp.encode("utf-8")).hexdigest(),
            "source_archive_candidates": len(run["archive"]),
            "source_validation_unique": run["ledger_stats"]["unique_episode_equivalent"]["validation"],
            "source_r3_cost": run["selection"]["metrics"]["r3_cost"],
        })
    result = {
        "protocol_id": "D-087-REPLICATION",
        "source_commit": SOURCE_COMMIT,
        "source_runs_sha256": _file_sha(SOURCE_RUNS),
        "source_config_sha256": _file_sha(SOURCE_CONFIG),
        "source_manifest_sha256": manifest["manifest_sha256"],
        "algorithm_sha256": {name: _file_sha(HERE / name) for name in ALGORITHM_FILES},
        "source_seeds": SEEDS,
        "source_population_size": 12,
        "source_generations": 6,
        "source_episode_cap": 6048,
        "candidate_evaluation_cap": 400,
        "train_search_performed": False,
        "new_genomes_created": False,
        "test_accessed": False,
        "candidates": candidates,
    }
    result["frozen_candidates_sha256"] = _sha256(result)
    _write_once(FROZEN_PATH, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return result


def load_frozen_candidates(path=FROZEN_PATH):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    if _sha256({key: value for key, value in result.items() if key != "frozen_candidates_sha256"}) != result["frozen_candidates_sha256"]:
        raise ValueError("frozen candidate hash mismatch")
    if result["source_runs_sha256"] != _file_sha(SOURCE_RUNS) or result["source_config_sha256"] != _file_sha(SOURCE_CONFIG):
        raise ValueError("source evidence changed after candidate freeze")
    if result["algorithm_sha256"] != {name: _file_sha(HERE / name) for name in ALGORITHM_FILES}:
        raise ValueError("algorithm code differs from the frozen source")
    if result["train_search_performed"] or result["new_genomes_created"] or result["test_accessed"]:
        raise ValueError("candidate freeze violates the D-087 boundary")
    return result


def _mean(values):
    return sum(values) / len(values) if values else None


def _metrics(rows):
    families = sorted({row["task_family_id"] for row in rows})
    per_family = []
    for family in families:
        group = [row for row in rows if row["task_family_id"] == family]
        r1 = [row for row in group if row["label"] == "R1"]
        r2 = [row for row in group if row["label"] == "R2"]
        r3 = [row for row in group if row["label"] == "R3"]
        r4 = [row for row in group if row["label"] == "R4"]
        per_family.append({
            "task_family_id": family,
            "scenario_count": len(group),
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
    metrics = {
        "family_count": len(per_family),
        "scenario_count": len(rows),
        "class_success": _mean([row["class_success"] for row in rows]),
        "r3_success": _mean([item["r3_success"] for item in per_family]),
        "r4_success": _mean([item["r4_success"] for item in per_family]),
        "condrec": _mean([item["condrec"] for item in per_family]),
        "prefix_compensation_success": _mean([item["prefix_compensation_success"] for item in per_family]),
        "residual": _mean([item["residual"] for item in per_family]),
        "avoid_harm": _mean([item["avoid_harm"] for item in per_family]),
        "r3_cost": _mean([item["r3_cost"] for item in per_family]),
        "action_cost": _mean([item["action_cost"] for item in per_family]),
        "constraint_count": sum(item["constraint_count"] for item in per_family),
        "duplicate_count": sum(item["duplicate_count"] for item in per_family),
        "pending_count": sum(item["pending_count"] for item in per_family),
    }
    return metrics, per_family


def _decision(candidate_metrics, family_metrics, baseline_metrics):
    greedy_cost = baseline_metrics["Greedy"]["r3_cost"]
    by_candidate_family = {
        (item["seed"], item["task_family_id"]): item
        for item in family_metrics if item["method"] == "FrozenNSGA-III"
    }
    checks = []
    for metrics in candidate_metrics:
        family_checks = [
            by_candidate_family[(metrics["seed"], family)]
            for family in sorted({item["task_family_id"] for item in family_metrics if item["method"] == "FrozenNSGA-III"})
        ]
        checks.append({
            "seed": metrics["seed"],
            "r3_one": metrics["r3_success"] == 1.0,
            "r4_one": metrics["r4_success"] == 1.0,
            "condrec_one": metrics["condrec"] == 1.0,
            "zero_hard_constraints": metrics["constraint_count"] == 0,
            "cost_below_greedy": metrics["r3_cost"] < greedy_cost,
            "all_families_safe_and_successful": all(
                item["r3_success"] == 1.0 and item["r4_success"] == 1.0
                and item["condrec"] == 1.0 and item["constraint_count"] == 0
                for item in family_checks
            ),
        })
    passed = [item for item in checks if all(value for key, value in item.items() if key != "seed")]
    any_hard_violation = any(item["constraint_count"] > 0 for item in candidate_metrics)
    supported = len(passed) >= 4 and not any_hard_violation
    if supported:
        status = "REPLICATION_SUPPORTED"
    elif any_hard_violation:
        status = "REPLICATION_FAILED"
    elif any(item["r3_success"] == 1.0 and item["r4_success"] == 1.0
             and item["condrec"] == 1.0 and item["constraint_count"] == 0
             for item in candidate_metrics):
        status = "PARTIAL_REPLICATION"
    else:
        status = "REPLICATION_FAILED"
    return {
        "status": status,
        "research_decision": "GO_FOR_INDEPENDENT_REPLICATION_EVIDENCE" if supported else "NO_GO",
        "candidate_pass_count": len(passed),
        "required_candidate_pass_count": 4,
        "any_candidate_hard_violation": any_hard_violation,
        "greedy_r3_cost": greedy_cost,
        "candidate_checks": checks,
        "statistics": "descriptive per-seed and per-family comparisons only; no confirmatory test or post-hoc CI",
    }


def summarize_rows(rows, frozen):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["optimizer_seed"])].append(row)
    candidates = []
    baselines = {}
    per_family = []
    for (method, seed), group in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1])):
        metrics, families = _metrics(group)
        record = {"method": method, "seed": seed, **metrics}
        if method == "FrozenNSGA-III":
            candidates.append(record)
            for family in families:
                per_family.append({"method": method, "seed": seed, **family})
        else:
            baselines[method] = record
    if len(candidates) != 5 or len(baselines) != 8 or len(per_family) != 20:
        raise ValueError("incomplete frozen candidate or baseline evaluation")
    decision = _decision(candidates, per_family, baselines)
    return {
        "protocol_id": "D-087-REPLICATION",
        "manifest_sha256": build_manifest()["manifest_sha256"],
        "candidate_sha256": frozen["frozen_candidates_sha256"],
        "source_commit": frozen["source_commit"],
        "source_runs_sha256": frozen["source_runs_sha256"],
        "source_config_sha256": frozen["source_config_sha256"],
        "algorithm_sha256": frozen["algorithm_sha256"],
        "candidate_seeds": SEEDS,
        "baseline_methods": list(BASELINES),
        "candidate_count": len(candidates),
        "baseline_count": len(baselines),
        "raw_row_count": len(rows),
        "evaluation_calls": len(rows),
        "unique_episode_equivalent": len(rows),
        "cache_hits": 0,
        "decision": decision["status"],
        "decision_detail": decision,
        "candidates": candidates,
        "baselines": baselines,
        "per_family": per_family,
        "budget": {
            "candidate_cap": 400,
            "baseline_cap": 640,
            "total_cap": 1040,
            "decision_cap_per_episode": 24,
        },
        "train_search_performed": False,
        "test_accessed": False,
        "real_llm_api_calls": 0,
    }


def evaluate_replication(manifest, frozen):
    if not validate_manifest(manifest)["ok"] or not validate_lock(manifest, LOCK_PATH)["ok"]:
        raise ValueError("D-087 manifest or lock is invalid")
    if frozen != load_frozen_candidates():
        raise ValueError("candidate file is not identical to the frozen source")
    rows = []
    unique = set()
    for scenario in manifest["scenarios"]:
        if scenario["split"] != "validation":
            raise ValueError("replication accepts only new Validation scenarios")
        for method in BASELINES:
            result = run_episode(make_policy(method, seed=RANDOM_SEED), scenario)
            key = (method, -1, scenario["scenario_id"], scenario["seed"])
            if key in unique:
                raise ValueError("duplicate baseline evaluation")
            unique.add(key)
            rows.append({
                "method": method,
                "optimizer_seed": -1,
                "policy_seed": RANDOM_SEED if method == "Random" else None,
                "genome_fingerprint": None,
                "task_family_id": scenario["task_family_id"],
                "difficulty_stratum": scenario["difficulty_stratum"],
                "composition": scenario["composition"],
                "repeat": scenario["repeat"],
                "scenario_seed": scenario["seed"],
                **result,
            })
        for candidate in frozen["candidates"]:
            genome = RecoveryGenome(**candidate["genome"])
            result = run_episode(GenomePolicy(genome), scenario)
            key = ("FrozenNSGA-III", candidate["seed"], scenario["scenario_id"], scenario["seed"])
            if key in unique:
                raise ValueError("duplicate frozen candidate evaluation")
            unique.add(key)
            rows.append({
                "method": "FrozenNSGA-III",
                "optimizer_seed": candidate["seed"],
                "policy_seed": None,
                "genome_fingerprint": candidate["genome_fingerprint"],
                "genome_sha256": candidate["genome_sha256"],
                "task_family_id": scenario["task_family_id"],
                "difficulty_stratum": scenario["difficulty_stratum"],
                "composition": scenario["composition"],
                "repeat": scenario["repeat"],
                "scenario_seed": scenario["seed"],
                **result,
            })
    if len(rows) != 1040 or len(unique) != 1040:
        raise ValueError("D-087 evaluation count differs from the frozen budget")
    return rows, summarize_rows(rows, frozen)


def write_outputs(summary, rows, per_family, outdir=OUTDIR):
    outdir = Path(outdir)
    fields = list(dict.fromkeys(
        key for row in rows for key in row if key != "trace"
    )) + ["trace_json"]
    import csv
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        output = {key: value for key, value in row.items() if key != "trace"}
        output["trace_json"] = json.dumps(row["trace"], ensure_ascii=False)
        writer.writerow(output)
    report = [
        "# D-087 frozen NSGA-III independent replication",
        "",
        "No Train search, Test, real LLM API, model training, or parameter modification was performed.",
        "",
        f"- Decision: **{summary['decision']}**",
        f"- Candidate pass count: {summary['decision_detail']['candidate_pass_count']}/5.",
        f"- Raw rows: {summary['raw_row_count']}; evaluation calls: {summary['evaluation_calls']}; cache hits: {summary['cache_hits']}.",
        "",
        "| Method | Seed | R3 | R4 | CondRecSucc | R3 cost | Constraints | Duplicate | Pending |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in list(summary["baselines"].values()) + summary["candidates"]:
        report.append(
            f"| {item['method']} | {item['seed']} | {item['r3_success']:.4f} | {item['r4_success']:.4f} | "
            f"{item['condrec']:.4f} | {item['r3_cost']:.4f} | {item['constraint_count']} | "
            f"{item['duplicate_count']} | {item['pending_count']} |"
        )
    texts = {
        "d087_replication_summary.json": json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "d087_replication_rows.json": json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "d087_replication_rows.csv": buffer.getvalue(),
        "d087_replication_report.md": "\n".join(report) + "\n",
        "d087_execution.log": json.dumps({
            "status": summary["decision"],
            "manifest_sha256": summary["manifest_sha256"],
            "candidate_sha256": summary["candidate_sha256"],
            "source_config_sha256": summary["source_config_sha256"],
            "algorithm_sha256": summary["algorithm_sha256"],
            "raw_row_count": summary["raw_row_count"],
            "budget": summary["budget"],
            "train_search_performed": False,
            "test_accessed": False,
        }, indent=2, sort_keys=True) + "\n",
    }
    for filename, text in texts.items():
        _write_once(outdir / filename, text, newline="" if filename.endswith(".csv") else None)
    artifact = {
        "files": {
            filename: _canonical_file_sha(outdir / filename)
            for filename in texts
        },
        "raw_sha256": {
            filename: _file_sha(outdir / filename)
            for filename in texts
        },
        "hash_semantics": "files use canonical UTF-8 content with line endings normalized to LF; raw_sha256 preserves generated bytes",
        "frozen_candidates_sha256": summary["candidate_sha256"],
        "manifest_sha256": summary["manifest_sha256"],
        "test_accessed": False,
    }
    _write_once(outdir / "d087_artifact_manifest.json", json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(OUTDIR))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        from d087_replication_audit import audit_replication
        print(json.dumps(audit_replication(args.outdir), indent=2))
        return
    frozen = freeze_candidates()
    manifest = build_manifest()
    rows, summary = evaluate_replication(manifest, frozen)
    write_outputs(summary, rows, summary["per_family"], args.outdir)
    print(json.dumps({
        "status": summary["decision"],
        "candidate_pass_count": summary["decision_detail"]["candidate_pass_count"],
        "raw_row_count": summary["raw_row_count"],
        "manifest_sha256": summary["manifest_sha256"],
        "candidate_sha256": summary["candidate_sha256"],
        "train_search_performed": False,
        "test_accessed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
