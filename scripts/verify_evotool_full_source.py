#!/usr/bin/env python3
"""Verify the vendored full EvoTool source against its pinned upstream Git blobs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "vendor" / "evotool" / "FULL_SOURCE_LOCK.json"


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_source_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    verified = []
    failures = []
    for item in lock["source_files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            failures.append(f"missing: {item['path']}")
            continue
        actual = git_blob_sha1(path.read_bytes())
        matches = actual == item["git_blob_sha"]
        verified.append({"path": item["path"], "git_blob_sha": actual, "matches_lock": matches})
        if not matches:
            failures.append(
                f"sha mismatch: {item['path']} expected={item['git_blob_sha']} actual={actual}"
            )
    return {
        "gate": "PASS" if not failures and len(verified) == len(lock["source_files"]) else "FAIL",
        "source_repository": lock["source_repository"],
        "source_commit": lock["source_commit"],
        "expected_file_count": len(lock["source_files"]),
        "verified_file_count": sum(x["matches_lock"] for x in verified),
        "failures": failures,
        "verified": verified,
    }


def main() -> int:
    report = verify_source_lock()
    print(json.dumps({
        "gate": report["gate"],
        "source_repository": report["source_repository"],
        "source_commit": report["source_commit"],
        "expected_file_count": report["expected_file_count"],
        "verified_file_count": report["verified_file_count"],
        "failures": report["failures"],
    }, indent=2))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
