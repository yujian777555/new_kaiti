"""Configurable SBCG-NSGA-III research runner.

Only Train scenarios are accepted. This runner is synthetic-tested and does not
authorize or execute real Train/Validation benchmark diagnostics or Test access.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict

from a3_bridge import hand_fsm, repair_fsm
from contract_validator import validate_genome
from ea import crossover, crowding_distance, fast_non_dominated_sort, mutate, niching_select, reference_dirs
from sbcg import (
    EliteArchive,
    StratifiedCounterexamplePool,
    evaluate_sbcg_candidate,
    fsm_fingerprint,
    select_validation_candidate,
)
from split_access import validate_evolution_scenarios


def _record_view(record):
    return {
        "objectives": list(record.objectives),
        "constraints": dict(record.constraints),
        "per_family_condrec": dict(record.per_family_condrec),
        "fingerprint": record.fingerprint,
        "source_split": record.source_split,
        "valid_genome": record.valid_genome,
        "feasible": record.feasible,
        "family_coverage": record.family_coverage,
        "worst_family_condrec": record.worst_family_condrec,
    }


def _niching_records(records, indices, dirs, needed, selected=(), rng=None, extreme_indices=None):
    """Use canonical NSGA-III association and niche counts across accepted fronts."""
    objectives = [record.objectives for record in records]
    return niching_select(
        objectives, indices, dirs, selected=selected, rng=rng,
        extreme_indices=extreme_indices,
    )[:needed]


def _select_survivor_records(records, count, optimizer, dirs, rng=None):
    """Feasibility first, then NSGA-II crowding or canonical NSGA-III niching."""
    feasible = [record for record in records if record.feasible]
    infeasible = [record for record in records if not record.feasible]
    chosen = []
    selected_indices = []
    if feasible:
        objectives = [record.objectives for record in feasible]
        fronts = fast_non_dominated_sort(objectives)
        for front_indices in fronts:
            front = [feasible[i] for i in front_indices]
            if len(chosen) + len(front) <= count:
                chosen.extend(front)
                selected_indices.extend(front_indices)
                continue
            needed = count - len(chosen)
            if optimizer == "nsga2":
                distances = crowding_distance(objectives, front_indices)
                ordered = sorted(
                    front_indices,
                    key=lambda i: (-distances[i], feasible[i].fingerprint),
                )
                picked = ordered[:needed]
            else:
                picked = _niching_records(
                    feasible, front_indices, dirs, needed,
                    selected=selected_indices, rng=rng, extreme_indices=fronts[0],
                )
            chosen.extend(feasible[i] for i in picked)
            break
    if len(chosen) < count:
        infeasible.sort(key=lambda record: (
            max(record.constraints.values()),
            tuple(record.constraints[name] for name in sorted(record.constraints)),
            record.fingerprint,
        ))
        chosen.extend(infeasible[:count - len(chosen)])
    return chosen


def run_sbcg_evolution(
    initial_pool,
    scenarios,
    verdicts,
    *,
    pop_size,
    generations,
    eval_budget,
    seed,
    use_five_objectives=True,
    use_stratified_counterexamples=True,
    use_elite_archive=True,
    remove_hand_from_pool=False,
    optimizer="nsga3",
):
    """Run one configurable SBCG/matched-objective EA arm on Train only."""
    validate_evolution_scenarios(scenarios)
    if optimizer not in {"nsga2", "nsga3"}:
        raise ValueError("optimizer must be nsga2 or nsga3")
    if pop_size < 1 or generations < 0:
        raise ValueError("invalid population or generation count")
    if eval_budget < pop_size * len(scenarios):
        raise ValueError("evaluation budget is insufficient for the initial population")

    pool = list(initial_pool)
    if remove_hand_from_pool:
        hand_fp = fsm_fingerprint(hand_fsm())
        pool = [candidate for candidate in pool if fsm_fingerprint(candidate) != hand_fp]
    if len(pool) < pop_size:
        raise ValueError("initial pool is smaller than the population after ablation")
    population = [candidate.clone() for candidate in pool[:pop_size]]
    initial_fingerprints = [fsm_fingerprint(candidate) for candidate in population]
    initial_pool_sha = hashlib.sha256(
        json.dumps(initial_fingerprints).encode("utf-8")
    ).hexdigest()
    scenario_families = {
        scenario["scenario_id"]: (
            scenario.get("task_family_id") or scenario.get("task") or scenario["scenario_id"]
        )
        for scenario in scenarios
    }
    rng = random.Random(seed)
    cache = {}
    episodes = 0
    unique_evaluations = 0
    cache_hits = 0
    evaluation_calls = 0

    def evaluate(candidate):
        nonlocal episodes, unique_evaluations, cache_hits, evaluation_calls
        fingerprint = fsm_fingerprint(candidate)
        if fingerprint in cache:
            cache_hits += 1
            evaluation_calls += 1
            return cache[fingerprint]
        if episodes + len(scenarios) > eval_budget:
            return None
        record = evaluate_sbcg_candidate(
            candidate,
            scenarios,
            verdicts,
            scenario_families=scenario_families,
            use_five_objectives=use_five_objectives,
        )
        episodes += len(scenarios)
        unique_evaluations += 1
        evaluation_calls += 1
        cache[fingerprint] = record
        return record

    records = []
    for candidate in population:
        record = evaluate(candidate)
        if record is None:
            raise RuntimeError("initial population exceeded the evaluation budget")
        records.append(record)
    archive = EliteArchive() if use_elite_archive else None
    if archive is not None:
        archive.update(records)
    counterexamples = StratifiedCounterexamplePool()
    strata_history = []
    mutation_audit = []
    seen = {record.fingerprint for record in records}
    directions = reference_dirs(
        m=5 if use_five_objectives else 3,
        p=3 if use_five_objectives else 6,
    )
    history = [{
        "generation": 0,
        "episodes": episodes,
        "unique_evaluations": unique_evaluations,
        "feasible": sum(record.feasible for record in records),
        "archive_size": len(archive.records) if archive is not None else 0,
    }]

    for generation in range(generations):
        if episodes >= eval_budget:
            break
        if use_stratified_counterexamples:
            counterexamples.clear()
            counterexamples.aggregate(
                [record.metrics for record in records], scenario_families
            )
            strata_history.append({
                "generation": generation + 1,
                "strata": counterexamples.stratum_statistics(),
            })

        ranks = {}
        fronts = fast_non_dominated_sort([record.objectives for record in records])
        for rank, front in enumerate(fronts):
            for i in front:
                ranks[i] = rank
        crowd = {}
        for front in fronts:
            crowd.update(crowding_distance([record.objectives for record in records], front))

        def pick_parent():
            i, j = rng.randrange(len(records)), rng.randrange(len(records))
            a, b = records[i], records[j]
            if a.feasible != b.feasible:
                return i if a.feasible else j
            if ranks[i] != ranks[j]:
                return i if ranks[i] < ranks[j] else j
            return i if crowd.get(i, 0) >= crowd.get(j, 0) else j

        offspring = []
        pending = []
        while len(offspring) < pop_size and episodes < eval_budget:
            a, b = population[pick_parent()], population[pick_parent()]
            child = crossover(a, b, rng)
            audit = None
            if use_stratified_counterexamples and counterexamples.stratum_statistics():
                child, audit = counterexamples.mutate_with_record(child, rng)
            else:
                child = mutate(child, rng)
            child = repair_fsm(child)
            validity = validate_genome(child.genes_list(), child.default_action, child.default_wait)
            valid = not validity.genome_invalid and validity.rule_invalid == 0
            record = evaluate(child)
            if record is None:
                break
            offspring.append(child)
            pending.append((audit, child, record, valid))

        # Reuse the exact evaluated offspring records; a second cache lookup would
        # inflate cache_hits/evaluation_calls without performing an evaluation.
        combined = records + [item[2] for item in pending]
        records = _select_survivor_records(combined, pop_size, optimizer, directions, rng=rng)
        population = [record.fsm for record in records]
        if archive is not None:
            archive.update(combined)
        archive_fingerprints = {record.fingerprint for record in archive.records} if archive is not None else set()
        for audit, child, record, valid in pending:
            new_valid = bool(
                valid and record.feasible and record.fingerprint not in seen
                and (archive is None or record.fingerprint in archive_fingerprints)
            )
            if audit is not None:
                counterexamples.record_repair_outcome(
                    audit["stratum"], valid=valid, new_valid=new_valid
                )
                mutation_audit.append({
                    **audit,
                    "fingerprint": record.fingerprint,
                    "repair_attempted": True,
                    "valid_genome": valid,
                    "new_valid_individual": new_valid,
                })
            seen.add(record.fingerprint)
        history.append({
            "generation": generation + 1,
            "episodes": episodes,
            "unique_evaluations": unique_evaluations,
            "feasible": sum(record.feasible for record in records),
            "archive_size": len(archive.records) if archive is not None else 0,
        })

    final_records = archive.records if archive is not None and archive.records else records
    train_source = "train_elite_archive" if archive is not None and archive.records else "train_final_population"
    # Train search must not masquerade as Validation selection. Validation is a
    # separate, explicit evaluation stage in sbcg_experiment.py.
    selection = {
        "status": "PENDING_VALIDATION",
        "candidate": None,
        "input": train_source,
        "validation_used": False,
    }
    return {
        "algorithm": "SBCG-NSGA-III" if use_five_objectives else "SBCG-NSGA-III-M1-ablation",
        "config": {
            "use_five_objectives": use_five_objectives,
            "use_stratified_counterexamples": use_stratified_counterexamples,
            "use_elite_archive": use_elite_archive,
            "remove_hand_from_pool": remove_hand_from_pool,
            "optimizer": optimizer,
            "pop_size": pop_size,
            "generations": generations,
        },
        "seed": seed,
        "eval_budget": eval_budget,
        "episodes": episodes,
        "unique_evaluations": unique_evaluations,
        "cache_hits": cache_hits,
        "evaluation_calls": evaluation_calls,
        "initial_pool_sha256": initial_pool_sha,
        "initial_pool_fingerprints": initial_fingerprints,
        "reference_direction_count": len(directions),
        "information_scope": "train_only_no_test",
        "history": history,
        "strata": counterexamples.stratum_statistics() if use_stratified_counterexamples else [],
        "strata_history": strata_history,
        "mutation_audit": mutation_audit,
        "archive": [_record_view(record) for record in archive.records] if archive is not None else [],
        "final_records": [_record_view(record) for record in records],
        "train_candidates": [_record_view(record) for record in final_records],
        "train_candidate_fsms": [record.fsm for record in final_records],
        # Reuse the already-computed records for independent Train-only
        # candidate selection; this must not trigger another simulator pass.
        "final_metrics": [record.metrics for record in records],
        "train_feasible_candidates": sum(record.feasible for record in final_records),
        "selection": selection,
        "best": None,
        "final_population": population,
    }
