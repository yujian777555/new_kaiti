"""Observation-based robust reachability checker and R1-R4/UNKNOWN classifier.

Implements the semantics frozen in 55_PILOT_A3B_RESEARCH_DESIGN_R1.md section 3
with the D-061/57-review fix: search results are THREE-VALUED.

    WIN         goal proved reachable by a robust observation-based policy
    PROVEN_LOSE search completed and no such policy exists
    UNKNOWN     horizon/resource cutoff; reachability NOT proved either way

Ladder rule (review 57 F8): when a HIGHER-priority goal search returns
UNKNOWN, the classifier must NOT fall through to a lower class; it returns
UNKNOWN. A scenario is only labelled R3 when TASK_COMPLETE is PROVEN_LOSE and
ZERO_RESIDUAL is WIN, and R4 only when both are PROVEN_LOSE and CONTAINMENT is
WIN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Hashable, Sequence, Tuple

CLS_R1 = "R1"
CLS_R2 = "R2"
CLS_R3 = "R3"
CLS_R4 = "R4"
CLS_UNKNOWN = "UNKNOWN"
ALL_CLASSES = (CLS_R1, CLS_R2, CLS_R3, CLS_R4, CLS_UNKNOWN)

WIN = "WIN"
PROVEN_LOSE = "PROVEN_LOSE"
UNKNOWN = "UNKNOWN"

GOAL_TASK = "TASK_COMPLETE"
GOAL_ZERO_RESIDUAL = "ZERO_RESIDUAL_TERMINAL"
GOAL_CONTAINMENT = "CONTAINMENT"


@dataclass(frozen=True)
class AugState:
    hidden: Hashable
    used_compensate: bool = False
    used_escalate: bool = False
    steps: int = 0
    harm: int = 0


@dataclass
class EpisodeSpec:
    """Finite deterministic episode transition system with explicit beliefs."""

    name: str
    initial_hidden: Sequence[Hashable]
    actions: Tuple[str, ...]
    transition: Callable[[Hashable, str], Tuple[Hashable, Hashable, int]]
    obs_key: Callable[[AugState], Hashable]
    terminal: Callable[[AugState], bool]
    goal_task: Callable[[AugState], bool]
    goal_zero_residual: Callable[[AugState], bool]
    min_reachable_harm: int = 0
    expected_class: str = ""
    notes: str = ""


@dataclass
class ReachabilityResult:
    status: str  # WIN / PROVEN_LOSE / UNKNOWN
    policy_tree: dict = field(default_factory=dict)
    nodes_expanded: int = 0
    cutoff: bool = False

    @property
    def reachable(self) -> bool:
        return self.status == WIN

    @property
    def proved(self) -> bool:
        return self.status in (WIN, PROVEN_LOSE)


class ReachabilityChecker:
    """AND-OR belief-state solver with bounded horizon (three-valued)."""

    def __init__(self, spec: EpisodeSpec, horizon: int = 12, max_nodes: int = 200_000):
        self.spec = spec
        self.horizon = horizon
        self.max_nodes = max_nodes
        self.nodes_expanded = 0
        self._cache: dict = {}
        self._cutoff = False
        self._onpath: set = set()
        self._harm_cap = (spec.min_reachable_harm or 0) + 2

    def _ident(self, belief: Tuple[AugState, ...]) -> frozenset:
        """Finite identity of a belief: hidden + flags + capped harm (steps are
        excluded so that loops are detected as cycles, not fresh states)."""
        return frozenset(
            (a.hidden, a.used_compensate, a.used_escalate, min(a.harm, self._harm_cap))
            for a in belief
        )

    def solve(self, goal: str, forbid_compensate: bool = False) -> ReachabilityResult:
        self.nodes_expanded = 0
        self._cache = {}
        self._cutoff = False
        self._onpath = set()
        aug0 = tuple(AugState(h) for h in self.spec.initial_hidden)
        status = self._or_solve(aug0, goal, forbid_compensate)
        cert = {}
        if status == WIN:
            self._extract(aug0, goal, forbid_compensate, (), cert)
        return ReachabilityResult(status, cert, self.nodes_expanded, self._cutoff)

    # -- recursion ----------------------------------------------------------
    def _or_solve(self, belief: Tuple[AugState, ...], goal: str, forbid_comp: bool) -> str:
        if self._cutoff:
            return UNKNOWN
        ident = self._ident(belief)
        key = (ident, goal, forbid_comp)
        if key in self._cache:
            return self._cache[key]
        self.nodes_expanded += 1
        if self.nodes_expanded > self.max_nodes:
            self._cutoff = True
            return UNKNOWN
        if all(self._goal_met(a, goal) for a in belief):
            self._cache[key] = WIN
            return WIN
        if ident in self._onpath:
            # cycle on the current policy path: revisiting the same information
            # state cannot win -> LOSE for this branch
            return PROVEN_LOSE
        if any(a.steps >= self.horizon for a in belief):
            # depth cap on a FRESH information state: not proved either way
            self._cache[key] = UNKNOWN
            return UNKNOWN

        self._onpath.add(ident)
        try:
            saw_unknown = False
            for action in self.spec.actions:
                if forbid_comp and "COMPENSATE" in action:
                    continue
                branches: dict = {}
                stuck = False
                for a in belief:
                    if self._goal_met(a, goal):
                        continue
                    if self.spec.terminal(a) and not self._goal_met(a, goal):
                        stuck = True
                        break
                    h2, obs, harm_delta = self.spec.transition(a.hidden, action)
                    aug2 = AugState(
                        hidden=h2,
                        used_compensate=a.used_compensate or ("COMPENSATE" in action),
                        used_escalate=a.used_escalate or action in ("ESCALATE", "STOP_SAFE"),
                        steps=a.steps + 1,
                        harm=a.harm + max(0, harm_delta),
                    )
                    branches.setdefault(self.spec.obs_key(aug2), []).append(aug2)
                if stuck:
                    continue
                ok = True
                for _obs, states in branches.items():
                    sub_status = self._or_solve(tuple(states), goal, forbid_comp)
                    if sub_status == WIN:
                        continue
                    if sub_status == UNKNOWN:
                        saw_unknown = True
                    ok = False
                    break
                if ok:
                    self._cache[key] = WIN
                    return WIN
            result = UNKNOWN if saw_unknown else PROVEN_LOSE
            self._cache[key] = result
            return result
        finally:
            self._onpath.discard(ident)

    def _goal_met(self, a: AugState, goal: str) -> bool:
        if goal == GOAL_TASK:
            return self.spec.goal_task(a)
        if goal == GOAL_ZERO_RESIDUAL:
            return self.spec.goal_zero_residual(a)
        if goal == GOAL_CONTAINMENT:
            return self.spec.terminal(a) and a.harm <= self.spec.min_reachable_harm
        raise ValueError(goal)

    def _extract(self, belief, goal, forbid_comp, hist, cert, seen=None) -> None:
        """Best-effort certificate extraction. A `seen` set of belief identities
        prevents infinite extraction through cyclic (but winning) regions:
        when an action leads back to an already-visited information state, it
        is skipped so the extracted policy makes progress."""
        if all(self._goal_met(a, goal) for a in belief):
            return
        if seen is None:
            seen = set()
        ident = self._ident(belief)
        seen.add(ident)
        try:
            for action in self.spec.actions:
                if forbid_comp and "COMPENSATE" in action:
                    continue
                branches: dict = {}
                stuck = False
                for a in belief:
                    if self._goal_met(a, goal):
                        continue
                    if self.spec.terminal(a) and not self._goal_met(a, goal):
                        stuck = True
                        break
                    h2, obs, harm_delta = self.spec.transition(a.hidden, action)
                    aug2 = AugState(
                        hidden=h2,
                        used_compensate=a.used_compensate or ("COMPENSATE" in action),
                        used_escalate=a.used_escalate or action in ("ESCALATE", "STOP_SAFE"),
                        steps=a.steps + 1,
                        harm=a.harm + max(0, harm_delta),
                    )
                    branches.setdefault(self.spec.obs_key(aug2), []).append(aug2)
                if stuck:
                    continue
                if any(self._ident(tuple(states)) in seen for states in branches.values()):
                    # cyclic continuation: skip in favour of a progress action
                    continue
                ok = True
                for obs, states in branches.items():
                    probe = ReachabilityChecker(self.spec, self.horizon, self.max_nodes)
                    probe._cache = self._cache
                    if probe._or_solve(tuple(states), goal, forbid_comp) != WIN:
                        ok = False
                        break
                if ok:
                    cert[hist] = action
                    for obs, states in branches.items():
                        self._extract(
                            tuple(states), goal, forbid_comp, hist + ((action, obs),), cert, seen
                        )
                    return
        finally:
            seen.discard(ident)


@dataclass
class Classification:
    label: str
    evidence: dict


def classify(spec: EpisodeSpec, horizon: int = 12, max_nodes: int = 200_000) -> Classification:
    """R1-R4 / UNKNOWN decision ladder with strict three-valued propagation."""
    ev: dict = {"spec": spec.name, "horizon": horizon}

    c1 = ReachabilityChecker(spec, horizon, max_nodes).solve(GOAL_TASK, forbid_compensate=True)
    ev["r1_task_no_comp"] = {"status": c1.status, "nodes": c1.nodes_expanded}
    if c1.status == WIN:
        return Classification(CLS_R1, ev)

    c2 = ReachabilityChecker(spec, horizon, max_nodes).solve(GOAL_TASK, forbid_compensate=False)
    ev["r2_task_with_comp"] = {"status": c2.status, "nodes": c2.nodes_expanded}
    if c2.status == WIN:
        return Classification(CLS_R2, ev)

    # TASK reachable not proved either way -> cannot classify lower classes
    if c2.status == UNKNOWN or c1.status == UNKNOWN:
        ev["reason"] = "task reachability UNKNOWN (horizon/resource cutoff); no downgrade"
        return Classification(CLS_UNKNOWN, ev)

    c3 = ReachabilityChecker(spec, horizon, max_nodes).solve(GOAL_ZERO_RESIDUAL)
    ev["r3_zero_residual"] = {"status": c3.status, "nodes": c3.nodes_expanded}
    if c3.status == WIN:
        return Classification(CLS_R3, ev)
    if c3.status == UNKNOWN:
        ev["reason"] = "zero-residual reachability UNKNOWN; no downgrade to R4"
        return Classification(CLS_UNKNOWN, ev)

    c4 = ReachabilityChecker(spec, horizon, max_nodes).solve(GOAL_CONTAINMENT)
    ev["r4_containment"] = {"status": c4.status, "nodes": c4.nodes_expanded}
    if c4.status == WIN:
        return Classification(CLS_R4, ev)

    ev["reason"] = "containment UNKNOWN" if c4.status == UNKNOWN else "all goals PROVEN_LOSE"
    return Classification(CLS_UNKNOWN, ev)
