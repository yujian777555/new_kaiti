"""SBCG comparison matrix and fair-accounting adapters.

No experiment is authorized by this module. Reflection is a deterministic
non-LLM proxy because real LLM API calls are forbidden in this phase.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from a3_bridge import (
    ACT_VERIFY,
    OBS_RATE_LIMIT,
    OBS_TIMEOUT,
    evaluate_controller,
    hand_fsm,
)
from ea import run_evolution
from sbcg import (
    evaluate_sbcg_candidate,
    fsm_fingerprint,
    make_shared_initial_pool,
    select_validation_candidate,
    validation_selection_report,
)
from sbcg_runner import run_sbcg_evolution
from split_access import validate_evaluation_scenarios, validate_evolution_scenarios


@dataclass(frozen=True)
class AlgorithmSpec:
    name: str
    kind: str
    method: str = ""
    config: dict = field(default_factory=dict)


def algorithm_specs():
    """Required baselines, matched controls, and one-factor ablations."""
    specs = [
        AlgorithmSpec("Hand FSM", "fixed", "hand"),
        AlgorithmSpec("Random", "legacy_ea", "random"),
        AlgorithmSpec("Rule-based", "fixed", "rule_based"),
        AlgorithmSpec("Reflection", "fixed", "reflection_proxy"),
        AlgorithmSpec("NSGA-II", "legacy_ea", "nsga2"),
        AlgorithmSpec("NSGA-III", "legacy_ea", "nsga3"),
        AlgorithmSpec("Matched-objective NSGA-II", "sbcg", config={
            "optimizer": "nsga2", "use_five_objectives": True,
            "use_stratified_counterexamples": False, "use_elite_archive": False,
            "remove_hand_from_pool": False,
        }),
        AlgorithmSpec("Matched-objective NSGA-III", "sbcg", config={
            "optimizer": "nsga3", "use_five_objectives": True,
            "use_stratified_counterexamples": False, "use_elite_archive": False,
            "remove_hand_from_pool": False,
        }),
        AlgorithmSpec("A", "legacy_ea", "A"),
        AlgorithmSpec("AB", "legacy_ea", "AB"),
        AlgorithmSpec("SBCG-NSGA-III", "sbcg", config={
            "optimizer": "nsga3", "use_five_objectives": True,
            "use_stratified_counterexamples": True, "use_elite_archive": True,
            "remove_hand_from_pool": False,
        }),
        AlgorithmSpec("SBCG-NSGA-III-no-M1", "sbcg", config={
            "optimizer": "nsga3", "use_five_objectives": False,
            "use_stratified_counterexamples": True, "use_elite_archive": True,
            "remove_hand_from_pool": False,
        }),
        AlgorithmSpec("SBCG-NSGA-III-no-M2", "sbcg", config={
            "optimizer": "nsga3", "use_five_objectives": True,
            "use_stratified_counterexamples": False, "use_elite_archive": True,
            "remove_hand_from_pool": False,
        }),
        AlgorithmSpec("SBCG-NSGA-III-no-M3", "sbcg", config={
            "optimizer": "nsga3", "use_five_objectives": True,
            "use_stratified_counterexamples": True, "use_elite_archive": False,
            "remove_hand_from_pool": True,
        }),
    ]
    return specs


def rule_based_fsm():
    """Fixed-wait observable-state rule baseline, distinct from Hand."""
    fsm = hand_fsm()
    for gene in fsm.genes_list():
        if gene.error == OBS_TIMEOUT:
            gene.wait_n = 1
    fsm.fixed_wait = True
    return fsm


def reflection_proxy_fsm():
    """Deterministic non-LLM reflection proxy: verify ambiguity before waiting."""
    fsm = hand_fsm()
    for gene in fsm.genes_list():
        if gene.error == OBS_TIMEOUT:
            gene.action = ACT_VERIFY
        elif gene.error == OBS_RATE_LIMIT:
            gene.wait_n = 2
    return fsm


def _fixed_policy(method):
    if method == "hand":
        return hand_fsm()
    if method == "rule_based":
        return rule_based_fsm()
    if method == "reflection_proxy":
        return reflection_proxy_fsm()
    raise ValueError(f"unknown fixed policy: {method}")


def run_algorithm_arm(
    spec,
    initial_pool,
    scenarios,
    verdicts,
    *,
    eval_budget,
    seed,
    pop_size,
    generations,
    validation_scenarios=None,
):
    """Run optimization on Train, then evaluate frozen candidates on Validation only."""
    if eval_budget < 0:
        raise ValueError("evaluation budget must be non-negative")
    if spec.kind == "fixed":
        if validation_scenarios is None:
            validation_scenarios = scenarios
        validate_evaluation_scenarios(validation_scenarios)
        if any(item.get("split") != "validation" for item in validation_scenarios):
            raise ValueError("fixed baselines must be evaluated on Validation, not Train")
        policy = _fixed_policy(spec.method)
        out = {
            "best": policy, "best_result": None,
            "selection": {"status": "FIXED_POLICY"},
            "episodes": 0, "unique_evaluations": 0,
            "cache_hits": 0, "evaluation_calls": 0,
        }
        candidate_fsms = [policy]
        train_split = "not_used_fixed_policy"
    elif spec.kind == "legacy_ea":
        validate_evolution_scenarios(scenarios)
        out = run_evolution(
            spec.method, initial_pool, scenarios, verdicts,
            pop_size=pop_size, generations=generations,
            eval_budget=eval_budget, seed=seed,
        )
        candidate_fsms = list(out.get("final_population", []))
        train_split = "train"
    elif spec.kind == "sbcg":
        validate_evolution_scenarios(scenarios)
        out = run_sbcg_evolution(
            initial_pool, scenarios, verdicts,
            pop_size=pop_size, generations=generations,
            eval_budget=eval_budget, seed=seed, **spec.config,
        )
        candidate_fsms = list(out.get("train_candidate_fsms", out.get("final_population", [])))
        train_split = "train"
    else:
        raise ValueError(f"unknown algorithm kind: {spec.kind}")

    fingerprints = [fsm_fingerprint(candidate) for candidate in initial_pool]
    input_pool_sha = hashlib.sha256(json.dumps(fingerprints).encode("utf-8")).hexdigest()
    validation_records = []
    validation_selection = {"status": "PENDING_VALIDATION", "candidate": None}
    validation_report = None
    if validation_scenarios is not None:
        validate_evaluation_scenarios(validation_scenarios)
        if any(item.get("split") != "validation" for item in validation_scenarios):
            raise ValueError("candidate selection requires Validation scenarios only")
        if not candidate_fsms:
            raise RuntimeError("no frozen Train candidates are available for Validation")
        validation_records = [
            evaluate_sbcg_candidate(
                candidate, validation_scenarios, verdicts,
                use_five_objectives=True,
            )
            for candidate in candidate_fsms
        ]
        validation_selection = select_validation_candidate(validation_records)
        validation_report = validation_selection_report(validation_records)

    selected = validation_selection.get("candidate")
    selected_view = None
    if selected is not None:
        selected_view = {
            "fingerprint": selected.fingerprint,
            "objectives": list(selected.objectives),
            "constraints": dict(selected.constraints),
            "family_coverage": selected.family_coverage,
            "worst_family_condrec": selected.worst_family_condrec,
            "source_split": selected.source_split,
        }
    split_label = (
        "validation_only_no_test" if spec.kind == "fixed"
        else "train_and_validation_no_test" if validation_scenarios is not None
        else "train_only_no_test"
    )
    return {
        "algorithm": spec.name,
        "kind": spec.kind,
        "config": dict(spec.config),
        "seed": seed,
        "eval_budget": eval_budget,
        "episodes": out.get("episodes", 0),
        "train_episodes": out.get("episodes", 0),
        "unique_evaluations": out.get("unique_evaluations", 0),
        "cache_hits": out.get("cache_hits", 0),
        "evaluation_calls": out.get("evaluation_calls", 0),
        "initial_pool_sha256": out.get("initial_pool_sha256", input_pool_sha),
        "train_split": train_split,
        "information_scope": split_label,
        "validation_calls": len(validation_records),
        "validation_episodes": len(validation_records) * len(validation_scenarios or []),
        "validation_selection": {
            "status": validation_selection["status"],
            "candidate": selected_view,
            "reason": validation_selection.get("reason"),
        },
        "validation_report": validation_report,
        "best_fsm": _fsm_view(selected.fsm) if selected is not None else None,
        "best_result": selected.metrics if selected is not None else None,
        "history": out.get("history", []),
        "strata": out.get("strata", []),
        "mutation_audit": out.get("mutation_audit", []),
    }



def _fsm_view(fsm):
    """JSON-safe genome representation for reproducible pilot artifacts."""
    if fsm is None:
        return None
    genes = []
    for key, gene in sorted(fsm.genes.items(), key=lambda item: repr(item[0])):
        genes.append({
            "state": list(key) if isinstance(key, tuple) else str(key),
            "action": gene.action,
            "wait_n": gene.wait_n,
        })
    return {
        "fingerprint": fsm_fingerprint(fsm),
        "genes": genes,
        "default_action": fsm.default_action,
        "default_wait": fsm.default_wait,
        "sla_aware": getattr(fsm, "sla_aware", None),
        "fixed_wait": getattr(fsm, "fixed_wait", None),
    }


def write_algorithm_matrix_outputs(result, outdir):
    """Persist a JSON-safe matrix and a concise per-arm Validation-selection report."""
    from pathlib import Path

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "matrix_results.json"
    report_path = outdir / "matrix_report.md"
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# SBCG 14-arm Train/Validation exploratory pilot",
        "",
        f"- Matrix version: {result['matrix_version']}",
        f"- Status: {result['status']}",
        f"- Seeds: {result['seeds']}",
        f"- Arms: {result['algorithm_count']}; runs: {result['run_count']}",
        f"- Train scenarios: {result['train_scenario_count']}",
        f"- Validation scenarios: {result['validation_scenario_count']}",
        f"- Population / generations: {result['population']} / {result['generations']}",
        f"- Train episode budget per evolutionary arm: {result['per_evolutionary_arm_train_episode_budget']}",
        "",
        "**Interpretation:** Validation is used for candidate selection. These selected Validation metrics are exploratory selection metrics, not an unbiased final generalization estimate. No Test payload or Test outcomes are used.",
        "",
        "| Algorithm | Seed | Train episodes | Validation episodes | Pareto candidates | Selection | CondRecSucc | Avoidable harm | Action cost | Hard violations |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in result["results"]:
        metrics = row.get("best_result") or {}
        selection = row.get("validation_selection", {}).get("status", "NOT_RUN")
        hard = sum(float(metrics.get(key, 0.0)) for key in ("dup", "sla_viol", "violations"))
        def fmt(value):
            return "NA" if value is None else f"{float(value):.4f}"
        pareto_count = (row.get("validation_report") or {}).get("pareto_candidates", 0)
        lines.append(
            f"| {row['algorithm']} | {row['seed']} | {row['train_episodes']} | "
            f"{row['validation_episodes']} | {pareto_count} | {selection} | "
            f"{fmt(metrics.get('cond_rec'))} | {fmt(metrics.get('avoid_resid'))} | "
            f"{fmt(metrics.get('unnec_actions_r12'))} | {hard:.4f} |"
        )
    lines.extend([
        "",
        "## Scope and limits",
        "",
        "- This is a non-confirmatory development pilot on the generated synthetic A-3b Train/Validation simulator.",
        "- Train is used for evolutionary fitness; Validation is used once after each arm's Train search to select a candidate.",
        "- Validation metrics are subject to selection optimism and must not be presented as unbiased generalization performance.",
        "- No Test scenarios are passed to the optimization or evaluation runners; no Test outcomes are read.",
        "- Reflection is a deterministic proxy, not an LLM call.",
        "- This run does not authorize formal A-3b, Test access, or a confirmatory paper claim.",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, report_path


def run_algorithm_matrix(
    train_scenarios,
    validation_scenarios,
    verdicts,
    *,
    seeds=(411, 522, 633),
    eval_budget,
    pop_size=48,
    generations=60,
    initial_pool_size=60,
):
    """Paired 14-arm matrix: shared per-seed initial pool, Train search, Validation selection."""
    validate_evolution_scenarios(train_scenarios)
    validate_evaluation_scenarios(validation_scenarios)
    if any(item.get("split") != "validation" for item in validation_scenarios):
        raise ValueError("matrix Validation input must contain Validation scenarios only")
    if not seeds:
        raise ValueError("at least one optimizer seed is required")
    specs = algorithm_specs()
    results = []
    for seed in seeds:
        shared_pool = make_shared_initial_pool(seed, size=initial_pool_size, include_hand=True)
        for spec in specs:
            results.append(run_algorithm_arm(
                spec, shared_pool, train_scenarios, verdicts,
                eval_budget=eval_budget, seed=seed,
                pop_size=pop_size, generations=generations,
                validation_scenarios=validation_scenarios,
            ))
    return {
        "matrix_version": "sbcg-14-arm-train-validation-v1",
        "status": "EXECUTED_NO_TEST",
        "seeds": list(seeds),
        "algorithm_count": len(specs),
        "run_count": len(results),
        "train_scenario_count": len(train_scenarios),
        "validation_scenario_count": len(validation_scenarios),
        "population": pop_size,
        "generations": generations,
        "per_evolutionary_arm_train_episode_budget": eval_budget,
        "results": results,
    }
