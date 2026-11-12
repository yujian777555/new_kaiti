import json

import pytest

from scripts.paper1_tau_bench_splits import (
    build_available_tools,
    build_generation_batch_plan,
    load_test_after_freeze,
    load_train_dev_splits,
    read_tau_bench_split,
    to_evotool_instance,
    to_evotool_splits,
)


def _row(split, index):
    return {
        "split": split,
        "task_id": f"retail-{split}-{index:04d}",
        "user_id": f"user-{index:04d}",
        "instruction": f"Task instruction {index}",
        "actions": [{"name": "lookup_order", "kwargs": {"order_id": f"o-{index}"}}],
        "outputs": [f"required output {index}"],
    }


def _write_split(path, split, count):
    path.write_text(
        "".join(json.dumps(_row(split, i)) + "\n" for i in range(count)),
        encoding="utf-8",
    )


def test_train_dev_loader_preserves_official_splits_and_never_reads_test(tmp_path):
    _write_split(tmp_path / "train.jsonl", "train", 500)
    _write_split(tmp_path / "dev.jsonl", "dev", 20)
    train, dev = load_train_dev_splits(tmp_path)
    assert len(train) == 500
    assert len(dev) == 20
    assert all(row["split"] == "train" for row in train)
    assert all(row["split"] == "dev" for row in dev)
    assert not (tmp_path / "test.jsonl").exists()
    assert not ({row["task_id"] for row in train} & {row["task_id"] for row in dev})


def test_test_loader_requires_policy_freeze_and_explicit_authorization(tmp_path):
    _write_split(tmp_path / "test.jsonl", "test", 115)
    with pytest.raises(PermissionError, match="policy freeze"):
        load_test_after_freeze(
            tmp_path, policy_frozen=False, explicit_authorization=True
        )
    with pytest.raises(PermissionError, match="explicit authorization"):
        load_test_after_freeze(
            tmp_path, policy_frozen=True, explicit_authorization=False
        )
    rows = load_test_after_freeze(
        tmp_path, policy_frozen=True, explicit_authorization=True
    )
    assert len(rows) == 115
    assert all(row["split"] == "test" for row in rows)


def test_official_tool_schemas_map_to_evotool_instance_shape():
    class LookupOrder:
        @staticmethod
        def get_info():
            return {
                "type": "function",
                "function": {
                    "name": "lookup_order",
                    "description": "Look up an order",
                    "parameters": {"type": "object", "properties": {}},
                },
            }

    schemas = build_available_tools([LookupOrder], adapter_tool_names={"lookup_order"})
    instance = to_evotool_instance(_row("train", 0), schemas)
    assert instance["id"] == "retail-train-0000"
    assert instance["query"] == "Task instruction 0"
    assert instance["benchmark"] == "taubench"
    assert instance["gold_plan"] == [
        {"tool": "lookup_order", "args": {"order_id": "o-0"}}
    ]
    assert instance["outputs"] == ["required output 0"]


def test_official_and_adapter_tool_set_mismatch_fails_closed():
    class LookupOrder:
        @staticmethod
        def get_info():
            return {
                "function": {
                    "name": "lookup_order",
                    "parameters": {"type": "object", "properties": {}},
                }
            }

    with pytest.raises(ValueError, match="tool-set mismatch"):
        build_available_tools([LookupOrder], adapter_tool_names={"lookup_order", "cancel_order"})


def test_generation_budget_is_eight_batches_of_three_distinct_train_tasks():
    train = [{"id": f"retail-train-{i:04d}"} for i in range(500)]
    first = build_generation_batch_plan(train, seed=11, generations=8, batch_size=3)
    repeat = build_generation_batch_plan(train, seed=11, generations=8, batch_size=3)
    other = build_generation_batch_plan(train, seed=22, generations=8, batch_size=3)
    assert first == repeat
    assert len(first) == 8
    assert all(len(batch["task_ids"]) == 3 for batch in first)
    flattened = [task_id for batch in first for task_id in batch["task_ids"]]
    assert len(flattened) == 24
    assert len(set(flattened)) == 24
    assert first != other


def test_split_reader_rejects_mislabelled_rows_and_duplicate_ids(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(
        json.dumps(_row("dev", 0)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected split"):
        read_tau_bench_split(tmp_path, "train")

    path.write_text(
        json.dumps(_row("train", 0)) + "\n" + json.dumps(_row("train", 0)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate task_id"):
        read_tau_bench_split(tmp_path, "train")
