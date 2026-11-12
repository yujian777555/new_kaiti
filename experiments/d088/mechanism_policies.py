"""D-088 three state-conditioned recovery mechanism policies.

Mechanism A: Failure-Feedback Route Switching
  - Track per-route failure counts and consecutive attempts.
  - After failure_switch_threshold failures, exclude/deprioritize the route.
  - Boost alternate route priority after primary fails.
  - Avoid repeated compensation on same route beyond max_consecutive_same_route.

Mechanism B: Delay-Aware Budget Scheduling
  - Track pending receipts across all tools.
  - Use WAIT as a shared resource: one WAIT advances all pending receipts.
  - Batch VERIFY when multiple receipts are ready.
  - Prioritize VERIFY near budget deadline (pre_deadline_verify_margin).
  - Urgency-aware scheduling: prefer actions that unlock key dependencies
    when budget is low.

Mechanism C: Dependency-Graph / Alternate-Path Coordination
  - Build the public dependency graph from route["requires"].
  - Detect primary-route dependency cycles (SCCs).
  - For tools in cycles, prefer alternate routes (which have no dependencies).
  - Topological ordering: act on tools whose dependencies are already
    COMPENSATED first.
  - Priority boost for actions that unlock blocked dependents.

All mechanisms use ONLY public information: tool states, route metadata
(cost, hint, requires, receipt type), and observed feedback (attempts,
last_receipt). No hidden outcomes, real delays, or scenario_id lookups.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_D087_SRC = Path(__file__).resolve().parent.parent.parent / "data" / "historical" / "d087" / "source"
if str(_D087_SRC) not in sys.path:
    sys.path.insert(0, str(_D087_SRC))

from dependency_genome import GenomePolicy  # noqa: E402

MAX_DECISIONS = 24


# ---------------------------------------------------------------------------
# Dependency graph utilities (Mechanism C)
# ---------------------------------------------------------------------------
def build_dependency_graph(view: dict) -> dict[str, list[str]]:
    """Build tool_id -> [dependency tool_ids] from the public view."""
    graph = {}
    for tool_id, tool in view["tools"].items():
        deps = set()
        for route in tool["routes"]:
            for req in route["requires"]:
                deps.add(req)
        graph[tool_id] = sorted(deps)
    return graph


def find_cycle_tools(graph: dict[str, list[str]]) -> set[str]:
    """Find tools involved in dependency cycles using iterative DFS."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    cycle_nodes: set[str] = set()

    def dfs(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Found a cycle: everything from neighbor to end of stack
                idx = stack.index(neighbor)
                cycle_nodes.update(stack[idx:])
            elif color[neighbor] == WHITE:
                dfs(neighbor, stack)
        stack.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node, [])
    return cycle_nodes


def topological_order(graph: dict[str, list[str]], compensated: set[str]) -> list[str]:
    """Return tools ordered so that dependencies come before dependents.

    Tools whose dependencies are all COMPENSATED come first.
    Tools in cycles or with unsatisfied deps are placed later.
    """
    in_degree = defaultdict(int)
    for node, deps in graph.items():
        for dep in deps:
            if dep in graph:
                in_degree[node] += 1 if dep not in compensated else 0

    # Kahn's algorithm on the subgraph of unsatisfied dependencies
    queue = [n for n in graph if in_degree.get(n, 0) == 0]
    order = []
    visited = set()
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for dependent, deps in graph.items():
            if node in deps and dependent not in visited:
                in_degree[dependent] -= 1
                if in_degree[dependent] <= 0:
                    queue.append(dependent)

    # Append remaining (cycle members) in original order
    for node in graph:
        if node not in visited:
            order.append(node)
    return order


# ---------------------------------------------------------------------------
# D-088 Mechanism-Aware Policy
# ---------------------------------------------------------------------------
class D088Policy(GenomePolicy):
    """GenomePolicy extended with three toggleable state-conditioned mechanisms."""

    def __init__(self, genome):
        super().__init__(genome)
        # Mechanism A state
        self.consecutive_route: dict[tuple, int] = defaultdict(int)
        self.route_failures: dict[tuple, int] = defaultdict(int)
        self.excluded_routes: set[tuple] = set()

        # Mechanism B state
        self.last_verified_tool: str | None = None
        self.wait_count_since_verify: int = 0

    # ---- Mechanism B: override pending handling for delay-aware scheduling ----
    def _pending_action(self, view):
        if not self.genome.enable_mech_b:
            return super()._pending_action(view)

        pending_tools = []
        for tool_id, tool in view["tools"].items():
            for route in tool["routes"]:
                if route["pending"]:
                    pending_tools.append((tool_id, route["name"]))

        if not pending_tools:
            self.wait_count_since_verify = 0
            return None

        # Mechanism B: NEVER stop on pending — always resolve receipts first.
        # This overrides the base policy's stop_pending behaviour.

        # Budget-aware scheduling
        budget_remaining = view.get("budget_remaining", MAX_DECISIONS)
        margin = self.genome.pre_deadline_verify_margin

        # If budget is critically low, verify all pending immediately
        if budget_remaining <= margin:
            self.wait_count_since_verify = 0
            tool_id = pending_tools[0][0]
            self.last_verified_tool = tool_id
            return ("VERIFY", tool_id)

        # If we just verified this tool, WAIT to let other tools' receipts advance
        if self.last_verified_tool is not None:
            self.last_verified_tool = None
            self.wait_count_since_verify += 1
            return ("WAIT",)

        # If we have waited at least once and have multiple pending, batch-verify
        if (len(pending_tools) >= self.genome.batch_verify_threshold
                and self.wait_count_since_verify >= 1):
            self.wait_count_since_verify = 0
            # Verify the tool with the most attempts first (most likely resolved)
            tool_id = max(pending_tools, key=lambda t: sum(
                r["attempts"] for r in view["tools"][t[0]]["routes"]
            ))[0]
            self.last_verified_tool = tool_id
            return ("VERIFY", tool_id)

        # If only one pending and we've waited once, verify it
        if len(pending_tools) == 1 and self.wait_count_since_verify >= 1:
            self.wait_count_since_verify = 0
            tool_id = pending_tools[0][0]
            self.last_verified_tool = tool_id
            return ("VERIFY", tool_id)

        # Default: wait to advance pending receipts (shared resource)
        self.wait_count_since_verify += 1
        return ("WAIT",)

    # ---- Mechanism A: override _update_evidence and _priority for route switching ----
    def _update_evidence(self, view):
        super()._update_evidence(view)
        if not self.genome.enable_mech_a:
            return
        for tool_id, tool in view["tools"].items():
            for route in tool["routes"]:
                key = (tool_id, route["name"])
                if route["last_receipt"] == "FAILED":
                    self.route_failures[key] += 1
                    self.consecutive_route[key] += 1
                    if self.route_failures[key] >= self.genome.failure_switch_threshold:
                        self.excluded_routes.add(key)
                elif route["last_receipt"] in ("COMPENSATED", "PENDING"):
                    self.consecutive_route[key] += 1
                    if self.consecutive_route[key] >= self.genome.max_consecutive_same_route:
                        self.excluded_routes.add(key)

    def _available(self, view, allow_alternates=True):
        available = super()._available(view, allow_alternates=allow_alternates)
        if not self.genome.enable_mech_a:
            return available
        # Filter out excluded routes
        return [
            (tool_id, route) for tool_id, route in available
            if (tool_id, route["name"]) not in self.excluded_routes
        ]

    def _priority(self, view, available):
        if not self.genome.enable_mech_a and not self.genome.enable_mech_c:
            return super()._priority(view, available)

        tool_ids = list(view["tools"])
        graph = build_dependency_graph(view) if self.genome.enable_mech_c else {}
        cycle_tools = find_cycle_tools(graph) if self.genome.enable_mech_c else set()
        compensated = {
            tid for tid, t in view["tools"].items()
            if t["state"] == "COMPENSATED"
        }
        topo_order = topological_order(graph, compensated) if self.genome.enable_mech_c else tool_ids
        topo_index = {tid: i for i, tid in enumerate(topo_order)}

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
            # Mechanism A: route failure penalty and alternate boost
            if self.genome.enable_mech_a:
                score += self.genome.route_failure_penalty * self.route_failures.get(key, 0)
                if route["name"] != "primary" and self.route_failures.get((tool_id, "primary"), 0) > 0:
                    score += self.genome.alternate_priority_boost
            # Mechanism C: cycle-aware routing and topological ordering
            if self.genome.enable_mech_c:
                if self.genome.cycle_aware_routing and tool_id in cycle_tools:
                    if route["name"] != "primary":
                        score += self.genome.dependency_unlock_priority
                    else:
                        score -= self.genome.topological_order_weight * 0.5
                score += self.genome.topological_order_weight * (len(topo_order) - topo_index.get(tool_id, 0)) / max(1, len(topo_order))
                # Boost for actions that unlock dependents
                unlock_count = sum(
                    1 for dependent, deps in graph.items()
                    if tool_id in deps and dependent not in compensated
                )
                score += self.genome.dependency_unlock_priority * unlock_count * 0.1

            scored.append((score, tool_id, route["name"]))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return scored[0]

    # ---- Mechanism C: override _abort to use topological ordering ----
    def _abort(self, view):
        if self.genome.enable_mech_c:
            active = sum(tool["state"] in ("COMMITTED", "PARTIAL") for tool in view["tools"].values())
            available = self._available(view)
            if active <= self.genome.stop_residual or not available:
                # Before stopping, check if any tool's dependency just became
                # COMPENSATED and would unlock a new action
                graph = build_dependency_graph(view)
                compensated = {
                    tid for tid, t in view["tools"].items()
                    if t["state"] == "COMPENSATED"
                }
                # Re-check availability with updated dependency state
                for tool_id, tool in view["tools"].items():
                    if tool["state"] not in ("COMMITTED", "PARTIAL"):
                        continue
                    if not tool["compensation_available"]:
                        continue
                    for route in tool["routes"]:
                        if route["name"] != "primary":
                            continue
                        if all(view["tools"].get(r, {}).get("state") == "COMPENSATED"
                               for r in route["requires"]):
                            if tool_id not in [t for t, _ in available]:
                                available.append((tool_id, route))
                                break
                if not available:
                    return self._finish((self.genome.stop_action,))
            _score, tool_id, route_name = self._priority(view, available)
            return self._finish(("COMPENSATE", tool_id, route_name))
        return super()._abort(view)
