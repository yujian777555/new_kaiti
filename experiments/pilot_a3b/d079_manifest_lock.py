"""Tamper-evident lock for the Train-only D-079 challenge manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from d079_challenge_generator import validate_challenge_manifest

LOCK_VERSION = "d079-train-only-manifest-lock-v1"


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _content_hash(manifest):
    value = {key: item for key, item in manifest.items() if key != "manifest_sha256"}
    return _sha256_bytes(_canonical(value))


def _scenario_ids_hash(manifest):
    scenario_ids = sorted(row["scenario_id"] for row in manifest["scenarios"])
    return _sha256_bytes(_canonical(scenario_ids))


def build_manifest_lock(manifest_path):
    """Build a lock only after the complete Train-only challenge gate passes."""
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    gate = validate_challenge_manifest(manifest)
    if not gate["ok"]:
        raise ValueError("challenge manifest gate failed: " + "; ".join(gate["problems"]))
    content_sha = _content_hash(manifest)
    if manifest.get("manifest_sha256") != content_sha:
        raise ValueError("challenge manifest content hash mismatch")
    return {
        "lock_version": LOCK_VERSION,
        "status": "LOCKED_TRAIN_ONLY",
        "generator_version": manifest["generator_version"],
        "seed_base": manifest["seed_base"],
        "family_count": manifest["family_count"],
        "scenario_count": manifest["scenario_count"],
        "search_scenario_count": manifest["search_scenario_count"],
        "diagnostic_scenario_count": manifest["diagnostic_scenario_count"],
        "cluster_count": manifest["cluster_count"],
        "manifest_file_name": manifest_path.name,
        "manifest_file_sha256": _sha256_bytes(raw),
        "manifest_content_sha256": content_sha,
        "scenario_ids_sha256": _scenario_ids_hash(manifest),
        "label_counts_by_role": manifest["label_counts_by_role"],
        "validation_included": False,
        "test_included": False,
        "test_outcomes_read": False,
    }


def verify_manifest_lock(manifest, lock):
    """Recompute all content/config/scenario invariants from the manifest."""
    problems = []
    if not isinstance(lock, dict) or lock.get("lock_version") != LOCK_VERSION:
        return {"ok": False, "problems": ["missing or unsupported manifest lock"]}
    if lock.get("status") != "LOCKED_TRAIN_ONLY":
        problems.append("lock status is not LOCKED_TRAIN_ONLY")
    if lock.get("manifest_content_sha256") != _content_hash(manifest):
        problems.append("manifest content hash mismatch")
    if lock.get("scenario_ids_sha256") != _scenario_ids_hash(manifest):
        problems.append("scenario ID set hash mismatch")
    for field in (
        "generator_version", "seed_base", "family_count", "scenario_count",
        "search_scenario_count", "diagnostic_scenario_count", "cluster_count",
        "label_counts_by_role",
    ):
        if lock.get(field) != manifest.get(field):
            problems.append(f"locked field mismatch: {field}")
    if lock.get("validation_included") is not False or lock.get("test_included") is not False:
        problems.append("lock is not restricted to Train-only development")
    return {"ok": not problems, "problems": problems}


def verify_manifest_lock_files(manifest_path, lock):
    """Verify raw file bytes in addition to all semantic content invariants."""
    raw = Path(manifest_path).read_bytes()
    problems = []
    if lock.get("manifest_file_sha256") != _sha256_bytes(raw):
        problems.append("manifest raw file hash mismatch")
    result = verify_manifest_lock(json.loads(raw), lock)
    problems.extend(result["problems"])
    return {"ok": not problems, "problems": problems}


def write_manifest_lock(lock, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "d079_manifest_lock.json"
    path.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    lock = build_manifest_lock(args.manifest)
    path = write_manifest_lock(lock, args.outdir)
    result = verify_manifest_lock_files(args.manifest, lock)
    if not result["ok"]:
        raise RuntimeError("manifest lock self-verification failed: " + "; ".join(result["problems"]))
    print(json.dumps({
        "status": lock["status"], "lock": str(path),
        "manifest_content_sha256": lock["manifest_content_sha256"],
        "manifest_file_sha256": lock["manifest_file_sha256"],
        "scenario_ids_sha256": lock["scenario_ids_sha256"],
        "verify_ok": result["ok"],
    }, indent=2))


if __name__ == "__main__":
    main()
