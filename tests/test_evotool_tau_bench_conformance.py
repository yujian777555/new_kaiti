from pathlib import Path
import json
import os

import pytest

from scripts.audit_evotool_tau_bench_conformance import (
    _DeterministicUser,
    _load_official_env,
    _make_official_env,
    build_conformance_report,
    write_report,
)
from scripts.prepare_tau_bench_retail import install_vendored_runtime


@pytest.fixture(scope="module")
def conformance_report(tmp_path_factory):
    configured = os.environ.get("TAU_BENCH_AUDIT_OUTPUT")
    if configured:
        dataset_dir = Path(configured)
        report_path = dataset_dir / "evotool_tau_bench_conformance.json"
        if report_path.is_file():
            return json.loads(report_path.read_text(encoding="utf-8"))
    else:
        from scripts.prepare_tau_bench_retail import build_dataset
        dataset_dir = tmp_path_factory.mktemp("tau-bench-retail")
        build_dataset(dataset_dir)

    report = build_conformance_report(dataset_dir)
    write_report(report, dataset_dir)
    return report


def test_pinned_evotool_snapshot_and_adapted_splits_are_integral(conformance_report):
    report = conformance_report
    assert report["sources"]["evotool"]["verified_file_count"] == 9
    assert {
        split: report["adapted_split_artifacts"][split]["task_count"]
        for split in ("train", "dev", "test")
    } == {"train": 500, "dev": 20, "test": 115}
    assert {
        split: report["adapted_split_artifacts"][split]["gold_action_count"]
        for split in ("train", "dev", "test")
    } == {"train": 768, "dev": 25, "test": 582}
    assert all(
        report["adapted_split_artifacts"][split]["available_tool_count"] == 16
        for split in ("train", "dev", "test")
    )


def test_official_and_evotool_tool_implementations_match_all_gold_calls(conformance_report):
    tool = conformance_report["tool_implementation_parity"]
    assert tool["gate"] == "PASS"
    assert tool["total_gold_action_calls"] == 1375
    assert tool["calls_by_split"] == {"train": 768, "dev": 25, "test": 582}
    assert tool["tool_name_sets_equal"] is True
    assert tool["unknown_official_tools"] == []
    assert tool["missing_evotool_tools"] == []
    assert tool["output_mismatch_count"] == 0
    assert tool["exception_mismatch_count"] == 0
    assert tool["full_database_state_mismatch_count"] == 0
    assert tool["product_mutation_count"] == 0
    assert tool["official_domain_rejection_count"] == 44
    assert tool["evotool_domain_rejection_count"] == 44


def test_official_gold_reward_replay_matches_evotool_gold_success(conformance_report):
    reward = conformance_report["reward_parity"]
    assert reward["gold_task_count"] == 635
    assert reward["official_vs_evotool_gold_mismatch_count"] == 0
    assert reward["official_gold_reward_failures"] == []
    assert reward["evotool_gold_success_failures"] == []
    assert reward["action_history_probe"]["matches_source_behavior"] is True


def test_output_matching_deviations_are_detected_not_silently_normalized(conformance_report):
    probes = conformance_report["output_semantics_probes"]
    assert probes["case_insensitive"]["official_reward"] == 1.0
    assert probes["case_insensitive"]["evotool_success"] is False
    assert probes["case_insensitive"]["same_result"] is False
    assert probes["comma_normalization"]["official_reward"] == 1.0
    assert probes["comma_normalization"]["evotool_success"] is False
    assert probes["comma_normalization"]["same_result"] is False
    assert probes["multiple_conversation_responses"]["official_reward"] == 1.0
    assert probes["multiple_conversation_responses"]["evotool_success"] is False
    assert probes["multiple_conversation_responses"]["same_result"] is False


def test_domain_rejection_is_call_return_success_not_business_success(conformance_report):
    probe = conformance_report["domain_error_progress_probe"]
    assert probe is not None
    assert probe["output"].startswith("Error:")
    assert probe["adapter_status"] == "success"
    assert probe["progress_when_returned_normally"] == 1.0
    assert probe["progress_if_domain_rejection_counted_as_error"] == 0.5
    assert probe["evolution_reward_component_delta_at_weight_0_3"] == 0.15


def test_protocol_difference_is_explicit_and_projection_scope_is_bounded(conformance_report):
    protocol = conformance_report["interaction_protocol"]
    official = protocol["official_tau_bench"]
    evotool = protocol["evotool"]
    assert official["calls_env_reset"] is True
    assert official["calls_env_step"] is True
    assert official["sends_tool_observations_back"] is True
    assert official["sends_user_responses_back"] is True
    assert official["uses_retail_wiki_as_system_prompt"] is True
    assert official["user_simulator_uses_litellm_completion"] is True
    assert official["retail_env_marks_transfer_terminal"] is True
    assert evotool["planner_selector_caller_synthesizer_pipeline"] is True
    assert evotool["calls_official_env_reset"] is False
    assert evotool["calls_user_simulator_step"] is False
    assert evotool["injects_retail_wiki"] is False
    assert evotool["max_steps_config"] == 6
    projection = conformance_report["mutable_state_projection_probe"]
    assert projection["actual_products_mutated_by_any_gold_action"] == 0
    assert projection["hypothetical_product_only_change_ignored_by_evotool_projection"] is True
    assert conformance_report["overall_gate"] == "PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS"

def test_return_error_aware_status_is_a_sensitivity_treatment_not_official_reward(conformance_report):
    status = conformance_report["status_treatment_replay"]
    assert status["policy_evaluation_performed"] is False
    assert status["llm_api_calls"] == 0
    assert status["binary_task_reward_in_scope"] is False
    assert status["tool_outputs_and_database_transitions_unchanged"] is True
    assert status["total_task_count"] == 635
    assert status["gold_action_count"] == 1375
    assert status["returned_error_action_count"] == 44
    assert status["tasks_with_returned_error"] == 38
    assert status["by_split"]["train"]["returned_error_action_count"] == 20
    assert status["by_split"]["dev"]["returned_error_action_count"] == 0
    assert status["by_split"]["test"]["returned_error_action_count"] == 24
    assert status["mean_return_error_aware_progress"] < status["mean_legacy_progress"]
    assert status["mean_weighted_shaped_reward_delta"] > 0


def test_harness_fake_user_is_a_scripted_transport_not_a_simulator():
    user = _DeterministicUser()
    assert user.reset("task-conditioned instruction") == "Deterministic test customer."
    user.responses = ["continue", "###STOP###"]
    assert user.step("Agent message one") == "continue"
    assert user.step("Agent message two") == "###STOP###"
    assert user.instruction == "task-conditioned instruction"
    assert user.received_agent_messages == ["Agent message one", "Agent message two"]
    assert user.get_total_cost() == 0.0


def test_official_env_calls_user_step_only_for_respond_and_uses_scripted_stop():
    all_tools, load_data = install_vendored_runtime()
    Env, Action, Task, fake_user, _ = _load_official_env(all_tools)
    row = {
        "user_id": "offline_fake_user_test",
        "instruction": "exercise the official Env protocol",
        "actions": [],
        "outputs": [],
    }
    env = _make_official_env([row], all_tools, load_data, Env, Action, Task, fake_user)
    fake_user.responses = ["continue", "###STOP###"]

    reset = env.reset(task_index=0)
    assert reset.observation == "Deterministic test customer."
    assert fake_user.reset_calls == 1
    assert fake_user.instruction == row["instruction"]

    tool_response = env.step(Action(name="think", kwargs={"thought": "offline"}))
    assert tool_response.done is False
    assert fake_user.step_calls == 0

    first = env.step(Action(name="respond", kwargs={"content": "Agent message one"}))
    assert first.observation == "continue"
    assert first.done is False
    assert fake_user.step_calls == 1

    final = env.step(Action(name="respond", kwargs={"content": "Agent message two"}))
    assert final.observation == "###STOP###"
    assert final.done is True
    assert final.reward == 1.0
    assert fake_user.step_calls == 2
    assert fake_user.received_agent_messages == ["Agent message one", "Agent message two"]


def test_official_terminal_tool_stops_without_calling_user_simulator():
    all_tools, load_data = install_vendored_runtime()
    Env, Action, Task, fake_user, _ = _load_official_env(all_tools)
    row = {
        "user_id": "offline_terminal_tool_test",
        "instruction": "exercise terminal tool behavior",
        "actions": [],
        "outputs": [],
    }
    env = _make_official_env([row], all_tools, load_data, Env, Action, Task, fake_user)
    env.reset(task_index=0)
    response = env.step(
        Action(name="transfer_to_human_agents", kwargs={"summary": "offline terminal test"})
    )
    assert response.observation == "Transfer successful"
    assert response.done is True
    assert response.reward == 1.0
    assert fake_user.step_calls == 0

