from pathlib import Path
import json
import os

import pytest

from scripts.audit_evotool_tau_bench_conformance import (
    build_conformance_report,
    write_report,
)


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



def test_action_history_matches_exact_ordered_sequence_for_every_gold_task(conformance_report):
    reward = conformance_report["reward_parity"]
    assert reward["action_history_checked_task_count"] == 635
    assert reward["action_history_mismatch_count"] == 0
    probe = reward["action_history_probe"]
    assert probe["matches_source_behavior"] is True
    assert probe["observed_history_length"] == probe["expected_history_length"]
    assert probe["first_mismatch_index"] is None
    assert len(probe["expected_sequence_sha256"]) == 64
    assert probe["observed_sequence_sha256"] == probe["expected_sequence_sha256"]


def test_official_reset_and_evotool_fresh_instances_are_isolated(conformance_report):
    probe = conformance_report["db_reset_copy_probe"]
    assert probe["gate"] == "PASS"
    assert probe["initial_official_matches_base"] is True
    assert probe["initial_adapter_matches_base"] is True
    assert probe["adapter_instances_are_isolated"] is True
    assert probe["official_reset_restores_base"] is True
    assert probe["adapter_reconstruction_restores_base"] is True
    assert probe["fresh_adapter_matches_official_reset"] is True


def test_environment_dispatch_parity_and_known_error_serialization(conformance_report):
    probes = conformance_report["dispatch_semantics_probe"]
    success = probes["successful_gold_action"]
    assert success["output_equal"] is True
    assert success["state_equal"] is True
    domain = probes["domain_rejection_gold_action"]
    assert domain["output_equal"] is True
    assert domain["state_equal"] is True
    assert domain["official_done"] is False
    assert domain["adapter_status"] == "success"
    assert domain["official_output"].startswith("Error:")
    unknown = probes["unknown_tool"]
    assert unknown["output_equal"] is False
    assert unknown["adapter_status"] == "error"
    assert unknown["official_output"].startswith("Unknown action")
    assert unknown["adapter_output"].startswith("Error:")
    malformed = probes["missing_required_argument"]
    assert malformed["output_equal"] is False
    assert malformed["adapter_status"] == "error"
    assert malformed["official_output"].startswith("Error:")
    assert malformed["adapter_output"].startswith("Error:")



def test_markdown_report_surfaces_step3_r1_evidence(conformance_report, tmp_path):
    write_report(conformance_report, tmp_path)
    report_text = (tmp_path / "evotool_tau_bench_conformance.md").read_text(encoding="utf-8")
    assert "## Dataset integrity precondition" in report_text
    assert "## Exact Action History" in report_text
    assert "Ordered sequence mismatches: 0" in report_text
    assert "## DB reset/copy isolation" in report_text
    assert "## Environment dispatch semantics" in report_text
    assert "unknown_tool: output_equal=False" in report_text
