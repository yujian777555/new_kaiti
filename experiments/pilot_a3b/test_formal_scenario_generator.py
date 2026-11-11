import unittest

from formal_scenario_generator import (
    ALLOWED_CLASSES_BY_COMPOSITION,
    FORMAL_COMPOSITIONS,
    SEED_BASE,
    _build_cluster,
    make_fault_vector,
    stable_seed,
)
from task_semantics import build_split_catalog


class FormalScenarioGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family = build_split_catalog()["train"][0]
        cls.tools = tuple(cls.family["tools"])

    def test_nine_compositions_are_frozen(self):
        self.assertEqual(len(FORMAL_COMPOSITIONS), 9)
        self.assertEqual(len(ALLOWED_CLASSES_BY_COMPOSITION), 9)

    def test_all_fault_vectors_align_with_three_tools(self):
        for composition in FORMAL_COMPOSITIONS:
            faults = make_fault_vector(self.tools, composition, 11, 29)
            self.assertEqual(len(faults), 3)
            for fault in faults:
                self.assertIn(fault["fault"], {
                    "none", "timeout_before", "timeout_after", "delayed_visibility",
                    "partial_commit", "rate_limit", "schema_drift", "permission_denied",
                })
                self.assertGreaterEqual(fault["delay"], 0)
                self.assertGreaterEqual(fault["retry_after"], 0)

    def test_pattern_is_constant_across_nested_repeats(self):
        family_id = self.family["family_id"]
        comp = "single_timeout"
        pattern_seed = stable_seed(SEED_BASE, "train", family_id, comp, "pattern")
        rows = [
            make_fault_vector(
                self.tools, comp, pattern_seed,
                stable_seed(SEED_BASE, "train", family_id, comp, rep),
            )
            for rep in range(3)
        ]
        self.assertEqual(
            [[f["fault"] for f in row] for row in rows],
            [[f["fault"] for f in row] for row in rows[:1]] * 3,
        )

    def test_formal_labeler_uses_three_step_safe_horizon(self):
        from formal_scenario_generator import LABELER_HORIZON, LABELER_MAX_NODES
        self.assertEqual(LABELER_HORIZON, 24)
        self.assertEqual(LABELER_MAX_NODES, 500000)

    def test_seed_derivation_is_stable_and_split_specific(self):
        a = stable_seed(SEED_BASE, "train", "family", "comp", 0)
        b = stable_seed(SEED_BASE, "train", "family", "comp", 0)
        c = stable_seed(SEED_BASE, "test", "family", "comp", 0)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_reachability_labels_follow_allowed_class_sets(self):
        for composition, allowed in ALLOWED_CLASSES_BY_COMPOSITION.items():
            cluster, scenarios, problems = _build_cluster(
                self.family, "train", composition
            )
            self.assertFalse(problems, problems)
            self.assertIn(cluster["label"], allowed)
            self.assertEqual(cluster["analytic_label"], scenarios[0]["analytic_label"])
            self.assertTrue(
                cluster["label_agreement"]
                or cluster["analytic_disagreement_reason"] is not None
            )
            self.assertEqual(len(scenarios), 3)
            self.assertEqual({s["label"] for s in scenarios}, {cluster["label"]})

    def test_recovery_labeler_starts_at_first_fault_after_committed_prefix(self):
        from a3_verdicts import classify_scenario
        scenario = {
            "tools": ["inventory", "order", "ledger"],
            "composition": "permission_after_compensatable_prefix",
            "faults": [
                {"fault": "none", "compensation_available": True},
                {"fault": "permission_denied", "compensation_available": True},
                {"fault": "none", "compensation_available": False},
            ],
        }
        result = classify_scenario(scenario, horizon=24, max_nodes=500000)
        self.assertEqual(result["class"], "R3")
        self.assertEqual(result["analytic_class"], "R3")
        self.assertTrue(result["agreement"])

    def test_partial_compensation_failure_is_not_assumed_successful(self):
        faults = make_fault_vector(self.tools, "partial_comp_failure", 11, 29)
        partial_idx = next(i for i, f in enumerate(faults) if f["fault"] == "partial_commit")
        self.assertFalse(faults[partial_idx]["compensation_available"])

    def test_primary_composition_denominator_is_seven_of_nine(self):
        eligible = sum(
            1 for allowed in ALLOWED_CLASSES_BY_COMPOSITION.values()
            if allowed.issubset({"R1", "R2"})
        )
        self.assertEqual(eligible, 7)

    def test_only_non_idempotent_timeout_after_explains_legacy_disagreement(self):
        from formal_scenario_generator import _explain_analytic_disagreement
        scenario = {
            "tools": ["inventory", "order", "ledger"],
            "faults": [
                {"fault": "timeout_after"},
                {"fault": "rate_limit"},
                {"fault": "none"},
            ],
        }
        reason = _explain_analytic_disagreement(scenario, "R2", "R1")
        self.assertIsNotNone(reason)
        scenario["tools"][0] = "calendar"
        self.assertIsNone(_explain_analytic_disagreement(scenario, "R2", "R1"))
        scenario["tools"][0] = "inventory"
        scenario["faults"][0]["fault"] = "delayed_visibility"
        self.assertIsNotNone(_explain_analytic_disagreement(scenario, "R2", "R1"))


if __name__ == "__main__":
    unittest.main()
