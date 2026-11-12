"""Deterministic, tool-boundary fault injection for D-080.

The wrapper never changes vendor tool implementations. Faults are injected before
or after the real pinned tool callable, and every event is bound to a task/tool/call
identity. This module contains no LLM, network, sleep, or retry loop.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable


SUPPORTED_MODES = {
    "timeout_before_execution",
    "rate_limit_before_execution",
    "schema_rejection_before_execution",
    "timeout_after_commit",
}


def state_sha256(db: dict[str, Any]) -> str:
    payload = json.dumps(db, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FaultEvent:
    task_id: str
    tool_name: str
    call_index: int
    mode: str
    seed: int

    def __post_init__(self):
        if not self.task_id or not self.tool_name or self.call_index < 0:
            raise ValueError("fault event requires task, tool and non-negative call index")
        if self.mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported fault mode: {self.mode}")

    @property
    def event_id(self) -> str:
        raw = f"{self.seed}|{self.task_id}|{self.tool_name}|{self.call_index}|{self.mode}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class InjectedToolFailure(RuntimeError):
    def __init__(self, mode: str, phase: str, event_id: str):
        super().__init__(f"injected {mode} at {phase}")
        self.mode = mode
        self.phase = phase
        self.event_id = event_id
        self.retryable = mode in {
            "timeout_before_execution", "rate_limit_before_execution",
            "timeout_after_commit",
        }


class FaultInjectionBoundary:
    """Invoke pinned tool callables while injecting pre/post execution failures."""

    def __init__(self, tool_map: dict[str, Callable[..., Any]], events=()):
        self.tool_map = dict(tool_map)
        self.events = {}
        for event in events:
            key = (event.task_id, event.tool_name, event.call_index)
            if key in self.events:
                raise ValueError(f"duplicate fault event key: {key}")
            self.events[key] = event
        self.audit: list[dict[str, Any]] = []

    def invoke(self, task_id: str, call_index: int, db: dict[str, Any],
               tool_name: str, kwargs: dict[str, Any] | None = None):
        kwargs = dict(kwargs or {})
        key = (task_id, tool_name, call_index)
        event = self.events.get(key)
        before = state_sha256(db)
        if tool_name not in self.tool_map:
            raise KeyError(f"tool is not in the pinned allowlist: {tool_name}")

        if event and event.mode in {
            "timeout_before_execution", "rate_limit_before_execution",
            "schema_rejection_before_execution",
        }:
            phase = "before_execution"
            self.audit.append({
                "event_id": event.event_id, "task_id": task_id,
                "tool_name": tool_name, "call_index": call_index,
                "mode": event.mode, "phase": phase,
                "state_before_sha256": before, "state_after_sha256": before,
                "tool_invoked": False,
            })
            raise InjectedToolFailure(event.mode, phase, event.event_id)

        output = self.tool_map[tool_name](db, **kwargs)
        after = state_sha256(db)
        if event and event.mode == "timeout_after_commit":
            if isinstance(output, str) and output.startswith("Error:"):
                raise ValueError("post-commit timeout requires a successful tool result")
            if before == after:
                raise ValueError("post-commit timeout requires an observed state change")
            self.audit.append({
                "event_id": event.event_id, "task_id": task_id,
                "tool_name": tool_name, "call_index": call_index,
                "mode": event.mode, "phase": "after_commit",
                "state_before_sha256": before, "state_after_sha256": after,
                "tool_invoked": True,
            })
            raise InjectedToolFailure(event.mode, "after_commit", event.event_id)

        self.audit.append({
            "event_id": event.event_id if event else None,
            "task_id": task_id, "tool_name": tool_name,
            "call_index": call_index, "mode": event.mode if event else "none",
            "phase": "completed", "state_before_sha256": before,
            "state_after_sha256": after, "tool_invoked": True,
        })
        return output
