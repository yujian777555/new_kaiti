#!/usr/bin/env python3
"""Deterministic Train-only audit of T1 instrumentation and T3 official scoring."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_evotool_tau_bench_conformance import (
    _load_evotool_snapshot,
    _load_official_env,
    _make_official_env,
    _official_score,
    _read_jsonl,
    _to_evotool_record,
    _verify_dataset_integrity,
)
from scripts.prepare_tau_bench_retail import install_vendored_runtime
from treatments.evotool_status import StatusDecomposedExecutor
from treatments.taubench_official_reward import score_task

def build_treatment_audit(dataset_dir: Path) -> dict[str, Any]:
    integrity = _verify_dataset_integrity(dataset_dir)
    all_tools, load_data = install_vendored_runtime()
    evotool_env, evotool_tools, metrics = _load_evotool_snapshot()
    base_data = load_data()
    evotool_env.load_db = lambda: copy.deepcopy(base_data)

    # Hard boundary: this treatment audit reads and scores Train only. The
    # integrity precondition verifies split hashes but does not load Dev/Test rows.
    train_rows = _read_jsonl(dataset_dir / "train.jsonl")
    if len(train_rows) != 500:
        raise RuntimeError(f"expected 500 Train tasks, found {len(train_rows)}")

    cards = [
        {
            "name": tool.get_info()["function"]["name"],
            "description": tool.get_info()["function"].get("description", ""),
            "parameters": tool.get_info()["function"].get("parameters", {}),
        }
        for tool in all_tools
    ]
    cards.sort(key=lambda item: item["name"])

    # T1: compare a legacy executor and a diagnostic wrapper from identical
    # database snapshots. The wrapper must preserve every legacy result field,
    # state transition, progress value, and episode reward.
    legacy_env = evotool_env.TauBenchEnv()
    diagnostic_env = evotool_env.TauBenchEnv()

    t1 = {
        "split": "train",
        "task_count": 0,
        "gold_action_call_count": 0,
        "domain_error_return_count": 0,
        "legacy_field_mismatch_count": 0,
        "database_state_mismatch_count": 0,
        "progress_mismatch_count": 0,
        "episode_reward_mismatch_count": 0,
        "business_outcome_counts": Counter(),
        "execution_status_counts": Counter(),
        "state_effect_counts": Counter(),
    }

    for row in train_rows:
        legacy_env.db = copy.deepcopy(base_data)
        diagnostic_env.db = copy.deepcopy(base_data)
        diagnostic = StatusDecomposedExecutor(
            diagnostic_env, evotool_tools.TOOLS.keys()
        )

        legacy_steps = []
        diagnostic_steps = []
        predicted = []
        for action in row["actions"]:
            tool, args = action["name"], action["kwargs"]
            legacy_result = legacy_env.execute(tool, args)
            diagnostic_result = diagnostic.execute(tool, args)
            t1["gold_action_call_count"] += 1

            legacy_core = {
                key: legacy_result.get(key)
                for key in ("tool", "args", "output", "status")
            }
            diagnostic_core = {
                key: diagnostic_result.get(key)
                for key in ("tool", "args", "output", "status")
            }
            if legacy_core != diagnostic_core:
                t1["legacy_field_mismatch_count"] += 1
            if legacy_env.db != diagnostic_env.db:
                t1["database_state_mismatch_count"] += 1

            t1["execution_status_counts"][diagnostic_result["execution_status"]] += 1
            t1["business_outcome_counts"][diagnostic_result["business_outcome"]] += 1
            t1["state_effect_counts"][diagnostic_result["state_effect"]] += 1
            if str(legacy_result.get("output", "")).startswith("Error:"):
                t1["domain_error_return_count"] += 1

            legacy_steps.append(
                {"tool": tool, "status": legacy_result.get("status")}
            )
            diagnostic_steps.append(
                {"tool": tool, "status": diagnostic_result.get("status")}
            )
            predicted.append({"tool": tool, "args": args})

        instance = _to_evotool_record(row, cards)
        legacy_progress = metrics.progress(legacy_steps, instance)
        diagnostic_progress = metrics.progress(diagnostic_steps, instance)
        if legacy_progress != diagnostic_progress:
            t1["progress_mismatch_count"] += 1

        legacy_success = bool(
            evotool_env.taubench_success(instance, predicted, "")
        )
        diagnostic_success = bool(
            evotool_env.taubench_success(instance, predicted, "")
        )
        legacy_reward = 0.7 * float(legacy_success) + 0.3 * legacy_progress
        diagnostic_reward = 0.7 * float(diagnostic_success) + 0.3 * diagnostic_progress
        if legacy_reward != diagnostic_reward:
            t1["episode_reward_mismatch_count"] += 1
        t1["task_count"] += 1

    for key in (
        "business_outcome_counts",
        "execution_status_counts",
        "state_effect_counts",
    ):
        t1[key] = dict(sorted(t1[key].items()))
    t1["gate"] = (
        "PASS"
        if t1["task_count"] == 500
        and t1["gold_action_call_count"] == 768
        and t1["legacy_field_mismatch_count"] == 0
        and t1["database_state_mismatch_count"] == 0
        and t1["progress_mismatch_count"] == 0
        and t1["episode_reward_mismatch_count"] == 0
        else "FAIL"
    )

    # T3: use the pinned official tool implementations and official Env.calculate_reward
    # as the reference. Only Train Gold trajectories are replayed; no policy is run.
    official_tool_map = {
        tool.get_info()["function"]["name"]: tool.invoke for tool in all_tools
    }
    Env, Action, Task, fake_user, _ = _load_official_env(all_tools)
    official_env = _make_official_env(
        train_rows, all_tools, load_data, Env, Action, Task, fake_user
    )
    official_env.data_load_func = lambda: copy.deepcopy(base_data)
    t3_db_loader = lambda: copy.deepcopy(base_data)
    t3 = {
        "split": "train",
        "gold_task_count": 0,
        "official_reward_mismatch_count": 0,
        "official_hash_mismatch_count": 0,
        "official_reward_sum": 0.0,
        "t3_reward_sum": 0.0,
        "gold_reward_failures": [],
    }
    for index, row in enumerate(train_rows):
        predicted = [
            {"tool": action["name"], "args": action["kwargs"]}
            for action in row["actions"]
        ]
        # Train has no required output strings; one empty response is only used
        # to close the deterministic official user-simulator loop.
        official_reward, _, _ = _official_score(
            official_env, index, predicted, [""], Action, fake_user
        )
        t3_result = score_task(
            t3_db_loader,
            official_tool_map,
            row["actions"],
            predicted,
            row["outputs"],
            [""],
        )
        t3["gold_task_count"] += 1
        t3["official_reward_sum"] += official_reward
        t3["t3_reward_sum"] += t3_result["reward"]
        if t3_result["reward"] != official_reward:
            t3["official_reward_mismatch_count"] += 1
            if len(t3["gold_reward_failures"]) < 20:
                t3["gold_reward_failures"].append(
                    {
                        "task_id": row["task_id"],
                        "official_reward": official_reward,
                        "t3_reward": t3_result["reward"],
                    }
                )
        if t3_result["gold_state_hash"] != t3_result["candidate_state_hash"]:
            t3["official_hash_mismatch_count"] += 1

    t3["gate"] = (
        "PASS"
        if t3["gold_task_count"] == 500
        and t3["official_reward_mismatch_count"] == 0
        and t3["official_hash_mismatch_count"] == 0
        else "FAIL"
    )

    return {
        "schema_version": 1,
        "overall_gate": "PASS" if t1["gate"] == "PASS" and t3["gate"] == "PASS" else "FAIL",
        "scope": {
            "split": "train",
            "task_count": 500,
            "gold_action_count": 768,
            "policy_execution": False,
            "model_inference": False,
            "api_calls": False,
            "gpu_or_optimizer": False,
            "dev_test_policy_scoring": False,
            "dataset_integrity": integrity,
        },
        "t1_status_decomposition": t1,
        "t3_official_reward": t3,
    }


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evotool_treatments_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    t1 = report["t1_status_decomposition"]
    t3 = report["t3_official_reward"]
    lines = [
        "# EvoTool T1/T3 deterministic treatment audit",
        "",
        f"- Overall gate: **{report['overall_gate']}**",
        f"- Scope: **{report['scope']['split']} only**",
        "- No policy execution, model inference, API calls, GPU startup, or optimizer execution.",
        "",
        "## T1 — status decomposition",
        "",
        f"- Gate: {t1['gate']}",
        f"- Gold tasks: {t1['task_count']}",
        f"- Gold Action calls: {t1['gold_action_call_count']}",
        f"- Domain Error returns: {t1['domain_error_return_count']}",
        f"- Legacy field mismatches: {t1['legacy_field_mismatch_count']}",
        f"- DB state mismatches: {t1['database_state_mismatch_count']}",
        f"- Progress mismatches: {t1['progress_mismatch_count']}",
        f"- Episode reward mismatches: {t1['episode_reward_mismatch_count']}",
        f"- Execution status counts: {t1['execution_status_counts']}",
        f"- Business outcome counts: {t1['business_outcome_counts']}",
        f"- State effect counts: {t1['state_effect_counts']}",
        "",
        "## T3 — official reward scorer",
        "",
        f"- Gate: {t3['gate']}",
        f"- Train Gold tasks: {t3['gold_task_count']}",
        f"- Official/T3 reward mismatches: {t3['official_reward_mismatch_count']}",
        f"- Gold/candidate full-state hash mismatches: {t3['official_hash_mismatch_count']}",
        f"- Official reward sum: {t3['official_reward_sum']}",
        f"- T3 reward sum: {t3['t3_reward_sum']}",
        "",
        "## Interpretation",
        "",
        "T1 is instrumentation only: it preserves the legacy result fields, DB transitions, progress and episode reward on Train Gold trajectories. It is not an algorithmic improvement.",
        "T3 is a separate deterministic evaluator implementation. Its Train Gold replay matches the pinned official Env reward and full-state hash on this audit; this does not establish policy performance or full conversational protocol parity.",
        "Required-output normalization is unit-tested separately, including multiple response messages. The EvoTool synthesizer still supplies one final answer in its reduced adapter.",
        "",
    ]
    (output_dir / "evotool_treatments_audit.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_treatment_audit(args.dataset_dir)
    write_report(report, args.dataset_dir)
    print(
        json.dumps(
            {
                "overall_gate": report["overall_gate"],
                "t1": report["t1_status_decomposition"],
                "t3": report["t3_official_reward"],
                "scope": report["scope"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["overall_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
