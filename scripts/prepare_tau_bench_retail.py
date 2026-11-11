#!/usr/bin/env python3
"""Build and audit split-preserving data from the pinned legacy tau-bench retail source.

This script parses upstream Python Task/Action literals with ast. It never executes
the task source. It replays each gold action sequence twice on independent copies
of the pinned retail DB using the unchanged upstream tool implementations.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib
import inspect
import json
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "vendor" / "tau_bench"
LOCK_PATH = ROOT / "data" / "taubench_legacy" / "retail" / "source_lock.json"
SOURCE_COMMIT = "59a200c6d575d595120f1cb70fea53cef0632f6b"
SPLITS = ("train", "dev", "test")


class AuditError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_literal(node: ast.AST) -> Any:
    """Decode only the static expression subset used by upstream Task/Action data."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [decode_literal(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return [decode_literal(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise AuditError("dictionary unpacking is not allowed in task literals")
            result[decode_literal(key_node)] = decode_literal(value_node)
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = decode_literal(node.operand)
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in {"Task", "Action"}:
            raise AuditError(f"unexpected constructor in task source: {ast.dump(node.func)}")
        if node.args:
            raise AuditError(f"positional arguments are not allowed for {node.func.id}")
        values = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                raise AuditError("keyword unpacking is not allowed in task source")
            if keyword.arg in values:
                raise AuditError(f"duplicate keyword {keyword.arg}")
            values[keyword.arg] = decode_literal(keyword.value)
        return values
    raise AuditError(f"non-literal expression in task source: {type(node).__name__}")


def parse_split(split: str, source_path: Path) -> list[dict[str, Any]]:
    variable = f"TASKS_{split.upper()}"
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(source_path))
    assignments = []
    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            if node.module != "tau_bench.types":
                raise AuditError(f"unexpected import in {source_path}: {node.module}")
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
                assignments.append(node.value)
        else:
            raise AuditError(f"unexpected top-level statement in {source_path}: {type(node).__name__}")
    if len(assignments) != 1 or not isinstance(assignments[0], ast.List):
        raise AuditError(f"expected one literal list assignment for {variable}")
    tasks = []
    for index, node in enumerate(assignments[0].elts):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "Task":
            raise AuditError(f"{variable}[{index}] is not a Task(...) literal")
        task = decode_literal(node)
        required = {"user_id", "instruction", "actions", "outputs"}
        missing = required - set(task)
        if missing:
            raise AuditError(f"{variable}[{index}] missing fields: {sorted(missing)}")
        if not isinstance(task["user_id"], str) or not task["user_id"]:
            raise AuditError(f"{variable}[{index}] has invalid user_id")
        if not isinstance(task["instruction"], str) or not task["instruction"].strip():
            raise AuditError(f"{variable}[{index}] has invalid instruction")
        if not isinstance(task["actions"], list):
            raise AuditError(f"{variable}[{index}] actions is not a list")
        if not isinstance(task["outputs"], list) or not all(isinstance(x, str) for x in task["outputs"]):
            raise AuditError(f"{variable}[{index}] outputs is not a list of strings")
        for action_index, action in enumerate(task["actions"]):
            if not isinstance(action, dict) or set(action) != {"name", "kwargs"}:
                raise AuditError(f"{variable}[{index}].actions[{action_index}] has invalid shape")
            if not isinstance(action["name"], str) or not isinstance(action["kwargs"], dict):
                raise AuditError(f"{variable}[{index}].actions[{action_index}] has invalid name/kwargs")
        tasks.append(task)
    return tasks


def install_vendored_runtime():
    """Bypass upstream package initializers that import optional LLM/user dependencies.

    Tool modules and the data loader themselves are imported unchanged from the
    pinned source. This validator does not instantiate the upstream conversational Env.
    """
    package_paths = {
        "tau_bench": VENDOR_ROOT / "tau_bench",
        "tau_bench.envs": VENDOR_ROOT / "tau_bench" / "envs",
        "tau_bench.envs.retail": VENDOR_ROOT / "tau_bench" / "envs" / "retail",
    }
    for name, path in package_paths.items():
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        module.__package__ = name
        sys.modules[name] = module
    tools_module = importlib.import_module("tau_bench.envs.retail.tools")
    data_module = importlib.import_module("tau_bench.envs.retail.data")
    return tools_module.ALL_TOOLS, data_module.load_data


def verify_source_files(lock: dict) -> tuple[list[dict], list[str]]:
    verified = []
    failures = []
    for item in lock["source_files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            failures.append(f"missing source file: {item['path']}")
            continue
        data = path.read_bytes()
        actual = git_blob_sha1(data)
        if actual != item["git_blob_sha"]:
            failures.append(f"Git blob SHA mismatch: {item['path']} expected={item['git_blob_sha']} actual={actual}")
        verified.append({
            "path": item["path"],
            "git_blob_sha": actual,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "matches_lock": actual == item["git_blob_sha"],
        })
    return verified, failures


def validate_database(base_data: dict) -> dict:
    orders = base_data["orders"]
    products = base_data["products"]
    users = base_data["users"]
    failures = []
    item_count = 0
    variant_count = sum(len(p.get("variants", {})) for p in products.values())
    for order_id, order in orders.items():
        if order.get("user_id") not in users:
            failures.append(f"order references missing user: {order_id}")
        for item in order.get("items", []):
            item_count += 1
            product_id = item.get("product_id")
            if product_id not in products:
                failures.append(f"order item references missing product: {order_id}")
                continue
            if item.get("item_id") not in products[product_id].get("variants", {}):
                failures.append(f"order item references missing product variant: {order_id}")
    return {
        "orders": len(orders),
        "users": len(users),
        "products": len(products),
        "product_variants": variant_count,
        "order_items": item_count,
        "referential_integrity_failures": failures[:20],
        "referential_integrity_failure_count": len(failures),
    }


def action_signature_issues(tool_class, kwargs: dict) -> tuple[list[str], list[str]]:
    signature = inspect.signature(tool_class.invoke)
    params = signature.parameters
    expected = {
        name for name, param in params.items()
        if name != "data" and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    required = {
        name for name, param in params.items()
        if name != "data" and param.default is inspect.Parameter.empty
        and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    actual = set(kwargs)
    return sorted(required - actual), sorted(actual - expected)


def audit_gold_actions(all_tasks: dict[str, list[dict]], base_data: dict, all_tools: list[type]) -> dict:
    tool_map = {tool.get_info()["function"]["name"]: tool for tool in all_tools}
    if len(tool_map) != len(all_tools):
        raise AuditError("duplicate tool names in upstream ALL_TOOLS")
    action_counts = Counter()
    unknown_tools = []
    signature_errors = []
    invocation_errors = []
    domain_errors = []
    replay_mismatches = []
    total_actions = 0
    tasks_replayed = 0

    for split in SPLITS:
        for index, task in enumerate(all_tasks[split]):
            task_id = f"retail-{split}-{index:04d}"
            left_db = copy.deepcopy(base_data)
            right_db = copy.deepcopy(base_data)
            left_outputs = []
            right_outputs = []
            for action_index, action in enumerate(task["actions"]):
                total_actions += 1
                name = action["name"]
                kwargs = action["kwargs"]
                action_counts[name] += 1
                tool_class = tool_map.get(name)
                if tool_class is None:
                    unknown_tools.append({"task_id": task_id, "action_index": action_index, "tool": name})
                    continue
                missing, extra = action_signature_issues(tool_class, kwargs)
                if missing or extra:
                    signature_errors.append({
                        "task_id": task_id,
                        "action_index": action_index,
                        "tool": name,
                        "missing_kwargs": missing,
                        "extra_kwargs": extra,
                    })
                    continue
                try:
                    left_output = tool_class.invoke(left_db, **kwargs)
                    right_output = tool_class.invoke(right_db, **kwargs)
                    left_outputs.append(left_output)
                    right_outputs.append(right_output)
                    if isinstance(left_output, str) and left_output.startswith("Error:"):
                        domain_errors.append({
                            "task_id": task_id,
                            "action_index": action_index,
                            "tool": name,
                            "error": left_output.splitlines()[0][:160],
                        })
                except Exception as exc:
                    invocation_errors.append({
                        "task_id": task_id,
                        "action_index": action_index,
                        "tool": name,
                        "exception": type(exc).__name__,
                        "message": str(exc)[:160],
                    })
            if canonical_json(left_db) != canonical_json(right_db) or canonical_json(left_outputs) != canonical_json(right_outputs):
                replay_mismatches.append({"task_id": task_id})
            tasks_replayed += 1

    domain_errors_by_tool = Counter(item["tool"] for item in domain_errors)
    domain_errors_by_split = Counter(item["task_id"].split("-")[1] for item in domain_errors)
    domain_errors_by_message = Counter(item["error"] for item in domain_errors)
    return {
        "tool_names": sorted(tool_map),
        "total_gold_actions": total_actions,
        "gold_tasks_replayed": tasks_replayed,
        "action_counts_by_tool": dict(sorted(action_counts.items())),
        "unknown_tools": unknown_tools[:20],
        "unknown_tool_count": len(unknown_tools),
        "signature_errors": signature_errors[:20],
        "signature_error_count": len(signature_errors),
        "invocation_errors": invocation_errors[:20],
        "invocation_error_count": len(invocation_errors),
        "domain_errors": domain_errors,
        "domain_error_count": len(domain_errors),
        "domain_error_task_count": len({item["task_id"] for item in domain_errors}),
        "domain_error_counts_by_tool": dict(sorted(domain_errors_by_tool.items())),
        "domain_error_counts_by_split": dict(sorted(domain_errors_by_split.items())),
        "domain_error_counts_by_message": dict(sorted(domain_errors_by_message.items())),
        "deterministic_replay_mismatches": replay_mismatches[:20],
        "deterministic_replay_mismatch_count": len(replay_mismatches),
    }


def build_dataset(output_dir: Path) -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["source_commit"] != SOURCE_COMMIT:
        raise AuditError("source lock commit does not match script pin")

    source_hashes, failures = verify_source_files(lock)
    all_tasks = {}
    split_stats = {}
    exact_fingerprints = defaultdict(set)
    instruction_splits = defaultdict(set)
    duplicate_within_split = {}

    for split in SPLITS:
        source_path = ROOT / lock["split_sources"][split]
        tasks = parse_split(split, source_path)
        all_tasks[split] = tasks
        expected = lock["expected_task_counts"][split]
        if len(tasks) != expected:
            failures.append(f"{split} task count mismatch: expected={expected} actual={len(tasks)}")

        rows = []
        output_string_count = 0
        nonempty_outputs = 0
        action_total = 0
        fingerprints = []
        for index, task in enumerate(tasks):
            fingerprint_payload = {
                key: task[key] for key in ("user_id", "instruction", "actions", "outputs")
            }
            fingerprint = sha256_bytes(canonical_json(fingerprint_payload).encode("utf-8"))
            fingerprints.append(fingerprint)
            exact_fingerprints[fingerprint].add(split)
            instruction_hash = sha256_bytes(task["instruction"].encode("utf-8"))
            instruction_splits[instruction_hash].add(split)
            output_string_count += len(task["outputs"])
            nonempty_outputs += bool(task["outputs"])
            action_total += len(task["actions"])
            row = {
                "benchmark": "tau-bench-legacy",
                "domain": "retail",
                "split": split,
                "task_index": index,
                "task_id": f"retail-{split}-{index:04d}",
                "source_commit": SOURCE_COMMIT,
                **task,
            }
            rows.append(row)

        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / f"{split}.jsonl"
        jsonl_bytes = ("".join(canonical_json(row) + "\n" for row in rows)).encode("utf-8")
        jsonl_path.write_bytes(jsonl_bytes)
        split_stats[split] = {
            "task_count": len(tasks),
            "tasks_with_nonempty_required_outputs": nonempty_outputs,
            "required_output_string_count": output_string_count,
            "tasks_with_empty_action_list": sum(not t["actions"] for t in tasks),
            "gold_action_count": action_total,
            "within_split_exact_duplicate_task_count": len(fingerprints) - len(set(fingerprints)),
            "normalized_jsonl_sha256": sha256_bytes(jsonl_bytes),
            "normalized_jsonl_bytes": len(jsonl_bytes),
            "source_file": lock["split_sources"][split],
        }
        duplicate_within_split[split] = split_stats[split]["within_split_exact_duplicate_task_count"]

    base_data = importlib.import_module("tau_bench.envs.retail.data").load_data()
    db_stats = validate_database(base_data)
    if db_stats["referential_integrity_failure_count"]:
        failures.append(f"database referential integrity failures: {db_stats['referential_integrity_failure_count']}")

    users = base_data["users"]
    missing_task_users = []
    for split in SPLITS:
        for index, task in enumerate(all_tasks[split]):
            if task["user_id"] not in users:
                missing_task_users.append(f"retail-{split}-{index:04d}")
    if missing_task_users:
        failures.append(f"tasks reference missing users: {len(missing_task_users)}")

    all_tools = importlib.import_module("tau_bench.envs.retail.tools").ALL_TOOLS
    gold_action_audit = audit_gold_actions(all_tasks, base_data, all_tools)
    for key in (
        "unknown_tool_count",
        "signature_error_count",
        "invocation_error_count",
        "deterministic_replay_mismatch_count",
    ):
        if gold_action_audit[key]:
            failures.append(f"gold action audit {key}: {gold_action_audit[key]}")

    warnings = []
    if gold_action_audit["domain_error_count"]:
        warnings.append(
            f"{gold_action_audit['domain_error_count']} gold-action calls returned domain-level Error results; "
            "preserve these source trajectories and interpret them under the official state-based reward"
        )

    source_integrity_gate = "PASS" if not failures else "FAIL"
    gold_action_gate = "PASS" if not warnings else "PASS_WITH_DOMAIN_REJECTIONS"
    overall_gate = (
        "PASS" if source_integrity_gate == "PASS" and gold_action_gate == "PASS"
        else "PASS_WITH_CAVEAT" if source_integrity_gate == "PASS"
        else "FAIL"
    )

    exact_duplicate_groups = sum(1 for splits in exact_fingerprints.values() if len(splits) > 1)
    instruction_duplicate_groups = sum(1 for splits in instruction_splits.values() if len(splits) > 1)

    report = {
        "schema_version": 1,
        "gate": overall_gate,
        "source_integrity_gate": source_integrity_gate,
        "gold_action_gate": gold_action_gate,
        "source": {
            "repository": lock["source_repository"],
            "commit": SOURCE_COMMIT,
            "license": lock["source_license"],
            "warning": lock["source_warning"],
            "verified_file_count": len(source_hashes),
            "source_files": source_hashes,
        },
        "splits": split_stats,
        "total_tasks": sum(x["task_count"] for x in split_stats.values()),
        "cross_split_exact_duplicate_fingerprint_groups": exact_duplicate_groups,
        "cross_split_instruction_duplicate_groups": instruction_duplicate_groups,
        "within_split_exact_duplicate_task_counts": duplicate_within_split,
        "database": db_stats,
        "task_user_reference_failures": missing_task_users[:20],
        "task_user_reference_failure_count": len(missing_task_users),
        "gold_action_audit": gold_action_audit,
        "warnings": warnings,
        "failures": failures,
    }

    (output_dir / "integrity_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Legacy tau-bench Retail split integrity report",
        "",
        f"- Overall gate: **{report['gate']}**",
        f"- Source integrity gate: **{report['source_integrity_gate']}**",
        f"- Gold-action gate: **{report['gold_action_gate']}**",
        f"- Source: {SOURCE_COMMIT}",
        f"- Total tasks: **{report['total_tasks']}**",
        f"- Vendored source files verified: **{len(source_hashes)}**",
        "",
        "| Split | Tasks | Tasks with outputs | Output strings | Gold actions | JSONL SHA-256 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for split in SPLITS:
        s = split_stats[split]
        lines.append(
            f"| {split} | {s['task_count']} | {s['tasks_with_nonempty_required_outputs']} | "
            f"{s['required_output_string_count']} | {s['gold_action_count']} | {s['normalized_jsonl_sha256']} |"
        )
    lines += [
        "",
        "## Database",
        "",
        f"- Orders: {db_stats['orders']}",
        f"- Users: {db_stats['users']}",
        f"- Products: {db_stats['products']}",
        f"- Product variants: {db_stats['product_variants']}",
        f"- Order items: {db_stats['order_items']}",
        f"- Referential-integrity failures: {db_stats['referential_integrity_failure_count']}",
        "",
        "## Gold-action audit",
        "",
        f"- Actions replayed: {gold_action_audit['total_gold_actions']}",
        f"- Unknown tools: {gold_action_audit['unknown_tool_count']}",
        f"- Signature errors: {gold_action_audit['signature_error_count']}",
        f"- Invocation exceptions: {gold_action_audit['invocation_error_count']}",
        f"- Domain-level Error results: {gold_action_audit['domain_error_count']}",
        f"- Tasks with domain-level errors: {gold_action_audit['domain_error_task_count']}",
        f"- Domain errors by split: {gold_action_audit['domain_error_counts_by_split']}",
        f"- Domain errors by tool: {gold_action_audit['domain_error_counts_by_tool']}",
        f"- Domain errors by message: {gold_action_audit['domain_error_counts_by_message']}",
        f"- Deterministic replay mismatches: {gold_action_audit['deterministic_replay_mismatch_count']}",
        "",
        "## Gold-action error examples",
        "",
    ]
    lines.extend(
        f"- {item['task_id']} action[{item['action_index']}] {item['tool']}: {item['error']}"
        for item in gold_action_audit["domain_errors"]
    )
    lines += [
        "",
        "## Split overlap diagnostics",
        "",
        f"- Exact task fingerprint groups appearing in multiple splits: {exact_duplicate_groups}",
        f"- Identical instruction groups appearing in multiple splits: {instruction_duplicate_groups}",
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- None"])
    lines += ["", "## Structural failures", ""]
    lines.extend([f"- {item}" for item in failures] if failures else ["- None"])
    lines += [
        "",
        "This audit validates source integrity, task parsing, split preservation, task-to-database references, "
        "tool signatures, gold-action execution, and deterministic replay. It does not run an LLM, evaluate an "
        "agent policy, or establish model performance.",
        "",
    ]
    (output_dir / "integrity_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    install_vendored_runtime()
    report = build_dataset(args.output_dir)
    summary = {
        "gate": report["gate"],
        "source_integrity_gate": report["source_integrity_gate"],
        "gold_action_gate": report["gold_action_gate"],
        "warnings": report["warnings"],
        "total_tasks": report["total_tasks"],
        "splits": {k: v["task_count"] for k, v in report["splits"].items()},
        "gold_actions": report["gold_action_audit"]["total_gold_actions"],
        "gold_action_errors": {
            "unknown_tools": report["gold_action_audit"]["unknown_tool_count"],
            "signature": report["gold_action_audit"]["signature_error_count"],
            "exceptions": report["gold_action_audit"]["invocation_error_count"],
            "domain_errors": report["gold_action_audit"]["domain_error_count"],
            "domain_errors_by_split": report["gold_action_audit"]["domain_error_counts_by_split"],
            "domain_errors_by_tool": report["gold_action_audit"]["domain_error_counts_by_tool"],
            "domain_errors_by_message": report["gold_action_audit"]["domain_error_counts_by_message"],
            "replay_mismatches": report["gold_action_audit"]["deterministic_replay_mismatch_count"],
        },
        "failures": report["failures"],
        "output_dir": str(args.output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if report["gate"] in {"PASS", "PASS_WITH_CAVEAT"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
