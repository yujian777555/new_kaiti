"""D-086 dependency-aware recovery environment with restricted policy views.

The evaluator can inspect deterministic attempt schedules. Policies see only
contracts, noisy reliability hints, their own attempts, and public receipts.
"""
from __future__ import annotations

ACTIVE_STATES = ("COMMITTED", "PARTIAL")
MAX_DECISIONS = 24


def classify_scenario(scenario):
    terminal = scenario["terminal_fault"]
    if terminal == "timeout_before":
        return "R1", 0
    if terminal == "partial_recover":
        return "R2", 0
    if terminal != "permission":
        raise ValueError("unknown terminal fault: " + str(terminal))
    active = {tool["id"] for tool in scenario["tools"] if tool["state"] in ACTIVE_STATES}
    possible = set()
    changed = True
    while changed:
        changed = False
        for tool in scenario["tools"]:
            tool_id = tool["id"]
            if tool_id not in active or tool_id in possible or not tool["compensation_available"]:
                continue
            for route in tool["routes"]:
                if (any(route["outcomes"])
                        and all(required not in active or required in possible
                                for required in route["requires"])):
                    possible.add(tool_id)
                    changed = True
                    break
    minimum = len(active - possible)
    return ("R3" if minimum == 0 else "R4"), minimum


def public_view(scenario):
    return DependencyRecoveryEnv(scenario).view()


class DependencyRecoveryEnv:
    def __init__(self, scenario):
        if scenario.get("split") not in ("train", "validation"):
            raise ValueError("D-086 environment permits only Train/Validation scenarios")
        self.scenario = scenario
        self.current = scenario["current_tool"]
        self.terminal_fault = scenario["terminal_fault"]
        self.tools = {tool["id"]: tool["state"] for tool in scenario["tools"]}
        self.contracts = {tool["id"]: bool(tool["compensation_available"]) for tool in scenario["tools"]}
        self.routes = {}
        for tool in scenario["tools"]:
            self.routes[tool["id"]] = {}
            for route in tool["routes"]:
                self.routes[tool["id"]][route["name"]] = {
                    "cost": int(route["cost"]),
                    "reliability_hint": route["reliability_hint"],
                    "requires": tuple(route["requires"]),
                    "receipt": route["receipt"],
                    "receipt_delay": int(route["receipt_delay"]),
                    "idempotent": bool(route["idempotent"]),
                    "visibility_bound": int(route["visibility_bound"]),
                    "outcomes": tuple(bool(value) for value in route["outcomes"]),
                    "attempt_index": 0,
                    "attempts": 0,
                    "pending_success": None,
                    "resolve_at": None,
                    "last_receipt": None,
                }
        self.tick = 0
        self.decision_count = 0
        self.action_cost = 0
        self.duplicate_compensation = 0
        self.trace = []
        self.terminal_action = None
        self.runtime_forced_abort = False

    def view(self):
        tools = {}
        for tool_id, state in self.tools.items():
            routes = []
            for name, route in self.routes[tool_id].items():
                routes.append({
                    "name": name,
                    "cost": route["cost"],
                    "reliability_hint": route["reliability_hint"],
                    "requires": list(route["requires"]),
                    "idempotent": route["idempotent"],
                    "visibility_bound": route["visibility_bound"],
                    "pending": route["pending_success"] is not None,
                    "attempts": route["attempts"],
                    "last_receipt": route["last_receipt"],
                })
            tools[tool_id] = {
                "state": state,
                "compensation_available": self.contracts[tool_id],
                "routes": routes,
            }
        return {
            "tools": tools,
            "current_tool": self.current,
            "terminal_fault": self.terminal_fault,
            "decision_count": self.decision_count,
            "budget_remaining": max(0, MAX_DECISIONS - self.decision_count),
        }

    def _record(self, action, observation, cost):
        self.decision_count += 1
        self.action_cost += cost
        self.trace.append({
            "action": list(action),
            "observation": observation,
            "cost": cost,
            "tick": self.tick,
        })
        return observation

    def _pending(self, tool_id):
        return any(route["pending_success"] is not None for route in self.routes[tool_id].values())

    def pending_count(self):
        return sum(self._pending(tool_id) for tool_id in self.tools)

    def active_count(self):
        return sum(state in ACTIVE_STATES for state in self.tools.values())

    def task_success(self):
        return int(all(state == "COMMITTED" for state in self.tools.values()))

    def step(self, action):
        if not isinstance(action, (tuple, list)) or not action:
            return self._record(("INVALID",), "INVALID_ACTION", 1)
        action = tuple(action)
        kind = action[0]
        if kind in ("ESCALATE", "STOP_SAFE"):
            self.terminal_action = kind
            return self._record(action, "ESCALATED" if kind == "ESCALATE" else "STOPPED_SAFE", 0)
        if kind == "WAIT":
            self.tick += 1
            return self._record(action, "WAITED", 1)
        if kind == "RETRY_WORKFLOW":
            return self._record(action, self._retry_workflow(), 1)
        if kind == "VERIFY" and len(action) == 2 and action[1] in self.tools:
            return self._record(action, self._verify(action[1]), 1)
        if kind == "COMPENSATE" and len(action) == 3 and action[1] in self.tools:
            if action[2] in self.routes[action[1]]:
                cost = self.routes[action[1]][action[2]]["cost"]
                return self._record(action, self._compensate(action[1], action[2]), cost)
        return self._record(action, "INVALID_ACTION", 1)

    def _retry_workflow(self):
        state = self.tools[self.current]
        if self.terminal_fault == "permission":
            return "PERMISSION"
        if self.terminal_fault == "timeout_before" and state == "NOT_COMMITTED":
            self.tools[self.current] = "COMMITTED"
            return "COMMITTED"
        if self.terminal_fault == "partial_recover":
            if state == "COMPENSATED" and not self._pending(self.current):
                self.tools[self.current] = "COMMITTED"
                return "COMMITTED"
            return "PARTIAL"
        return "INVALID_ACTION"

    def _verify(self, tool_id):
        pending = [
            route for route in self.routes[tool_id].values()
            if route["pending_success"] is not None
        ]
        if not pending:
            if self.tools[tool_id] == "COMPENSATED":
                return "COMPENSATED"
            receipts = [route["last_receipt"] for route in self.routes[tool_id].values()
                        if route["last_receipt"] is not None]
            return receipts[-1] if receipts else "NOT_COMMITTED"
        route = pending[-1]
        if self.tick < route["resolve_at"]:
            return "PENDING"
        result = "COMPENSATED" if route["pending_success"] else "FAILED"
        route["pending_success"] = None
        route["resolve_at"] = None
        route["last_receipt"] = result
        return result

    def _compensate(self, tool_id, route_name):
        route = self.routes[tool_id][route_name]
        if self.tools[tool_id] == "COMPENSATED":
            if self._pending(tool_id) and not route["idempotent"]:
                self.duplicate_compensation += 1
                return "DUPLICATE_COMPENSATION"
            return "ALREADY_COMPENSATED"
        if self._pending(tool_id):
            return "PENDING"
        if not self.contracts[tool_id]:
            route["last_receipt"] = "CONTRACT_BLOCKED"
            return "CONTRACT_BLOCKED"
        if any(self.tools[required] != "COMPENSATED" for required in route["requires"]):
            route["last_receipt"] = "DEPENDENCY_BLOCKED"
            return "DEPENDENCY_BLOCKED"
        index = route["attempt_index"]
        outcomes = route["outcomes"]
        success = outcomes[min(index, len(outcomes) - 1)] if outcomes else False
        route["attempt_index"] += 1
        route["attempts"] += 1
        if success:
            self.tools[tool_id] = "COMPENSATED"
        if route["receipt"] == "delayed":
            route["pending_success"] = success
            route["resolve_at"] = self.tick + route["receipt_delay"]
            route["last_receipt"] = "TIMEOUT"
            return "TIMEOUT"
        route["last_receipt"] = "COMPENSATED" if success else "FAILED"
        return route["last_receipt"]

    def report(self):
        label, minimum = classify_scenario(self.scenario)
        task = self.task_success()
        residual = 0 if task else self.active_count()
        pending = self.pending_count()
        constraint = int(self.duplicate_compensation > 0 or pending > 0)
        avoidable = max(0, self.duplicate_compensation + residual - minimum)
        escalated = self.terminal_action == "ESCALATE"
        if label in ("R1", "R2"):
            class_success = int(task and not constraint)
        elif label == "R3":
            class_success = int(escalated and not task and residual == 0 and not constraint)
        else:
            class_success = int(escalated and not task and avoidable == 0 and not constraint)
        return {
            "scenario_id": self.scenario["scenario_id"],
            "split": self.scenario["split"],
            "label": label,
            "class_success": class_success,
            "task_success": task,
            "conditional_recovery_success": class_success if label in ("R1", "R2") else None,
            "correct_escalation": class_success if label == "R3" else None,
            "prefix_compensation_success": class_success if label == "R3" else None,
            "residual_side_effects": residual,
            "min_reachable_harm": minimum,
            "avoidable_harm": avoidable,
            "action_cost": self.action_cost,
            "recovery_cost": self.action_cost,
            "decision_count": self.decision_count,
            "tool_action_count": self.action_cost,
            "constraint_violation": constraint,
            "duplicate_compensation": self.duplicate_compensation,
            "pending_compensation": pending,
            "policy_selected_escalation": int(escalated),
            "safe_stop": int(self.terminal_action == "STOP_SAFE"),
            "runtime_forced_abort": int(self.runtime_forced_abort),
            "trace": self.trace,
            "final_tool_states": dict(self.tools),
        }


def run_episode(policy, scenario, max_actions=MAX_DECISIONS):
    env = DependencyRecoveryEnv(scenario)
    while not env.task_success() and env.terminal_action is None:
        if env.decision_count >= max_actions:
            env.runtime_forced_abort = True
            break
        env.step(policy(env.view()))
    return env.report()
