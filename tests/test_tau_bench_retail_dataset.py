from pathlib import Path
import json
import tempfile

from scripts.prepare_tau_bench_retail import (
    build_dataset,
    install_vendored_runtime,
)


def test_legacy_tau_bench_retail_splits_are_source_pinned_and_integral():
    install_vendored_runtime()
    with tempfile.TemporaryDirectory(prefix="tau-bench-retail-audit-") as tmp:
        report = build_dataset(Path(tmp))

    assert report["gate"] == "PASS", report["failures"]
    assert report["total_tasks"] == 635
    assert {name: item["task_count"] for name, item in report["splits"].items()} == {
        "train": 500,
        "dev": 20,
        "test": 115,
    }
    assert report["source"]["verified_file_count"] == 35
    assert report["database"]["referential_integrity_failure_count"] == 0
    assert report["task_user_reference_failure_count"] == 0

    gold = report["gold_action_audit"]
    assert gold["unknown_tool_count"] == 0
    assert gold["signature_error_count"] == 0
    assert gold["invocation_error_count"] == 0
    assert gold["domain_error_count"] == 0
    assert gold["deterministic_replay_mismatch_count"] == 0


def test_normalized_records_keep_original_split_and_gold_fields():
    install_vendored_runtime()
    with tempfile.TemporaryDirectory(prefix="tau-bench-retail-records-") as tmp:
        out = Path(tmp)
        report = build_dataset(out)
        assert report["gate"] == "PASS"
        for split in ("train", "dev", "test"):
            rows = (out / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            assert len(rows) == report["splits"][split]["task_count"]
            first = json.loads(rows[0])
            assert first["split"] == split
            assert first["task_index"] == 0
            assert first["task_id"] == f"retail-{split}-0000"
            assert "actions" in first and "outputs" in first
