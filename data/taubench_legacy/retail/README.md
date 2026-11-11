# Pinned legacy tau-bench Retail dataset

This folder contains the split-preserving source lock for the historical tau-bench Retail task snapshot used by the EvoTool reproduction preflight.

- Upstream repository: https://github.com/sierra-research/tau-bench
- Pinned upstream commit: 59a200c6d575d595120f1cb70fea53cef0632f6b
- License: MIT; see vendor/tau_bench/LICENSE.
- Exact source files are vendored under vendor/tau_bench/tau_bench/envs/retail/.
- The source lock records the Git blob SHA for every vendored task, database, and tool file.
- Expected source split counts: Train 500, Dev 20, Test 115. The parser verifies these counts from the source AST rather than trusting filenames or documentation.

## Split contract

The three original task files are kept separate. Normalized records are generated as three independent JSONL files:

- train.jsonl
- dev.jsonl
- test.jsonl

Each record preserves the original Task fields, including actions and outputs, and adds:

- benchmark: tau-bench-legacy
- domain: retail
- split: the original split name
- task_index: zero-based position in that original split
- task_id: retail-{split}-{task_index:04d}
- source_commit: the pinned upstream commit

Do not shuffle, merge, or repartition these three splits. The task ID's index is local to the official split list, not a global index.

## Build and audit

Run:

    python scripts/prepare_tau_bench_retail.py --output-dir ./build/tau_bench_retail

The command writes three normalized JSONL files, integrity_report.json, and integrity_report.md. CI uploads the generated files as an Actions artifact.

The audit checks:

1. Exact Git blob SHA-1 for all vendored source files.
2. Safe AST parsing of Task/Action literals; task source is never executed.
3. Required task fields and preservation of the original outputs list.
4. Task counts, split-specific stable IDs, and cross-split duplicate diagnostics.
5. Orders/users/products referential integrity and task-user references.
6. Gold action tool names, Python function signatures, execution errors, domain-level error results, and deterministic replay.

The gold-action replay uses the unchanged upstream tool modules and the pinned retail DB. Package initializers that import optional conversational-agent dependencies are bypassed by namespace shims; this audit does not instantiate the upstream LLM user simulator or run an agent.

## Scope and limitations

The upstream tau-bench README warns that this legacy task snapshot is outdated and recommends tau³-bench for new benchmark work. It is pinned here solely to support historical reproduction and comparison against work that used this version. Do not present it as the latest tau-bench release.

This step is a data/source integrity audit only. It does not call an LLM, launch vLLM/A800, run an evolutionary optimizer, or measure agent performance.
