#!/usr/bin/env python3
"""Deterministic conformance audit: pinned tau-bench Retail vs pinned EvoTool adapter.

No LLM, provider, vLLM, GPU, optimizer, or network calls are made. The official
tau-bench Env is loaded from the pinned source with a deterministic fake user
transport so its real step()/calculate_reward() code can be exercised offline.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_tau_bench_retail import install_vendored_runtime

TAU_ROOT = ROOT / "vendor" / "tau_bench"
TAU_DATA = TAU_ROOT / "tau_bench" / "envs" / "retail" / "data"
EVOTOOL_ROOT = ROOT / "vendor" / "evotool"
EVOTOOL_LOCK = EVOTOOL_ROOT / "SOURCE_LOCK.json"
SPLITS = ("train", "dev", "test")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")
    path.write_bytes(payload)
    return _sha256(payload)


def _verify_evotool_snapshot() -> dict:
    lock = json.loads(EVOTOOL_LOCK.read_text(encoding="utf-8"))
    verified, failures = [], []
    for item in lock["source_files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            failures.append(f"missing EvoTool source: {item['path']}")
            continue
        actual = _git_blob_sha1(path.read_bytes())
        verified.append({"path": item["path"], "git_blob_sha": actual, "matches_lock": actual == item["git_blob_sha"]})
        if actual != item["git_blob_sha"]:
            failures.append(f"EvoTool source SHA mismatch: {item['path']}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return {
        "repository": lock["source_repository"],
        "commit": lock["source_commit"],
        "license": lock["source_license"],
        "verified_file_count": len(verified),
        "verified": verified,
    }


def _install_namespace(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module


def _load_file_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_evotool_snapshot():
    src_root = EVOTOOL_ROOT / "src"
    envs_root = src_root / "envs"
    package_name = "_new_kaiti_evotool_snapshot"
    _install_namespace(package_name, src_root)
    _install_namespace(package_name + ".envs", envs_root)

    # Force the vendored taubench_env.py to take its relative-import fallback,
    # independent of any unrelated top-level package named "src" on the runner.
    saved_src = sys.modules.get("src")
    saved_src_envs = sys.modules.get("src.envs")
    src_stub = types.ModuleType("src")
    src_stub.__path__ = []
    src_envs_stub = types.ModuleType("src.envs")
    src_envs_stub.__path__ = []
    sys.modules["src"] = src_stub
    sys.modules["src.envs"] = src_envs_stub
    try:
        tools_mod = _load_file_module(
            package_name + ".envs.taubench_tools",
            envs_root / "taubench_tools.py",
        )
        env_mod = _load_file_module(
            package_name + ".envs.taubench_env",
            envs_root / "taubench_env.py",
        )
    finally:
        if saved_src is None:
            sys.modules.pop("src", None)
        else:
            sys.modules["src"] = saved_src
        if saved_src_envs is None:
            sys.modules.pop("src.envs", None)
        else:
            sys.modules["src.envs"] = saved_src_envs

    metrics_mod = _load_file_module(
        package_name + ".metrics",
        EVOTOOL_ROOT / "src" / "metrics.py",
    )
    env_mod._DATA_DIR = str(TAU_DATA)
    return env_mod, tools_mod, metrics_mod


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self):
        return dict(self.__dict__)


class _DeterministicUser:
    """Offline transport shim; preserves Env's reset/step interface without an LLM."""

    def __init__(self):
        self.responses = ["###STOP###"]
        self.cursor = 0
        self.instruction = None

    def reset(self, instruction=None):
        self.cursor = 0
        self.instruction = instruction
        return "Deterministic test customer."

    def step(self, content):
        if self.cursor < len(self.responses):
            response = self.responses[self.cursor]
        else:
            response = "###STOP###"
        self.cursor += 1
        return response

    def get_total_cost(self):
        return 0.0


def _load_official_env(all_tools):
    """Load the exact pinned Env class with minimal type/user shims (no Pydantic/LLM)."""
    user_module = types.ModuleType("tau_bench.envs.user")

    class UserStrategy:
        HUMAN = "human"
        LLM = "llm"

    fake_user = _DeterministicUser()
    user_module.UserStrategy = UserStrategy
    user_module.load_user = lambda **kwargs: fake_user
    sys.modules["tau_bench.envs.user"] = user_module

    type_module = types.ModuleType("tau_bench.types")
    for name in (
        "Action", "Task", "EnvInfo", "EnvResetResponse", "EnvResponse",
        "RewardResult", "RewardOutputInfo", "RewardActionInfo",
    ):
        setattr(type_module, name, type(name, (_Record,), {}))
    type_module.RESPOND_ACTION_NAME = "respond"
    sys.modules["tau_bench.types"] = type_module
    sys.modules.pop("tau_bench.envs.base", None)
    base_module = importlib.import_module("tau_bench.envs.base")
    return base_module.Env, type_module.Action, type_module.Task, fake_user, base_module


def _tool_name(tool_class) -> str:
    return tool_class.get_info()["function"]["name"]


def _flat_tool_cards(all_tools) -> list[dict]:
    cards = []
    for tool_class in all_tools:
        function = tool_class.get_info()["function"]
        cards.append({
            "name": function["name"],
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {}),
        })
    return sorted(cards, key=lambda item: item["name"])


def _to_evotool_record(row: dict, cards: list[dict]) -> dict:
    return {
        "id": row["task_id"],
        "benchmark": "taubench",
        "split": row["split"],
        "task_index": row["task_index"],
        "source_commit": row["source_commit"],
        "query": row["instruction"],
        "available_tools": cards,
        "gold_plan": [
            {"tool": action["name"], "args": action["kwargs"]}
            for action in row["actions"]
        ],
        "gold_answer": None,
        "outputs": list(row["outputs"]),
        "mock_outputs": {},
        "metric": "tau-bench",
    }


def _invoke_pair(official_tool, evotool_fn, official_db, evotool_db, kwargs):
    try:
        official_out = ("return", official_tool.invoke(official_db, **kwargs))
    except Exception as exc:  # pragma: no cover - diagnostic path
        official_out = ("exception", type(exc).__name__, str(exc))
    try:
        evotool_out = ("return", evotool_fn(evotool_db, **kwargs))
    except Exception as exc:  # pragma: no cover - diagnostic path
        evotool_out = ("exception", type(exc).__name__, str(exc))
    return official_out, evotool_out


def _audit_tool_replay(rows_by_split, all_tools, evotool_env, base_data):
    official_map = {_tool_name(tool): tool for tool in all_tools}
    evotool_map = evotool_env.TOOLS
    result = {
        "total_gold_action_calls": 0,
        "unknown_official_tools": [],
        "missing_evotool_tools": [],
        "output_mismatch_count": 0,
        "output_mismatch_examples": [],
        "exception_mismatch_count": 0,
        "exception_mismatch_examples": [],
        "full_database_state_mismatch_count": 0,
        "state_mismatch_examples": [],
        "product_mutation_count": 0,
        "product_mutation_examples": [],
        "official_domain_rejection_count": 0,
        "evotool_domain_rejection_count": 0,
        "domain_rejection_examples": [],
        "calls_by_split": {},
    }

    for split, rows in rows_by_split.items():
        split_calls = 0
        for row in rows:
            official_db = copy.deepcopy(base_data)
            evotool_db = copy.deepcopy(base_data)
            original_products = copy.deepcopy(base_data["products"])
            for action_index, action in enumerate(row["actions"]):
                name, kwargs = action["name"], action["kwargs"]
                result["total_gold_action_calls"] += 1
                split_calls += 1
                official_tool = official_map.get(name)
                evotool_fn = evotool_map.get(name)
                if official_tool is None:
                    result["unknown_official_tools"].append({"task_id": row["task_id"], "action_index": action_index, "tool": name})
                    continue
                if evotool_fn is None:
                    result["missing_evotool_tools"].append({"task_id": row["task_id"], "action_index": action_index, "tool": name})
                    continue

                official_out, evotool_out = _invoke_pair(
                    official_tool, evotool_fn, official_db, evotool_db, kwargs
                )
                if official_out != evotool_out:
                    result["output_mismatch_count"] += 1
                    if len(result["output_mismatch_examples"]) < 20:
                        result["output_mismatch_examples"].append({
                            "task_id": row["task_id"], "action_index": action_index,
                            "tool": name, "official": repr(official_out)[:240],
                            "evotool": repr(evotool_out)[:240],
                        })
                if (official_out[0] == "exception") != (evotool_out[0] == "exception"):
                    result["exception_mismatch_count"] += 1
                    if len(result["exception_mismatch_examples"]) < 20:
                        result["exception_mismatch_examples"].append({
                            "task_id": row["task_id"], "action_index": action_index,
                            "tool": name, "official": repr(official_out),
                            "evotool": repr(evotool_out),
                        })
                if official_out[0] == "return" and str(official_out[1]).startswith("Error:"):
                    result["official_domain_rejection_count"] += 1
                    if len(result["domain_rejection_examples"]) < 20:
                        result["domain_rejection_examples"].append({
                            "task_id": row["task_id"], "action_index": action_index,
                            "tool": name, "kwargs": kwargs, "output": official_out[1],
                        })
                if evotool_out[0] == "return" and str(evotool_out[1]).startswith("Error:"):
                    result["evotool_domain_rejection_count"] += 1

                if official_db != evotool_db:
                    result["full_database_state_mismatch_count"] += 1
                    if len(result["state_mismatch_examples"]) < 20:
                        result["state_mismatch_examples"].append({
                            "task_id": row["task_id"], "action_index": action_index,
                            "tool": name,
                        })
                if official_db["products"] != original_products or evotool_db["products"] != original_products:
                    result["product_mutation_count"] += 1
                    if len(result["product_mutation_examples"]) < 20:
                        result["product_mutation_examples"].append({
                            "task_id": row["task_id"], "action_index": action_index,
                            "tool": name,
                        })
        result["calls_by_split"][split] = split_calls

    result["tool_name_count_official"] = len(official_map)
    result["tool_name_count_evotool"] = len(evotool_map)
    result["tool_name_sets_equal"] = set(official_map) == set(evotool_map)
    return result


def _make_official_env(rows, all_tools, load_data, Env, Action, Task, fake_user):
    tasks = []
    for row in rows:
        tasks.append(Task(
            user_id=row["user_id"],
            instruction=row["instruction"],
            actions=[Action(name=a["name"], kwargs=a["kwargs"]) for a in row["actions"]],
            outputs=row["outputs"],
        ))
    env = Env(
        data_load_func=load_data,
        tools=all_tools,
        tasks=tasks,
        wiki="pinned retail wiki",
        rules=["pinned retail rules"],
        user_strategy="human",
        user_model="offline-test-user",
        task_index=0,
    )
    # Match MockRetailDomainEnv's official terminal-tool configuration.
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _official_score(env, task_index, candidate_actions, response_contents, Action, fake_user):
    # response_contents are Agent messages; the fake user must reply with
    # continuation messages and finally ###STOP###, never echo the Agent text.
    fake_user.responses = (
        ["continue"] * (len(response_contents) - 1) + ["###STOP###"]
        if response_contents else ["###STOP###"]
    )
    reset = env.reset(task_index=task_index)
    del reset
    response = None
    done = False
    for action in candidate_actions:
        response = env.step(Action(name=action["tool"], kwargs=action["args"]))
        if response.done:
            done = True
            break
    if not done:
        for content in response_contents:
            response = env.step(Action(name="respond", kwargs={"content": content}))
            if response.done:
                done = True
                break
    if response is None or not done:
        raise RuntimeError("deterministic fake-user episode did not terminate")
    return float(response.reward), list(env.actions), done


def _audit_reward_parity(rows_by_split, all_tools, load_data, Env, Action, Task, fake_user, evotool_env, base_data):
    result = {
        "gold_task_count": 0,
        "official_gold_reward_failures": [],
        "evotool_gold_success_failures": [],
        "official_vs_evotool_gold_mismatch_count": 0,
        "official_vs_evotool_gold_mismatch_examples": [],
        "official_reward_sum": 0.0,
        "evotool_gold_success_count": 0,
        "action_history_probe": None,
    }
    for split, rows in rows_by_split.items():
        env = _make_official_env(rows, all_tools, load_data, Env, Action, Task, fake_user)
        for index, row in enumerate(rows):
            predicted = [
                {"tool": action["name"], "args": action["kwargs"]}
                for action in row["actions"]
            ]
            answer = "\n".join(row["outputs"])
            official_reward, history, _ = _official_score(
                env, index, predicted, [answer], Action, fake_user
            )
            instance = {
                "id": row["task_id"],
                "gold_plan": predicted,
                "outputs": row["outputs"],
            }
            evotool_success = bool(evotool_env.taubench_success(instance, predicted, answer))
            result["gold_task_count"] += 1
            result["official_reward_sum"] += official_reward
            result["evotool_gold_success_count"] += int(evotool_success)
            if official_reward != 1.0:
                result["official_gold_reward_failures"].append({
                    "task_id": row["task_id"], "reward": official_reward,
                    "action_count": len(predicted), "required_output_count": len(row["outputs"]),
                })
            if not evotool_success:
                result["evotool_gold_success_failures"].append({"task_id": row["task_id"]})
            if (official_reward == 1.0) != evotool_success:
                result["official_vs_evotool_gold_mismatch_count"] += 1
                if len(result["official_vs_evotool_gold_mismatch_examples"]) < 20:
                    result["official_vs_evotool_gold_mismatch_examples"].append({
                        "task_id": row["task_id"],
                        "official_reward": official_reward,
                        "evotool_success": evotool_success,
                    })
            if result["action_history_probe"] is None:
                response_count = 0 if any(a["tool"] == "transfer_to_human_agents" for a in predicted) else 1
                gold_replay_count = sum(a["name"] != "transfer_to_human_agents" for a in row["actions"])
                expected = len(predicted) + response_count + gold_replay_count
                result["action_history_probe"] = {
                    "task_id": row["task_id"],
                    "observed_history_length": len(history),
                    "expected_candidate_response_and_gold_replay_length": expected,
                    "matches_source_behavior": len(history) == expected,
                    "explanation": "Env.calculate_reward replays Gold Actions through self.step(), which appends them to the same self.actions list after the candidate response.",
                }
    return result


def _run_output_probe(rows, all_tools, load_data, Env, Action, Task, fake_user, evotool_env, outputs, responses):
    synthetic = {
        "user_id": "offline_probe_user",
        "instruction": "deterministic output semantics probe",
        "actions": [],
        "outputs": list(outputs),
    }
    env = _make_official_env([synthetic], all_tools, load_data, Env, Action, Task, fake_user)
    official_reward, _, _ = _official_score(env, 0, [], responses, Action, fake_user)
    instance = {"gold_plan": [], "outputs": list(outputs)}
    evotool_answer = responses[-1] if responses else ""
    evotool_success = bool(evotool_env.taubench_success(instance, [], evotool_answer))
    return {
        "required_outputs": outputs,
        "response_messages": responses,
        "official_reward": official_reward,
        "evotool_final_answer": evotool_answer,
        "evotool_success": evotool_success,
        "same_result": (official_reward == 1.0) == evotool_success,
    }


def _protocol_audit():
    official_agent = (TAU_ROOT / "tau_bench" / "agents" / "tool_calling_agent.py").read_text(encoding="utf-8")
    official_env = (TAU_ROOT / "tau_bench" / "envs" / "retail" / "env.py").read_text(encoding="utf-8")
    official_user = (TAU_ROOT / "tau_bench" / "envs" / "user.py").read_text(encoding="utf-8")
    evotool_agent = (EVOTOOL_ROOT / "src" / "policy" / "agent.py").read_text(encoding="utf-8")
    evotool_config = (EVOTOOL_ROOT / "configs" / "base.yaml").read_text(encoding="utf-8")
    return {
        "official_tau_bench": {
            "calls_env_reset": "env.reset(" in official_agent,
            "calls_env_step": "env.step(action)" in official_agent,
            "sends_tool_observations_back": '"role": "tool"' in official_agent,
            "sends_user_responses_back": '"role": "user", "content": env_response.observation' in official_agent,
            "uses_retail_wiki_as_system_prompt": '"content": self.wiki' in official_agent,
            "user_simulator_uses_litellm_completion": "completion(" in official_user,
            "retail_env_marks_transfer_terminal": 'self.terminate_tools = ["transfer_to_human_agents"]' in official_env,
            "agent_default_max_steps": 30,
            "rules_object_is_passed_to_tool_calling_agent": "rules" in official_agent,
        },
        "evotool": {
            "planner_selector_caller_synthesizer_pipeline": all(
                token in evotool_agent for token in (
                    "modules.run_planner", "modules.run_selector",
                    "modules.run_caller", "modules.run_synthesizer",
                )
            ),
            "calls_official_env_reset": "env.reset(" in evotool_agent,
            "calls_user_simulator_step": "user.step(" in evotool_agent,
            "injects_retail_wiki": "wiki" in evotool_agent,
            "exposes_terminal_done_flag": "done" in evotool_agent,
            "max_steps_config": 6 if "max_steps: 6" in evotool_config else None,
            "progress_status_success_fraction": 's.get("status") == "success"' in (
                EVOTOOL_ROOT / "src" / "metrics.py"
            ).read_text(encoding="utf-8"),
        },
        "interpretation": [
            "Official tau-bench ToolCallingAgent runs a multi-turn loop: reset user simulator, call one tool, feed tool output back, respond to user, and stop when the user simulator emits ###STOP### or a terminal tool is called.",
            "The official retail environment stores rules and wiki; the default ToolCallingAgent receives the wiki as its system prompt (the rules list itself is not passed by this agent constructor).",
            "EvoTool run_episode is a single-instruction modular rollout (planner -> selector/caller/tool loop -> synthesizer). It does not instantiate or step the official user simulator, does not inject the retail wiki, and has no terminal-tool done signal.",
            "Therefore, the pinned EvoTool tau-bench lane is an offline stateful task adapter, not a full conversational tau-bench interaction reproduction.",
        ],
    }


def build_conformance_report(dataset_dir: Path) -> dict:
    evotool_source = _verify_evotool_snapshot()
    all_tools, load_data = install_vendored_runtime()
    evotool_env, evotool_tools, metrics = _load_evotool_snapshot()
    base_data = load_data()
    evotool_env.load_db = lambda: copy.deepcopy(base_data)

    rows_by_split = {}
    adapted_manifest = {}
    cards = _flat_tool_cards(all_tools)
    for split in SPLITS:
        rows = _read_jsonl(dataset_dir / f"{split}.jsonl")
        if len(rows) != {"train": 500, "dev": 20, "test": 115}[split]:
            raise RuntimeError(f"{split} count mismatch: {len(rows)}")
        for index, row in enumerate(rows):
            if row["split"] != split or row["task_index"] != index or row["task_id"] != f"retail-{split}-{index:04d}":
                raise RuntimeError(f"split/index/task_id contract failed: {split}[{index}]")
        rows_by_split[split] = rows
        adapted = [_to_evotool_record(row, cards) for row in rows]
        digest = _write_jsonl(dataset_dir / f"evotool_{split}.jsonl", adapted)
        adapted_manifest[split] = {
            "task_count": len(adapted),
            "gold_action_count": sum(len(row["gold_plan"]) for row in adapted),
            "available_tool_count": len(cards),
            "jsonl_sha256": digest,
        }

    tool_replay = _audit_tool_replay(rows_by_split, all_tools, evotool_env, base_data)
    Env, Action, Task, fake_user, _ = _load_official_env(all_tools)
    reward_parity = _audit_reward_parity(
        rows_by_split, all_tools, load_data, Env, Action, Task,
        fake_user, evotool_env, base_data,
    )

    output_probes = {
        "case_insensitive": _run_output_probe(
            [], all_tools, load_data, Env, Action, Task, fake_user,
            evotool_env, ["retail-case-token"], ["RETAIL-CASE-TOKEN"],
        ),
        "comma_normalization": _run_output_probe(
            [], all_tools, load_data, Env, Action, Task, fake_user,
            evotool_env, ["1234"], ["1,234"],
        ),
        "multiple_conversation_responses": _run_output_probe(
            [], all_tools, load_data, Env, Action, Task, fake_user,
            evotool_env, ["first-token", "second-token"],
            ["first-token", "second-token"],
        ),
    }

    domain_example = tool_replay["domain_rejection_examples"][0] if tool_replay["domain_rejection_examples"] else None
    progress_probe = None
    if domain_example:
        instance = {"gold_plan": [{"tool": domain_example["tool"], "args": domain_example["kwargs"]}]}
        adapter_env = evotool_env.TauBenchEnv()
        observation = adapter_env.execute(domain_example["tool"], domain_example["kwargs"])
        steps_reported = [{"tool": domain_example["tool"], "status": observation["status"]}]
        steps_reclassified = [{"tool": domain_example["tool"], "status": "error"}]
        progress_as_returned = metrics.progress(steps_reported, instance)
        progress_if_domain_error = metrics.progress(steps_reclassified, instance)
        progress_probe = {
            "tool": domain_example["tool"],
            "output": observation["output"],
            "adapter_status": observation["status"],
            "progress_when_returned_normally": progress_as_returned,
            "progress_if_domain_rejection_counted_as_error": progress_if_domain_error,
            "evolution_reward_component_delta_at_weight_0_3": round(
                0.3 * (progress_as_returned - progress_if_domain_error), 10
            ),
            "interpretation": "The adapter's status means the Python tool function returned without raising. A business-level Error string is still counted in the progress metric's status==success fraction; it is not a semantic success of the requested business operation.",
        }

    protocol = _protocol_audit()
    product_probe_a = copy.deepcopy(base_data)
    product_probe_b = copy.deepcopy(base_data)
    first_product = next(iter(product_probe_b["products"]))
    product_probe_b["products"][first_product]["name"] = product_probe_b["products"][first_product]["name"] + " [probe]"
    projection_ignores_product_only_change = (
        evotool_env._mutable_state(product_probe_a) == evotool_env._mutable_state(product_probe_b)
    )

    tool_gate = (
        tool_replay["tool_name_sets_equal"]
        and not tool_replay["unknown_official_tools"]
        and not tool_replay["missing_evotool_tools"]
        and tool_replay["output_mismatch_count"] == 0
        and tool_replay["exception_mismatch_count"] == 0
        and tool_replay["full_database_state_mismatch_count"] == 0
        and tool_replay["product_mutation_count"] == 0
    )
    reward_gate = (
        reward_parity["official_vs_evotool_gold_mismatch_count"] == 0
        and not reward_parity["official_gold_reward_failures"]
        and not reward_parity["evotool_gold_success_failures"]
    )

    return {
        "schema_version": 1,
        "overall_gate": "PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS" if tool_gate and reward_gate else "REVIEW_REQUIRED",
        "model_inference_performed": False,
        "llm_api_calls": 0,
        "optimizer_runs": 0,
        "sources": {
            "tau_bench_repository": "https://github.com/sierra-research/tau-bench",
            "tau_bench_commit": "59a200c6d575d595120f1cb70fea53cef0632f6b",
            "tau_bench_source_files_verified_by_dataset_gate": 42,
            "evotool": evotool_source,
        },
        "adapted_split_artifacts": adapted_manifest,
        "tool_implementation_parity": {
            "gate": "PASS" if tool_gate else "FAIL",
            **tool_replay,
        },
        "reward_parity": {
            "gate": "PASS" if reward_gate else "FAIL",
            **reward_parity,
        },
        "output_semantics_probes": output_probes,
        "domain_error_progress_probe": progress_probe,
        "mutable_state_projection_probe": {
            "actual_products_mutated_by_any_gold_action": tool_replay["product_mutation_count"],
            "hypothetical_product_only_change_ignored_by_evotool_projection": projection_ignores_product_only_change,
            "interpretation": "The official Env hashes the full DB; EvoTool compares orders/users only. The projection is equivalent for the pinned Retail tool set only because the full 1,375-action replay observed no products mutations.",
        },
        "interaction_protocol": protocol,
        "known_deviations": [
            "Required-output matching differs: official tau-bench lowercases both strings and removes commas from response content; EvoTool uses case-sensitive exact substring matching.",
            "Official tau-bench checks required outputs across all respond actions in the conversation; EvoTool checks one synthesized final answer string.",
            "EvoTool progress counts every tool function that returns normally as status=success, including domain-level Error strings. This is call-return success, not business-operation success.",
            "Official tau-bench's default ToolCallingAgent runs a user-simulator conversation and stops on ###STOP### or transfer_to_human_agents; EvoTool uses a single-instruction modular rollout and does not implement that conversation/termination loop.",
            "Official Env hashes the complete DB; EvoTool compares only orders/users. This is equivalent for the pinned current tool set because products are read-only in all audited calls, but it is not a general equivalence if future tools mutate products.",
            "Official tool-calling default allows up to 30 steps; EvoTool's base config uses max_steps=6.",
            "The official Retail Env stores a rules list, but the default ToolCallingAgent constructor receives wiki and tool schemas, not the separate rules list.",
        ],
    }


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evotool_tau_bench_conformance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tool = report["tool_implementation_parity"]
    reward = report["reward_parity"]
    lines = [
        "# EvoTool × legacy tau-bench Retail conformance report",
        "",
        f"- Overall gate: **{report['overall_gate']}**",
        f"- Model inference: {report['model_inference_performed']}",
        f"- LLM API calls: {report['llm_api_calls']}",
        f"- Optimizer runs: {report['optimizer_runs']}",
        "",
        "## Tool implementation parity",
        "",
        f"- Calls compared: {tool['total_gold_action_calls']}",
        f"- Official/EvoTool tool sets equal: {tool['tool_name_sets_equal']}",
        f"- Return-value mismatches: {tool['output_mismatch_count']}",
        f"- Exception mismatches: {tool['exception_mismatch_count']}",
        f"- Full DB state mismatches after actions: {tool['full_database_state_mismatch_count']}",
        f"- Product mutations: {tool['product_mutation_count']}",
        f"- Domain-level Error returns: official={tool['official_domain_rejection_count']}, EvoTool={tool['evotool_domain_rejection_count']}",
        "",
        "## Gold reward replay",
        "",
        f"- Tasks compared: {reward['gold_task_count']}",
        f"- Official gold reward failures: {len(reward['official_gold_reward_failures'])}",
        f"- EvoTool gold success failures: {len(reward['evotool_gold_success_failures'])}",
        f"- Official/EvoTool gold-result mismatches: {reward['official_vs_evotool_gold_mismatch_count']}",
        "",
        "## Known semantic deviations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["known_deviations"])
    lines += ["", "## Output semantics probes", ""]
    for name, probe in report["output_semantics_probes"].items():
        lines.append(
            f"- {name}: official_reward={probe['official_reward']}, "
            f"evotool_success={probe['evotool_success']}, same={probe['same_result']}"
        )
    lines += [
        "",
        "## Interaction protocol",
        "",
        "- Official tau-bench: conversational user-simulator/tool loop.",
        "- EvoTool: single-instruction modular planner/selector/caller/synthesizer rollout.",
        "- Therefore this is an offline stateful adapter comparison, not full conversational tau-bench parity.",
        "",
        "## Interpretation",
        "",
        "Passing tool-level and exact-Gold reward checks does not make the two interaction protocols equivalent. Keep the original EvoTool adapter unchanged as the baseline snapshot; any corrected or full-conversation adapter must be a separately named treatment with its own protocol and budget.",
        "",
    ]
    (output_dir / "evotool_tau_bench_conformance.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_conformance_report(args.dataset_dir)
    write_report(report, args.dataset_dir)
    print(json.dumps({
        "overall_gate": report["overall_gate"],
        "tool_gate": report["tool_implementation_parity"]["gate"],
        "reward_gate": report["reward_parity"]["gate"],
        "tool_calls": report["tool_implementation_parity"]["total_gold_action_calls"],
        "output_mismatches": report["tool_implementation_parity"]["output_mismatch_count"],
        "state_mismatches": report["tool_implementation_parity"]["full_database_state_mismatch_count"],
        "gold_reward_mismatches": report["reward_parity"]["official_vs_evotool_gold_mismatch_count"],
        "output_semantics_probes": report["output_semantics_probes"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall_gate"] != "REVIEW_REQUIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
