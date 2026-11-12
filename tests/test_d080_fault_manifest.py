import os
from pathlib import Path
import pytest
from scripts.build_d080_fault_manifest import build_manifest,validate_manifest,load_rows
from scripts.prepare_tau_bench_retail import install_vendored_runtime

def test_d080_train_manifest_is_balanced_split_pure_and_gold_argument_free():
 dataset=os.environ.get("D080_DATASET_DIR")
 if not dataset: pytest.skip("D080_DATASET_DIR is supplied by CI")
 manifest=build_manifest(Path(dataset))
 rows,digest=load_rows(Path(dataset))
 classes,load_data=install_vendored_runtime()
 tool_map={x.get_info()["function"]["name"]:x.invoke for x in classes}
 result=validate_manifest(manifest,rows,tool_map,load_data())
 assert result["ok"] and result["event_count"]==48 and result["unique_task_count"]==48
 assert manifest["source_train_jsonl_sha256"]==digest
 for event in manifest["events"]:
  assert "kwargs" not in event and "args" not in event
  assert event["task_id"].startswith("retail-train-")
