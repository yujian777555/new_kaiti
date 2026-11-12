"""D-087 independent Validation challenge generation and content lock."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from dependency_recovery import classify_scenario
from d079_challenge_generator import stable_seed

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "results" / "d087_replication" / "replication_manifest.json"
LOCK_PATH = HERE / "d087_replication_lock.json"
GENERATOR_VERSION = "d087-independent-validation-v1"
SEED_BASE = 2026112200
REPEATS = 5
STRATA = (
    "D1_RECOVERABLE_TIMEOUT",
    "D2_PARTIAL_THEN_REDO",
    "D3_DEPENDENT_ABORT",
    "D4_BLOCKED_COMPENSATION",
)
EXPECTED_LABELS = dict(zip(STRATA, ("R1", "R2", "R3", "R4")))
FAMILY_SPECS = {
    "rv01_PARALLEL_ALT": {
        "requires": {"A": ["C"], "B": ["A"], "C": []},
        "primary_cost": 4, "alternate_cost": 1, "block": "C",
        "primary_delay": [0, 0, 0, 1, 2],
        "alternate_delay": [0, 0, 0, 0, 0],
        "alternate_patterns": [[True]] * 5,
    },
    "rv02_CROSS_DELAY": {
        "requires": {"A": ["B"], "B": ["C"], "C": []},
        "primary_cost": 3, "alternate_cost": 1, "block": "B",
        "primary_delay": [0, 0, 0, 0, 0],
        "alternate_delay": [0, 0, 0, 1, 2],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, False, True]],
    },
    "rv03_MULTI_ROUTE": {
        "requires": {"A": ["C"], "B": ["C"], "C": ["A"]},
        "primary_cost": 3, "alternate_cost": 1, "block": "C",
        "primary_delay": [0, 0, 0, 0, 1],
        "alternate_delay": [0, 0, 0, 1, 2],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, False, True]],
    },
    "rv04_REVERSE_RECOVERY": {
        "requires": {"A": [], "B": ["A"], "C": ["B"]},
        "primary_cost": 4, "alternate_cost": 1, "block": "B",
        "primary_delay": [0, 0, 0, 0, 0],
        "alternate_delay": [0, 0, 0, 1, 2],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, False, True]],
    },
}
ALLOCATION = {"validation": list(FAMILY_SPECS)}
BUDGET = {
    "frozen_candidate_episodes": 400,
    "fixed_baseline_episodes": 640,
    "total_episode_cap": 1040,
    "decision_cap_per_episode": 24,
    "train_search": False,
    "test_access": False,
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _source_sha256():
    text = Path(__file__).read_text(encoding="utf-8")
    return hashlib.sha256("\n".join(text.splitlines()).encode("utf-8")).hexdigest()


def _route_for_tool(family, tool_id, alternate, repeat):
    spec = FAMILY_SPECS[family]
    primary_patterns = [[True], [False, True], [False, False, True], [True], [False, True]]
    outcomes = spec["alternate_patterns"][repeat] if alternate else primary_patterns[repeat]
    delay = spec["alternate_delay"][repeat] if alternate else spec["primary_delay"][repeat]
    return {
        "name": "alternate" if alternate else "primary",
        "outcomes": list(outcomes),
        "cost": spec["alternate_cost"] if alternate else spec["primary_cost"],
        "reliability_hint": "LOW" if alternate else "HIGH",
        "requires": [] if alternate else list(spec["requires"].get(tool_id, [])),
        "receipt": "delayed" if delay else "immediate",
        "receipt_delay": delay,
        "idempotent": delay == 0,
        "visibility_bound": 3,
    }


def make_scenario(family, stratum, repeat, seed_base=SEED_BASE):
    if family not in FAMILY_SPECS or stratum not in STRATA or repeat not in range(REPEATS):
        raise ValueError("invalid D-087 family, stratum, or repeat")
    spec = FAMILY_SPECS[family]
    terminal = {
        "D1_RECOVERABLE_TIMEOUT": "timeout_before",
        "D2_PARTIAL_THEN_REDO": "partial_recover",
    }.get(stratum, "permission")
    tools = []
    for tool_id in ("A", "B", "C"):
        tools.append({
            "id": tool_id,
            "state": "COMMITTED",
            "compensation_available": not (
                stratum == "D4_BLOCKED_COMPENSATION" and tool_id == spec["block"]
            ),
            "routes": [
                _route_for_tool(family, tool_id, False, repeat),
                _route_for_tool(family, tool_id, True, repeat),
            ],
        })
    tools.append({
        "id": "D",
        "state": "PARTIAL" if stratum == "D2_PARTIAL_THEN_REDO" else "NOT_COMMITTED",
        "compensation_available": True,
        "routes": [
            _route_for_tool(family, "D", False, 0),
            _route_for_tool(family, "D", True, 0),
        ],
    })
    label, minimum = classify_scenario({"terminal_fault": terminal, "tools": tools})
    if label != EXPECTED_LABELS[stratum]:
        raise RuntimeError("D-087 label mismatch: " + family + "/" + stratum)
    return {
        "scenario_id": f"d086r|validation|{family}|{stratum}|r{repeat}",
        "cluster_id": family + "|" + stratum,
        "task_family_id": family,
        "split": "validation",
        "evaluation_role": "frozen_replication",
        "difficulty_stratum": stratum,
        "composition": family,
        "repeat": repeat,
        "seed": stable_seed(seed_base, family, stratum, repeat),
        "terminal_fault": terminal,
        "current_tool": "D",
        "tools": tools,
        "label": label,
        "min_reachable_harm": minimum,
        "labeler": "d086-contract-and-schedule-reachability-v1",
        "label_evidence_sha256": _sha256({"label": label, "minimum": minimum, "tools": tools}),
    }


def build_manifest(seed_base=SEED_BASE):
    scenarios = [
        make_scenario(family, stratum, repeat, seed_base=seed_base)
        for family in FAMILY_SPECS
        for stratum in STRATA
        for repeat in range(REPEATS)
    ]
    manifest = {
        "protocol_id": "D-087-REPLICATION",
        "generator_version": GENERATOR_VERSION,
        "seed_base": seed_base,
        "validation_only": True,
        "train_included": False,
        "test_included": False,
        "test_outcomes_read": False,
        "repeats_per_family_stratum": REPEATS,
        "strata": list(STRATA),
        "expected_labels": dict(EXPECTED_LABELS),
        "allocation": {key: list(value) for key, value in ALLOCATION.items()},
        "family_count": len(FAMILY_SPECS),
        "family_counts": {"validation": len(FAMILY_SPECS)},
        "scenario_counts": dict(sorted(Counter(row["split"] for row in scenarios).items())),
        "scenario_count": len(scenarios),
        "families": [{"family_id": family, **FAMILY_SPECS[family]} for family in FAMILY_SPECS],
        "label_counts": dict(sorted(Counter(row["label"] for row in scenarios).items())),
        "budget": dict(BUDGET),
        "scenarios": scenarios,
    }
    manifest["manifest_sha256"] = _sha256(manifest)
    return manifest


def validate_manifest(manifest):
    problems = []
    scenarios = manifest.get("scenarios", [])
    if manifest.get("validation_only") is not True or manifest.get("train_included") is not False:
        problems.append("replication must be Validation-only")
    if manifest.get("test_included") is not False or manifest.get("test_outcomes_read") is not False:
        problems.append("Test isolation declaration failed")
    if manifest.get("scenario_count") != 80 or len(scenarios) != 80:
        problems.append("expected 80 scenarios")
    if manifest.get("scenario_counts") != {"validation": 80}:
        problems.append("unexpected split counts")
    if manifest.get("family_count") != 4 or manifest.get("allocation") != ALLOCATION:
        problems.append("family allocation changed")
    if len({row.get("scenario_id") for row in scenarios}) != 80:
        problems.append("scenario IDs are not unique")
    for row in scenarios:
        if row.get("split") != "validation" or row.get("evaluation_role") != "frozen_replication":
            problems.append("invalid replication split or role")
            continue
        family = row.get("task_family_id")
        stratum = row.get("difficulty_stratum")
        repeat = row.get("repeat")
        if family in FAMILY_SPECS and stratum in STRATA and repeat in range(REPEATS):
            expected = make_scenario(family, stratum, repeat, manifest.get("seed_base", SEED_BASE))
            if row != expected:
                problems.append("scenario content mismatch: " + expected["scenario_id"])
        else:
            problems.append("unknown scenario metadata")
    if manifest.get("budget") != BUDGET:
        problems.append("replication budget changed")
    expected_hash = _sha256({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    if manifest.get("manifest_sha256") != expected_hash:
        problems.append("manifest canonical SHA-256 mismatch")
    return {"ok": not problems, "problems": sorted(set(problems))}


def make_lock(manifest):
    return {
        "lock_schema_version": 1,
        "protocol_id": "D-087-REPLICATION",
        "generator_version": manifest["generator_version"],
        "generator_source_sha256": _source_sha256(),
        "manifest_sha256": manifest["manifest_sha256"],
        "seed_base": manifest["seed_base"],
        "scenario_count": manifest["scenario_count"],
        "scenario_counts": manifest["scenario_counts"],
        "family_count": manifest["family_count"],
        "allocation": manifest["allocation"],
        "strata": manifest["strata"],
        "validation_only": True,
        "train_included": False,
        "test_included": False,
        "test_outcomes_read": False,
        "budget": manifest["budget"],
        "lock_status": "FROZEN_REPLICATION_VALIDATION_ONLY",
    }


def validate_lock(manifest, lock_path=LOCK_PATH):
    path = Path(lock_path)
    if not path.is_file():
        return {"ok": False, "problems": ["D-087 replication lock missing"]}
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "problems": ["cannot read D-087 lock: " + str(exc)]}
    expected = make_lock(manifest)
    problems = ["lock mismatch: " + key for key in expected if lock.get(key) != expected[key]]
    return {"ok": not problems, "problems": problems}


def _write_once(path, value):
    path = Path(path)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FileExistsError("refusing to overwrite different D-087 artifact: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(MANIFEST_PATH.parent))
    parser.add_argument("--lock-path", default=str(LOCK_PATH))
    args = parser.parse_args()
    manifest = build_manifest()
    gate = validate_manifest(manifest)
    if not gate["ok"]:
        raise RuntimeError("; ".join(gate["problems"]))
    _write_once(Path(args.outdir) / MANIFEST_PATH.name, manifest)
    _write_once(args.lock_path, make_lock(manifest))
    lock_gate = validate_lock(manifest, args.lock_path)
    if not lock_gate["ok"]:
        raise RuntimeError("; ".join(lock_gate["problems"]))
    print(json.dumps({
        "status": "D087_INDEPENDENT_VALIDATION_LOCKED_NOT_EXECUTED",
        "manifest_sha256": manifest["manifest_sha256"],
        "scenario_count": manifest["scenario_count"],
        "label_counts": manifest["label_counts"],
        "budget": manifest["budget"],
        "test_accessed": False,
        "optimizer_runs": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
