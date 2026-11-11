"""Train-only difficulty-stratified synthetic challenge generator for D-079.

The family catalog reproduces only the eight-family Train selection. This
module never calls build_split_catalog() and never constructs Validation/Test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT_DIR = HERE.parent / "pilot_a_recovery"
if str(PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(PILOT_DIR))

from pilot_a3 import TOOLS
from a3_bridge import scenario_verdict
from a3_verdicts import classify_scenario
from task_semantics import (
    LEGACY_TASKS,
    _greedy_select,
    build_task_family,
    enumerate_primary_compatible_sequences,
)

GENERATOR_VERSION = "d079-train-only-difficulty-strata-v2"
SEED_BASE = 2026111200
REPEATS_PER_CLUSTER = 3
ROLES = ("search", "diagnostic")

STRATA = (
    {
        "id": "D1_CLEAR_PRECOMMIT_TIMEOUT",
        "level": 1,
        "description": "Timeout before execution; no committed-effect ambiguity.",
    },
    {
        "id": "D2_AMBIGUOUS_NONIDEMPOTENT_COMMIT",
        "level": 2,
        "description": "Timeout after execution on a non-idempotent tool.",
    },
    {
        "id": "D3_COMPENSATABLE_PARTIAL_COMMIT",
        "level": 3,
        "description": "Partial commit with an available compensation path.",
    },
    {
        "id": "D4_CROSS_TOOL_THREE_FAULT_INTERACTION",
        "level": 4,
        "description": "Partial commit, rate limit and schema drift across three saga steps.",
    },
    {
        "id": "D5_PERMISSION_AFTER_COMMITTED_PREFIX",
        "level": 4,
        "description": "Permission denial after a committed prefix; contracts determine R3/R4.",
    },
    {
        "id": "D6_UNCOMPENSATABLE_PARTIAL_COMMIT",
        "level": 5,
        "description": "Partial commit on a non-compensatable tool; damage containment.",
    },
)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def stable_seed(*parts):
    return int.from_bytes(
        hashlib.sha256(_canonical(list(parts))).digest()[:8], "big"
    )


def build_train_family_catalog():
    """Reproduce the eight-family Train catalog without other split catalogs."""
    legacy_sequences = [tuple(value) for value in LEGACY_TASKS.values()]
    legacy_specs = [
        build_task_family(seq, family_id=name, legacy=True)
        for name, seq in LEGACY_TASKS.items()
    ]
    candidates = [
        seq for seq in enumerate_primary_compatible_sequences()
        if seq not in legacy_sequences
    ]
    train_add, _unused_pool = _greedy_select(
        candidates, 2, legacy_sequences, legacy_sequences
    )
    families = legacy_specs + [build_task_family(seq) for seq in train_add]
    if len(families) != 8:
        raise RuntimeError("D-079 Train catalog must contain exactly eight families")
    if len({family["family_id"] for family in families}) != 8:
        raise RuntimeError("D-079 Train family IDs are not unique")
    return families


def _base_faults(tools):
    return [
        {
            "fault": "none",
            "delay": 0,
            "retry_after": 0,
            "compensation_available": bool(TOOLS[tool]["compensatable"]),
        }
        for tool in tools
    ]


def _assign(faults, tools, index, fault, rng, compensation_available=None):
    tool = tools[index]
    can_compensate = bool(TOOLS[tool]["compensatable"])
    if compensation_available is None:
        compensation_available = can_compensate
    faults[index] = {
        "fault": fault,
        "delay": rng.randint(1, 4)
        if fault in ("timeout_after", "delayed_visibility") else 0,
        "retry_after": rng.randint(1, 3) if fault == "rate_limit" else 0,
        "compensation_available": bool(compensation_available and can_compensate),
    }


def make_fault_vector(tools, stratum_id, pattern_seed, parameter_seed):
    tools = tuple(tools)
    if len(tools) != 3:
        raise ValueError("D-079 requires three-step saga families")
    if stratum_id not in {item["id"] for item in STRATA}:
        raise ValueError("unknown D-079 stratum: " + str(stratum_id))

    pattern_rng = random.Random(pattern_seed)
    parameter_rng = random.Random(parameter_seed)
    faults = _base_faults(tools)
    non_idempotent = [
        i for i, tool in enumerate(tools) if not TOOLS[tool]["idempotent"]
    ]
    compensatable = [
        i for i, tool in enumerate(tools) if TOOLS[tool]["compensatable"]
    ]
    uncompensatable = [
        i for i, tool in enumerate(tools) if not TOOLS[tool]["compensatable"]
    ]
    if not compensatable:
        raise ValueError("D-079 family must contain at least one compensatable tool")
    first_non_idempotent = non_idempotent[0] if non_idempotent else 0

    if stratum_id == "D1_CLEAR_PRECOMMIT_TIMEOUT":
        index = pattern_rng.choice(non_idempotent or [0])
        _assign(faults, tools, index, "timeout_before", parameter_rng)
    elif stratum_id == "D2_AMBIGUOUS_NONIDEMPOTENT_COMMIT":
        _assign(faults, tools, first_non_idempotent, "timeout_after", parameter_rng)
    elif stratum_id == "D3_COMPENSATABLE_PARTIAL_COMMIT":
        index = pattern_rng.choice(compensatable)
        _assign(
            faults, tools, index, "partial_commit", parameter_rng,
            compensation_available=True,
        )
    elif stratum_id == "D4_CROSS_TOOL_THREE_FAULT_INTERACTION":
        partial_index = pattern_rng.choice(compensatable)
        other = [i for i in range(3) if i != partial_index]
        _assign(
            faults, tools, partial_index, "partial_commit", parameter_rng,
            compensation_available=True,
        )
        _assign(faults, tools, other[0], "rate_limit", parameter_rng)
        _assign(faults, tools, other[1], "schema_drift", parameter_rng)
    elif stratum_id == "D5_PERMISSION_AFTER_COMMITTED_PREFIX":
        possible = [
            index for index in (1, 2)
            if all(TOOLS[tools[j]]["compensatable"] for j in range(index))
        ]
        index = possible[0] if possible else 1
        _assign(faults, tools, index, "permission_denied", parameter_rng)
    elif stratum_id == "D6_UNCOMPENSATABLE_PARTIAL_COMMIT":
        # A family need not contain a contract-level irreversible tool: a
        # compensatable tool with runtime compensation unavailable creates
        # the same R4 damage-containment condition without changing the
        # frozen task-family catalog.
        index = pattern_rng.choice(uncompensatable or compensatable)
        _assign(
            faults, tools, index, "partial_commit", parameter_rng,
            compensation_available=False,
        )
    return faults


def build_challenge_manifest(seed_base=SEED_BASE):
    families = build_train_family_catalog()
    scenarios = []
    clusters = []
    for family in families:
        family_id = family["family_id"]
        tools = tuple(family["tools"])
        for stratum in STRATA:
            stratum_id = stratum["id"]
            pattern_seed = stable_seed(
                seed_base, family_id, stratum_id, "fault-pattern"
            )
            cluster_labels = set()
            for role in ROLES:
                for repeat in range(REPEATS_PER_CLUSTER):
                    parameter_seed = stable_seed(
                        seed_base, family_id, stratum_id, role, repeat
                    )
                    faults = make_fault_vector(
                        tools, stratum_id, pattern_seed, parameter_seed
                    )
                    scenario_id = (
                        "d079|train|" + role + "|" + family_id
                        + "|" + stratum_id + "|r" + str(repeat)
                    )
                    scenario = {
                        "scenario_id": scenario_id,
                        "cluster_id": family_id + "|" + stratum_id,
                        "task_family_id": family_id,
                        "split": "train",
                        "evaluation_role": role,
                        "difficulty_stratum": stratum_id,
                        "difficulty_level": stratum["level"],
                        "composition": stratum_id,
                        "repeat": repeat,
                        "seed": parameter_seed,
                        "tools": list(tools),
                        "faults": faults,
                    }
                    label_info = classify_scenario(scenario)
                    analytic = scenario_verdict(scenario)
                    robust_label = label_info["class"]
                    if robust_label not in {"R1", "R2", "R3", "R4"}:
                        raise RuntimeError(
                            "D-079 scenario has unresolved reachability: " + scenario_id
                        )
                    if robust_label != analytic["class"] and not (
                        robust_label == "R2" and analytic["class"] == "R1"
                    ):
                        raise RuntimeError(
                            "unapproved robust/analytic disagreement: "
                            + scenario_id + " " + robust_label + "/" + analytic["class"]
                        )
                    evidence_sha = _sha256(label_info["evidence"])
                    scenario.update({
                        "label": robust_label,
                        "analytic_label": analytic["class"],
                        "labeler": "observation-based-AND-OR-robust-reachability-v1",
                        "label_evidence_sha256": evidence_sha,
                        "analytic_disagreement_reason": (
                            "legacy analytic label treats ambiguous non-idempotent "
                            "commit as R1; robust reachability requires R2"
                            if robust_label == "R2" and analytic["class"] == "R1"
                            else None
                        ),
                    })
                    scenarios.append(scenario)
                    cluster_labels.add(robust_label)

            if len(cluster_labels) != 1:
                raise RuntimeError(
                    "nested repeats do not share one robust label: "
                    + family_id + "/" + stratum_id
                )
            clusters.append({
                "cluster_id": family_id + "|" + stratum_id,
                "task_family_id": family_id,
                "difficulty_stratum": stratum_id,
                "difficulty_level": stratum["level"],
                "label": next(iter(cluster_labels)),
                "scenario_count": len(ROLES) * REPEATS_PER_CLUSTER,
                "roles": list(ROLES),
            })

    role_counts = Counter(row["evaluation_role"] for row in scenarios)
    label_counts = {
        role: dict(sorted(Counter(
            row["label"] for row in scenarios
            if row["evaluation_role"] == role
        ).items()))
        for role in ROLES
    }
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed_base": seed_base,
        "train_only": True,
        "validation_included": False,
        "test_included": False,
        "test_outcomes_read": False,
        "family_count": len(families),
        "strata": [dict(item) for item in STRATA],
        "roles": list(ROLES),
        "repeats_per_cluster_per_role": REPEATS_PER_CLUSTER,
        "search_scenario_count": role_counts["search"],
        "diagnostic_scenario_count": role_counts["diagnostic"],
        "scenario_count": len(scenarios),
        "cluster_count": len(clusters),
        "families": [
            {
                "family_id": family["family_id"],
                "tools": list(family["tools"]),
                "contract_profile": [
                    {
                        "tool": tool,
                        "idempotent": bool(TOOLS[tool]["idempotent"]),
                        "compensatable": bool(TOOLS[tool]["compensatable"]),
                        "visibility_bound": int(TOOLS[tool]["visibility_bound"]),
                    }
                    for tool in family["tools"]
                ],
            }
            for family in families
        ],
        "label_counts_by_role": label_counts,
        "clusters": clusters,
        "scenarios": scenarios,
    }
    manifest["manifest_sha256"] = _sha256(manifest)
    return manifest


def validate_challenge_manifest(manifest):
    problems = []
    scenarios = manifest.get("scenarios", [])
    clusters = manifest.get("clusters", [])
    if manifest.get("train_only") is not True:
        problems.append("manifest is not Train-only")
    if manifest.get("validation_included") is not False:
        problems.append("Validation must not be included")
    if manifest.get("test_included") is not False or manifest.get("test_outcomes_read") is not False:
        problems.append("Test isolation declaration failed")
    if manifest.get("family_count") != 8 or len(manifest.get("families", [])) != 8:
        problems.append("expected exactly eight Train families")
    if manifest.get("scenario_count") != 288 or len(scenarios) != 288:
        problems.append("expected exactly 288 scenarios")
    if manifest.get("search_scenario_count") != 144:
        problems.append("expected 144 search scenarios")
    if manifest.get("diagnostic_scenario_count") != 144:
        problems.append("expected 144 diagnostic scenarios")
    if manifest.get("cluster_count") != 48 or len(clusters) != 48:
        problems.append("expected exactly 48 family-by-stratum clusters")

    if any(row.get("split") != "train" for row in scenarios):
        problems.append("non-Train scenario found")
    if any(row.get("label") not in {"R1", "R2", "R3", "R4"} for row in scenarios):
        problems.append("UNKNOWN or invalid robust label found")
    if any(row.get("analytic_label") not in {"R1", "R2", "R3", "R4"} for row in scenarios):
        problems.append("UNKNOWN or invalid analytic label found")
    if len({row.get("scenario_id") for row in scenarios}) != 288:
        problems.append("scenario IDs are not unique")
    if {row.get("label") for row in scenarios} != {"R1", "R2", "R3", "R4"}:
        problems.append("challenge must cover all R1-R4 classes")

    family_ids = {family.get("family_id") for family in manifest.get("families", [])}
    if len(family_ids) != 8:
        problems.append("family IDs are not unique")
    if {row.get("task_family_id") for row in scenarios} != family_ids:
        problems.append("scenario family IDs differ from the family catalog")

    cluster_registry = {cluster.get("cluster_id"): cluster for cluster in clusters}
    if len(cluster_registry) != len(clusters):
        problems.append("cluster registry contains duplicate IDs")
    scenario_cluster_ids = {row.get("cluster_id") for row in scenarios}
    if scenario_cluster_ids != set(cluster_registry):
        problems.append("scenario cluster IDs do not match the cluster registry")

    for row in scenarios:
        expected_cluster_id = (
            str(row.get("task_family_id")) + "|" + str(row.get("difficulty_stratum"))
        )
        if row.get("cluster_id") != expected_cluster_id:
            problems.append("scenario cluster ID must identify family × stratum")
        expected_scenario_id = (
            "d079|train|" + str(row.get("evaluation_role")) + "|"
            + str(row.get("task_family_id")) + "|"
            + str(row.get("difficulty_stratum")) + "|r" + str(row.get("repeat"))
        )
        if row.get("scenario_id") != expected_scenario_id:
            problems.append("scenario ID fields are inconsistent")
        if row.get("label") != row.get("analytic_label"):
            allowed_legacy_mismatch = (
                row.get("label") == "R2"
                and row.get("analytic_label") == "R1"
                and bool(row.get("analytic_disagreement_reason"))
            )
            if not allowed_legacy_mismatch:
                problems.append("unapproved robust/analytic label disagreement")
        evidence_sha = row.get("label_evidence_sha256", "")
        if len(evidence_sha) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha):
            problems.append("invalid label evidence SHA-256")

    for cluster_id, cluster in cluster_registry.items():
        rows = [row for row in scenarios if row.get("cluster_id") == cluster_id]
        if len(rows) != 6 or cluster.get("scenario_count") != 6:
            problems.append("cluster must contain six scenarios: " + str(cluster_id))
        role_counts = Counter(row.get("evaluation_role") for row in rows)
        if role_counts != Counter({"search": 3, "diagnostic": 3}):
            problems.append("cluster must contain three scenarios per role: " + str(cluster_id))
        if {row.get("label") for row in rows} != {cluster.get("label")}:
            problems.append("cluster label differs from its scenarios: " + str(cluster_id))
        if {row.get("task_family_id") for row in rows} != {cluster.get("task_family_id")}:
            problems.append("cluster family differs from its scenarios: " + str(cluster_id))
        if {row.get("difficulty_stratum") for row in rows} != {cluster.get("difficulty_stratum")}:
            problems.append("cluster stratum differs from its scenarios: " + str(cluster_id))

    role_counts = Counter(row.get("evaluation_role") for row in scenarios)
    if role_counts != Counter({"search": 144, "diagnostic": 144}):
        problems.append("role counts must be 144 search and 144 diagnostic")
    label_counts = {
        role: dict(sorted(Counter(
            row.get("label") for row in scenarios
            if row.get("evaluation_role") == role
        ).items()))
        for role in ROLES
    }
    if manifest.get("label_counts_by_role") != label_counts:
        problems.append("label_counts_by_role does not match scenario labels")

    stored_hash = manifest.get("manifest_sha256")
    hash_payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if stored_hash != _sha256(hash_payload):
        problems.append("manifest SHA-256 does not match canonical content")
    return {"ok": not problems, "problems": sorted(set(problems))}


def validate_manifest_lock(manifest, lock_path=None):
    """Fail-closed check against the committed D-079 Train-only manifest lock."""
    path = Path(lock_path) if lock_path is not None else Path(__file__).with_name("d079_manifest_lock.json")
    problems = []
    if not path.exists():
        return {"ok": False, "problems": ["committed D-079 manifest lock is missing"]}
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "problems": [f"cannot read D-079 manifest lock: {exc}"]}
    expected = {
        "protocol_id": "D-079",
        "generator_version": manifest.get("generator_version"),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "scenario_count": manifest.get("scenario_count"),
        "cluster_count": manifest.get("cluster_count"),
        "family_count": manifest.get("family_count"),
        "train_only": True,
        "validation_included": False,
        "test_included": False,
        "test_outcomes_read": False,
    }
    for key, value in expected.items():
        if lock.get(key) != value:
            problems.append(f"manifest lock mismatch: {key}")
    if lock.get("role_counts") != {"search": 144, "diagnostic": 144}:
        problems.append("manifest lock role counts mismatch")
    if lock.get("label_counts_by_role") != manifest.get("label_counts_by_role"):
        problems.append("manifest lock label counts mismatch")
    return {"ok": not problems, "problems": sorted(set(problems))}

def write_manifest(manifest, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "d079_challenge_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        key: manifest[key]
        for key in (
            "generator_version", "seed_base", "train_only",
            "family_count", "strata", "search_scenario_count",
            "diagnostic_scenario_count", "scenario_count", "cluster_count",
            "label_counts_by_role", "manifest_sha256",
        )
    }
    (outdir / "d079_challenge_candidate_report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return outdir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    manifest = build_challenge_manifest()
    gate = validate_challenge_manifest(manifest)
    if not gate["ok"]:
        raise RuntimeError("; ".join(gate["problems"]))
    write_manifest(manifest, args.outdir)
    print(json.dumps({
        "status": "D079_CHALLENGE_CANDIDATE_READY_FOR_PREREGISTRATION_LOCK",
        "manifest_sha256": manifest["manifest_sha256"],
        "family_count": manifest["family_count"],
        "search_scenarios": manifest["search_scenario_count"],
        "diagnostic_scenarios": manifest["diagnostic_scenario_count"],
        "label_counts_by_role": manifest["label_counts_by_role"],
        "test_outcomes_read": False,
    }, indent=2))


if __name__ == "__main__":
    main()
