from copy import deepcopy

import pytest

from treatments.evotool_status import StatusDecomposedExecutor, make_status_decomposed_env_factory
from scripts.audit_evotool_tau_bench_conformance import (
    _load_official_env,
    _make_official_env,
)
from scripts.prepare_tau_bench_retail import install_vendored_runtime
from treatments.taubench_official_reward import (
    official_state_hash,
    replay_actions,
    score_official_reward,
    score_official_task,
    score_task,
)


class FakeExecutor:
    def __init__(self):
        self.db = {"orders": {}, "users": {}, "products": {}}

    def execute(self, tool, args):
        args = args or {}
        if tool == "modify_pending_order_payment":
            self.db["orders"]["o1"] = {"status": "pending"}
            return {
                "tool": tool,
                "args": args,
                "output": '{"status": "pending"}',
                "status": "success",
            }
        if tool == "get_user_details":
            return {
                "tool": tool,
                "args": args,
                "output": "Error: user not found",
                "status": "success",
            }
        if tool == "cancel_pending_order":
            return {
                "tool": tool,
                "args": args,
                "output": "Error: insufficient gift card balance",
                "status": "success",
            }
        if tool == "think":
            return {
                "tool": tool,
                "args": args,
                "output": "",
                "status": "success",
            }
        if tool == "explode":
            return {
                "tool": tool,
                "args": args,
                "output": "Error: ValueError: malformed",
                "status": "error",
            }
        return {
            "tool": tool,
            "args": args,
            "output": f"Error: unknown tool '{tool}'",
            "status": "error",
        }


def test_t1_preserves_legacy_fields_and_records_state_effect():
    delegate = FakeExecutor()
    wrapped = StatusDecomposedExecutor(
        delegate,
        {
            "modify_pending_order_payment",
            "get_user_details",
            "cancel_pending_order",
            "think",
            "explode",
        },
    )
    result = wrapped.execute("modify_pending_order_payment", {"order_id": "o1"})

    assert result["status"] == "success"
    assert result["execution_status"] == "returned"
    assert result["business_outcome"] == "accepted"
    assert result["state_effect"] == "changed"
    assert result["tool_observation"] == result["output"]
    assert result["state_before_sha256"] != result["state_after_sha256"]
    assert set(("tool", "args", "output", "status")).issubset(result)


def test_t1_distinguishes_no_match_from_business_rejection_and_not_applicable():
    wrapped = StatusDecomposedExecutor(
        FakeExecutor(),
        {"get_user_details", "cancel_pending_order", "think"},
    )
    no_match = wrapped.execute("get_user_details", {"user_id": "missing"})
    rejected = wrapped.execute("cancel_pending_order", {"order_id": "o1"})
    not_applicable = wrapped.execute("think", {"thought": "inspect state"})

    assert no_match["execution_status"] == "returned"
    assert no_match["business_outcome"] == "no_match"
    assert no_match["state_effect"] == "unchanged"
    assert rejected["execution_status"] == "returned"
    assert rejected["business_outcome"] == "rejected"
    assert not_applicable["business_outcome"] == "not_applicable"


def test_t1_separates_unknown_tool_and_raised_exception():
    wrapped = StatusDecomposedExecutor(FakeExecutor(), {"explode"})
    unknown = wrapped.execute("not_registered", {})
    raised = wrapped.execute("explode", {})

    assert unknown["status"] == "error"
    assert unknown["execution_status"] == "unknown_tool"
    assert unknown["business_outcome"] == "unknown"
    assert raised["status"] == "error"
    assert raised["execution_status"] == "raised_exception"
    assert raised["business_outcome"] == "unknown"


def test_t1_env_factory_wraps_only_tau_bench():
    created = []

    def base_factory(instance):
        item = {"benchmark": instance["benchmark"], "db": {}}
        item["execute"] = lambda tool, args: {
            "tool": tool, "args": args, "output": "ok", "status": "success"
        }
        # The wrapper expects an attribute-style delegate.
        class Delegate:
            def __init__(self, payload):
                self.benchmark = payload["benchmark"]
                self.db = payload["db"]
            def execute(self, tool, args):
                return {"tool": tool, "args": args, "output": "ok", "status": "success"}
        delegate = Delegate(item)
        created.append(delegate)
        return delegate

    factory = make_status_decomposed_env_factory(base_factory, {"read"})
    wrapped = factory({"benchmark": "taubench"})
    unchanged = factory({"benchmark": "restbench"})
    assert isinstance(wrapped, StatusDecomposedExecutor)
    assert unchanged is created[-1]
    assert wrapped.execute("read", {})["execution_status"] == "returned"


def test_official_hash_is_order_independent_but_covers_all_database_tables():
    left = {
        "orders": {"o1": {"status": "pending"}},
        "users": {"u1": {"name": "A"}},
        "products": {"p1": {"name": "P"}},
    }
    right = {
        "products": {"p1": {"name": "P"}},
        "users": {"u1": {"name": "A"}},
        "orders": {"o1": {"status": "pending"}},
    }
    assert official_state_hash(left) == official_state_hash(right)

    product_changed = deepcopy(right)
    product_changed["products"]["p1"]["name"] = "P2"
    assert official_state_hash(left) != official_state_hash(product_changed)


def test_t3_matches_official_output_normalization_across_multiple_messages():
    db = {"orders": {}, "users": {}, "products": {}}
    result = score_official_reward(
        db,
        deepcopy(db),
        ["retail-case-token", "1234"],
        ["RETAIL-CASE-TOKEN", "1,234"],
    )
    assert result["reward"] == 1.0
    assert result["r_actions"] == 1.0
    assert result["r_outputs"] == 1.0
    assert result["output_checks"][0]["matched_response_indices"] == [0]
    assert result["output_checks"][1]["matched_response_indices"] == [1]


def test_t3_only_removes_commas_from_response_not_required_string():
    db = {"orders": {}, "users": {}, "products": {}}
    result = score_official_reward(db, db, ["1,234"], ["1234"])
    assert result["outputs_match"] is False
    assert result["reward"] == 0.0


def test_t3_requires_every_output_but_accepts_them_across_messages():
    db = {"orders": {}, "users": {}, "products": {}}
    result = score_official_reward(
        db, db, ["alpha", "beta", "gamma"], ["ALPHA", "some beta", "gamma"]
    )
    assert result["reward"] == 1.0
    missing = score_official_reward(
        db, db, ["alpha", "beta"], ["alpha only"]
    )
    assert missing["reward"] == 0.0
    assert missing["r_outputs"] == 0.0


def test_t3_no_required_outputs_uses_only_full_state_match():
    db = {"orders": {}, "users": {}, "products": {}}
    result = score_official_reward(db, db, [], [])
    assert result["reward"] == 1.0
    assert result["r_outputs"] is None
    assert result["outputs_match"] is True


def test_t3_replay_supports_both_action_schemas_and_terminal_semantics():
    base = {"orders": {"o1": {"status": "pending"}}, "users": {}, "products": {}}

    def set_status(db, value):
        db["orders"]["o1"]["status"] = value
        return "ok"

    def terminal(db, summary):
        db["orders"]["o1"]["terminal_called"] = True
        return "Transfer successful"

    tool_map = {"set_status": set_status, "transfer_to_human_agents": terminal}
    gold = replay_actions(
        base,
        [{"name": "set_status", "kwargs": {"value": "cancelled"}}],
        tool_map,
    )
    assert gold["orders"]["o1"]["status"] == "cancelled"

    candidate = replay_actions(
        base,
        [
            {"tool": "set_status", "args": {"value": "cancelled"}},
            {"tool": "transfer_to_human_agents", "args": {"summary": "done"}},
            {"tool": "set_status", "args": {"value": "pending"}},
        ],
        tool_map,
        stop_on_terminal=True,
    )
    assert candidate["orders"]["o1"]["status"] == "cancelled"
    assert candidate["orders"]["o1"]["terminal_called"] is True


def test_t3_official_task_scorer_uses_gold_replay_and_live_candidate_state():
    base = {"orders": {"o1": {"status": "pending"}}, "users": {}, "products": {}}

    def loader():
        return deepcopy(base)

    def set_status(db, value):
        db["orders"]["o1"]["status"] = value

    candidate_db = deepcopy(base)
    set_status(candidate_db, "cancelled")
    result = score_official_task(
        loader,
        {"set_status": set_status},
        [{"name": "set_status", "kwargs": {"value": "cancelled"}}],
        candidate_db,
        [],
        [],
    )
    assert result["reward"] == 1.0

    plan_result = score_task(
        loader,
        {"set_status": set_status},
        [{"name": "set_status", "kwargs": {"value": "cancelled"}}],
        [{"tool": "set_status", "args": {"value": "cancelled"}}],
        [],
        [],
    )
    assert plan_result["reward"] == 1.0
    assert plan_result["gold_action_count"] == 1
    assert plan_result["candidate_action_count"] == 1



def test_t3_hash_is_identical_to_pinned_official_env_hash():
    all_tools, load_data = install_vendored_runtime()
    Env, Action, Task, fake_user, _ = _load_official_env(all_tools)
    from scripts.audit_evotool_tau_bench_conformance import _make_official_env

    row = {
        "user_id": "hash-probe-user",
        "instruction": "deterministic hash probe",
        "actions": [],
        "outputs": [],
    }
    env = _make_official_env(
        [row], all_tools, load_data, Env, Action, Task, fake_user
    )
    env.reset(task_index=0)
    assert official_state_hash(env.data) == env.get_data_hash()

    first_tool = next(
        tool for tool in all_tools
        if tool.get_info()["function"]["name"] != "transfer_to_human_agents"
    )
    tool_name = first_tool.get_info()["function"]["name"]
    # Use an action with the first tool's required argument schema only when
    # a no-argument tool is available; otherwise the base-state hash probe above
    # remains the deterministic reference check.
    if not first_tool.get_info()["function"].get("parameters", {}).get("required"):
        env.step(Action(name=tool_name, kwargs={}))
        assert official_state_hash(env.data) == env.get_data_hash()
