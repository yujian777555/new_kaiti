import unittest

from task_semantics import (
    LEGACY_TASKS,
    audit_split_catalog,
    build_split_catalog,
    build_task_family,
    enumerate_primary_compatible_sequences,
    profile_id,
    validate_task_family,
)


class TaskSemanticValidatorTests(unittest.TestCase):
    def test_all_legacy_families_satisfy_abstract_saga_contract(self):
        for name, tools in LEGACY_TASKS.items():
            spec = build_task_family(tools, family_id=name, legacy=True)
            result = validate_task_family(spec)
            self.assertTrue(result["ok"], (name, result["errors"]))

    def test_primary_compatible_pool_has_312_sequences(self):
        from task_semantics import TOOLS
        candidates = enumerate_primary_compatible_sequences()
        self.assertEqual(len(candidates), 312)
        for seq in candidates:
            self.assertTrue(TOOLS[seq[0]]["compensatable"])
            self.assertTrue(any(not TOOLS[t]["compensatable"] for t in seq))

    def test_duplicate_tool_is_rejected(self):
        spec = build_task_family(("inventory", "inventory", "ledger"))
        result = validate_task_family(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("at most once" in e for e in result["errors"]))

    def test_wrong_predecessor_receipt_is_rejected(self):
        spec = build_task_family(("inventory", "order", "ledger"))
        spec["steps"][1]["inputs"]["previous_receipt"]["producer"] = "calendar"
        result = validate_task_family(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("predecessor" in e or "previous receipt" in e for e in result["errors"]))

    def test_tool_contract_tampering_is_rejected(self):
        spec = build_task_family(("inventory", "order", "ledger"))
        spec["steps"][0]["tool_contract"]["idempotent"] = True
        result = validate_task_family(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("tool contract mismatch" in e for e in result["errors"]))

    def test_missing_postcondition_is_rejected(self):
        spec = build_task_family(("inventory", "order", "ledger"))
        spec["steps"][2]["postconditions"] = ["receipt_emitted"]
        result = validate_task_family(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing postconditions" in e for e in result["errors"]))

    def test_formal_split_is_8_4_40_and_disjoint(self):
        catalog = build_split_catalog()
        audit = audit_split_catalog(catalog)
        self.assertTrue(audit["ok"], audit["problems"])
        self.assertEqual([len(catalog[k]) for k in ("train", "validation", "test")], [8, 4, 40])
        ids = [f["family_id"] for split in ("train", "validation", "test") for f in catalog[split]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_test_split_covers_all_ten_primary_compatible_profiles(self):
        catalog = build_split_catalog()
        counts = {}
        for family in catalog["test"]:
            pid = profile_id(family["tools"])
            counts[pid] = counts.get(pid, 0) + 1
        self.assertEqual(len(counts), 10)
        self.assertEqual(set(counts.values()), {4})


if __name__ == "__main__":
    unittest.main()
