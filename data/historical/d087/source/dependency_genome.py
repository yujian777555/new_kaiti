"""Typed recovery genomes and public-feedback policies for D-086."""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass

from dependency_policies import BasePolicy

CONTINUOUS = {
    "hint_weight": (-3.0, 3.0),
    "cost_weight": (-3.0, 0.0),
    "failure_weight": (-3.0, 0.0),
    "position_weight": (-1.0, 1.0),
    "dependency_weight": (0.0, 2.0),
}
DISCRETE = {
    "max_attempts": (1, 2, 3, 4),
    "verify_delay": (0, 1, 2),
    "stop_residual": (0, 1, 2),
}
BOOLEAN = ("retry_unknown", "stop_pending", "allow_alternate", "allow_verify")


@dataclass(frozen=True)
class RecoveryGenome:
    hint_weight: float = 2.0
    cost_weight: float = -0.2
    failure_weight: float = -1.5
    position_weight: float = 0.0
    dependency_weight: float = 1.0
    max_attempts: int = 3
    verify_delay: int = 0
    retry_unknown: bool = False
    stop_pending: bool = False
    stop_residual: int = 0
    allow_alternate: bool = True
    allow_verify: bool = True
    stop_action: str = "ESCALATE"

    def fingerprint(self):
        return dataclasses.asdict(self)

    def clone(self):
        return dataclasses.replace(self)


def random_genome(rng):
    return RecoveryGenome(
        **{name: rng.uniform(*bounds) for name, bounds in CONTINUOUS.items()},
        **{name: rng.choice(values) for name, values in DISCRETE.items()},
        **{name: rng.choice((True, False)) for name in BOOLEAN},
        stop_action=rng.choice(("ESCALATE", "STOP_SAFE")),
    )


def mutate(genome, rng):
    name = rng.choice(list(CONTINUOUS) + list(DISCRETE) + list(BOOLEAN) + ["stop_action"])
    if name in CONTINUOUS:
        lower, upper = CONTINUOUS[name]
        delta = rng.uniform(-0.25 * (upper - lower), 0.25 * (upper - lower))
        value = min(upper, max(lower, getattr(genome, name) + delta))
        if value == getattr(genome, name):
            value = upper if value == lower else lower
    elif name in DISCRETE:
        value = rng.choice(DISCRETE[name])
        if value == getattr(genome, name):
            values = DISCRETE[name]
            value = values[(values.index(value) + 1) % len(values)]
    elif name in BOOLEAN:
        value = not getattr(genome, name)
    else:
        value = "STOP_SAFE" if genome.stop_action == "ESCALATE" else "ESCALATE"
    return dataclasses.replace(genome, **{name: value})


def crossover(first, second, rng):
    return dataclasses.replace(
        first,
        **{
            name: getattr(first if rng.random() < 0.5 else second, name)
            for name in dataclasses.asdict(first)
        },
    )


def make_initial_pool(seed):
    rng = random.Random(seed * 7919 + 29)
    anchors = [
        RecoveryGenome(),
        RecoveryGenome(hint_weight=2.0, cost_weight=-0.2, failure_weight=-2.0),
        RecoveryGenome(hint_weight=0.2, cost_weight=-2.0, failure_weight=-1.0),
        RecoveryGenome(hint_weight=0.0, cost_weight=-0.1, failure_weight=-1.0,
                       dependency_weight=2.0, position_weight=1.0, max_attempts=2),
    ]
    return anchors + [random_genome(rng) for _ in range(12 - len(anchors))]


class GenomePolicy(BasePolicy):
    def __init__(self, genome):
        super().__init__()
        self.genome = genome
        self.unknown_retried = False
        self.verify_waits = 0

    def _pending_tool(self, view):
        for tool_id, tool in view["tools"].items():
            for route in tool["routes"]:
                if route["pending"]:
                    return tool_id, route["name"]
        return None

    def _pending_action(self, view):
        pending = self._pending_tool(view)
        if pending is None:
            self.unknown_retried = False
            self.verify_waits = 0
            return None
        if self.genome.stop_pending:
            return (self.genome.stop_action,)
        tool_id, route_name = pending
        if self.genome.retry_unknown and not self.unknown_retried:
            self.unknown_retried = True
            return "COMPENSATE", tool_id, route_name
        if not self.genome.allow_verify:
            return ("WAIT",)
        if self.last_action == ("VERIFY", tool_id):
            self.verify_waits = 0
            return ("WAIT",)
        if self.verify_waits < self.genome.verify_delay:
            self.verify_waits += 1
            return ("WAIT",)
        self.verify_waits = 0
        return "VERIFY", tool_id

    def _available(self, view, allow_alternates=True):
        available = super()._available(view, allow_alternates=self.genome.allow_alternate)
        return [
            (tool_id, route) for tool_id, route in available
            if route["attempts"] < self.genome.max_attempts
        ]

    def _priority(self, view, available):
        tool_ids = list(view["tools"])
        scored = []
        for tool_id, route in available:
            key = (tool_id, route["name"])
            score = (
                self.genome.hint_weight * (route["reliability_hint"] == "HIGH")
                + self.genome.cost_weight * route["cost"]
                + self.genome.failure_weight * self.failures.get(key, 0)
                + self.genome.position_weight * tool_ids.index(tool_id)
                + self.genome.dependency_weight * len(route["requires"])
            )
            scored.append((score, tool_id, route["name"]))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return scored[0]

    def _abort(self, view):
        active = sum(tool["state"] in ("COMMITTED", "PARTIAL") for tool in view["tools"].values())
        available = self._available(view)
        if active <= self.genome.stop_residual or not available:
            return self._finish((self.genome.stop_action,))
        _score, tool_id, route_name = self._priority(view, available)
        return self._finish(("COMPENSATE", tool_id, route_name))

    def _recover_current(self, view):
        current = view["current_tool"]
        if view["tools"][current]["state"] == "COMPENSATED":
            return self._finish(("RETRY_WORKFLOW",))
        available = [
            (tool_id, route) for tool_id, route in self._available(view)
            if tool_id == current
        ]
        if not available:
            return self._finish((self.genome.stop_action,))
        _score, tool_id, route_name = self._priority(view, available)
        return self._finish(("COMPENSATE", tool_id, route_name))
