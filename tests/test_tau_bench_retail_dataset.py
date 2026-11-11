from pathlib import Path
import json
import os
import tempfile

import pytest

from scripts.prepare_tau_bench_retail import build_dataset, install_vendored_runtime


@pytest.fixture(scope="module")
def audited_dataset(tmp_path_factory):
    configured = os.environ.get("TAU_BENCH_AUDIT_OUTPUT")
    if configured:
        out = Path(configured)
        report_path = out / "integrity_report.json"
        assert report_path.is_file(), f"missing prebuilt audit report: {report_path}"
        return json.loads(report_path.read_text(encoding="utf-8")), out

    install_vendored_runtime()
    out = tmp_path_factory.mktemp("tau-bench-retail-audit")
    report = build_dataset(out)
    return report, out


def test_legacy_tau_bench_retail_splits_are_source_pinned_and_integral(audited_dataset):
    report, _ = audited_dataset
    gold = report["gold_action_audit"]
    diagnostics = {
        "failures": report["failures"],
        "domain_error_count": gold["domain_error_count"],
        "domain_error_examples": gold["domain_errors"],
        "invocation_errors": gold["invocation_errors"],
        "signature_errors": gold["signature_errors"],
    }
    assert report["source_integrity_gate"] == "PASS", json.dumps(diagnostics, ensure_ascii=False, indent=2)
    assert report["gold_action_gate"] == "PASS_WITH_DOMAIN_REJECTIONS", json.dumps(diagnostics, ensure_ascii=False, indent=2)
    assert report["gate"] == "PASS_WITH_CAVEAT", json.dumps(diagnostics, ensure_ascii=False, indent=2)
    assert report["total_tasks"] == 635
    assert {name: item["task_count"] for name, item in report["splits"].items()} == {
        "train": 500,
        "dev": 20,
        "test": 115,
    }
    assert report["source"]["verified_file_count"] == 42
    assert report["database"]["referential_integrity_failure_count"] == 0
    assert report["task_user_reference_failure_count"] == 0
    assert report["cross_split_exact_duplicate_fingerprint_groups"] == 0
    assert report["cross_split_instruction_duplicate_groups"] == 0
    assert report["within_split_exact_duplicate_task_counts"] == {"train": 0, "dev": 0, "test": 1}
    assert report["splits"]["train"]["tasks_with_nonempty_required_outputs"] == 0
    assert report["splits"]["dev"]["tasks_with_nonempty_required_outputs"] == 0
    assert report["splits"]["test"]["tasks_with_nonempty_required_outputs"] == 37
    assert report["splits"]["test"]["required_output_string_count"] == 62
    assert gold["unknown_tool_count"] == 0
    assert gold["signature_error_count"] == 0
    assert gold["invocation_error_count"] == 0
    assert gold["domain_error_count"] == 44
    assert gold["domain_error_task_count"] == 38
    assert gold["domain_error_counts_by_split"] == {"test": 24, "train": 20}
    assert gold["domain_error_counts_by_tool"] == {
        "exchange_delivered_order_items": 5,
        "find_user_id_by_email": 6,
        "find_user_id_by_name_zip": 4,
        "get_order_details": 4,
        "get_product_details": 6,
        "modify_pending_order_items": 8,
        "modify_pending_order_payment": 9,
        "return_delivered_order_items": 2,
    }
    assert gold["domain_error_counts_by_message"] == {
        "Error: insufficient gift card balance to pay for the new item": 8,
        "Error: insufficient gift card balance to pay for the order": 9,
        "Error: insufficient gift card balance to pay for the price difference": 4,
        "Error: non-delivered order cannot be exchanged": 1,
        "Error: order not found": 4,
        "Error: payment method should be either the original payment method or a gift card": 2,
        "Error: product not found": 6,
        "Error: user not found": 10,
    }
    assert gold["deterministic_replay_mismatch_count"] == 0


def test_normalized_records_keep_original_split_and_gold_fields(audited_dataset):
    report, out = audited_dataset
    for split in ("train", "dev", "test"):
        rows = (out / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(rows) == report["splits"][split]["task_count"]
        first = json.loads(rows[0])
        assert first["split"] == split
        assert first["task_index"] == 0
        assert first["task_id"] == f"retail-{split}-0000"
        assert "actions" in first and "outputs" in first
