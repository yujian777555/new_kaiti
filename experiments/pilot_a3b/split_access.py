"""R4 split-access controls and atomic one-time final-evaluation gate.

Development/optimization APIs can consume Train only. Ordinary evaluation
APIs may consume Train or Validation, never Test/Battery/unknown splits.
Test payload access is reserved for a separately approved one-time wrapper.
All tests in this module use synthetic sentinels only.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path


DEVELOPMENT_SPLITS = frozenset(("train", "validation"))


def public_manifest_view(manifest):
    """Return a safe manifest view with no Test scenario/family payload."""
    splits = manifest.get("splits")
    if not isinstance(splits, dict):
        raise ValueError("manifest splits must be an object")
    if "train" not in splits or "validation" not in splits or "test_locked" not in splits:
        raise ValueError("manifest must contain train, validation, and test_locked")

    locked = splits["test_locked"]
    safe_test = {
        "summary": deepcopy(locked.get("summary")),
        "family_sha256": locked.get("family_sha256"),
        "scenario_sha256": locked.get("scenario_sha256"),
        "payload_disclosed": False,
    }
    return {
        "schema_version": manifest.get("schema_version"),
        "generator_version": manifest.get("generator_version"),
        "status": manifest.get("status"),
        "semantic_contract_version": manifest.get("semantic_contract_version"),
        "seed_base": manifest.get("seed_base"),
        "hashes": deepcopy(manifest.get("hashes", {})),
        "splits": {
            "train": deepcopy(splits["train"]),
            "validation": deepcopy(splits["validation"]),
            "test_locked": safe_test,
        },
    }


def scenarios_for_split(manifest, split):
    """Return a copied Train/Validation scenario list; Test is never returned."""
    if split not in DEVELOPMENT_SPLITS:
        raise PermissionError("Test split is restricted to the final-evaluation gate")
    try:
        scenarios = manifest["splits"][split]["scenarios"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"manifest lacks {split} scenarios") from exc
    copied = deepcopy(scenarios)
    if not isinstance(copied, list) or not copied:
        raise ValueError(f"{split} scenarios must be a non-empty list")
    for scenario in copied:
        if not isinstance(scenario, dict) or scenario.get("split") != split:
            raise ValueError(f"scenario split metadata mismatch for {split}")
    return copied


def validate_evolution_scenarios(scenarios):
    """Fail before fitness evaluation unless every scenario is explicitly Train."""
    if not scenarios:
        raise ValueError("evolution requires a non-empty Train scenario set")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or scenario.get("split") != "train":
            raise ValueError("run_evolution accepts train split only")


def validate_evaluation_scenarios(scenarios):
    """Ordinary evaluator accepts Train/Validation, but never Test or Battery."""
    if not scenarios:
        raise ValueError("evaluation requires a non-empty Train/Validation scenario set")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or scenario.get("split") not in DEVELOPMENT_SPLITS:
            raise ValueError("test split is restricted to the final-evaluation gate")


def consume_final_evaluation_once(
    ledger_path,
    approval_record,
    expected_manifest_sha256,
    actual_manifest_sha256,
    expected_code_sha256,
    actual_code_sha256,
    payload_loader,
    evaluator,
):
    """Consume an atomic one-time ledger before invoking the Test payload loader.

    The ledger remains consumed if payload loading or evaluation fails. This is
    deliberate fail-closed behavior: a failed final attempt cannot be retried
    by silently opening Test a second time.
    """
    required = (
        approval_record.get("status") == "APPROVED"
        and approval_record.get("preflight_status") == "GO"
        and approval_record.get("ci_conclusion") == "success"
        and approval_record.get("tests_passed") is True
        and approval_record.get("independent_review_status") == "ACCEPTED"
        and approval_record.get("advisor_mde_approved") is True
        and approval_record.get("user_approved") is True
    )
    if not required:
        raise PermissionError("final evaluation requires pre-flight GO, successful CI/tests, independent, advisor, and user approval")
    if (approval_record.get("manifest_sha256") != expected_manifest_sha256
            or approval_record.get("code_sha256") != expected_code_sha256):
        raise ValueError("approval record hash mismatch")
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise ValueError("manifest hash mismatch")
    if actual_code_sha256 != expected_code_sha256:
        raise ValueError("code hash mismatch")

    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "state": "CONSUMED",
        "manifest_sha256": expected_manifest_sha256,
        "code_sha256": expected_code_sha256,
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("final-evaluation one-time ledger already consumed") from exc
    try:
        payload = json.dumps(record, sort_keys=True).encode("utf-8")
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    test_payload = payload_loader()
    return evaluator(test_payload)


def execute_final_evaluation_once(
    ledger_path,
    approval_record,
    preflight_result,
    expected_manifest_sha256,
    actual_manifest_sha256,
    expected_code_sha256,
    actual_code_sha256,
    payload_loader,
    evaluator,
):
    """Production wrapper: require pre-run GO, consume once, then issue a bound receipt."""
    if not isinstance(preflight_result, dict) or preflight_result.get("phase") != "PRE_RUN_AUTHORIZATION" or preflight_result.get("status") != "GO":
        raise PermissionError("final evaluation requires a successful PRE_RUN_AUTHORIZATION GO")
    approved = dict(approval_record)
    approved["preflight_status"] = preflight_result["status"]
    access_log_path = Path(str(ledger_path) + ".access.json")

    def logged_payload_loader():
        access_record = {
            "event": "TEST_PAYLOAD_LOAD_ATTEMPT",
            "state": "RECORDED",
            "manifest_sha256": actual_manifest_sha256,
            "code_sha256": actual_code_sha256,
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(access_log_path), flags, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("Test access log already exists; refusing another load") from exc
        try:
            os.write(fd, json.dumps(access_record, sort_keys=True).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return payload_loader()

    outcome_ledger = consume_final_evaluation_once(
        ledger_path, approved,
        expected_manifest_sha256, actual_manifest_sha256,
        expected_code_sha256, actual_code_sha256,
        logged_payload_loader, evaluator,
    )
    if not isinstance(outcome_ledger, dict):
        raise ValueError("final evaluator must return a run-ledger object")
    canonical = json.dumps(outcome_ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt = {
        "status": "COMPLETED",
        "manifest_sha256": actual_manifest_sha256,
        "code_sha256": actual_code_sha256,
        "ledger_path": str(ledger_path),
        "access_log_path": str(access_log_path),
        "test_access_log_count": 1,
        "outcome_ledger_sha256": __import__("hashlib").sha256(canonical).hexdigest(),
    }
    return outcome_ledger, receipt
