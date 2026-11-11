"""T3: deterministic scorer aligned with the pinned official tau-bench Retail Env.

The scorer compares the full database hash and applies the official required-output
rule: each required string must occur case-insensitively in at least one response
message after commas are removed from the response message only.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any


DEFAULT_TERMINAL_TOOLS = frozenset({"transfer_to_human_agents"})


def to_official_hashable(value: Any):
    """Mirror tau_bench.envs.base.to_hashable for JSON-backed Retail state."""
    if isinstance(value, dict):
        return tuple(
            (key, to_official_hashable(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, list):
        return tuple(to_official_hashable(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(to_official_hashable(item) for item in value))
    return value


def official_state_hash(db: Mapping[str, Any]) -> str:
    """Return the exact SHA-256 representation used by official Env.get_data_hash."""
    digest_input = str(to_official_hashable(dict(db))).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def _action_parts(action: Mapping[str, Any]) -> tuple[str | None, dict]:
    tool = action.get("tool") or action.get("name")
    args = action.get("args")
    if args is None:
        args = action.get("kwargs", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise TypeError("action args/kwargs must be a dict")
    return tool, args


def replay_actions(
    base_db: Mapping[str, Any],
    actions: Sequence[Mapping[str, Any]] | None,
    tool_map: Mapping[str, Callable[..., Any]],
    *,
    terminal_tools: Collection[str] = DEFAULT_TERMINAL_TOOLS,
    stop_on_terminal: bool = False,
) -> dict:
    """Replay actions on a fresh DB using official Env semantics.

    Gold replay skips terminal tools and continues, matching calculate_reward().
    Candidate replay sets stop_on_terminal=True: the terminal tool is invoked and
    the candidate sequence then stops, matching Env.step() termination.
    Unknown tools and invocation exceptions do not mutate state, matching the
    official Env's observation/error behavior.
    """
    db = copy.deepcopy(dict(base_db))
    for action in actions or ():
        tool, args = _action_parts(action)
        if not tool:
            continue
        if tool == "respond":
            continue
        if tool in terminal_tools:
            if stop_on_terminal:
                terminal_fn = tool_map.get(tool)
                if terminal_fn is not None:
                    try:
                        terminal_fn(db, **args)
                    except Exception:
                        pass
                break
            continue
        fn = tool_map.get(tool)
        if fn is None:
            continue
        try:
            fn(db, **args)
        except Exception:
            # Official Env.step catches tool exceptions and keeps the DB object.
            continue
    return db


def score_official_reward(
    gold_db: Mapping[str, Any],
    candidate_db: Mapping[str, Any],
    required_outputs: Sequence[str] | None,
    response_messages: Sequence[str] | None,
) -> dict:
    """Score state and response evidence with the official Retail reward rule.

    The official implementation searches across all response actions. The caller
    should pass every candidate response message in order. Supplying one final
    synthesizer answer is supported but is a reduced-adapter approximation.
    """
    messages = list(response_messages or ())
    if any(not isinstance(message, str) for message in messages):
        raise TypeError("response_messages must contain only strings")
    outputs = [str(item) for item in (required_outputs or ())]

    gold_hash = official_state_hash(gold_db)
    candidate_hash = official_state_hash(candidate_db)
    actions_match = gold_hash == candidate_hash

    output_checks = []
    for required in outputs:
        matched_indices = [
            index
            for index, message in enumerate(messages)
            if required.lower() in message.lower().replace(",", "")
        ]
        output_checks.append(
            {
                "required_output": required,
                "matched": bool(matched_indices),
                "matched_response_indices": matched_indices,
            }
        )

    outputs_match = all(item["matched"] for item in output_checks)
    reward = 1.0 if actions_match and outputs_match else 0.0
    return {
        "reward": reward,
        "r_actions": float(actions_match),
        "r_outputs": float(outputs_match) if outputs else None,
        "actions_match": actions_match,
        "outputs_match": outputs_match,
        "gold_state_hash": gold_hash,
        "candidate_state_hash": candidate_hash,
        "output_checks": output_checks,
        "response_message_count": len(messages),
        "required_output_count": len(outputs),
        "state_comparison_scope": "full_database",
        "output_rule": "required.lower() in response.lower().replace(',', '')",
    }


def score_official_task(
    db_loader: Callable[[], Mapping[str, Any]],
    tool_map: Mapping[str, Callable[..., Any]],
    gold_actions: Sequence[Mapping[str, Any]],
    candidate_db: Mapping[str, Any],
    required_outputs: Sequence[str] | None,
    response_messages: Sequence[str] | None,
    *,
    terminal_tools: Collection[str] = DEFAULT_TERMINAL_TOOLS,
) -> dict:
    """Score a live candidate DB against the official gold-action replay."""
    gold_db = replay_actions(
        db_loader(),
        gold_actions,
        tool_map,
        terminal_tools=terminal_tools,
        stop_on_terminal=False,
    )
    return score_official_reward(
        gold_db, candidate_db, required_outputs, response_messages
    )


def score_task(
    db_loader: Callable[[], Mapping[str, Any]],
    tool_map: Mapping[str, Callable[..., Any]],
    gold_actions: Sequence[Mapping[str, Any]],
    candidate_actions: Sequence[Mapping[str, Any]],
    required_outputs: Sequence[str] | None,
    response_messages: Sequence[str] | None,
    *,
    terminal_tools: Collection[str] = DEFAULT_TERMINAL_TOOLS,
) -> dict:
    """Replay a candidate action plan and score it against the official rule."""
    gold_db = replay_actions(
        db_loader(),
        gold_actions,
        tool_map,
        terminal_tools=terminal_tools,
        stop_on_terminal=False,
    )
    candidate_db = replay_actions(
        db_loader(),
        candidate_actions,
        tool_map,
        terminal_tools=terminal_tools,
        stop_on_terminal=True,
    )
    result = score_official_reward(
        gold_db, candidate_db, required_outputs, response_messages
    )
    result["gold_action_count"] = len(gold_actions)
    result["candidate_action_count"] = len(candidate_actions)
    return result
