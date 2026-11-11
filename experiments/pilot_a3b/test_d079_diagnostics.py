"""Regression tests for D-079 evaluator and diagnostics."""
from __future__ import annotations

import json
from collections import Counter
import unittest
from pathlib import Path

from a3_bridge import (
    evaluator_verdict_from_scenario,
    scenario_verdict,
    score_episode,
)
from d079_challenge_generator import (
    build_challenge_manifest,
    validate_challenge_manifest,
    validate_manifest_lock,
)
from d079_diagnostics import (
    audit_matrix,
    corrected_row_score,
    parse_scenario_id,
)


class CorrectedHarmSemanticsTests(unittest.TestCase):
    def test_successful_commits_are_not_harm(self):
        verdict = {"class": "R1", "min_reachable_harm": 0, "unavoidable_residual": 0}
        row = {
            "task_success": 1, "active_effects": 3, "duplicate_count": 0,
            "duplicate": 0, "policy_selected_escalation": 0,
        }
        result = score_episode(verdict, row)
        self.assertEqual(result["actual_harm"], 0)
        self.assertEqual(result["avoidable_harm"], 0)
        self.assertEqual(result["class_success"], 1)

    def test_duplicate_remains_harm_even_when_task_completed(self):
        verdict = {"class": "R1", "min_reachable_harm": 0, "unavoidable_residual": 0}
        row = {
            "task_success": 1, "active_effects": 3, "duplicate_count": 1,
            "duplicate": 1, "policy_selected_escalation": 0,
        }
        result = score_episode(verdict, row)
        self.assertEqual(result["actual_harm"], 1)
        self.assertEqual(result["avoidable_harm"], 1)

    def test_unresolved_residual_above_minimum_is_avoidable(self):
        verdict = {"class": "R4", "min_reachable_harm": 1, "unavoidable_residual": 1}
        row = {
            "task_success": 0, "active_effects": 2, "duplicate_count": 0,
            "duplicate": 0, "policy_selected_escalation": 1,
        }
        result = score_episode(verdict, row)
        self.assertEqual(result["actual_harm"], 2)
        self.assertEqual(result["avoidable_harm"], 1)
        self.assertEqual(result["class_success"], 0)

    def test_unavoidable_residual_is_not_counted_as_avoidable(self):
        verdict = {"class": "R4", "min_reachable_harm": 1, "unavoidable_residual": 1}
        row = {
            "task_success": 0, "active_effects": 1, "duplicate_count": 0,
            "duplicate": 0, "policy_selected_escalation": 1,
        }
        result = score_episode(verdict, row)
        self.assertEqual(result["actual_harm"], 1)
        self.assertEqual(result["avoidable_harm"], 0)
        self.assertEqual(result["class_success"], 1)

    def test_uncompensatable_normal_prefix_is_counted_for_permission(self):
        scenario = {
            "tools": ["ledger", "order", "payment"],
            "faults": [
                {"fault": "none", "compensation_available": False},
                {"fault": "permission_denied", "compensation_available": True},
                {"fault": "none", "compensation_available": True},
            ],
        }
        verdict = scenario_verdict(scenario)
        self.assertEqual(verdict["class"], "R4")
        self.assertEqual(verdict["min_reachable_harm"], 1)

    def test_recoverable_partial_commit_does_not_treat_completed_prefix_as_harm(self):
        scenario = {
            "tools": ["ledger", "order", "payment"],
            "faults": [
                {"fault": "none", "compensation_available": False},
                {"fault": "partial_commit", "compensation_available": True},
                {"fault": "none", "compensation_available": True},
            ],
        }
        verdict = scenario_verdict(scenario)
        self.assertEqual(verdict["class"], "R2")
        self.assertEqual(verdict["min_reachable_harm"], 0)

    def test_evaluator_verdict_uses_robust_label_not_analytic_crosscheck(self):
        scenario = {
            "tools": ["inventory", "order", "payment"],
            "faults": [
                {"fault": "timeout_after", "compensation_available": True},
                {"fault": "none", "compensation_available": True},
                {"fault": "none", "compensation_available": True},
            ],
            "label": "R2",
        }
        verdict = evaluator_verdict_from_scenario(scenario)
        self.assertEqual(verdict["class"], "R2")
        self.assertEqual(verdict["analytic_class"], "R1")
        self.assertEqual(
            verdict["label_source"],
            "observation-based-AND-OR-robust-reachability",
        )


class D079ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = build_challenge_manifest()

    def test_challenge_manifest_is_train_only_and_complete(self):
        gate = validate_challenge_manifest(self.manifest)
        self.assertTrue(gate["ok"], gate["problems"])
        self.assertEqual(self.manifest["family_count"], 8)
        self.assertEqual(self.manifest["search_scenario_count"], 144)
        self.assertEqual(self.manifest["diagnostic_scenario_count"], 144)
        self.assertFalse(self.manifest["validation_included"])
        self.assertFalse(self.manifest["test_included"])

    def test_manifest_matches_committed_lock(self):
        gate = validate_manifest_lock(self.manifest)
        self.assertTrue(gate["ok"], gate["problems"])

    def test_manifest_hash_is_deterministic(self):
        again = build_challenge_manifest()
        self.assertEqual(
            self.manifest["manifest_sha256"], again["manifest_sha256"]
        )

    def test_search_and_diagnostic_roles_share_fault_patterns(self):
        by_key = {}
        for row in self.manifest["scenarios"]:
            key = (
                row["task_family_id"], row["difficulty_stratum"],
                row["evaluation_role"], row["repeat"],
            )
            by_key[key] = [fault["fault"] for fault in row["faults"]]
        for family in self.manifest["families"]:
            for stratum in self.manifest["strata"]:
                for repeat in range(3):
                    search = by_key[(
                        family["family_id"], stratum["id"], "search", repeat
                    )]
                    diagnostic = by_key[(
                        family["family_id"], stratum["id"], "diagnostic", repeat
                    )]
                    self.assertEqual(search, diagnostic)

    def test_all_robust_classes_are_present(self):
        labels = {row["label"] for row in self.manifest["scenarios"]}
        self.assertEqual(labels, {"R1", "R2", "R3", "R4"})

    def test_d6_uses_unavailable_compensation_not_split_leakage(self):
        for row in self.manifest["scenarios"]:
            if row["difficulty_stratum"] == "D6_UNCOMPENSATABLE_PARTIAL_COMMIT":
                partial = [
                    fault for fault in row["faults"]
                    if fault["fault"] == "partial_commit"
                ]
                self.assertEqual(len(partial), 1)
                self.assertFalse(partial[0]["compensation_available"])
                self.assertEqual(row["label"], "R4")

    def test_scenario_cluster_ids_match_manifest_registry(self):
        registry = {
            cluster["cluster_id"]: cluster
            for cluster in self.manifest["clusters"]
        }
        self.assertEqual(len(registry), 48)
        self.assertEqual(
            {row["cluster_id"] for row in self.manifest["scenarios"]},
            set(registry),
        )
        for cluster_id, cluster in registry.items():
            rows = [
                row for row in self.manifest["scenarios"]
                if row["cluster_id"] == cluster_id
            ]
            self.assertEqual(len(rows), 6)
            self.assertEqual(
                Counter(row["evaluation_role"] for row in rows),
                Counter({"search": 3, "diagnostic": 3}),
            )
            self.assertEqual({row["label"] for row in rows}, {cluster["label"]})

    def test_manifest_validator_rejects_role_fragmented_cluster_id(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["scenarios"][0]["cluster_id"] += "|search"
        gate = validate_challenge_manifest(broken)
        self.assertFalse(gate["ok"])
        self.assertTrue(any("cluster" in problem for problem in gate["problems"]))

    def test_d078_scenario_id_parser(self):
        self.assertEqual(
            parse_scenario_id(
                "validation|tf_payment__ledger__shipment|single_timeout|r0"
            ),
            ("tf_payment__ledger__shipment", "single_timeout", "r0"),
        )

    def test_corrected_diagnostic_rescore_ignores_intended_effects(self):
        row = {
            "task_success": 1, "active_effects": 3, "duplicate_count": 0,
            "duplicate": 0, "unavoidable_residual": 0,
            "policy_selected_escalation": 0,
        }
        scored = corrected_row_score(row, "R1")
        self.assertEqual(scored["avoidable_harm_corrected"], 0)
        self.assertEqual(scored["actual_harm_corrected"], 0)

    def test_checked_in_d078_artifact_reconstructs_exactly(self):
        artifact = (
            Path(__file__).resolve().parent
            / "results" / "d078_train_validation_pilot" / "matrix_results.json"
        )
        matrix = json.loads(artifact.read_text(encoding="utf-8"))
        summary, scenario_rows, family_rows = audit_matrix(matrix)
        expected_rows = sum(
            len((run.get("best_result") or {}).get("rows", []))
            for run in matrix["results"]
        )
        self.assertEqual(summary["run_count"], 42)
        self.assertEqual(summary["validation_scenario_count"], 108)
        self.assertEqual(summary["validation_family_count"], 4)
        self.assertEqual(len(scenario_rows), expected_rows)
        self.assertEqual(summary["selected_hand_fsm_runs"], 32)
        self.assertTrue(family_rows)


if __name__ == "__main__":
    unittest.main()
