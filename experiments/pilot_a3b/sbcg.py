"""SBCG-NSGA-III mechanisms with synthetic-testable interfaces.

Development is restricted to Train. The module contains no real benchmark or
Test loader and performs no LLM calls.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from a3_bridge import ACTIONS, evaluate_controller, hand_fsm
from contract_validator import validate_genome
from ea import CounterexamplePool, _SIG_REPAIR, dominates, mutate, reference_dirs
from run_diagnostic3 import sensible_random_fsm

OBJECTIVE_NAMES = (
    "1_minus_CondRecSucc",
    "AvoidableHarm",
    "UnnecessaryActionCost",
    "1_minus_CorrectEscalation",
    "1_minus_DamageContainment",
)
HARD_CONSTRAINT_NAMES = ("duplicate", "sla_violation", "invariant_violation")


def sbcg_objectives(metrics):
    """Frozen five-dimensional minimization vector."""
    return (
        1.0 - metrics["cond_rec"],
        float(metrics["avoid_resid"]),
        float(metrics["unnec_actions_r12"]),
        1.0 - metrics["corr_esc"],
        1.0 - metrics["containment"],
    )


def hard_constraint_violations(metrics):
    """Hard safety constraints use zero tolerance and never enter objectives."""
    return {
        "duplicate": float(metrics.get("dup", 0.0)),
        "sla_violation": float(metrics.get("sla_viol", 0.0)),
        "invariant_violation": float(metrics.get("violations", 0.0)),
    }


def is_safety_feasible(metrics):
    return all(value <= 0.0 for value in hard_constraint_violations(metrics).values())


def sbcg_reference_directions():
    """Five-objective Das-Dennis directions: p=3 gives C(7,4)=35."""
    return reference_dirs(m=5, p=3)


@dataclass
class CandidateRecord:
    fsm: Any
    objectives: tuple
    constraints: dict
    per_family_condrec: dict
    fingerprint: str
    valid_genome: bool
    metrics: dict = field(default_factory=dict)
    source_split: str = "unknown"

    @property
    def feasible(self):
        return self.valid_genome and all(value <= 0.0 for value in self.constraints.values())

    @property
    def family_coverage(self):
        return len(self.per_family_condrec)

    @property
    def worst_family_condrec(self):
        return min(self.per_family_condrec.values()) if self.per_family_condrec else 0.0


def _selection_tiebreak(record):
    objectives = record.objectives
    if len(objectives) == 5:
        objective_order = (objectives[1], objectives[3], objectives[4], objectives[2], objectives[0])
    else:
        objective_order = tuple(objectives)
    return objective_order, record.fingerprint


def _non_dominated(records):
    return [
        candidate for candidate in records
        if not any(other is not candidate and dominates(other.objectives, candidate.objectives)
                   for other in records)
    ]


class EliteArchive:
    """Feasible Pareto archive with deduplication and a per-family guard."""

    def __init__(self):
        self._records = {}

    @property
    def records(self):
        return [self._records[key] for key in sorted(self._records)]

    def update(self, candidates):
        before = len(self._records)
        rejected = 0
        for candidate in candidates:
            if not candidate.feasible:
                rejected += 1
                continue
            incumbent = self._records.get(candidate.fingerprint)
            if incumbent is None or _selection_tiebreak(candidate) < _selection_tiebreak(incumbent):
                self._records[candidate.fingerprint] = candidate
        feasible = self.records
        keep = {candidate.fingerprint for candidate in _non_dominated(feasible)}
        # Preserve the best available recovery candidate for every observed family.
        by_family = {}
        for candidate in feasible:
            for family, value in candidate.per_family_condrec.items():
                current = by_family.get(family)
                key = (-value, _selection_tiebreak(candidate))
                if current is None or key < current[0]:
                    by_family[family] = (key, candidate)
        keep.update(item[1].fingerprint for item in by_family.values())
        self._records = {
            key: candidate for key, candidate in self._records.items() if key in keep
        }
        return {
            "before": before,
            "after": len(self._records),
            "new_valid_individuals": max(0, len(self._records) - before),
            "rejected_infeasible": rejected,
        }


def _select_candidate(records, required_split):
    if not records:
        return {
            "status": "HOLD", "candidate": None,
            "reason": f"no {required_split} candidates",
            "rule": f"{required_split} feasibility gate; no candidate available",
        }
    if any(record.source_split != required_split for record in records):
        split_label = required_split.capitalize()
        raise ValueError(f"{split_label} selector accepts {split_label}-evaluated candidates only")
    feasible = [record for record in records if record.feasible]
    if not feasible:
        return {
            "status": "HOLD",
            "candidate": None,
            "reason": "no candidate satisfies the frozen hard safety constraints",
            "rule": "zero-tolerance hard safety feasibility before Pareto selection",
        }
    candidates = _non_dominated(feasible)
    chosen = min(
        candidates,
        key=lambda candidate: (
            -candidate.family_coverage,
            -candidate.worst_family_condrec,
            _selection_tiebreak(candidate),
        ),
    )
    return {
        "status": "SELECTED",
        "candidate": chosen,
        "rule": "feasible Pareto; family coverage; worst-family CondRecSucc; frozen lexicographic tie-break",
    }


def select_validation_candidate(records):
    """Validation-only feasibility -> Pareto -> coverage -> worst-family selection."""
    return _select_candidate(records, "validation")


def select_train_diagnostic_candidate(records):
    """Apply the same frozen rule to Train diagnostic candidates only."""
    return _select_candidate(records, "train")


def fsm_fingerprint(fsm):
    return repr((
        tuple(sorted((key, gene.action, gene.wait_n) for key, gene in fsm.genes.items())),
        fsm.default_action,
        fsm.default_wait,
        fsm.sla_aware,
        fsm.fixed_wait,
    ))


def make_shared_initial_pool(seed, size=60, include_hand=True):
    """All EA arms share the same sensible-random pool; only slot 0 is anchored."""
    if size < 1:
        raise ValueError("initial pool must be non-empty")
    rng = random.Random(seed * 7919 + 29)
    pool = [sensible_random_fsm(rng) for _ in range(size)]
    if include_hand:
        pool[0] = hand_fsm()
    return pool


class StratifiedCounterexamplePool:
    """Family x failure-signature x safety-class counterexample strata.

    Strata are sampled uniformly, so no globally common failure can monopolize
    the mutation budget. Every observed stratum has sampling probability 1/S.
    """

    def __init__(self):
        self._strata = {}
        self._audit = {}
        self._key_lookup = {}

    @staticmethod
    def _key_text(key):
        family, signature, safety_class = key
        return repr((family, signature, safety_class))

    def clear(self):
        self._strata.clear()
        self._audit.clear()
        self._key_lookup.clear()

    def aggregate(self, results, scenario_families):
        for result in results:
            for row in result["rows"]:
                if row["class_success"] in (1, None) or not row.get("decision_trace"):
                    continue
                sid = row["scenario_id"]
                if sid not in scenario_families:
                    raise ValueError(f"missing task-family metadata for {sid}")
                signature = CounterexamplePool._signature(row)
                key = (scenario_families[sid], signature, row.get("label", "UNKNOWN"))
                entry = self._strata.setdefault(key, {"examples": 0, "genes": Counter()})
                entry["examples"] += 1
                for obs, attempts, stack, _action in row["decision_trace"]:
                    entry["genes"][(obs, attempts, stack)] += 1
                text = self._key_text(key)
                self._key_lookup[text] = key
                self._audit.setdefault(key, {
                    "sampled": 0, "gene_hits": 0, "repair_attempts": 0,
                    "repair_valid": 0, "new_valid_individuals": 0,
                })

    def stratum_statistics(self):
        count = len(self._strata)
        output = []
        for key in sorted(self._strata, key=self._key_text):
            entry = self._strata[key]
            audit = self._audit.get(key, {})
            attempts = audit.get("repair_attempts", 0)
            output.append({
                "key": self._key_text(key),
                "family": key[0],
                "failure_signature": repr(key[1]),
                "safety_class": key[2],
                "examples": entry["examples"],
                "sampling_probability": 1.0 / count if count else 0.0,
                "sampled": audit.get("sampled", 0),
                "gene_hits": audit.get("gene_hits", 0),
                "repair_attempts": attempts,
                "repair_valid": audit.get("repair_valid", 0),
                "repair_success_rate": audit.get("repair_valid", 0) / attempts if attempts else None,
                "new_valid_individuals": audit.get("new_valid_individuals", 0),
            })
        return output

    def mutate_with_record(self, fsm, rng: random.Random):
        child = fsm.clone()
        if not self._strata:
            return mutate(child, rng), {
                "stratum": None, "gene_key": None, "gene_hit": False,
                "cause": None, "fallback": "standard_mutation_empty_pool",
            }
        key = sorted(self._strata, key=self._key_text)[rng.randrange(len(self._strata))]
        text = self._key_text(key)
        cause = key[1][0]
        implicated = self._strata[key]["genes"]
        candidates = [gene_key for gene_key in implicated if gene_key in child.genes]
        gene_hit = bool(candidates)
        if candidates:
            gene_key = rng.choice(candidates)
        else:
            gene_key = rng.choice(list(child.genes))
        gene = child.genes[gene_key]
        gene.action = rng.choice(_SIG_REPAIR.get(cause, ACTIONS))
        if rng.random() < 0.3:
            gene.wait_n = rng.randint(1, 4)
        audit = self._audit[key]
        audit["sampled"] += 1
        audit["gene_hits"] += int(gene_hit)
        return child, {
            "stratum": text,
            "gene_key": gene_key,
            "gene_hit": gene_hit,
            "cause": cause,
            "fallback": None if gene_hit else "random_gene_outside_implicated_set",
        }

    def record_repair_outcome(self, stratum_key, valid, new_valid):
        key = self._key_lookup[stratum_key]
        audit = self._audit[key]
        audit["repair_attempts"] += 1
        audit["repair_valid"] += int(bool(valid))
        audit["new_valid_individuals"] += int(bool(new_valid))


def evaluate_sbcg_candidate(
    fsm,
    scenarios,
    verdicts,
    *,
    scenario_families=None,
    use_five_objectives=True,
):
    """Evaluate one controller and construct its feasibility/objective record."""
    splits = {scenario.get("split") for scenario in scenarios}
    if len(splits) != 1 or not splits.issubset({"train", "validation"}):
        raise ValueError("candidate evaluation requires one explicit Train or Validation split")
    source_split = next(iter(splits))
    metrics = evaluate_controller(fsm, scenarios, verdicts, None)
    if scenario_families is None:
        scenario_families = {
            scenario["scenario_id"]: (
                scenario.get("task_family_id") or scenario.get("task") or scenario["scenario_id"]
            )
            for scenario in scenarios
        }
    by_family = {}
    for row in metrics["rows"]:
        if row.get("label") not in ("R1", "R2") or row.get("class_success") is None:
            continue
        family = scenario_families[row["scenario_id"]]
        by_family.setdefault(family, []).append(float(row["class_success"]))
    per_family = {
        family: sum(values) / len(values) for family, values in by_family.items()
    }
    validity = validate_genome(fsm.genes_list(), fsm.default_action, fsm.default_wait)
    objectives = (
        sbcg_objectives(metrics) if use_five_objectives else tuple(metrics["objectives"])
    )
    return CandidateRecord(
        fsm=fsm,
        objectives=objectives,
        constraints=hard_constraint_violations(metrics),
        per_family_condrec=per_family,
        fingerprint=fsm_fingerprint(fsm),
        valid_genome=not validity.genome_invalid and validity.rule_invalid == 0,
        metrics=metrics,
        source_split=source_split,
    )


def validation_selection_report(records):
    """JSON-safe report for the frozen Validation selection rule."""
    feasible = [record for record in records if record.feasible]
    selection = select_validation_candidate(records)
    candidate = selection["candidate"]
    candidate_view = None
    if candidate is not None:
        candidate_view = {
            "objectives": list(candidate.objectives),
            "constraints": dict(candidate.constraints),
            "per_family_condrec": dict(candidate.per_family_condrec),
            "fingerprint": candidate.fingerprint,
            "source_split": candidate.source_split,
            "family_coverage": candidate.family_coverage,
            "worst_family_condrec": candidate.worst_family_condrec,
        }
    return {
        "report_version": "sbcg-validation-selection-v1",
        "status": selection["status"],
        "reason": selection["reason"] if candidate is None else None,
        "candidate": candidate_view,
        "candidate_count": len(records),
        "feasible_candidates": len(feasible),
        "pareto_candidates": len(_non_dominated(feasible)),
        "pareto_front": [
            {
                "fingerprint": item.fingerprint,
                "objectives": list(item.objectives),
                "constraints": dict(item.constraints),
                "family_coverage": item.family_coverage,
                "worst_family_condrec": item.worst_family_condrec,
                "source_split": item.source_split,
            }
            for item in _non_dominated(feasible)
        ],
        "hard_constraint_limit": 0.0,
        "selection_rule": selection["rule"],
        "equal_weight_sum_used": False,
    }
