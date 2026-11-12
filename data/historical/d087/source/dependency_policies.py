"""Fixed and feedback-driven baseline policies for the D-086 environment."""
from __future__ import annotations

import random


class BasePolicy:
    def __call__(self, view):
        return self.act(view)

    def __init__(self):
        self.last_action = None
        self.seen_attempts = {}
        self.failures = {}
        self.excluded = set()

    def _pending_action(self, view):
        for tool_id, tool in view["tools"].items():
            if any(route["pending"] for route in tool["routes"]):
                if self.last_action == ("VERIFY", tool_id):
                    return ("WAIT",)
                return ("VERIFY", tool_id)
        return None

    def _update_evidence(self, view):
        for tool_id, tool in view["tools"].items():
            for route in tool["routes"]:
                key = (tool_id, route["name"])
                previous = self.seen_attempts.get(key, 0)
                attempts = route["attempts"]
                if attempts > previous and route["last_receipt"] == "FAILED":
                    self.failures[key] = self.failures.get(key, 0) + attempts - previous
                self.seen_attempts[key] = attempts

    def _finish(self, action):
        self.last_action = action
        return action

    def _recover_current(self, view):
        current = view["current_tool"]
        state = view["tools"][current]["state"]
        if state == "COMPENSATED":
            return self._finish(("RETRY_WORKFLOW",))
        route = view["tools"][current]["routes"][0]
        return self._finish(("COMPENSATE", current, route["name"]))

    def _available(self, view, allow_alternates=True):
        available = []
        for tool_id, tool in view["tools"].items():
            if tool["state"] not in ("COMMITTED", "PARTIAL"):
                continue
            if not tool["compensation_available"]:
                continue
            for route in tool["routes"]:
                key = (tool_id, route["name"])
                if key in self.excluded or route["pending"]:
                    continue
                if not allow_alternates and route["name"] != "primary":
                    continue
                if all(view["tools"][required]["state"] == "COMPENSATED"
                       for required in route["requires"]):
                    available.append((tool_id, route))
        return available

    def act(self, view):
        pending = self._pending_action(view)
        if pending is not None:
            return self._finish(pending)
        self._update_evidence(view)
        if view["terminal_fault"] == "timeout_before":
            return self._finish(("RETRY_WORKFLOW",))
        if view["terminal_fault"] == "partial_recover":
            return self._recover_current(view)
        return self._abort(view)

    def _abort(self, view):
        return self._finish(("ESCALATE",))


class HandPolicy(BasePolicy):
    def _abort(self, view):
        return self._finish(("ESCALATE",))


class FixedPrefixPolicy(BasePolicy):
    def __init__(self, reverse=True):
        super().__init__()
        self.reverse = reverse
        self.attempted = set()

    def _abort(self, view):
        ordered = list(view["tools"])
        if self.reverse:
            ordered.reverse()
        for tool_id in ordered:
            if tool_id in self.attempted:
                continue
            tool = view["tools"][tool_id]
            if tool["state"] not in ("COMMITTED", "PARTIAL") or not tool["compensation_available"]:
                continue
            route = next((item for item in tool["routes"] if item["name"] == "primary"), None)
            if route is None or route["pending"]:
                continue
            self.attempted.add(tool_id)
            if all(view["tools"][required]["state"] == "COMPENSATED"
                   for required in route["requires"]):
                return self._finish(("COMPENSATE", tool_id, route["name"]))
        return self._finish(("ESCALATE",))


class RuleBasedPolicy(BasePolicy):
    def _abort(self, view):
        available = self._available(view, allow_alternates=False)
        for tool_id, route in available:
            key = (tool_id, route["name"])
            if self.failures.get(key, 0) >= 2:
                self.excluded.add(key)
                continue
            return self._finish(("COMPENSATE", tool_id, route["name"]))
        return self._finish(("ESCALATE",))


class GreedyCompensationPolicy(BasePolicy):
    def _abort(self, view):
        available = self._available(view)
        available.sort(key=lambda item: (
            0 if item[1]["reliability_hint"] == "HIGH" else 1,
            item[1]["cost"],
            item[0],
            item[1]["name"],
        ))
        for tool_id, route in available:
            key = (tool_id, route["name"])
            if self.failures.get(key, 0) >= 3:
                self.excluded.add(key)
                continue
            return self._finish(("COMPENSATE", tool_id, route["name"]))
        return self._finish(("ESCALATE",))


class AdaptiveProbePolicy(BasePolicy):
    def __init__(self, cost_first=False):
        super().__init__()
        self.priority = None
        self.cost_first = cost_first

    def _abort(self, view):
        available = self._available(view)
        if self.priority is None:
            self.priority = [
                (tool_id, route["name"])
                for tool_id, route in sorted(available, key=lambda item: (
                    item[1]["cost"] if self.cost_first
                    else 0 if item[1]["reliability_hint"] == "HIGH" else 1,
                    item[1]["cost"], item[0], item[1]["name"],
                ))
            ]
        for tool_id, route in available:
            key = (tool_id, route["name"])
            if self.failures.get(key, 0) >= 3:
                self.excluded.add(key)
        available = [item for item in available if (item[0], item[1]["name"]) not in self.excluded]
        if not available:
            return self._finish(("ESCALATE",))
        keys = {(tool_id, route["name"]) for tool_id, route in available}
        self.priority = [key for key in self.priority if key in keys]
        self.priority.extend(sorted(key for key in keys if key not in self.priority))
        failed = [key for key in self.priority if self.failures.get(key, 0) > 0]
        for key in failed:
            self.priority.remove(key)
            self.priority.append(key)
        tool_id, route_name = self.priority[0]
        route = view["tools"][tool_id]["routes"][0]
        if route["name"] != route_name:
            route = next(item for item in view["tools"][tool_id]["routes"]
                         if item["name"] == route_name)
        return self._finish(("COMPENSATE", tool_id, route_name))


class RandomPolicy(BasePolicy):
    def __init__(self, seed):
        super().__init__()
        self.rng = random.Random(seed)

    def _abort(self, view):
        available = self._available(view)
        actions = [("COMPENSATE", tool_id, route["name"]) for tool_id, route in available]
        actions.append(("ESCALATE",))
        if not available:
            actions.append(("RETRY_WORKFLOW",))
        return self._finish(self.rng.choice(actions))

    def act(self, view):
        pending = [
            tool_id for tool_id, tool in view["tools"].items()
            if any(route["pending"] for route in tool["routes"])
        ]
        if pending:
            return self._finish(self.rng.choice([("WAIT",), ("VERIFY", pending[0])]))
        if view["terminal_fault"] in ("timeout_before", "partial_recover"):
            if view["terminal_fault"] == "partial_recover" and self.rng.random() < 0.5:
                return self._recover_current(view)
            return self._finish(("RETRY_WORKFLOW",))
        return self._abort(view)


def make_policy(name, seed=0):
    factories = {
        "Hand": HandPolicy,
        "FixedPrefix": FixedPrefixPolicy,
        "FixedPrefixForward": lambda: FixedPrefixPolicy(reverse=False),
        "RuleBased": RuleBasedPolicy,
        "Greedy": GreedyCompensationPolicy,
        "AdaptiveProbe": AdaptiveProbePolicy,
        "CostAware": lambda: AdaptiveProbePolicy(cost_first=True),
        "Random": lambda: RandomPolicy(seed),
    }
    if name not in factories:
        raise ValueError("unknown D-086 policy: " + str(name))
    return factories[name]()
