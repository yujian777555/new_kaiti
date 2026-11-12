from scripts.verify_evotool_full_source import verify_source_lock


def test_full_evotool_source_matches_pinned_upstream():
    report = verify_source_lock()
    assert report["gate"] == "PASS"
    assert report["source_commit"] == "6a82719ea6e22cf23f963078e2527094e50b47f6"
    assert report["expected_file_count"] == 34
    assert report["verified_file_count"] == 34
    assert report["failures"] == []
