"""Fault-Stratified Pareto Archive Evolution (FSPAE).

Bounded feasible Pareto archives are indexed by (task family, fault stratum).
A coverage-deficit scheduler targets under-covered / weak strata; local
NSGA-III niche selection chooses the archive parent. Global survivors still
use the same NSGA-III environmental selection as the matched baseline.

Only D-079 Train/search scenarios are accepted by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass

from a3_bridge import repair_fsm
from contract_validator import validate_genome
from ea import (
    _associate_reference_directions, _nsga3_normalize, crossover,
    crowding_distance, fast_non_dominated_sort, mutate, niching_select,
    reference_dirs,
)
from sbcg import CandidateRecord, StratifiedCounterexamplePool, evaluate_sbcg_candidate, fsm_fingerprint
from sbcg_runner import _select_survivor_records
from split_access import validate_evolution_scenarios


@dataclass
class StratumArchiveEntry:
    candidate: CandidateRecord
    objectives: tuple[float, float, float]


class StratumParetoArchive:
    """Bounded local Pareto archive with persistent NSGA-III niche counts."""

    def __init__(self, cluster_id, label, capacity=4, directions=None):
        if capacity < 1:
            raise ValueError("archive capacity must be positive")
        self.cluster_id = cluster_id
        self.label = label
        self.capacity = capacity
        self.directions = directions or reference_dirs(m=3, p=4)
        self.records = []
        self.niche_counts = [0] * len(self.directions)
        self.target_selections = 0

    @staticmethod
    def _dominates(a, b):
        return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))

    def update(self, candidate, objectives, rng):
        if not candidate.feasible:
            return False
        fingerprint = candidate.fingerprint
        if any(item.candidate.fingerprint == fingerprint for item in self.records):
            return False
        if any(self._dominates(item.objectives, objectives) for item in self.records):
            return False
        kept = [
            item for item in self.records
            if not self._dominates(objectives, item.objectives)
        ]
        kept.append(StratumArchiveEntry(candidate, tuple(float(x) for x in objectives)))
        if len(kept) > self.capacity:
            objective_matrix = [item.objectives for item in kept]
            fronts = fast_non_dominated_sort(objective_matrix)
            selected = []
            for front in fronts:
                if len(selected) + len(front) <= self.capacity:
                    selected.extend(front)
                    continue
                picked = niching_select(
                    objective_matrix, front, self.directions,
                    selected=selected, rng=rng, extreme_indices=fronts[0],
                )
                selected.extend(picked[: self.capacity - len(selected)])
                break
            kept = [kept[index] for index in selected]
        self.records = sorted(kept, key=lambda item: item.candidate.fingerprint)
        return any(item.candidate.fingerprint == fingerprint for item in self.records)

    def select_parent(self, rng):
        """Choose a local Pareto specialist by least-used NSGA-III niche."""
        if not self.records:
            return None
        objectives = [item.objectives for item in self.records]
        normalized, _ideal, _intercepts = _nsga3_normalize(objectives)
        associations, distances = _associate_reference_directions(normalized, self.directions)
        members_by_direction = defaultdict(list)
        for index, direction in enumerate(associations):
            members_by_direction[direction].append(index)
        direction = min(
            members_by_direction,
            key=lambda value: (self.niche_counts[value], value),
        )
        members = members_by_direction[direction]
        if self.niche_counts[direction] == 0:
            selected = min(
                members,
                key=lambda index: (distances[index], self.records[index].candidate.fingerprint),
            )
        else:
            selected = rng.choice(members)
        self.niche_counts[direction] += 1
        return self.records[selected].candidate.fsm

    def best_objectives(self):
        if not self.records:
            return None
        best = min(
            self.records,
            key=lambda item: (
                item.objectives[0], item.objectives[1],
                item.objectives[2], item.candidate.fingerprint,
            ),
        )
        return list(best.objectives)

    def view(self):
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "capacity": self.capacity,
            "archive_size": len(self.records),
            "best_local_objectives": self.best_objectives(),
            "niche_counts": list(self.niche_counts),
            "target_selections": self.target_selections,
            "fingerprints": [item.candidate.fingerprint for item in self.records],
        }


def _cluster_objectives(rows, label):
    if not rows:
        raise ValueError("cannot score an empty fault stratum")
    successes = [
        float(row["class_success"])
        for row in rows if row.get("class_success") is not None
    ]
    if len(successes) != len(rows):
        raise ValueError("D-079 robust class labels must be decisive")
    success = sum(successes) / len(successes)
    harm = sum(float(row.get("avoidable_harm", 0.0)) for row in rows) / len(rows)
    # R1/R2 escalation is unnecessary cost; R3/R4 escalation is required and
    # therefore is not penalized. The latter use recovery-decision count.
    if label in ("R1", "R2"):
        cost = sum(
            float(row.get("decision_count", 0))
            + float(row.get("policy_selected_escalation", 0))
            for row in rows
        ) / len(rows)
    else:
        cost = sum(float(row.get("decision_count", 0)) for row in rows) / len(rows)
    return (1.0 - success, harm, cost)


def _scenario_registry(scenarios):
    scenario_to_cluster, cluster_labels, scenario_families = {}, {}, {}
    for scenario in scenarios:
        family = scenario.get("task_family_id") or scenario.get("task")
        stratum = scenario.get("difficulty_stratum") or scenario.get("composition")
        if not family or not stratum:
            raise ValueError("FSPAE requires task_family_id and difficulty_stratum")
        cluster = scenario.get("cluster_id") or f"{family}|{stratum}"
        if cluster != f"{family}|{stratum}":
            raise ValueError("cluster_id must equal task_family_id|difficulty_stratum")
        label = scenario.get("label")
        if label not in {"R1", "R2", "R3", "R4"}:
            raise ValueError("FSPAE requires decisive robust R1-R4 labels")
        previous = cluster_labels.setdefault(cluster, label)
        if previous != label:
            raise ValueError("one fault stratum contains multiple robust classes")
        scenario_to_cluster[scenario["scenario_id"]] = cluster
        scenario_families[scenario["scenario_id"]] = family
    return scenario_to_cluster, cluster_labels, scenario_families, sorted(set(scenario_to_cluster.values()))


def _local_rows_by_cluster(record, scenario_to_cluster):
    grouped = defaultdict(list)
    for row in record.metrics.get("rows", []):
        scenario_id = row.get("scenario_id")
        if scenario_id not in scenario_to_cluster:
            raise ValueError("candidate evaluation returned an unknown scenario")
        grouped[scenario_to_cluster[scenario_id]].append(row)
    if set(grouped) != set(scenario_to_cluster.values()):
        raise ValueError("candidate evaluation omitted one or more fault strata")
    return grouped


def _cluster_performance_deficit(archive):
    """Dimensionless local deficit: recovery loss (0.8) plus capped harm (0.2).

    Archive cardinality is deliberately excluded: it measures retained Pareto
    diversity, not evaluation exposure or controller performance.
    """
    if not archive.records:
        return 1.0
    scores = []
    for item in archive.records:
        loss = max(0.0, min(1.0, float(item.objectives[0])))
        harm = max(0.0, min(1.0, float(item.objectives[1])))
        scores.append(0.8 * loss + 0.2 * harm)
    return min(scores)


def _target_cluster(archives, rng, mode):
    cluster_ids = sorted(archives)
    if not cluster_ids:
        raise ValueError("FSPAE requires at least one fault stratum")
    if mode == "uniform":
        return rng.choice(cluster_ids)
    if mode in {"deficit", "legacy_deficit"}:
        scored = []
        for cluster_id in cluster_ids:
            archive = archives[cluster_id]
            archive_deficit = 1.0 - min(1.0, len(archive.records) / archive.capacity)
            best = archive.best_objectives()
            best_loss = float(best[0]) if best is not None else 1.0
            best_harm = float(best[1]) if best is not None else 1.0
            scored.append((archive_deficit + 0.5 * best_loss + 0.1 * best_harm, cluster_id))
    elif mode == "performance_deficit":
        scored = [
            (_cluster_performance_deficit(archives[cluster_id]), cluster_id)
            for cluster_id in cluster_ids
        ]
    else:
        raise ValueError(
            "target_mode must be deficit, legacy_deficit, performance_deficit, or uniform"
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    shortlist_size = max(1, math.ceil(len(scored) * 0.2))
    return rng.choice([cluster_id for _score, cluster_id in scored[:shortlist_size]])


def _population_tournament(records, ranks, crowding, rng):
    left, right = rng.randrange(len(records)), rng.randrange(len(records))
    a, b = records[left], records[right]
    if a.feasible != b.feasible:
        return left if a.feasible else right
    if ranks[left] != ranks[right]:
        return left if ranks[left] < ranks[right] else right
    return left if crowding.get(left, 0.0) >= crowding.get(right, 0.0) else right


def _archive_candidate_records(archives):
    unique = {}
    for archive in archives.values():
        for item in archive.records:
            unique[item.candidate.fingerprint] = item.candidate
    return [unique[key] for key in sorted(unique)]


def _record_view(record):
    return {
        "fingerprint": record.fingerprint,
        "objectives": list(record.objectives),
        "constraints": dict(record.constraints),
        "feasible": record.feasible,
        "family_coverage": record.family_coverage,
        "worst_family_condrec": record.worst_family_condrec,
    }


def run_fspae_evolution(
    initial_pool, scenarios, verdicts, *,
    pop_size=8, generations=5, eval_budget, seed,
    archive_capacity=4, target_mode="deficit",
    parent_mode="local_a_global_b", variation_mode="global",
):
    """Run FSPAE on Train/search only; return a deduplicated feasible archive union."""
    validate_evolution_scenarios(scenarios)
    if any(item.get("evaluation_role") != "search" for item in scenarios):
        raise ValueError("FSPAE fitness accepts search-role scenarios only")
    if pop_size < 1 or generations < 0 or archive_capacity < 1:
        raise ValueError("invalid FSPAE population, generation, or archive capacity")
    if target_mode not in {"deficit", "legacy_deficit", "performance_deficit", "uniform"}:
        raise ValueError("invalid FSPAE target mode")
    if parent_mode not in {"local_a_global_b", "local_pair"}:
        raise ValueError("parent_mode must be local_a_global_b or local_pair")
    if variation_mode not in {"global", "target_cluster"}:
        raise ValueError("variation_mode must be global or target_cluster")
    if eval_budget < pop_size * len(scenarios):
        raise ValueError("evaluation budget is insufficient for the initial population")
    if len(initial_pool) < pop_size:
        raise ValueError("initial pool is smaller than the population")

    scenario_to_cluster, cluster_labels, scenario_families, cluster_ids = _scenario_registry(scenarios)
    local_directions = reference_dirs(m=3, p=4)
    archives = {
        cluster_id: StratumParetoArchive(
            cluster_id, cluster_labels[cluster_id],
            capacity=archive_capacity, directions=local_directions,
        )
        for cluster_id in cluster_ids
    }
    population = [candidate.clone() for candidate in initial_pool[:pop_size]]
    initial_fingerprints = [fsm_fingerprint(candidate) for candidate in population]
    initial_pool_sha = hashlib.sha256(
        json.dumps(initial_fingerprints, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    rng = random.Random(seed)
    cache, episodes = {}, 0
    unique_evaluations = cache_hits = evaluation_calls = 0

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
            candidate, scenarios, verdicts,
            scenario_families=scenario_families,
            use_five_objectives=True,
        )
        if record.source_split != "train":
            raise ValueError("FSPAE candidate fitness must remain Train-only")
        episodes += len(scenarios)
        unique_evaluations += 1
        evaluation_calls += 1
        cache[fingerprint] = record
        return record

    records = []
    for candidate in population:
        record = evaluate(candidate)
        if record is None:
            raise RuntimeError("FSPAE initial population exceeded the evaluation budget")
        records.append(record)
        grouped = _local_rows_by_cluster(record, scenario_to_cluster)
        for cluster_id, rows in grouped.items():
            archives[cluster_id].update(
                record, _cluster_objectives(rows, cluster_labels[cluster_id]), rng
            )

    counterexamples = StratifiedCounterexamplePool()
    mutation_audit, strata_history = [], []
    target_counts = {cluster_id: 0 for cluster_id in cluster_ids}
    seen = {record.fingerprint for record in records}
    global_directions = reference_dirs(m=5, p=3)
    history = [{
        "generation": 0,
        "episodes": episodes,
        "unique_evaluations": unique_evaluations,
        "feasible_population": sum(record.feasible for record in records),
        "covered_strata": sum(bool(item.records) for item in archives.values()),
        "archive_entries": sum(len(item.records) for item in archives.values()),
    }]

    for generation in range(generations):
        if episodes >= eval_budget:
            break
        counterexamples.clear()
        counterexamples.aggregate(
            [record.metrics for record in records], scenario_families,
            scenario_clusters=(
                scenario_to_cluster if variation_mode == "target_cluster" else None
            ),
        )
        strata_history.append({
            "generation": generation + 1,
            "strata": counterexamples.stratum_statistics(),
        })
        fronts = fast_non_dominated_sort([record.objectives for record in records])
        ranks = {index: rank for rank, front in enumerate(fronts) for index in front}
        crowding = {}
        for front in fronts:
            crowding.update(crowding_distance([record.objectives for record in records], front))

        pending = []
        for _ in range(pop_size):
            if episodes >= eval_budget:
                break
            target = _target_cluster(archives, rng, target_mode)
            target_counts[target] += 1
            archives[target].target_selections += 1
            target_archive = archives[target]
            parent_a = target_archive.select_parent(rng)
            parent_a_source = "target_archive" if parent_a is not None else "global_population"
            if parent_a is None:
                parent_a = population[_population_tournament(records, ranks, crowding, rng)]
            if parent_mode == "local_pair" and target_archive.records:
                parent_b = target_archive.select_parent(rng)
                parent_b_source = "target_archive"
            else:
                parent_b = population[_population_tournament(records, ranks, crowding, rng)]
                parent_b_source = "global_population"
            parent_a_fingerprint = fsm_fingerprint(parent_a)
            parent_b_fingerprint = fsm_fingerprint(parent_b)
            child = crossover(parent_a, parent_b, rng)
            if variation_mode == "target_cluster":
                child, audit = counterexamples.mutate_with_record(
                    child, rng, target_cluster=target,
                )
            elif counterexamples.stratum_statistics():
                child, audit = counterexamples.mutate_with_record(child, rng)
            else:
                child = mutate(child, rng)
                audit = {
                    "stratum": None, "gene_key": None, "gene_hit": False,
                    "cause": None, "target_cluster": target,
                    "selected_cluster": None, "target_match": False,
                    "fallback": "standard_mutation_empty_pool",
                }
            audit.update({
                "parent_a_source": parent_a_source,
                "parent_b_source": parent_b_source,
                "parent_a_fingerprint": parent_a_fingerprint,
                "parent_b_fingerprint": parent_b_fingerprint,
            })
            child = repair_fsm(child)
            validation = validate_genome(child.genes_list(), child.default_action, child.default_wait)
            valid_genome = not validation.genome_invalid and validation.rule_invalid == 0
            record = evaluate(child)
            if record is None:
                break
            pending.append((audit, record, valid_genome))

        combined = records + [item[1] for item in pending]
        records = _select_survivor_records(
            combined, pop_size, "nsga3", global_directions, rng=rng
        )
        population = [record.fsm for record in records]

        for _audit, record, _valid in pending:
            grouped = _local_rows_by_cluster(record, scenario_to_cluster)
            for cluster_id, rows in grouped.items():
                archives[cluster_id].update(
                    record, _cluster_objectives(rows, cluster_labels[cluster_id]), rng
                )
        archived_fingerprints = {
            item.candidate.fingerprint
            for archive in archives.values() for item in archive.records
        }
        for audit, record, valid_genome in pending:
            has_counterexample = audit.get("stratum") is not None
            new_valid = bool(
                has_counterexample and valid_genome and record.feasible
                and record.fingerprint not in seen
                and record.fingerprint in archived_fingerprints
            )
            if has_counterexample:
                counterexamples.record_repair_outcome(
                    audit["stratum"], valid=valid_genome, new_valid=new_valid
                )
            mutation_audit.append({
                **audit, "fingerprint": record.fingerprint,
                "repair_attempted": has_counterexample,
                "valid_genome": valid_genome,
                "new_valid_individual": new_valid,
            })
            seen.add(record.fingerprint)

        history.append({
            "generation": generation + 1,
            "episodes": episodes,
            "unique_evaluations": unique_evaluations,
            "feasible_population": sum(record.feasible for record in records),
            "covered_strata": sum(bool(item.records) for item in archives.values()),
            "archive_entries": sum(len(item.records) for item in archives.values()),
        })

    candidate_records = _archive_candidate_records(archives)
    if unique_evaluations + cache_hits != evaluation_calls:
        raise AssertionError("FSPAE evaluation-call accounting is inconsistent")
    if episodes > eval_budget:
        raise AssertionError("FSPAE exceeded its Train episode budget")
    return {
        "algorithm": (
            "FSPAE-R2" if (
                target_mode == "performance_deficit"
                and parent_mode == "local_pair"
                and variation_mode == "target_cluster"
            ) else (
                "FSPAE-R2-global-mutation-ablation" if (
                    target_mode == "performance_deficit"
                    and parent_mode == "local_pair"
                    and variation_mode == "global"
                ) else (
                    "FSPAE-R2-uniform-target-ablation" if (
                        target_mode == "uniform"
                        and parent_mode == "local_pair"
                        and variation_mode == "target_cluster"
                    ) else (
                        "FSPAE-R2-legacy-scheduler-ablation" if (
                            target_mode == "legacy_deficit"
                            and parent_mode == "local_pair"
                            and variation_mode == "target_cluster"
                        ) else (
                            "FSPAE-uniform-target" if target_mode == "uniform" else "FSPAE"
                        )
                    )
                )
            )
        ),
        "config": {
            "pop_size": pop_size, "generations": generations,
            "archive_capacity_per_stratum": archive_capacity,
            "target_mode": target_mode,
            "parent_mode": parent_mode,
            "variation_mode": variation_mode,
            "performance_deficit": {
                "formula": "min_archive(0.8 * clip(1 - class_success, 0, 1) + 0.2 * clip(avoidable_harm, 0, 1))",
                "archive_cardinality_used": False,
            } if target_mode == "performance_deficit" else None,
            "local_objectives": ["1 - class_success", "avoidable_harm", "class_relevant_recovery_action_cost"],
            "global_hard_constraints": ["duplicate", "sla_violation", "invariant_violation"],
            "local_reference_direction_count": len(local_directions),
            "global_survivor_optimizer": "NSGA-III",
            "counterexample_guidance": True,
            "target_cluster_mutation_is_fail_closed": variation_mode == "target_cluster",
        },
        "seed": seed, "eval_budget": eval_budget, "episodes": episodes,
        "unique_evaluations": unique_evaluations, "cache_hits": cache_hits,
        "evaluation_calls": evaluation_calls, "initial_pool_sha256": initial_pool_sha,
        "initial_pool_fingerprints": initial_fingerprints,
        "information_scope": "d079_train_search_only",
        "history": history,
        "archive_stats": [archives[key].view() for key in cluster_ids],
        "target_selection_counts": target_counts,
        "strata_history": strata_history, "mutation_audit": mutation_audit,
        "train_candidate_records": candidate_records,
        "train_candidate_fsms": [record.fsm for record in candidate_records],
        "train_candidates": [_record_view(record) for record in candidate_records],
        "train_feasible_candidates": len(candidate_records),
        "final_records": [_record_view(record) for record in records],
        "final_population": population,
        "final_metrics": [record.metrics for record in records],
    }
