"""Sanity tests: analytic A-3 verdicts follow the 55-R1 ladder."""
import unittest

from a3_bridge import scenario_verdict
from pilot_a3 import TASKS, make_fault_vector


def sc(task, comp, seed=7):
    return {
        "scenario_id": f"t|{task}|{comp}|{seed}",
        "task": task,
        "composition": comp,
        "seed": seed,
        "tools": TASKS[task],
        "faults": make_fault_vector(task, comp, seed),
    }


class A3VerdictTests(unittest.TestCase):
    def test_single_timeout_is_r1_or_r2(self):
        for seed in range(20):
            s = sc("inventory_order_payment", "single_timeout", seed)
            self.assertIn(scenario_verdict(s)["class"], ("R1", "R2"))

    def test_partial_comp_failure_is_r4(self):
        for seed in range(20):
            s = sc("inventory_order_payment", "partial_comp_failure", seed)
            self.assertEqual(scenario_verdict(s)["class"], "R4", msg=str(s["faults"]))

    def test_permission_family_is_r3_or_r4(self):
        for seed in range(20):
            s = sc("calendar_order_ledger", "delay_rate_permission", seed)
            self.assertIn(scenario_verdict(s)["class"], ("R3", "R4"), msg=str(s["faults"]))

    def test_partial_then_delay_with_comp_is_r2(self):
        seen = set()
        for seed in range(30):
            s = sc("customer_order_shipment", "partial_then_delay", seed)
            seen.add(scenario_verdict(s)["class"])
        self.assertIn("R2", seen)

    def test_permission_with_uncompensated_prefix_commit_is_r4(self):
        s = {
            "scenario_id": "manual",
            "task": "subscription_ledger_notification",
            "composition": "manual",
            "seed": 1,
            "tools": TASKS["subscription_ledger_notification"],
            "faults": [
                {"fault": "timeout_after", "delay": 2, "retry_after": 0, "compensation_available": False},
                {"fault": "permission_denied", "delay": 0, "retry_after": 0, "compensation_available": False},
                {"fault": "none", "delay": 0, "retry_after": 0, "compensation_available": True},
            ],
        }
        self.assertEqual(scenario_verdict(s)["class"], "R4")

    def test_verdicts_deterministic_and_have_harm_fields(self):
        for comp in ("single_timeout", "partial_comp_failure", "triple_mixed"):
            v1 = scenario_verdict(sc("inventory_order_payment", comp, 11))
            v2 = scenario_verdict(sc("inventory_order_payment", comp, 11))
            self.assertEqual(v1, v2)
            self.assertIn("unavoidable_residual", v1)
            self.assertIn("min_reachable_harm", v1)


if __name__ == "__main__":
    unittest.main()
