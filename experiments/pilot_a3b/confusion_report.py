"""Confusion matrix report for the Stage-1 recoverability classifier."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from mini_env import all_specs
from reachability import classify

HORIZON_DEFAULT = 12
HORIZON_OVERRIDES = {"c10_depth_exceeded": 4}


def build_confusion():
    rows = []
    matrix = defaultdict(lambda: Counter())
    for spec in all_specs():
        horizon = HORIZON_OVERRIDES.get(spec.name, HORIZON_DEFAULT)
        got = classify(spec, horizon=horizon)
        expected = spec.expected_class
        matrix[expected][got.label] += 1
        rows.append(
            {
                "case": spec.name,
                "expected": expected,
                "predicted": got.label,
                "match": got.label == expected,
                "horizon": horizon,
                "notes": spec.notes,
                "evidence_keys": sorted(got.evidence.keys()),
                "reason": got.evidence.get("reason", ""),
            }
        )
    unknown = sum(1 for r in rows if r["predicted"] == "UNKNOWN")
    mismatches = [r for r in rows if not r["match"]]
    return {
        "total": len(rows),
        "correct": len(rows) - len(mismatches),
        "mismatch_count": len(mismatches),
        "unknown_count": unknown,
        "unknown_ratio": round(unknown / len(rows), 4),
        "matrix": {k: dict(v) for k, v in sorted(matrix.items())},
        "mismatches": mismatches,
        "rows": rows,
    }


def main():
    report = build_confusion()
    out = Path(__file__).parent / "confusion_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total", "correct", "mismatch_count", "unknown_count", "unknown_ratio", "matrix")}, indent=2))
    if report["mismatches"]:
        print("MISMATCHES:")
        for m in report["mismatches"]:
            print(" ", m)
    else:
        print("All ground-truth cases classified correctly.")


if __name__ == "__main__":
    main()
