"""Deterministic D-064-C formal scenario generator.

Generates an 8/4/40 task-family split, nine predeclared fault-composition
families, three nested scenario seeds per task-family x composition cluster,
and evaluator-side robust R1-R4/UNKNOWN labels. The locked test payload is
hashed and summarized but never serialized into the candidate manifest.
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

from pilot_a3 import (  # noqa: E402
    TOOLS,
    TRAIN_COMPOSITIONS,
    VALIDATION_COMPOSITIONS,
    HELDOUT_COMPOSITIONS,
)
from a3_bridge import scenario_verdict  # noqa: E402
from a3_verdicts import classify_scenario  # noqa: E402
from task_semantics import (  # noqa: E402
    SEMANTIC_CONTRACT_VERSION,
    audit_split_catalog,
    build_split_catalog,
    profile_id,
)

GENERATOR_VERSION = "d064c-formal-generator-v1"
SEED_BASE = 2026111100
REPEATS_PER_CLUSTER = 3
LABELER_HORIZON = 24
LABELER_MAX_NODES = 500000
FORMAL_COMPOSITIONS = (
    tuple(TRAIN_COMPOSITIONS)
    + tuple(VALIDATION_COMPOSITIONS)
    + tuple(HELDOUT_COMPOSITIONS)
)
FORMAL_COMPOSITIONS = tuple(
    "permission_after_compensatable_prefix" if c == "delay_rate_permission" else c
    for c in FORMAL_COMPOSITIONS
)
ALLOWED_CLASSES_BY_COMPOSITION = {
    "single_timeout": {"R1", "R2"},
    "timeout_then_rate_limit": {"R1", "R2"},
    "partial_then_delay": {"R2"},
    "schema_then_timeout": {"R1"},
    "independent_mixed_val": {"R1", "R2"},
    "partial_then_timeout_val": {"R2"},
    "partial_comp_failure": {"R4"},
    "permission_after_compensatable_prefix": {"R3"},
    "triple_mixed": {"R1", "R2"},
}
PRIMARY_CLASSES = {"R1", "R2"}
UNKNOWN_LIMIT = 0.05

# R4 freezes five of the seven R1/R2-eligible compositions by mechanism
# coverage, before any confirmatory outcomes are observed.
PRIMARY_ANALYSIS_COMPOSITIONS = (
    "single_timeout",
    "timeout_then_rate_limit",
    "partial_then_delay",
    "independent_mixed_val",
    "triple_mixed",
)
SENSITIVITY_ONLY_PRIMARY_COMPOSITIONS = (
    "schema_then_timeout",
    "partial_then_timeout_val",
)
if len(PRIMARY_ANALYSIS_COMPOSITIONS) != 5 or len(set(PRIMARY_ANALYSIS_COMPOSITIONS)) != 5:
    raise RuntimeError("R4 primary composition roster must contain five unique compositions")
if any(c not in ALLOWED_CLASSES_BY_COMPOSITION
       or not (ALLOWED_CLASSES_BY_COMPOSITION[c] & PRIMARY_CLASSES)
       for c in PRIMARY_ANALYSIS_COMPOSITIONS):
    raise RuntimeError("R4 primary composition roster contains a non-primary composition")
if set(PRIMARY_ANALYSIS_COMPOSITIONS) & set(SENSITIVITY_ONLY_PRIMARY_COMPOSITIONS):
    raise RuntimeError("R4 primary and sensitivity-only composition rosters overlap")
if set(PRIMARY_ANALYSIS_COMPOSITIONS) | set(SENSITIVITY_ONLY_PRIMARY_COMPOSITIONS) != {
    c for c, labels in ALLOWED_CLASSES_BY_COMPOSITION.items() if labels & PRIMARY_CLASSES
}:
    raise RuntimeError("R4 must partition all seven primary-eligible compositions")

# D-064-B candidate design freeze. These are planning assumptions, not an
# empirical claim about the true ICC or a claim that a formal experiment ran.
POWER_DESIGN = {
    "primary_estimand": "family-equal-weight mean of task-family R1/R2 eligible composition-cluster CondRecSucc differences (AB minus canonical NSGA-II)",
    "mde_absolute": 0.10,
    "mde_status": "PROPOSED_MDE_PENDING_ADVISOR_APPROVAL",
    "mde_rationale": "A 10-percentage-point absolute CondRecSucc gain is the minimum practically worthwhile improvement to justify the additional complexity and rollout cost of the evolutionary recovery controller; this threshold is not derived from the observed diagnostic effect and requires advisor/user acceptance.",
    "alpha_two_sided": 0.05,
    "target_power": 0.80,
    "design_icc_sensitivity_ceiling": 0.20,
    "family_attrition": 0.15,
    "cluster_attrition": 0.15,
    "test_families_design": 40,
    "eligible_compositions_per_family": 7,
    "test_design_clusters": 360,
    "test_primary_eligible_clusters": 280,
    "primary_analysis_compositions_per_family": 5,
    "primary_analysis_composition_ids": list(PRIMARY_ANALYSIS_COMPOSITIONS),
    "primary_analysis_selection_rule": (
        "outcome-blind mechanism-coverage roster frozen in R4: simple timeout, "
        "ordered timeout/rate-limit, partial-effect/delayed-visibility, "
        "independent mixed faults, and triple mixed faults; no outcome or Test "
        "label is used for selection"
    ),
    "sensitivity_only_primary_eligible_composition_ids": list(SENSITIVITY_ONLY_PRIMARY_COMPOSITIONS),
    "test_primary_analysis_clusters": 200,
    "effective_families_after_attrition": 34,
    "effective_eligible_compositions_per_family_after_attrition": 5,
    "effective_primary_clusters_after_attrition": 170,
    "expected_power_from_D064B_MC": 0.839,
    "r4_power_recalibration": {
        "input_sha256": "2946bcf97883c74c407a204d5ce50bb325e4597a47be4831ccaff4ef8a4f414c",
        "code_commit": "3258399bbc238b83cba5e0fb0fcde69b76129ea0",
        "seed": 20261114,
        "mc_reps_per_cell": 10000,
        "families": [33, 34, 40],
        "compositions_per_family": 5,
        "icc_grid": [0.0, 0.05, 0.10, 0.20],
        "mde": 0.10,
        "f34_icc020_power": 0.8427,
        "f34_icc020_power_ci95": [0.8354326572499048, 0.8497041502668335],
        "f34_icc020_type_i": 0.0503,
        "f34_icc020_type_i_ci95": [0.04618626511967923, 0.05475910301490729],
        "f40_icc020_power": 0.9028,
        "f40_icc020_power_ci95": [0.8968383804179927, 0.9084522704945903],
        "f40_icc020_type_i": 0.0547,
        "f40_icc020_type_i_ci95": [0.05041173530937794, 0.05933025363954662],
        "source_note": "Variance/residual calibration uses historical six-family, 42-cluster diagnostic data; this is a simulation assumption, not an empirical ICC estimate."
    },
    "expected_power_ci95": [0.832, 0.846],
    "expected_power_provenance": ("recomputed 2026-11-09 with power_hierarchical.mc_power_at "
                                 "on the CondRecSucc cluster-diff distribution from "
                                 "diagnostic3_results.json (SHA-256 b9498195...): "
                                 "MDE=0.10, ICC=0.20 ceiling, n_families=34 effective "
                                 "(40 design, 15% family attrition), m=5 effective "
                                 "(7 eligible, 15% cluster attrition), 10,000 MC, "
                                 "seed 20261113; see power_final_design_check.json. "
                                 "Worst-case ICC power 0.839 >= 0.80 target; "
                                 "the earlier unverified 0.85 figure is superseded."),
    "power_source": "68_D064B_HIERARCHICAL_POWER_REPORT.md; ICC=0.20, MDE=0.10, m=7, 40 design families, dual 15% family/cluster attrition",
    "reachability_horizon": LABELER_HORIZON,
    "reachability_max_nodes": LABELER_MAX_NODES,
    "reachability_horizon_rationale": "At most 3 steps x (CALL + 4 WAIT + VERIFY) = 18 actions are required for three maximally delayed commits; horizon 24 provides a fixed buffer.",
    "primary_test": "two-sided family-level Student-t test on task-family means; df=39 before attrition",
    "sign_flip": "secondary sensitivity only",
    "family_block_bootstrap": "descriptive interval only; not an alpha test (D-064-B Type-I calibration was anti-conservative)",
}

FAULT_COMPOSITION_NOTES = {
    "single_timeout": "one timeout_before/timeout_after/delayed_visibility fault at a deterministic step",
    "timeout_then_rate_limit": "timeout_after at step 0 followed by rate_limit at step 1",
    "partial_then_delay": "partial commit at the first contract-compensatable step with guaranteed compensation, plus delayed visibility at another step",
    "schema_then_timeout": "schema drift at step 0 followed by timeout_before at step 1",
    "independent_mixed_val": "independent per-step recoverable faults only; excludes permission_denied and partial_commit",
    "partial_then_timeout_val": "partial commit at the first contract-compensatable step with guaranteed compensation, plus timeout_after at another step",
    "partial_comp_failure": "partial commit at the first contract-compensatable step with compensation outcome hidden/uncertain, plus timeout_after",
    "permission_after_compensatable_prefix": (
        "permission_denied at step 1 after a clean step-0 commit; the committed "
        "prefix is compensatable by task-family design (primary-compatible "
        "requirement). Historical alias: legacy A-3 'delay_rate_permission' "
        "triple-fault composition was renamed and simplified to isolate the "
        "R3 (safe-escalation) mechanism."
    ),
    "triple_mixed": "timeout_after, rate_limit, and schema_drift across the three steps",
}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_seed(*parts):
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _other_step(index):
    return index + 1 if index < 2 else index - 1


def make_fault_vector(tools, composition, pattern_seed, parameter_seed):
    """Generate a fixed fault pattern with repeat-specific numeric parameters."""
    tools = tuple(tools)
    if len(tools) != 3:
        raise ValueError("formal scenarios require exactly three tools")
    if composition not in FORMAL_COMPOSITIONS:
        raise ValueError("unknown formal composition: " + str(composition))

    pattern_rng = random.Random(pattern_seed)
    parameter_rng = random.Random(parameter_seed)
    faults = [
        {
            "fault": "none",
            "delay": 0,
            "retry_after": 0,
            "compensation_available": bool(TOOLS[t]["compensatable"]),
        }
        for t in tools
    ]

    def assign(index, fault, compensation_available=None):
        tool = tools[index]
        contract_comp = bool(TOOLS[tool]["compensatable"])
        if compensation_available is None:
            compensation_available = contract_comp
        faults[index] = {
            "fault": fault,
            "delay": parameter_rng.randint(1, 4)
            if fault in ("timeout_after", "delayed_visibility") else 0,
            "retry_after": parameter_rng.randint(1, 3) if fault == "rate_limit" else 0,
            "compensation_available": bool(compensation_available and contract_comp),
        }

    first_comp = next(
        (i for i, tool in enumerate(tools) if TOOLS[tool]["compensatable"]),
        None,
    )
    if first_comp is None:
        raise ValueError("formal task family has no compensatable step")

    if composition == "single_timeout":
        assign(
            pattern_rng.randrange(3),
            pattern_rng.choice(("timeout_before", "timeout_after", "delayed_visibility")),
        )
    elif composition == "timeout_then_rate_limit":
        assign(0, "timeout_after")
        assign(1, "rate_limit")
    elif composition == "partial_then_delay":
        assign(first_comp, "partial_commit", True)
        assign(_other_step(first_comp), "delayed_visibility")
    elif composition == "schema_then_timeout":
        assign(0, "schema_drift")
        assign(1, "timeout_before")
    elif composition == "independent_mixed_val":
        choices = (
            "none", "timeout_before", "timeout_after",
            "delayed_visibility", "rate_limit", "schema_drift",
        )
        for i in range(3):
            assign(i, pattern_rng.choice(choices))
    elif composition == "partial_then_timeout_val":
        assign(first_comp, "partial_commit", True)
        assign(_other_step(first_comp), "timeout_after")
    elif composition == "partial_comp_failure":
        assign(first_comp, "partial_commit", False)
        assign(_other_step(first_comp), "timeout_after")
    elif composition == "permission_after_compensatable_prefix":
        assign(1, "permission_denied")
    elif composition == "triple_mixed":
        assign(0, "timeout_after")
        assign(1, "rate_limit")
        assign(2, "schema_drift")
    return faults


def _explain_analytic_disagreement(scenario, robust_label, analytic_label):
    """Whitelist only the known legacy heuristic gap, never arbitrary mismatches."""
    if robust_label == "R2" and analytic_label == "R1":
        for tool, fault in zip(scenario["tools"], scenario["faults"]):
            if fault["fault"] in ("timeout_after", "delayed_visibility") and not TOOLS[tool]["idempotent"]:
                return (
                    "legacy scenario_verdict labels ambiguous commit/visibility faults as R1; "
                    "the robust AND-OR checker requires compensation for this non-idempotent "
                    "tool state and therefore labels it R2"
                )
    return None


def _build_cluster(family, split, composition, seed_base=SEED_BASE):
    family_id = family["family_id"]
    tools = tuple(family["tools"])
    pattern_seed = stable_seed(seed_base, split, family_id, composition, "pattern")
    scenarios = []
    for repeat in range(REPEATS_PER_CLUSTER):
        seed = stable_seed(seed_base, split, family_id, composition, repeat)
        faults = make_fault_vector(tools, composition, pattern_seed, seed)
        scenarios.append({
            "scenario_id": f"{split}|{family_id}|{composition}|r{repeat}",
            "cluster_id": f"{family_id}|{composition}",
            "task_family_id": family_id,
            "split": split,
            "composition": composition,
            "repeat": repeat,
            "seed": seed,
            "tools": list(tools),
            "faults": faults,
        })

    label_info = classify_scenario(scenarios[0], horizon=LABELER_HORIZON, max_nodes=LABELER_MAX_NODES)
    analytic_labels = [scenario_verdict(s)["class"] for s in scenarios]
    analytic_label = analytic_labels[0]
    disagreement_reason = _explain_analytic_disagreement(
        scenarios[0], label_info["class"], analytic_label
    )
    evidence_hash = sha256_json(label_info["evidence"])
    for scenario in scenarios:
        scenario["label"] = label_info["class"]
        scenario["analytic_label"] = analytic_label
        scenario["labeler"] = "observation-based-AND-OR-robust-reachability-v1"
        scenario["label_evidence_sha256"] = evidence_hash
        scenario["analytic_disagreement_reason"] = disagreement_reason

    cluster = {
        "cluster_id": f"{family_id}|{composition}",
        "task_family_id": family_id,
        "composition": composition,
        "label": label_info["class"],
        "analytic_label": analytic_label,
        "label_agreement": bool(label_info["agreement"]),
        "analytic_disagreement_reason": disagreement_reason,
        "label_evidence": label_info["evidence"],
        "label_evidence_sha256": evidence_hash,
        "primary_eligible": label_info["class"] in PRIMARY_CLASSES,
        "scenario_ids": [s["scenario_id"] for s in scenarios],
        "n_repeats": len(scenarios),
    }
    problems = []
    if label_info["class"] == "UNKNOWN":
        problems.append(
            f"{cluster['cluster_id']}: reachability evidence {label_info['evidence']}"
        )
    if len(set(analytic_labels)) != 1:
        problems.append(f"{cluster['cluster_id']}: analytic labels vary across repeats")
    if not label_info["agreement"] and disagreement_reason is None:
        problems.append(
            f"{cluster['cluster_id']}: unexplained robust/analytic disagreement "
            f"({label_info['class']} vs {analytic_label})"
        )
    allowed = ALLOWED_CLASSES_BY_COMPOSITION[composition]
    if label_info["class"] not in allowed:
        problems.append(
            f"{cluster['cluster_id']}: label {label_info['class']} outside allowed set {sorted(allowed)}"
        )
    return cluster, scenarios, problems

def _split_summary(families, clusters, scenarios):
    scenario_counts = Counter(s["label"] for s in scenarios)
    cluster_counts = Counter(c["label"] for c in clusters)
    eligible_by_family = Counter(
        c["task_family_id"] for c in clusters if c["primary_eligible"]
    )
    eligible_values = sorted(eligible_by_family.values())
    unknown_n = scenario_counts.get("UNKNOWN", 0)
    return {
        "n_families": len(families),
        "n_design_clusters": len(clusters),
        "n_scenarios": len(scenarios),
        "n_primary_eligible_clusters": sum(
            1 for c in clusters if c["primary_eligible"]
        ),
        "n_zero_primary_denominator_clusters": sum(
            1 for c in clusters if c["label"] not in PRIMARY_CLASSES
        ),
        "scenario_label_counts": dict(sorted(scenario_counts.items())),
        "cluster_label_counts": dict(sorted(cluster_counts.items())),
        "eligible_clusters_per_family_min": min(eligible_values, default=0),
        "eligible_clusters_per_family_max": max(eligible_values, default=0),
        "unknown_scenario_rate": unknown_n / max(1, len(scenarios)),
        "profile_counts": dict(sorted(Counter(profile_id(f["tools"]) for f in families).items())),
    }


def build_candidate_manifest(seed_base=SEED_BASE):
    catalog = build_split_catalog()
    catalog_audit = audit_split_catalog(catalog)
    problems = list(catalog_audit["problems"])
    split_internal = {}
    split_summaries = {}

    for split in ("train", "validation", "test"):
        families = catalog[split]
        clusters = []
        scenarios = []
        for family in families:
            for composition in FORMAL_COMPOSITIONS:
                cluster, rows, findings = _build_cluster(
                    family, split, composition, seed_base=seed_base
                )
                clusters.append(cluster)
                scenarios.extend(rows)
                problems.extend(findings)

        summary = _split_summary(families, clusters, scenarios)
        split_summaries[split] = summary
        split_internal[split] = {
            "families": families,
            "clusters": clusters,
            "scenarios": scenarios,
        }

        if summary["unknown_scenario_rate"] > UNKNOWN_LIMIT:
            problems.append(
                f"{split}: UNKNOWN rate {summary['unknown_scenario_rate']:.4f} exceeds {UNKNOWN_LIMIT:.2%}"
            )
        if summary["eligible_clusters_per_family_min"] != 7 or summary["eligible_clusters_per_family_max"] != 7:
            problems.append(f"{split}: each family must have exactly 7 R1/R2 eligible composition clusters")

        expected_families = {"train": 8, "validation": 4, "test": 40}[split]
        if summary["n_families"] != expected_families:
            problems.append(f"{split}: incorrect family count")
        if summary["n_design_clusters"] != expected_families * 9:
            problems.append(f"{split}: incorrect design cluster count")
        if summary["n_primary_eligible_clusters"] != expected_families * 7:
            problems.append(f"{split}: incorrect primary eligible cluster count")

    all_scenarios = [
        s for split_data in split_internal.values() for s in split_data["scenarios"]
    ]
    scenario_ids = [s["scenario_id"] for s in all_scenarios]
    seeds = [s["seed"] for s in all_scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        problems.append("duplicate scenario_id")
    if len(seeds) != len(set(seeds)):
        problems.append("duplicate scenario seed")

    test_families = split_internal["test"]["families"]
    test_clusters = split_internal["test"]["clusters"]
    test_scenarios = split_internal["test"]["scenarios"]
    hashes = {
        "train_family_sha256": sha256_json(split_internal["train"]["families"]),
        "validation_family_sha256": sha256_json(split_internal["validation"]["families"]),
        "test_family_sha256": sha256_json(test_families),
        "train_scenario_sha256": sha256_json(split_internal["train"]),
        "validation_scenario_sha256": sha256_json(split_internal["validation"]),
        "test_scenario_sha256": sha256_json({
            "clusters": test_clusters,
            "scenarios": test_scenarios,
        }),
    }

    manifest = {
        "schema_version": "d064c-formal-scenario-manifest-v1",
        "generator_version": GENERATOR_VERSION,
        "status": "CANDIDATE_NOT_FROZEN_PENDING_INDEPENDENT_REVIEW_AND_USER_APPROVAL",
        "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
        "semantic_scope": (
            "Abstract synthetic ordered saga: each step consumes a typed WorkflowContext "
            "and prior committed EffectReceipt. This is not a claim of real-world business "
            "process validity or unseen-tool generalization."
        ),
        "seed_base": int(seed_base),
        "repeats_per_family_composition_cluster": REPEATS_PER_CLUSTER,
        "fault_compositions": [
            {"name": c, "definition": FAULT_COMPOSITION_NOTES[c]}
            for c in FORMAL_COMPOSITIONS
        ],
        "power_design_candidate": POWER_DESIGN,
        "splits": {
            "train": {
                "summary": split_summaries["train"],
                "families": split_internal["train"]["families"],
                "clusters": split_internal["train"]["clusters"],
                "scenarios": split_internal["train"]["scenarios"],
            },
            "validation": {
                "summary": split_summaries["validation"],
                "families": split_internal["validation"]["families"],
                "clusters": split_internal["validation"]["clusters"],
                "scenarios": split_internal["validation"]["scenarios"],
            },
            "test_locked": {
                "summary": split_summaries["test"],
                "family_sha256": hashes["test_family_sha256"],
                "scenario_sha256": hashes["test_scenario_sha256"],
                "payload_disclosed": False,
            },
        },
        "hashes": hashes,
        "gate": {
            "passed": not problems,
            "problems": problems,
            "unknown_rate_limit": UNKNOWN_LIMIT,
            "allowed_class_by_composition": {k: sorted(v) for k, v in ALLOWED_CLASSES_BY_COMPOSITION.items()},
        },
    }
    manifest["manifest_sha256"] = sha256_json(manifest)

    # Public audit output contains development scenarios only. Test payloads
    # remain local to this builder for hashing/gate checks and are never returned.
    development_scenarios = (
        split_internal["train"]["scenarios"]
        + split_internal["validation"]["scenarios"]
    )
    audit = {
        "catalog_audit": catalog_audit,
        "split_summaries": split_summaries,
        "development_scenarios": development_scenarios,
        "problems": problems,
    }
    return manifest, audit


def render_report(manifest):
    lines = [
        "# D-064-C — Synthetic task semantics and formal scenario generator",
        "",
        "- Status: " + str(manifest["status"]),
        "- Generator: " + str(manifest["generator_version"]),
        "- Semantic contract: " + str(manifest["semantic_contract_version"]),
        "- Manifest SHA-256: " + str(manifest["manifest_sha256"]),
        "",
        "## Split and primary denominator",
        "",
        "| Split | Families | Design clusters | Scenarios | R1/R2 eligible clusters | Zero-denominator clusters |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, label in (("train", "Train"), ("validation", "Validation"), ("test_locked", "Test (locked)")):
        s = manifest["splits"][split]["summary"]
        lines.append(
            f"| {label} | {s['n_families']} | {s['n_design_clusters']} | "
            f"{s['n_scenarios']} | {s['n_primary_eligible_clusters']} | "
            f"{s['n_zero_primary_denominator_clusters']} |"
        )
    test = manifest["splits"]["test_locked"]
    lines.extend([
        "",
        "## Unique power/sample-size candidate",
        "",
        "- MDE: " + str(POWER_DESIGN["mde_absolute"]) + " absolute CondRecSucc",
        "- Design ICC sensitivity ceiling: " + str(POWER_DESIGN["design_icc_sensitivity_ceiling"]),
        "- Target power: " + str(POWER_DESIGN["target_power"]) + ", two-sided alpha " + str(POWER_DESIGN["alpha_two_sided"]),
        "- Test families: " + str(POWER_DESIGN["test_families_design"]),
        "- Eligible compositions/family: " + str(POWER_DESIGN["eligible_compositions_per_family"]),
        "- Test primary eligible clusters: " + str(test["summary"]["n_primary_eligible_clusters"]),
        "- Dual 15% attrition: 34 effective families x 5 eligible compositions = 170 effective primary clusters",
        "- D-064-B simulated power at ICC=.20: " + str(POWER_DESIGN["expected_power_from_D064B_MC"]),
        "",
        "MDE rationale is an explicit practical-value judgment, not an estimate from the observed diagnostic effect. It requires advisor/user acceptance before the preregistration is approved.",
        "",
        "## Locked test hashes",
        "",
        "- Task-family SHA-256: " + str(test["family_sha256"]),
        "- Full scenario/label SHA-256: " + str(test["scenario_sha256"]),
        "- Test family IDs, scenario rows, and labels are not serialized in this candidate report.",
        "",
        "## Label and semantic gates",
        "",
        "- Allowed robust class by composition: " + str({k: sorted(v) for k, v in ALLOWED_CLASSES_BY_COMPOSITION.items()}),
        "- UNKNOWN limit: " + str(UNKNOWN_LIMIT),
        "- Gate: " + ("PASS" if manifest["gate"]["passed"] else "FAIL"),
        "- Problems: " + str(manifest["gate"]["problems"]),
        "",
        "## Scope limits",
        "",
        "- Task families are abstract typed three-step synthetic sagas, not manually validated real-world business processes.",
        "- All splits use the same ten-tool pool, the same nine fault-composition vocabulary, and the same generator; claims are limited to new ordered tool sequences under this fixed tool pool.",
        "- No unseen-tool or unseen-fault-type OOD claim is permitted.",
        "- The test payload is represented by hashes and aggregate counts only; no optimizer was run and no test performance was inspected.",
        "- This manifest is a candidate artifact, not a user-approved preregistration and not authorization to run formal A-3b.",
        "",
    ])
    return "\n".join(lines)


def write_candidate_manifest(outdir, seed_base=SEED_BASE):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest, audit = build_candidate_manifest(seed_base=seed_base)
    json_path = outdir / "formal_scenario_manifest_candidate.json"
    report_path = outdir / "formal_scenario_manifest_report.md"
    json_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(render_report(manifest), encoding="utf-8")
    print("D064C gate:", "PASS" if manifest["gate"]["passed"] else "FAIL")
    print("manifest_sha256:", manifest["manifest_sha256"])
    print("test_family_sha256:", manifest["splits"]["test_locked"]["family_sha256"])
    print("test_scenario_sha256:", manifest["splits"]["test_locked"]["scenario_sha256"])
    for split, summary in audit["split_summaries"].items():
        print(split, json.dumps(summary, sort_keys=True))
    if audit["problems"]:
        raise RuntimeError("formal manifest gate failed: " + "; ".join(audit["problems"]))
    return manifest, audit, json_path, report_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(HERE))
    parser.add_argument("--seed-base", type=int, default=SEED_BASE)
    args = parser.parse_args()
    write_candidate_manifest(args.outdir, seed_base=args.seed_base)


if __name__ == "__main__":
    main()
