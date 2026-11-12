"""D-088 extended genome encoding three state-conditioned recovery mechanisms.

Extends the D-086 RecoveryGenome with evolvable parameters for:
  A: Failure-Feedback Route Switching
  B: Delay-Aware Budget Scheduling
  C: Dependency-Graph / Alternate-Path Coordination

Each mechanism is toggleable via enable_mech_{a,b,c} so the same genome
encoding supports all 8 experimental groups (L, A, B, C, AB, AC, BC, ABC).
"""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass, field

# Import the base genome from the D-086 historical source.
import sys
from pathlib import Path

_D087_SRC = Path(__file__).resolve().parent.parent.parent / "data" / "historical" / "d087" / "source"
if str(_D087_SRC) not in sys.path:
    sys.path.insert(0, str(_D087_SRC))

from dependency_genome import RecoveryGenome  # noqa: E402
from dependency_policies import BasePolicy  # noqa: E402

# ---------------------------------------------------------------------------
# Mechanism parameter ranges (evolvable)
# ---------------------------------------------------------------------------
MECH_A_DISCRETE = {
    "failure_switch_threshold": (1, 2, 3, 4),
    "max_consecutive_same_route": (1, 2, 3, 4),
}
MECH_A_CONTINUOUS = {
    "alternate_priority_boost": (0.0, 3.0),
    "route_failure_penalty": (-3.0, 0.0),
}
MECH_B_DISCRETE = {
    "batch_verify_threshold": (1, 2, 3),
    "pre_deadline_verify_margin": (0, 1, 2, 3, 4),
}
MECH_B_CONTINUOUS = {
    "budget_urgency_weight": (0.0, 2.0),
    "wait_efficiency_weight": (0.0, 2.0),
}
MECH_C_CONTINUOUS = {
    "topological_order_weight": (0.0, 2.0),
    "dependency_unlock_priority": (0.0, 3.0),
}
MECH_C_BOOLEAN = ("cycle_aware_routing",)

ALL_MECH_NAMES = (
    list(MECH_A_DISCRETE) + list(MECH_A_CONTINUOUS)
    + list(MECH_B_DISCRETE) + list(MECH_B_CONTINUOUS)
    + list(MECH_C_CONTINUOUS) + list(MECH_C_BOOLEAN)
    + ["enable_mech_a", "enable_mech_b", "enable_mech_c"]
)


@dataclass(frozen=True)
class D088Genome(RecoveryGenome):
    # --- Mechanism A: Failure-Feedback Route Switching ---
    enable_mech_a: bool = True
    failure_switch_threshold: int = 1
    max_consecutive_same_route: int = 2
    alternate_priority_boost: float = 1.5
    route_failure_penalty: float = -1.0

    # --- Mechanism B: Delay-Aware Budget Scheduling ---
    enable_mech_b: bool = True
    budget_urgency_weight: float = 1.0
    batch_verify_threshold: int = 1
    wait_efficiency_weight: float = 1.0
    pre_deadline_verify_margin: int = 2

    # --- Mechanism C: Dependency-Graph Coordination ---
    enable_mech_c: bool = True
    cycle_aware_routing: bool = True
    topological_order_weight: float = 1.0
    dependency_unlock_priority: float = 2.0

    def fingerprint(self):
        return dataclasses.asdict(self)

    def clone(self):
        return dataclasses.replace(self)

    def mech_label(self) -> str:
        """Return the experimental-group label for this genome's mechanism flags."""
        parts = []
        if self.enable_mech_a:
            parts.append("A")
        if self.enable_mech_b:
            parts.append("B")
        if self.enable_mech_c:
            parts.append("C")
        return "".join(parts) if parts else "L"


# ---------------------------------------------------------------------------
# Random genome construction
# ---------------------------------------------------------------------------
def random_d088_genome(rng: random.Random, mech_flags: dict[str, bool] | None = None) -> D088Genome:
    """Create a random D-088 genome with specified mechanism flags."""
    flags = mech_flags or {"enable_mech_a": True, "enable_mech_b": True, "enable_mech_c": True}
    base_kwargs = {}
    # Sample base RecoveryGenome parameters from their ranges.
    from dependency_genome import CONTINUOUS, DISCRETE, BOOLEAN
    for name, bounds in CONTINUOUS.items():
        base_kwargs[name] = rng.uniform(*bounds)
    for name, values in DISCRETE.items():
        base_kwargs[name] = rng.choice(values)
    for name in BOOLEAN:
        base_kwargs[name] = rng.choice((True, False))
    base_kwargs["stop_action"] = rng.choice(("ESCALATE", "STOP_SAFE"))

    mech_kwargs = dict(flags)
    for name, bounds in MECH_A_CONTINUOUS.items():
        mech_kwargs[name] = rng.uniform(*bounds)
    for name, values in MECH_A_DISCRETE.items():
        mech_kwargs[name] = rng.choice(values)
    for name, bounds in MECH_B_CONTINUOUS.items():
        mech_kwargs[name] = rng.uniform(*bounds)
    for name, values in MECH_B_DISCRETE.items():
        mech_kwargs[name] = rng.choice(values)
    for name, bounds in MECH_C_CONTINUOUS.items():
        mech_kwargs[name] = rng.uniform(*bounds)
    for name in MECH_C_BOOLEAN:
        mech_kwargs[name] = rng.choice((True, False))

    return D088Genome(**base_kwargs, **mech_kwargs)


def mutate_d088(genome: D088Genome, rng: random.Random) -> D088Genome:
    """Mutate one gene (base or mechanism) of a D-088 genome."""
    all_names = (
        list(dataclasses.asdict(genome))
    )
    name = rng.choice(all_names)
    current = getattr(genome, name)

    if name.startswith("enable_mech_"):
        new_val = not current
    elif name in MECH_A_CONTINUOUS or name in MECH_B_CONTINUOUS or name in MECH_C_CONTINUOUS:
        bounds = (MECH_A_CONTINUOUS.get(name) or MECH_B_CONTINUOUS.get(name)
                  or MECH_C_CONTINUOUS.get(name))
        lo, hi = bounds
        delta = rng.uniform(-0.25 * (hi - lo), 0.25 * (hi - lo))
        new_val = min(hi, max(lo, current + delta))
        if new_val == current:
            new_val = hi if current == lo else lo
    elif name in MECH_A_DISCRETE or name in MECH_B_DISCRETE:
        values = MECH_A_DISCRETE.get(name) or MECH_B_DISCRETE.get(name)
        new_val = rng.choice(values)
        if new_val == current:
            idx = values.index(current)
            new_val = values[(idx + 1) % len(values)]
    elif name in MECH_C_BOOLEAN or name in ("retry_unknown", "stop_pending", "allow_alternate", "allow_verify"):
        new_val = not current
    elif name == "stop_action":
        new_val = "STOP_SAFE" if current == "ESCALATE" else "ESCALATE"
    else:
        # Base RecoveryGenome continuous/discrete
        from dependency_genome import CONTINUOUS, DISCRETE
        if name in CONTINUOUS:
            lo, hi = CONTINUOUS[name]
            delta = rng.uniform(-0.25 * (hi - lo), 0.25 * (hi - lo))
            new_val = min(hi, max(lo, current + delta))
            if new_val == current:
                new_val = hi if current == lo else lo
        elif name in DISCRETE:
            values = DISCRETE[name]
            new_val = rng.choice(values)
            if new_val == current:
                idx = values.index(current)
                new_val = values[(idx + 1) % len(values)]
        else:
            new_val = current  # unknown gene, no mutation

    return dataclasses.replace(genome, **{name: new_val})


def crossover_d088(a: D088Genome, b: D088Genome, rng: random.Random) -> D088Genome:
    """Uniform crossover over all genes."""
    kwargs = {}
    for name in dataclasses.asdict(a):
        src = a if rng.random() < 0.5 else b
        kwargs[name] = getattr(src, name)
    return D088Genome(**kwargs)
