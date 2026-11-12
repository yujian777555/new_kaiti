"""D-088 eight-group comparative experiment runner.

Groups: L, A, B, C, AB, AC, BC, ABC.
Each group runs NSGA-III evolution on new Train-only families with matched
budget, scenarios, seeds, and evaluator.  Results are written to a JSONL ledger.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

from d088_scenario_generator import build_manifest  # noqa: E402
from d088_nsga3 import run_evolution  # noqa: E402

RESULTS_DIR = HERE / "results"


EXPERIMENT_GROUPS = {
    "L":   {"enable_mech_a": False, "enable_mech_b": False, "enable_mech_c": False},
    "A":   {"enable_mech_a": True,  "enable_mech_b": False, "enable_mech_c": False},
    "B":   {"enable_mech_a": False, "enable_mech_b": True,  "enable_mech_c": False},
    "C":   {"enable_mech_a": False, "enable_mech_b": False, "enable_mech_c": True},
    "AB":  {"enable_mech_a": True,  "enable_mech_b": True,  "enable_mech_c": False},
    "AC":  {"enable_mech_a": True,  "enable_mech_b": False, "enable_mech_c": True},
    "BC":  {"enable_mech_a": False, "enable_mech_b": True,  "enable_mech_c": True},
    "ABC": {"enable_mech_a": True,  "enable_mech_b": True,  "enable_mech_c": True},
}

SEEDS = [411, 522, 633]
POP_SIZE = 24
GENERATIONS = 30
INITIAL_POOL_SIZE = 36


def _sha256(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_all_experiments(tier: str = "discovery") -> dict:
    """Run all 8 experiment groups and write the ledger."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Build and freeze manifest
    manifest = build_manifest(tier=tier)
    manifest_path = RESULTS_DIR / f"d088_{tier}_manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    scenarios = manifest["scenarios"]
    print(f"[D-088] Tier={tier}, scenarios={len(scenarios)}, families={manifest['family_count']}")

    all_results = {}
    for group_name, mech_flags in EXPERIMENT_GROUPS.items():
        print(f"\n[D-088] Group {group_name} (flags={mech_flags})")
        group_results = []
        for seed in SEEDS:
            t0 = time.time()
            result = run_evolution(
                scenarios=scenarios,
                mech_flags=mech_flags,
                pop_size=POP_SIZE,
                generations=GENERATIONS,
                seed=seed,
                initial_pool_size=INITIAL_POOL_SIZE,
            )
            elapsed = time.time() - t0
            best = result["best"]
            print(f"  seed={seed}: R3={best['r3_success']:.3f} R4={best['r4_success']:.3f} "
                  f"CondRec={best['cond_rec']:.3f} cost={best['action_cost']:.1f} "
                  f"({elapsed:.1f}s)")
            group_results.append(result)

        all_results[group_name] = group_results

        # Write per-group result
        group_path = RESULTS_DIR / f"d088_{tier}_group_{group_name}.json"
        group_path.write_text(
            json.dumps(group_results, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    # Write summary
    summary = {
        "protocol_id": "D-088-MECHANISM-EXPERIMENT",
        "tier": tier,
        "manifest_sha256": manifest["manifest_sha256"],
        "scenario_count": len(scenarios),
        "seeds": SEEDS,
        "pop_size": POP_SIZE,
        "generations": GENERATIONS,
        "groups": {},
    }
    for group_name, results in all_results.items():
        best_per_seed = [r["best"] for r in results]
        summary["groups"][group_name] = {
            "mean_r3": sum(b["r3_success"] for b in best_per_seed) / len(best_per_seed),
            "mean_r4": sum(b["r4_success"] for b in best_per_seed) / len(best_per_seed),
            "mean_cond_rec": sum(b["cond_rec"] for b in best_per_seed) / len(best_per_seed),
            "mean_action_cost": sum(b["action_cost"] for b in best_per_seed) / len(best_per_seed),
            "mean_avoid_harm": sum(b["avoid_harm"] for b in best_per_seed) / len(best_per_seed),
            "per_seed": [
                {"seed": r["seed"], **{k: v for k, v in r["best"].items() if k != "genome"}}
                for r in results
            ],
        }

    summary["summary_sha256"] = _sha256({k: v for k, v in summary.items() if k != "summary_sha256"})
    summary_path = RESULTS_DIR / f"d088_{tier}_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    print(f"\n[D-088] Summary written to {summary_path}")
    print(f"[D-088] Summary SHA-256: {summary['summary_sha256']}")

    # Print comparison table
    print("\n" + "=" * 70)
    print(f"{'Group':<6} {'R3':>6} {'R4':>6} {'CondRec':>8} {'Cost':>7} {'Harm':>7}")
    print("-" * 70)
    for group_name in EXPERIMENT_GROUPS:
        g = summary["groups"][group_name]
        print(f"{group_name:<6} {g['mean_r3']:>6.3f} {g['mean_r4']:>6.3f} "
              f"{g['mean_cond_rec']:>8.3f} {g['mean_action_cost']:>7.1f} "
              f"{g['mean_avoid_harm']:>7.3f}")
    print("=" * 70)

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", default="discovery", choices=["discovery", "fresh"])
    args = parser.parse_args()
    run_all_experiments(tier=args.tier)
