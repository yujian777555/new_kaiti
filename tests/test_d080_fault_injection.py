from copy import deepcopy

import pytest

from scripts.prepare_tau_bench_retail import install_vendored_runtime
from treatments.fault_injection import (
    FaultEvent, FaultInjectionBoundary, InjectedToolFailure, state_sha256,
)


def _runtime():
    tool_classes, load_data = install_vendored_runtime()
    tools = {item.get_info()["function"]["name"]: item.invoke for item in tool_classes}
    return tools, load_data


def _pending_order(db):
    for order_id, order in db["orders"].items():
        if order.get("status") == "pending" and order.get("payment_history"):
            return order_id, order
    raise AssertionError("pinned retail DB has no payable pending order")


def test_timeout_before_execution_has_no_side_effect_and_retry_executes_once():
    tools, load_data = _runtime()
    db = load_data()
    order_id, order = _pending_order(db)
    args = {"order_id": order_id, "reason": "no longer needed"}
    boundary = FaultInjectionBoundary(tools, [
        FaultEvent("train-smoke-1", "cancel_pending_order", 0,
                   "timeout_before_execution", 17)
    ])
    before = state_sha256(db)
    with pytest.raises(InjectedToolFailure) as error:
        boundary.invoke("train-smoke-1", 0, db, "cancel_pending_order", args)
    assert error.value.phase == "before_execution"
    assert state_sha256(db) == before
    output = boundary.invoke("train-smoke-1", 1, db, "cancel_pending_order", args)
    assert not output.startswith("Error:")
    assert db["orders"][order_id]["status"] == "cancelled"
    assert boundary.audit[0]["tool_invoked"] is False
    assert boundary.audit[1]["tool_invoked"] is True


def test_timeout_after_commit_is_observable_and_retry_does_not_duplicate_refund():
    tools, load_data = _runtime()
    db = load_data()
    order_id, order = _pending_order(db)
    args = {"order_id": order_id, "reason": "no longer needed"}
    original_history = deepcopy(order["payment_history"])
    boundary = FaultInjectionBoundary(tools, [
        FaultEvent("train-smoke-2", "cancel_pending_order", 0,
                   "timeout_after_commit", 29)
    ])
    before = state_sha256(db)
    with pytest.raises(InjectedToolFailure) as error:
        boundary.invoke("train-smoke-2", 0, db, "cancel_pending_order", args)
    assert error.value.phase == "after_commit"
    assert state_sha256(db) != before
    cancelled = db["orders"][order_id]
    assert cancelled["status"] == "cancelled"
    committed_history = deepcopy(cancelled["payment_history"])
    assert len(committed_history) == len(original_history) * 2

    # A blind retry is rejected by the real tool and cannot append a second refund.
    retry_output = boundary.invoke("train-smoke-2", 1, db, "cancel_pending_order", args)
    assert retry_output.startswith("Error: non-pending order")
    assert db["orders"][order_id]["payment_history"] == committed_history
    assert boundary.audit[0]["tool_invoked"] is True
    assert boundary.audit[0]["state_before_sha256"] != boundary.audit[0]["state_after_sha256"]


def test_rate_limit_and_schema_rejection_are_pre_execution_failures():
    tools, load_data = _runtime()
    db = load_data()
    order_id, _ = _pending_order(db)
    before = state_sha256(db)
    events = [
        FaultEvent("train-smoke-3", "cancel_pending_order", 0,
                   "rate_limit_before_execution", 31),
        FaultEvent("train-smoke-3", "cancel_pending_order", 1,
                   "schema_rejection_before_execution", 31),
    ]
    boundary = FaultInjectionBoundary(tools, events)
    for index in (0, 1):
        with pytest.raises(InjectedToolFailure) as error:
            boundary.invoke("train-smoke-3", index, db, "cancel_pending_order",
                            {"order_id": order_id, "reason": "no longer needed"})
        assert error.value.phase == "before_execution"
    assert state_sha256(db) == before
    assert all(row["tool_invoked"] is False for row in boundary.audit)


def test_fault_events_are_bound_to_unique_task_tool_call_and_seed():
    first = FaultEvent("task-a", "cancel_pending_order", 0,
                       "timeout_before_execution", 1)
    same = FaultEvent("task-a", "cancel_pending_order", 0,
                      "timeout_before_execution", 1)
    other_seed = FaultEvent("task-a", "cancel_pending_order", 0,
                            "timeout_before_execution", 2)
    assert first.event_id == same.event_id
    assert first.event_id != other_seed.event_id
    with pytest.raises(ValueError, match="duplicate fault event"):
        FaultInjectionBoundary({}, [first, same])



def test_post_commit_timeout_on_address_update_is_idempotent_on_retry():
    tools, load_data = _runtime()
    db = load_data()
    order_id, order = _pending_order(db)
    args = {
        "order_id": order_id,
        "address1": "42 Deterministic Test Way",
        "address2": "Unit 3",
        "city": "Seattle",
        "state": "WA",
        "country": "USA",
        "zip": "98101",
    }
    boundary = FaultInjectionBoundary(tools, [
        FaultEvent("train-smoke-4", "modify_pending_order_address", 0,
                   "timeout_after_commit", 43)
    ])
    with pytest.raises(InjectedToolFailure) as error:
        boundary.invoke("train-smoke-4", 0, db, "modify_pending_order_address", args)
    assert error.value.phase == "after_commit"
    committed_address = deepcopy(db["orders"][order_id]["address"])
    committed_hash = state_sha256(db)
    output = boundary.invoke(
        "train-smoke-4", 1, db, "modify_pending_order_address", args
    )
    assert not output.startswith("Error:")
    assert db["orders"][order_id]["address"] == committed_address
    assert state_sha256(db) == committed_hash
