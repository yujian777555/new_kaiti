"""Split-preserving tau-bench Retail adapter for Paper 1.

This module never merges the official Train/Dev/Test splits. Test loading is
explicitly gated so the evolution/selection preflight can operate on Train/Dev
without touching the held-out Test file.
"""
from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path
from typing import Any, Iterable

EXPECTED_SPLIT_COUNTS = {"train": 500, "dev": 20, "test": 115}
ALLOWED_SPLITS = frozenset(EXPECTED_SPLIT_COUNTS)


def read_tau_bench_split(
    data_dir: str | Path,
    split: str,
    *,
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    if split not in ALLOWED_SPLITS:
        raise ValueError(f"unsupported split: {split}")
    path = Path(data_dir) / f"{split}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(path)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            if row.get("split") != split:
                raise ValueError(
                    f"{path}:{line_number}: expected split={split!r}, got {row.get('split')!r}"
                )
            task_id = row.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise ValueError(f"{path}:{line_number}: missing stable task_id")
            if task_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate task_id={task_id}")
            seen.add(task_id)

            instruction = row.get("instruction")
            user_id = row.get("user_id")
            actions = row.get("actions")
            outputs = row.get("outputs", [])
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError(f"{path}:{line_number}: missing instruction")
            if not isinstance(user_id, str) or not user_id:
                raise ValueError(f"{path}:{line_number}: missing user_id")
            if not isinstance(actions, list):
                raise ValueError(f"{path}:{line_number}: actions must be a list")
            for action_index, action in enumerate(actions):
                if (
                    not isinstance(action, dict)
                    or not isinstance(action.get("name"), str)
                    or not isinstance(action.get("kwargs"), dict)
                ):
                    raise ValueError(
                        f"{path}:{line_number}: malformed action at index {action_index}"
                    )
            if not isinstance(outputs, list) or any(not isinstance(x, str) for x in outputs):
                raise ValueError(f"{path}:{line_number}: outputs must be a list of strings")
            rows.append(row)

    if expected_count is not None and len(rows) != expected_count:
        raise ValueError(
            f"{split} count mismatch: expected {expected_count}, observed {len(rows)}"
        )
    return rows


def load_train_dev_splits(
    data_dir: str | Path,
    *,
    expected_counts: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = expected_counts or {"train": 500, "dev": 20}
    train = read_tau_bench_split(
        data_dir, "train", expected_count=counts.get("train")
    )
    dev = read_tau_bench_split(
        data_dir, "dev", expected_count=counts.get("dev")
    )
    train_ids = {row["task_id"] for row in train}
    dev_ids = {row["task_id"] for row in dev}
    overlap = sorted(train_ids & dev_ids)
    if overlap:
        raise ValueError(f"Train/Dev task_id overlap: {overlap[:5]}")
    return train, dev


def load_test_after_freeze(
    data_dir: str | Path,
    *,
    policy_frozen: bool,
    explicit_authorization: bool,
    expected_count: int = 115,
) -> list[dict[str, Any]]:
    if not policy_frozen:
        raise PermissionError("Test may only be loaded after policy freeze on Dev")
    if not explicit_authorization:
        raise PermissionError("Test loading requires separate explicit authorization")
    return read_tau_bench_split(
        data_dir, "test", expected_count=expected_count
    )


def build_available_tools(
    official_tools: Iterable[Any],
    *,
    adapter_tool_names: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    names: list[str] = []
    for tool in official_tools:
        info = tool.get_info()
        function = info.get("function", info) if isinstance(info, dict) else None
        if not isinstance(function, dict):
            raise ValueError(f"invalid official tool schema: {tool!r}")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"official tool schema has no name: {tool!r}")
        if name in names:
            raise ValueError(f"duplicate official tool schema: {name}")
        if not isinstance(function.get("parameters"), dict):
            raise ValueError(f"official tool schema has no parameters object: {name}")
        names.append(name)
        schemas.append(copy.deepcopy(function))

    if adapter_tool_names is not None:
        adapter_names = set(adapter_tool_names)
        official_names = set(names)
        if official_names != adapter_names:
            raise ValueError(
                "official/adapter tool-set mismatch: "
                f"official_only={sorted(official_names - adapter_names)}, "
                f"adapter_only={sorted(adapter_names - official_names)}"
            )
    return schemas


def to_evotool_instance(
    row: dict[str, Any],
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    tool_names = {tool["name"] for tool in available_tools}
    gold_plan = []
    for action in row["actions"]:
        name = action["name"]
        if name not in tool_names:
            raise ValueError(f"Gold Action references unavailable tool: {name}")
        gold_plan.append({
            "tool": name,
            "args": copy.deepcopy(action["kwargs"]),
        })
    return {
        "id": row["task_id"],
        "source_task_id": row["task_id"],
        "query": row["instruction"],
        "user_id": row["user_id"],
        "split": row["split"],
        "benchmark": "taubench",
        "available_tools": copy.deepcopy(available_tools),
        "gold_plan": gold_plan,
        "outputs": list(row["outputs"]),
    }


def to_evotool_splits(
    train_rows: list[dict[str, Any]],
    dev_rows: list[dict[str, Any]],
    available_tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = [to_evotool_instance(row, available_tools) for row in train_rows]
    dev = [to_evotool_instance(row, available_tools) for row in dev_rows]
    if {x["id"] for x in train} & {x["id"] for x in dev}:
        raise ValueError("mapped Train/Dev task_id overlap")
    return train, dev


def build_generation_batch_plan(
    train_instances: list[dict[str, Any]],
    *,
    seed: int,
    generations: int = 8,
    batch_size: int = 3,
) -> list[dict[str, Any]]:
    """Mirror the pinned loop's first-epoch shuffle and mini-batch order.

    The Paper 1 G=8/B=3 budget fits within the first epoch for 500 Train tasks.
    Parent-sampling RNG draws happen after the order has been shuffled, so they
    do not change these first-epoch batch IDs.
    """
    if generations <= 0 or batch_size <= 0:
        raise ValueError("generations and batch_size must be positive")
    if generations > math.ceil(len(train_instances) / batch_size):
        raise ValueError(
            "this preflight helper only mirrors one-epoch budgets; "
            "requested generations exceed the first-epoch batch count"
        )
    ids = [item.get("id", item.get("task_id")) for item in train_instances]
    if any(not isinstance(task_id, str) or not task_id for task_id in ids):
        raise ValueError("every Train instance must have a stable id/task_id")
    if len(set(ids)) != len(ids):
        raise ValueError("Train instance IDs must be unique")
    if generations * batch_size > len(ids):
        raise ValueError("requested generation budget would require a partial batch")

    order = list(range(len(ids)))
    random.Random(seed).shuffle(order)
    batches = []
    for generation in range(generations):
        selected = order[generation * batch_size:(generation + 1) * batch_size]
        batches.append({
            "generation": generation + 1,
            "task_ids": [ids[index] for index in selected],
        })
    return batches
