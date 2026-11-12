"""D-088 Train-only scenario generator with new family topologies.

Generates fresh families under namespace `d088|train|...` that do NOT overlap
with D-086/D-087/D-079/D-085 scenario IDs.  Two tiers:
  - Discovery families: for mechanism development and evolutionary search.
  - Fresh families: for post-freeze independent internal replication.

All scenarios use the D-086 DependencyRecoveryEnv contract.
Only public information (dependencies, contracts, hints, receipt types)
is exposed to policies.  Hidden outcomes and true delays are evaluator-only.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

_D087_SRC = Path(__file__).resolve().parent.parent.parent / "data" / "historical" / "d087" / "source"
if str(_D087_SRC) not in sys.path:
    sys.path.insert(0, str(_D087_SRC))

from dependency_recovery import classify_scenario  # noqa: E402


def stable_seed(*args) -> int:
    """Deterministic seed derivation from arbitrary hashable arguments."""
    h = hashlib.sha256(":".join(str(a) for a in args).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


STRATA = (
    "D1_RECOVERABLE_TIMEOUT",
    "D2_PARTIAL_THEN_REDO",
    "D3_DEPENDENT_ABORT",
    "D4_BLOCKED_COMPENSATION",
)
EXPECTED_LABELS = dict(zip(STRATA, ("R1", "R2", "R3", "R4")))

# ---------------------------------------------------------------------------
# New family topologies (different from rv01-rv04)
# ---------------------------------------------------------------------------
# Each family defines: dependency graph, cost structure, delay patterns,
# and alternate outcome patterns.  All are Train-only.
DISCOVERY_FAMILIES = {
    "d088t_CHAIN_BLOCK": {
        "requires": {"A": ["B"], "B": ["C"], "C": ["D"], "D": []},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 3,
        "alternate_cost": 1,
        "block": "B",
        "primary_delay": [0, 1, 0, 0, 1],
        "alternate_delay": [1, 0, 2, 1, 0],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, False, True]],
        "primary_patterns": [[True], [False, True], [False, False, True], [True], [False, True]],
    },
    "d088t_FORK_JOIN": {
        "requires": {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 2,
        "alternate_cost": 1,
        "block": "D",
        "primary_delay": [0, 0, 1, 0, 0],
        "alternate_delay": [0, 1, 0, 2, 1],
        "alternate_patterns": [[True], [True], [False, True], [True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [True]],
    },
    "d088t_CYCLE_ALT": {
        "requires": {"A": ["C"], "B": ["A"], "C": ["B"]},
        "tools": ["A", "B", "C"],
        "primary_cost": 3,
        "alternate_cost": 1,
        "block": "A",
        "primary_delay": [1, 0, 0, 1, 0],
        "alternate_delay": [0, 1, 2, 0, 1],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [False, True]],
    },
    "d088t_PARALLEL_SINK": {
        "requires": {"A": [], "B": [], "C": ["A", "B"]},
        "tools": ["A", "B", "C"],
        "primary_cost": 2,
        "alternate_cost": 1,
        "block": "C",
        "primary_delay": [0, 0, 1, 0, 1],
        "alternate_delay": [1, 0, 0, 1, 0],
        "alternate_patterns": [[True], [True], [False, True], [True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [True]],
    },
    "d088t_DEEP_CHAIN": {
        "requires": {"A": ["B"], "B": ["C"], "C": []},
        "tools": ["A", "B", "C"],
        "primary_cost": 4,
        "alternate_cost": 1,
        "block": "C",
        "primary_delay": [0, 1, 0, 0, 0],
        "alternate_delay": [1, 0, 1, 2, 0],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [True]],
        "primary_patterns": [[True], [False, True], [False, False, True], [True], [False, True]],
    },
    "d088t_STAR_HUB": {
        "requires": {"A": [], "B": ["A"], "C": ["A"], "D": ["A"]},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 3,
        "alternate_cost": 1,
        "block": "A",
        "primary_delay": [0, 0, 1, 1, 0],
        "alternate_delay": [1, 1, 0, 0, 1],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [True]],
        "primary_patterns": [[True], [True], [False, True], [True], [False, True]],
    },
}

FRESH_FAMILIES = {
    "d088f_DIAMOND": {
        "requires": {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 2,
        "alternate_cost": 1,
        "block": "C",
        "primary_delay": [0, 1, 0, 0, 1],
        "alternate_delay": [1, 0, 1, 2, 0],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, False, True], [True]],
    },
    "d088f_LADDER": {
        "requires": {"A": ["B"], "B": ["C"], "C": ["D"], "D": []},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 3,
        "alternate_cost": 1,
        "block": "C",
        "primary_delay": [1, 0, 0, 1, 0],
        "alternate_delay": [0, 1, 0, 0, 2],
        "alternate_patterns": [[True], [True], [False, True], [True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [True]],
    },
    "d088f_MULTI_FORK": {
        "requires": {"A": [], "B": ["A"], "C": ["A"], "D": ["A"]},
        "tools": ["A", "B", "C", "D"],
        "primary_cost": 2,
        "alternate_cost": 1,
        "block": "B",
        "primary_delay": [0, 0, 1, 0, 1],
        "alternate_delay": [1, 0, 0, 1, 0],
        "alternate_patterns": [[True], [True], [False, True], [True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [True]],
    },
    "d088f_LOOP_BREAK": {
        "requires": {"A": ["B"], "B": ["A"], "C": []},
        "tools": ["A", "B", "C"],
        "primary_cost": 3,
        "alternate_cost": 1,
        "block": "B",
        "primary_delay": [0, 1, 0, 0, 1],
        "alternate_delay": [1, 0, 2, 1, 0],
        "alternate_patterns": [[True], [False, True], [True], [False, True], [False, True]],
        "primary_patterns": [[True], [False, True], [True], [False, True], [True]],
    },
}

REPEATS = 5


def _route_for_tool(spec: dict, tool_id: str, alternate: bool, repeat: int) -> dict:
    primary_patterns = spec.get("primary_patterns", [[True]] * 5)
    outcomes = spec["alternate_patterns"][repeat] if alternate else primary_patterns[repeat]
    delay = spec["alternate_delay"][repeat] if alternate else spec["primary_delay"][repeat]
    return {
        "name": "alternate" if alternate else "primary",
        "outcomes": list(outcomes),
        "cost": spec["alternate_cost"] if alternate else spec["primary_cost"],
        "reliability_hint": "LOW" if alternate else "HIGH",
        "requires": [] if alternate else list(spec["requires"].get(tool_id, [])),
        "receipt": "delayed" if delay else "immediate",
        "receipt_delay": delay,
        "idempotent": delay == 0,
        "visibility_bound": 3,
    }


def make_scenario(family: str, stratum: str, repeat: int,
                  tier: str = "discovery", seed_base: int = 2026120100) -> dict:
    """Build one D-088 Train-only scenario."""
    specs = DISCOVERY_FAMILIES if tier == "discovery" else FRESH_FAMILIES
    if family not in specs or stratum not in STRATA or repeat not in range(REPEATS):
        raise ValueError(f"invalid D-088 family/stratum/repeat: {family}/{stratum}/{repeat}")
    spec = specs[family]
    terminal = {
        "D1_RECOVERABLE_TIMEOUT": "timeout_before",
        "D2_PARTIAL_THEN_REDO": "partial_recover",
    }.get(stratum, "permission")

    tools = []
    main_tools = spec["tools"]
    for tool_id in main_tools:
        tools.append({
            "id": tool_id,
            "state": "COMMITTED",
            "compensation_available": not (
                stratum == "D4_BLOCKED_COMPENSATION" and tool_id == spec["block"]
            ),
            "routes": [
                _route_for_tool(spec, tool_id, False, repeat),
                _route_for_tool(spec, tool_id, True, repeat),
            ],
        })
    # Auxiliary tool (NOT_COMMITTED or PARTIAL depending on stratum)
    aux_id = "Z"
    tools.append({
        "id": aux_id,
        "state": "PARTIAL" if stratum == "D2_PARTIAL_THEN_REDO" else "NOT_COMMITTED",
        "compensation_available": True,
        "routes": [
            _route_for_tool(spec, aux_id, False, 0),
            _route_for_tool(spec, aux_id, True, 0),
        ],
    })

    label, minimum = classify_scenario({"terminal_fault": terminal, "tools": tools})
    if label != EXPECTED_LABELS[stratum]:
        raise RuntimeError(f"D-088 label mismatch: {family}/{stratum}: got {label}, expected {EXPECTED_LABELS[stratum]}")

    namespace = "d088|train"
    scenario_id = f"{namespace}|{tier}|{family}|{stratum}|r{repeat}"
    return {
        "scenario_id": scenario_id,
        "cluster_id": f"{tier}|{family}|{stratum}",
        "task_family_id": family,
        "split": "train",
        "evaluation_role": "d088_mechanism_search" if tier == "discovery" else "d088_fresh_replication",
        "difficulty_stratum": stratum,
        "composition": family,
        "tier": tier,
        "repeat": repeat,
        "seed": stable_seed(seed_base, tier, family, stratum, repeat),
        "terminal_fault": terminal,
        "current_tool": aux_id,
        "tools": tools,
        "label": label,
        "min_reachable_harm": minimum,
        "labeler": "d088-contract-and-schedule-reachability-v1",
    }


def build_manifest(tier: str = "discovery", seed_base: int = 2026120100) -> dict:
    """Build a frozen manifest for the specified tier."""
    specs = DISCOVERY_FAMILIES if tier == "discovery" else FRESH_FAMILIES
    scenarios = [
        make_scenario(family, stratum, repeat, tier=tier, seed_base=seed_base)
        for family in specs
        for stratum in STRATA
        for repeat in range(REPEATS)
    ]
    manifest = {
        "protocol_id": "D-088-MECHANISM-SEARCH" if tier == "discovery" else "D-088-FRESH-REPLICATION",
        "tier": tier,
        "generator_version": "d088-train-only-v1",
        "seed_base": seed_base,
        "split": "train",
        "test_included": False,
        "test_outcomes_read": False,
        "repeats_per_family_stratum": REPEATS,
        "strata": list(STRATA),
        "expected_labels": dict(EXPECTED_LABELS),
        "family_count": len(specs),
        "families": [{"family_id": f, **specs[f]} for f in specs],
        "scenario_count": len(scenarios),
        "scenario_counts": dict(sorted(Counter(row["split"] for row in scenarios).items())),
        "label_counts": dict(sorted(Counter(row["label"] for row in scenarios).items())),
        "scenarios": scenarios,
        "decision_cap_per_episode": 24,
    }
    manifest["manifest_sha256"] = _sha256(manifest)
    return manifest


def _sha256(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
