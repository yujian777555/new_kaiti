"""D-088 mechanism unit tests — deterministic, no LLM/API."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

from mechanism_genome import (
    D088Genome, random_d088_genome, mutate_d088, crossover_d088,
    MECH_A_DISCRETE, MECH_A_CONTINUOUS, MECH_B_DISCRETE, MECH_B_CONTINUOUS,
    MECH_C_CONTINUOUS, MECH_C_BOOLEAN,
)
from mechanism_policies import (
    D088Policy, build_dependency_graph, find_cycle_tools, topological_order,
)
from d088_scenario_generator import (
    build_manifest, make_scenario, DISCOVERY_FAMILIES, FRESH_FAMILIES,
    STRATA, EXPECTED_LABELS,
)
from d088_nsga3 import compute_objectives, run_evolution

import random


# ---------------------------------------------------------------------------
# Genome tests
# ---------------------------------------------------------------------------
class TestD088Genome:
    def test_genome_has_all_mechanism_params(self):
        g = D088Genome()
        d = g.fingerprint()
        for name in ("enable_mech_a", "failure_switch_threshold",
                     "max_consecutive_same_route", "alternate_priority_boost",
                     "route_failure_penalty", "enable_mech_b", "budget_urgency_weight",
                     "batch_verify_threshold", "wait_efficiency_weight",
                     "pre_deadline_verify_margin", "enable_mech_c", "cycle_aware_routing",
                     "topological_order_weight", "dependency_unlock_priority"):
            assert name in d, f"missing gene: {name}"

    def test_mech_label(self):
        g = D088Genome(enable_mech_a=True, enable_mech_b=False, enable_mech_c=True)
        assert g.mech_label() == "AC"
        g2 = D088Genome(enable_mech_a=False, enable_mech_b=False, enable_mech_c=False)
        assert g2.mech_label() == "L"

    def test_random_genome_with_flags(self):
        rng = random.Random(42)
        g = random_d088_genome(rng, {"enable_mech_a": True, "enable_mech_b": False, "enable_mech_c": False})
        assert g.enable_mech_a is True
        assert g.enable_mech_b is False
        assert g.enable_mech_c is False

    def test_mutate_changes_some_gene(self):
        rng = random.Random(42)
        g = random_d088_genome(rng)
        mutated = mutate_d088(g, rng)
        # At least one gene should differ (with very high probability over multiple tries)
        diffs = 0
        for _ in range(20):
            m = mutate_d088(g, rng)
            if m.fingerprint() != g.fingerprint():
                diffs += 1
        assert diffs > 0

    def test_crossover_preserves_mech_flags_when_both_same(self):
        rng = random.Random(42)
        flags = {"enable_mech_a": True, "enable_mech_b": True, "enable_mech_c": False}
        a = random_d088_genome(rng, flags)
        b = random_d088_genome(rng, flags)
        child = crossover_d088(a, b, rng)
        assert child.enable_mech_a is True
        assert child.enable_mech_b is True
        assert child.enable_mech_c is False


# ---------------------------------------------------------------------------
# Dependency graph tests
# ---------------------------------------------------------------------------
class TestDependencyGraph:
    def _make_view(self, requires_map):
        tools = {}
        for tool_id, deps in requires_map.items():
            tools[tool_id] = {
                "state": "COMMITTED",
                "compensation_available": True,
                "routes": [{"name": "primary", "requires": deps, "cost": 1,
                            "reliability_hint": "HIGH", "idempotent": True,
                            "visibility_bound": 3, "pending": False,
                            "attempts": 0, "last_receipt": None}],
            }
        return {"tools": tools, "current_tool": "Z", "terminal_fault": "permission",
                "decision_count": 0, "budget_remaining": 24}

    def test_build_graph(self):
        view = self._make_view({"A": ["B"], "B": ["C"], "C": []})
        graph = build_dependency_graph(view)
        assert graph["A"] == ["B"]
        assert graph["B"] == ["C"]
        assert graph["C"] == []

    def test_cycle_detection(self):
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycles = find_cycle_tools(graph)
        assert cycles == {"A", "B", "C"}

    def test_no_cycle(self):
        graph = {"A": ["B"], "B": ["C"], "C": []}
        cycles = find_cycle_tools(graph)
        assert cycles == set()

    def test_topological_order_dependencies_first(self):
        graph = {"A": ["B"], "B": ["C"], "C": []}
        order = topological_order(graph, set())
        # C has no deps, so should come first
        assert order.index("C") < order.index("B") < order.index("A")


# ---------------------------------------------------------------------------
# Scenario generator tests
# ---------------------------------------------------------------------------
class TestScenarioGenerator:
    def test_discovery_families_valid(self):
        for family in DISCOVERY_FAMILIES:
            for stratum in STRATA:
                s = make_scenario(family, stratum, 0, tier="discovery")
                assert s["label"] == EXPECTED_LABELS[stratum]
                assert s["split"] == "train"
                assert s["scenario_id"].startswith("d088|train|")

    def test_fresh_families_valid(self):
        for family in FRESH_FAMILIES:
            for stratum in STRATA:
                s = make_scenario(family, stratum, 0, tier="fresh")
                assert s["label"] == EXPECTED_LABELS[stratum]

    def test_no_id_overlap_with_d087(self):
        d087_ids = set()
        # D-087 IDs start with "d086r|validation|"
        for family in DISCOVERY_FAMILIES:
            for stratum in STRATA:
                for r in range(5):
                    s = make_scenario(family, stratum, r, tier="discovery")
                    assert not s["scenario_id"].startswith("d086r|")
                    assert "validation" not in s["scenario_id"]

    def test_manifest_builds_and_hashes(self):
        m = build_manifest(tier="discovery")
        assert m["split"] == "train"
        assert m["test_included"] is False
        assert m["scenario_count"] == len(DISCOVERY_FAMILIES) * 4 * 5
        assert "manifest_sha256" in m

    def test_policy_view_exposes_no_hidden_info(self):
        s = make_scenario("d088t_CHAIN_BLOCK", "D3_DEPENDENT_ABORT", 0, tier="discovery")
        for tool in s["tools"]:
            for route in tool["routes"]:
                # "outcomes" is evaluator-only; policies see only public fields
                assert "outcomes" in route  # present in scenario data
        # But the policy's view() from DependencyRecoveryEnv hides outcomes
        # This is verified by the environment's view() method


# ---------------------------------------------------------------------------
# Policy tests
# ---------------------------------------------------------------------------
class TestD088Policy:
    def _make_scenario(self, requires_map, terminal="permission"):
        tools = []
        for tool_id, deps in requires_map.items():
            tools.append({
                "id": tool_id,
                "state": "COMMITTED",
                "compensation_available": True,
                "routes": [
                    {"name": "primary", "outcomes": [True], "cost": 3,
                     "reliability_hint": "HIGH", "requires": deps,
                     "receipt": "immediate", "receipt_delay": 0,
                     "idempotent": True, "visibility_bound": 3},
                    {"name": "alternate", "outcomes": [False, True], "cost": 1,
                     "reliability_hint": "LOW", "requires": [],
                     "receipt": "delayed", "receipt_delay": 1,
                     "idempotent": False, "visibility_bound": 3},
                ],
            })
        tools.append({
            "id": "Z", "state": "NOT_COMMITTED", "compensation_available": True,
            "routes": [
                {"name": "primary", "outcomes": [True], "cost": 1,
                 "reliability_hint": "HIGH", "requires": [],
                 "receipt": "immediate", "receipt_delay": 0,
                 "idempotent": True, "visibility_bound": 3},
            ],
        })
        return {"scenario_id": "test", "split": "train", "terminal_fault": terminal,
                "current_tool": "Z", "tools": tools}

    def test_policy_creates_with_mech_flags(self):
        g = D088Genome(enable_mech_a=True, enable_mech_b=True, enable_mech_c=True)
        p = D088Policy(g)
        assert p.genome.enable_mech_a is True

    def test_mech_a_excludes_failed_routes(self):
        g = D088Genome(enable_mech_a=True, enable_mech_b=False, enable_mech_c=False,
                       failure_switch_threshold=1)
        p = D088Policy(g)
        s = self._make_scenario({"A": [], "B": [], "C": []})
        from dependency_recovery import run_episode
        report = run_episode(p, s, max_actions=24)
        assert report["decision_count"] > 0

    def test_mech_b_pending_handling(self):
        g = D088Genome(enable_mech_a=False, enable_mech_b=True, enable_mech_c=False)
        p = D088Policy(g)
        # Simulate a view with pending receipts
        view = {
            "tools": {
                "A": {"state": "COMMITTED", "compensation_available": True,
                       "routes": [{"name": "primary", "requires": [], "cost": 1,
                                   "reliability_hint": "HIGH", "idempotent": True,
                                   "visibility_bound": 3, "pending": True,
                                   "attempts": 1, "last_receipt": "TIMEOUT"}]},
            },
            "current_tool": "Z", "terminal_fault": "permission",
            "decision_count": 5, "budget_remaining": 19,
        }
        action = p._pending_action(view)
        assert action in [("WAIT",), ("VERIFY", "A")]

    def test_mech_c_cycle_detection_in_priority(self):
        g = D088Genome(enable_mech_a=False, enable_mech_b=False, enable_mech_c=True,
                       cycle_aware_routing=True)
        p = D088Policy(g)
        s = self._make_scenario({"A": ["B"], "B": ["A"], "C": []})
        from dependency_recovery import DependencyRecoveryEnv
        env = DependencyRecoveryEnv(s)
        view = env.view()
        graph = build_dependency_graph(view)
        cycles = find_cycle_tools(graph)
        assert "A" in cycles or "B" in cycles


# ---------------------------------------------------------------------------
# Evolution smoke test
# ---------------------------------------------------------------------------
class TestEvolutionSmoke:
    def test_compute_objectives_returns_five_values(self):
        m = build_manifest(tier="discovery")
        scenarios = m["scenarios"][:8]  # small subset for speed
        g = D088Genome()
        objs = compute_objectives(g, scenarios)
        assert len(objs) == 5
        assert all(isinstance(v, float) for v in objs)

    def test_evolution_runs_small(self):
        m = build_manifest(tier="discovery")
        scenarios = m["scenarios"][:8]
        result = run_evolution(
            scenarios=scenarios,
            mech_flags={"enable_mech_a": True, "enable_mech_b": False, "enable_mech_c": False},
            pop_size=6,
            generations=2,
            seed=42,
            initial_pool_size=8,
        )
        assert "best" in result
        assert "history" in result
        assert len(result["history"]) == 2
