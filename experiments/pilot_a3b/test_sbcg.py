"""Synthetic unit tests for SBCG mechanisms; no benchmark or Test data."""
import json
import random
import unittest

from a3_bridge import ACT_ESCALATE, OBS_PERMISSION, hand_fsm
from sbcg import (
    CandidateRecord,
    EliteArchive,
    StratifiedCounterexamplePool,
    fsm_fingerprint,
    hard_constraint_violations,
    is_safety_feasible,
    make_shared_initial_pool,
    sbcg_objectives,
    sbcg_reference_directions,
    select_validation_candidate,
    validation_selection_report,
)


def metrics(cond=0.5, harm=0.2, cost=0.3, esc=0.4, contain=0.7,
            duplicate=0.0, sla=0.0, invariant=0.0):
    return {
        "cond_rec": cond,
        "avoid_resid": harm,
        "unnec_esc": 0.1,
        "unnec_actions_r12": cost,
        "corr_esc": esc,
        "containment": contain,
        "dup": duplicate,
        "sla_viol": sla,
        "violations": invariant,
    }


def record(name, objectives, *, feasible=True, family_values=None):
    constraints = {"duplicate": 0.0, "sla_violation": 0.0, "invariant_violation": 0.0}
    if not feasible:
        constraints["duplicate"] = 0.1
    return CandidateRecord(
        fsm=None,
        objectives=tuple(objectives),
        constraints=constraints,
        per_family_condrec=family_values or {"f1": 0.5},
        fingerprint=name,
        valid_genome=True,
        source_split="validation",
    )


class ObjectiveTests(unittest.TestCase):
    def test_five_objectives_follow_the_frozen_formulas(self):
        result = sbcg_objectives(metrics())
        self.assertEqual(len(result), 5)
        self.assertAlmostEqual(result[0], 0.5)
        self.assertAlmostEqual(result[1], 0.2)
        self.assertAlmostEqual(result[2], 0.3)
        self.assertAlmostEqual(result[3], 0.6)
        self.assertAlmostEqual(result[4], 0.3)

    def test_hard_constraints_are_not_compensable_objectives(self):
        unsafe = metrics(duplicate=0.01)
        self.assertEqual(hard_constraint_violations(unsafe)["duplicate"], 0.01)
        self.assertFalse(is_safety_feasible(unsafe))
        self.assertTrue(is_safety_feasible(metrics()))

    def test_five_dimensional_reference_directions_are_frozen(self):
        directions = sbcg_reference_directions()
        self.assertEqual(len(directions), 35)
        self.assertTrue(all(len(d) == 5 for d in directions))
        self.assertTrue(all(abs(sum(d) - 1.0) < 1e-12 for d in directions))


class StratifiedCounterexampleTests(unittest.TestCase):
    def _row(self, sid, label, cause, action):
        return {
            "scenario_id": sid,
            "label": label,
            "class_success": 0,
            "duplicate": cause == "dup",
            "sla_violation": cause == "sla",
            "avoidable_harm": 0,
            "compensation_failure": False,
            "policy_selected_escalation": 0,
            "decision_trace": [(OBS_PERMISSION, 0, False, action)],
        }

    def _pool(self):
        pool = StratifiedCounterexamplePool()
        rows = []
        # A common family/signature/class and two rare strata.
        for i in range(8):
            rows.append(self._row(f"common|{i}", "R1", "dup", ACT_ESCALATE))
        rows.append(self._row("rare|0", "R1", "sla", ACT_ESCALATE))
        rows.append(self._row("safety|0", "R3", "sla", ACT_ESCALATE))
        pool.aggregate(
            [{"rows": rows}],
            {row["scenario_id"]: row["scenario_id"].split("|")[0] for row in rows},
        )
        return pool

    def test_strata_include_family_signature_and_safety_class(self):
        pool = self._pool()
        stats = pool.stratum_statistics()
        self.assertEqual(len(stats), 3)
        self.assertEqual(sum(item["examples"] for item in stats), 10)
        self.assertEqual({item["safety_class"] for item in stats}, {"R1", "R3"})
        self.assertTrue(all(item["family"] for item in stats))

    def test_sampling_probability_does_not_follow_global_failure_frequency(self):
        pool = self._pool()
        stats = pool.stratum_statistics()
        self.assertTrue(all(abs(item["sampling_probability"] - 1 / 3) < 1e-12 for item in stats))

    def test_mutation_targets_an_implicated_gene_and_records_hit(self):
        pool = self._pool()
        child, audit = pool.mutate_with_record(hand_fsm(), random.Random(3))
        self.assertIsNotNone(audit["stratum"])
        self.assertTrue(audit["gene_hit"])
        self.assertEqual(audit["gene_key"], (OBS_PERMISSION, 0, False))

    def test_repair_and_new_valid_individual_counts_are_recorded(self):
        pool = self._pool()
        key = pool.stratum_statistics()[0]["key"]
        pool.record_repair_outcome(key, valid=True, new_valid=True)
        stats = {item["key"]: item for item in pool.stratum_statistics()}
        self.assertEqual(stats[key]["repair_valid"], 1)
        self.assertEqual(stats[key]["new_valid_individuals"], 1)


class ArchiveTests(unittest.TestCase):
    def test_infeasible_candidates_never_enter_elite_archive(self):
        archive = EliteArchive()
        archive.update([record("bad", [0.1, 0.1], feasible=False)])
        self.assertEqual(archive.records, [])

    def test_archive_deduplicates_and_keeps_non_dominated_candidates(self):
        archive = EliteArchive()
        archive.update([
            record("a", [0.1, 0.4]),
            record("a", [0.1, 0.4]),
            record("b", [0.4, 0.1]),
            record("dominated", [0.5, 0.5]),
        ])
        self.assertEqual({r.fingerprint for r in archive.records}, {"a", "b"})

    def test_family_best_guard_retains_coverage(self):
        archive = EliteArchive()
        archive.update([
            record("global", [0.1, 0.1], family_values={"f1": 0.9}),
            record("rare-family", [0.4, 0.4], family_values={"f2": 0.8}),
        ])
        self.assertIn("rare-family", {r.fingerprint for r in archive.records})

    def test_validation_selector_rejects_train_candidate_records(self):
        train_record = record("train", [0.1, 0.2])
        train_record.source_split = "train"
        with self.assertRaisesRegex(ValueError, "Validation-evaluated"):
            select_validation_candidate([train_record])

    def test_validation_returns_hold_when_no_feasible_candidate_exists(self):
        infeasible = record("bad", [0.1, 0.1], feasible=False)
        result = select_validation_candidate([infeasible])
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["candidate"])
        report = validation_selection_report([infeasible])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("selection_rule", report)
        self.assertEqual(report["pareto_front"], [])

    def test_validation_uses_pareto_then_worst_family_not_sum(self):
        a = record("a", [0.2, 0.2], family_values={"f1": 0.2, "f2": 0.2})
        b = record("b", [0.3, 0.1], family_values={"f1": 0.9, "f2": 0.9})
        result = select_validation_candidate([a, b])
        self.assertEqual(result["status"], "SELECTED")
        self.assertEqual(result["candidate"].fingerprint, "b")
        report = validation_selection_report([a, b])
        self.assertEqual(report["pareto_candidates"], 2)
        self.assertEqual(len(report["pareto_front"]), 2)

    def test_dominated_candidate_cannot_win_by_worst_family(self):
        pareto = record("pareto", [0.2, 0.2], family_values={"f1": 0.2})
        dominated = record("dominated", [0.3, 0.3], family_values={"f1": 1.0})
        result = select_validation_candidate([pareto, dominated])
        self.assertEqual(result["candidate"].fingerprint, "pareto")

    def test_validation_report_is_json_serializable_and_fail_closed(self):
        report = validation_selection_report([
            record("a", [0.2, 0.2]),
            record("bad", [0.1, 0.1], feasible=False),
        ])
        self.assertEqual(report["status"], "SELECTED")
        self.assertEqual(report["candidate"]["fingerprint"], "a")
        self.assertEqual(report["feasible_candidates"], 1)
        self.assertEqual(report["hard_constraint_limit"], 0.0)
        json.dumps(report)


class SharedPoolTests(unittest.TestCase):
    def test_hand_anchor_changes_only_the_anchor_slot(self):
        with_hand = make_shared_initial_pool(41, size=12, include_hand=True)
        without_hand = make_shared_initial_pool(41, size=12, include_hand=False)
        self.assertEqual(fsm_fingerprint(with_hand[0]), fsm_fingerprint(hand_fsm()))
        self.assertNotEqual(fsm_fingerprint(without_hand[0]), fsm_fingerprint(hand_fsm()))
        self.assertEqual(
            [fsm_fingerprint(x) for x in with_hand[1:]],
            [fsm_fingerprint(x) for x in without_hand[1:]],
        )


if __name__ == "__main__":
    unittest.main()
