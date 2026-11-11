"""Synthetic SBCG evolution-loop tests; no real benchmark or Test access."""
import random
import unittest
from unittest.mock import patch

from sbcg import make_shared_initial_pool, fsm_fingerprint
from sbcg_runner import run_sbcg_evolution


SCENARIOS = [
    {"scenario_id": "train|f1|c1|r0", "split": "train", "task": "f1", "composition": "c1"},
    {"scenario_id": "train|f2|c1|r0", "split": "train", "task": "f2", "composition": "c1"},
]
VERDICTS = {s["scenario_id"]: {"class": "R1"} for s in SCENARIOS}


def fake_metrics(fsm, scenarios, verdicts, _weights=None):
    # Deterministic synthetic outcomes; no simulator or real benchmark is called.
    action = fsm.genes_list()[0].action
    cond = 0.25 + 0.05 * (len(action) % 5)
    rows = []
    for scenario in scenarios:
        rows.append({
            "scenario_id": scenario["scenario_id"],
            "label": "R1",
            "class_success": 1,
            "decision_trace": [],
        })
    return {
        "cond_rec": cond,
        "avoid_resid": 0.0,
        "unnec_esc": 0.0,
        "unnec_actions_r12": 0.2,
        "corr_esc": 1.0,
        "containment": 1.0,
        "dup": 0.0,
        "sla_viol": 0.0,
        "violations": 0.0,
        "objectives": (1.0 - cond, 0.0, 0.02),
        "rows": rows,
    }


def run_with(patch_target, **overrides):
    kwargs = {
        "initial_pool": make_shared_initial_pool(41, size=12, include_hand=True),
        "scenarios": SCENARIOS,
        "verdicts": VERDICTS,
        "pop_size": 4,
        "generations": 2,
        "eval_budget": 4 * 3 * len(SCENARIOS),
        "seed": 7,
    }
    kwargs.update(overrides)
    with patch(patch_target, side_effect=fake_metrics):
        return run_sbcg_evolution(**kwargs)


class EvolutionLoopTests(unittest.TestCase):
    def test_reproducible_budget_and_cache_accounting(self):
        first = run_with("sbcg.evaluate_controller")
        second = run_with("sbcg.evaluate_controller")
        self.assertEqual(first["history"], second["history"])
        self.assertEqual(first["unique_evaluations"], second["unique_evaluations"])
        self.assertEqual(first["cache_hits"], second["cache_hits"])
        self.assertEqual(first["initial_pool_sha256"], second["initial_pool_sha256"])
        self.assertLessEqual(first["episodes"], first["eval_budget"])
        self.assertEqual(first["unique_evaluations"] + first["cache_hits"], first["evaluation_calls"])

    def test_full_candidate_uses_five_objectives_and_three_mechanisms(self):
        result = run_with("sbcg.evaluate_controller")
        self.assertTrue(result["config"]["use_five_objectives"])
        self.assertTrue(result["config"]["use_stratified_counterexamples"])
        self.assertTrue(result["config"]["use_elite_archive"])
        self.assertEqual(result["selection"]["status"], "PENDING_VALIDATION")
        self.assertIsNone(result["selection"]["candidate"])
        self.assertTrue(result["train_candidates"])
        self.assertEqual(len(result["train_candidates"][0]["objectives"]), 5)
        self.assertEqual(result["reference_direction_count"], 35)

    def test_m1_ablation_uses_only_legacy_three_objectives(self):
        result = run_with("sbcg.evaluate_controller", use_five_objectives=False)
        self.assertFalse(result["config"]["use_five_objectives"])
        self.assertEqual(len(result["train_candidates"][0]["objectives"]), 3)

    def test_m2_ablation_uses_standard_mutation(self):
        result = run_with("sbcg.evaluate_controller", use_stratified_counterexamples=False)
        self.assertFalse(result["config"]["use_stratified_counterexamples"])
        self.assertEqual(result["strata"], [])
        self.assertEqual(result["mutation_audit"], [])

    def test_stratified_failures_produce_gene_hit_and_repair_audit(self):
        def failing(fsm, scenarios, verdicts, _weights=None):
            result = fake_metrics(fsm, scenarios, verdicts)
            result["avoid_resid"] = 0.2
            for row in result["rows"]:
                row["class_success"] = 0
                row["decision_trace"] = [("PERMISSION", 0, False, "RETRY")]
                row["avoidable_harm"] = 1
                row["duplicate"] = 0
                row["sla_violation"] = 0
                row["compensation_failure"] = False
                row["policy_selected_escalation"] = 0
            return result
        with patch("sbcg.evaluate_controller", side_effect=failing):
            result = run_sbcg_evolution(
                make_shared_initial_pool(41, size=12), SCENARIOS, VERDICTS,
                pop_size=4, generations=1, eval_budget=16, seed=7,
            )
        self.assertEqual(len(result["strata"]), 2)
        self.assertTrue(result["mutation_audit"])
        self.assertTrue(all(item["gene_hit"] for item in result["mutation_audit"]))
        self.assertTrue(all(item["repair_attempted"] for item in result["mutation_audit"]))

    def test_m3_ablation_removes_hand_anchor_and_archive(self):
        result = run_with(
            "sbcg.evaluate_controller",
            use_elite_archive=False,
            remove_hand_from_pool=True,
        )
        self.assertFalse(result["config"]["use_elite_archive"])
        self.assertTrue(result["config"]["remove_hand_from_pool"])
        self.assertEqual(result["archive"], [])
        self.assertNotIn(
            fsm_fingerprint(make_shared_initial_pool(41, size=12, include_hand=True)[0]),
            result["initial_pool_fingerprints"],
        )

    def test_infeasible_population_returns_hold(self):
        def unsafe(fsm, scenarios, verdicts, _weights=None):
            result = fake_metrics(fsm, scenarios, verdicts)
            result["dup"] = 0.1
            return result
        with patch("sbcg.evaluate_controller", side_effect=unsafe):
            result = run_sbcg_evolution(
                make_shared_initial_pool(41, size=12), SCENARIOS, VERDICTS,
                pop_size=4, generations=1, eval_budget=16, seed=7,
            )
        self.assertEqual(result["selection"]["status"], "PENDING_VALIDATION")
        self.assertEqual(result["train_feasible_candidates"], 0)

    def test_invalid_optimizer_or_test_split_fails_before_fitness(self):
        with patch("sbcg.evaluate_controller", side_effect=AssertionError("fitness must not run")):
            with self.assertRaisesRegex(ValueError, "optimizer"):
                run_sbcg_evolution(
                    make_shared_initial_pool(41, size=12), SCENARIOS, VERDICTS,
                    pop_size=4, generations=1, eval_budget=16, seed=7, optimizer="bad",
                )
            with self.assertRaisesRegex(ValueError, "train split only"):
                run_sbcg_evolution(
                    make_shared_initial_pool(41, size=12),
                    [{"scenario_id": "sentinel", "split": "test"}], {},
                    pop_size=4, generations=1, eval_budget=16, seed=7,
                )


if __name__ == "__main__":
    unittest.main()
