#!/usr/bin/env python3
"""Deterministic real-tool smoke through the pinned EvoTool run_episode seam."""
from __future__ import annotations
import argparse, copy, importlib, json, sys, types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
EVOTOOL_ROOT = ROOT / "vendor" / "evotool"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def _install_agent_import_stubs(actions):
    src_pkg = types.ModuleType("src")
    src_pkg.__path__ = [str(EVOTOOL_ROOT / "src")]
    sys.modules["src"] = src_pkg
    llm_pkg = types.ModuleType("src.llm")
    llm_pkg.__path__ = []
    sys.modules["src.llm"] = llm_pkg
    llm_client = types.ModuleType("src.llm.client")
    llm_client.LLMClient = type("LLMClient", (), {})
    sys.modules["src.llm.client"] = llm_client
    executor_mod = types.ModuleType("src.env.executor")
    def unused_executor(_instance):
        raise AssertionError("non-TauBench executor must not be called")
    executor_mod.executor_for = unused_executor
    sys.modules["src.env.executor"] = executor_mod
    module_stubs = types.ModuleType("src.policy.modules")
    module_stubs.Policy = type("Policy", (), {})
    subgoals = [f"gold_action_{i}" for i in range(len(actions))]
    action_by_subgoal = dict(zip(subgoals, actions))
    module_stubs.run_planner = lambda _c, _p, _q: list(subgoals)
    module_stubs.run_selector = lambda _c, _p, _q, sub, _s, _t: action_by_subgoal[sub]["name"]
    module_stubs.run_caller = lambda _c, _p, _card, _q, sub, _s: dict(action_by_subgoal[sub]["kwargs"])
    module_stubs.run_synthesizer = lambda _c, _p, _q, steps: "\n".join(str(x.observation.get("output", "")) for x in steps)
    sys.modules["src.policy.modules"] = module_stubs
    importlib.import_module("src.policy").modules = module_stubs

def _choose_train_row(rows, tool_map, base_db, max_steps=6):
    for row in rows:
        actions = row.get("actions") or []
        if not actions or len(actions) > max_steps: continue
        names = [item.get("name") for item in actions]
        if any(name not in tool_map for name in names): continue
        if "transfer_to_human_agents" in names[:-1]: continue
        trial = copy.deepcopy(base_db)
        valid = True
        try:
            for action in actions:
                output = tool_map[action["name"]](trial, **(action.get("kwargs") or {}))
                if isinstance(output, str) and output.startswith("Error:"):
                    valid = False
                    break
        except Exception:
            valid = False
        if valid and trial != base_db: return row
    raise RuntimeError("no valid state-changing Train Gold task with <=6 actions")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    from scripts.audit_evotool_tau_bench_conformance import _flat_tool_cards, _read_jsonl, _to_evotool_record
    from scripts.prepare_tau_bench_retail import install_vendored_runtime
    from treatments.evotool_episode_integration import run_treated_episode
    rows = _read_jsonl(args.dataset_dir / "train.jsonl")
    if len(rows) != 500 or any(x.get("split") != "train" for x in rows):
        raise RuntimeError("smoke is restricted to the pinned 500-row Train split")
    official_tools, load_data = install_vendored_runtime()
    base_db = load_data()
    tool_map = {t.get_info()["function"]["name"]: t.invoke for t in official_tools}
    row = _choose_train_row(rows, tool_map, base_db)
    actions = list(row["actions"])
    instance = _to_evotool_record(row, _flat_tool_cards(official_tools))
    _install_agent_import_stubs(actions)
    agent = importlib.import_module("src.policy.agent")
    env = importlib.import_module("src.envs.taubench_env")
    env.load_db = lambda: copy.deepcopy(base_db)
    policy = SimpleNamespace(planner="stub", selector="stub", caller="stub", synthesizer="stub")
    agent._EPISODE_CACHE.clear()
    result = run_treated_episode(
        agent, object(), policy, instance, len(actions),
        known_tools=env.TOOLS.keys(),
        db_loader=lambda: copy.deepcopy(base_db), tool_map=tool_map)
    if len(result["episode"].steps) != len(actions): raise AssertionError("episode action count mismatch")
    if not result["t0_legacy_success"] or result["t3"]["reward"] != 1.0:
        raise AssertionError("exact Gold action episode failed T0/T3")
    if not result["comparison"]["t0_and_t3_success_match"]: raise AssertionError("T0/T3 disagreement")
    if any(x["execution_status"] != "returned" for x in result["t1"]["steps"]):
        raise AssertionError("T1 execution status missing")
    if not any(x["state_effect"] == "changed" for x in result["t1"]["steps"]):
        raise AssertionError("no state change observed by T1")
    if agent._EPISODE_CACHE: raise AssertionError("episode cache leak")
    report = {
        "status": "PASS", "scope": "train_only_deterministic_real_tool_episode_smoke",
        "task_id": instance["id"], "source_commit": row.get("source_commit"),
        "action_count": len(actions), "tools": [x["name"] for x in actions],
        "required_output_count": len(instance.get("outputs") or []),
        "t0_legacy_success": result["t0_legacy_success"],
        "t0_legacy_reward": result["t0_legacy_reward"], "t1": result["t1"],
        "t3_reward": result["t3"]["reward"], "t3_actions_match": result["t3"]["actions_match"],
        "t3_outputs_match": result["t3"]["outputs_match"], "cache_empty_after_run": not bool(agent._EPISODE_CACHE),
        "protocol": "Pinned run_episode/TauBenchEnv/tools/evaluator; planner/selector/caller/synthesizer are deterministic stubs; no LLM or official conversational user-simulator/wiki loop."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
