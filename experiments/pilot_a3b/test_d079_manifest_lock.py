"""Tamper-evidence tests for the Train-only D-079 manifest lock."""
import json
import tempfile
import unittest
from pathlib import Path

from d079_challenge_generator import build_challenge_manifest
from d079_manifest_lock import (
    build_manifest_lock,
    verify_manifest_lock,
    verify_manifest_lock_files,
)


class ManifestLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest_path = Path(self.tmp.name) / "d079_challenge_manifest.json"
        manifest = build_challenge_manifest()
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.manifest = manifest
        self.lock = build_manifest_lock(self.manifest_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_records_generator_config_scenarios_and_both_hashes(self):
        lock = self.lock
        self.assertEqual(lock["status"], "LOCKED_TRAIN_ONLY")
        self.assertEqual(lock["scenario_count"], 288)
        self.assertEqual(lock["family_count"], 8)
        self.assertEqual(lock["manifest_content_sha256"], self.manifest["manifest_sha256"])
        self.assertEqual(len(lock["manifest_file_sha256"]), 64)
        self.assertEqual(len(lock["scenario_ids_sha256"]), 64)
        self.assertEqual(lock["generator_version"], self.manifest["generator_version"])
        self.assertEqual(lock["seed_base"], self.manifest["seed_base"])
        self.assertTrue(verify_manifest_lock(self.manifest, lock)["ok"])
        self.assertTrue(verify_manifest_lock_files(self.manifest_path, lock)["ok"])

    def test_label_tampering_invalidates_content_lock(self):
        tampered = json.loads(json.dumps(self.manifest))
        tampered["scenarios"][0]["label"] = (
            "R2" if tampered["scenarios"][0]["label"] != "R2" else "R1"
        )
        result = verify_manifest_lock(tampered, self.lock)
        self.assertFalse(result["ok"])
        self.assertTrue(any("content" in problem for problem in result["problems"]))

    def test_scenario_id_tampering_invalidates_id_and_content_locks(self):
        tampered = json.loads(json.dumps(self.manifest))
        tampered["scenarios"][0]["scenario_id"] += "|tampered"
        result = verify_manifest_lock(tampered, self.lock)
        self.assertFalse(result["ok"])
        self.assertTrue(any("scenario" in problem.lower() for problem in result["problems"]))

    def test_raw_file_whitespace_tampering_invalidates_file_hash(self):
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        result = verify_manifest_lock_files(self.manifest_path, self.lock)
        self.assertFalse(result["ok"])
        self.assertTrue(any("file" in problem for problem in result["problems"]))

    def test_generator_or_seed_change_fails_closed(self):
        tampered = dict(self.lock)
        tampered["seed_base"] += 1
        self.assertFalse(verify_manifest_lock(self.manifest, tampered)["ok"])

    def test_unknown_or_count_tampering_is_rejected_before_lock(self):
        tampered = json.loads(json.dumps(self.manifest))
        tampered["scenarios"][0]["label"] = "UNKNOWN"
        tampered_path = self.manifest_path.with_name("tampered.json")
        tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "challenge manifest gate"):
            build_manifest_lock(tampered_path)


if __name__ == "__main__":
    unittest.main()
