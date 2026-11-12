"""T1: diagnostic status decomposition that leaves EvoTool's legacy fields intact.

This module wraps an existing executor. It never edits the vendored EvoTool source,
changes the legacy status field, or changes the reward/progress calculation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Collection, Mapping
from typing import Any


_NO_MATCH_PREFIXES = {
    "find_user_id_by_email": ("Error: user not found",),
    "find_user_id_by_name_zip": ("Error: user not found",),
    "get_order_details": ("Error: order not found",),
    "get_product_details": ("Error: product not found",),
    "get_user_details": ("Error: user not found",),
}

_NOT_APPLICABLE_TOOLS = frozenset({"think"})


def _state_sha256(state: Any) -> str | None:
    if state is None:
        return None
    try:
        payload = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(payload).hexdigest()


def _execution_status(tool: str, legacy_result: Mapping[str, Any], known_tools: Collection[str]) -> str:
    if tool not in known_tools:
        return "unknown_tool"
    if legacy_result.get("fault_injected") is True:
        return "injected_failure"
    if legacy_result.get("status") == "success":
        return "returned"
    if legacy_result.get("status") == "error":
        return "raised_exception"
    return "unknown"


def _business_outcome(tool: str, output: Any, execution_status: str) -> str:
    if execution_status != "returned":
        return "unknown"
    if tool in _NOT_APPLICABLE_TOOLS:
        return "not_applicable"
    if not isinstance(output, str):
        return "unknown"
    if not output.startswith("Error:"):
        return "accepted"

    if any(
        output.startswith(prefix)
        for prefix in _NO_MATCH_PREFIXES.get(tool, ())
    ):
        return "no_match"

    # For a known tool that returned normally, an Error observation is a
    # domain/input rejection, not a Python invocation exception. The raw
    # observation is retained so downstream work can refine this mapping.
    return "rejected"


class StatusDecomposedExecutor:
    """Wrap a legacy executor and append T1 diagnostics to each result.

    The delegate's original keys and values are preserved exactly. In
    particular, result["status"] remains the legacy execution-status field
    consumed by EvoTool's existing progress metric.
    """

    def __init__(self, delegate: Any, known_tools: Collection[str]):
        self._delegate = delegate
        self._known_tools = frozenset(known_tools)

    @property
    def db(self):
        return self._delegate.db

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def execute(self, tool: str, args: dict | None = None) -> dict:
        args = args or {}
        before = getattr(self._delegate, "db", None)
        before_hash = _state_sha256(before)
        # JSON-backed Retail state is hashed directly. A snapshot is needed only
        # for a non-JSON delegate whose state cannot be represented by SHA-256.
        before_fallback = copy.deepcopy(before) if before_hash is None else None

        # Do not catch exceptions here: preserve the delegate's exact behavior.
        legacy_result = self._delegate.execute(tool, args)
        after = getattr(self._delegate, "db", None)
        after_hash = _state_sha256(after)

        if before_hash is not None and after_hash is not None:
            state_effect = "changed" if before_hash != after_hash else "unchanged"
        elif before_fallback is not None and after is not None:
            state_effect = "changed" if before_fallback != after else "unchanged"
        else:
            state_effect = "unknown"

        execution_status = _execution_status(
            tool, legacy_result, self._known_tools
        )
        output = legacy_result.get("output")
        result = dict(legacy_result)
        result.update(
            {
                "execution_status": execution_status,
                "business_outcome": _business_outcome(
                    tool, output, execution_status
                ),
                "state_effect": state_effect,
                "tool_observation": copy.deepcopy(output),
                "state_before_sha256": before_hash,
                "state_after_sha256": after_hash,
            }
        )
        return result


def make_status_decomposed_env_factory(
    base_env_factory: Callable[[dict], Any],
    known_tools: Collection[str],
) -> Callable[[dict], Any]:
    """Return an env_for-compatible factory that instruments only tau-bench.

    Pass the returned function as the EvoTool agent module's env_for factory
    in an explicitly enabled T1 run. Other benchmark environments are returned
    unchanged. This avoids patching the pinned vendor source.
    """

    def env_factory(instance: dict):
        executor = base_env_factory(instance)
        if instance.get("benchmark") != "taubench":
            return executor
        return StatusDecomposedExecutor(executor, known_tools)

    return env_factory
