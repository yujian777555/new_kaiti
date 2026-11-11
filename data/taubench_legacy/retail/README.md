# Pinned legacy tau-bench Retail dataset

This folder contains the split-preserving source lock for the historical tau-bench Retail task snapshot used by the EvoTool reproduction preflight.

- Upstream repository: https://github.com/sierra-research/tau-bench
- Pinned upstream commit: 59a200c6d575d595120f1cb70fea53cef0632f6b
- License: MIT; see vendor/tau_bench/LICENSE.
- Exact source files are vendored under vendor/tau_bench/tau_bench/envs/retail/.
- The source lock records the Git blob SHA for every vendored task, database, and tool file.
- Official split counts: Train 500, Dev 20, Test 115. The parser verifies these counts from the source AST.

## Split contract

The three original task files are kept separate. Normalized records are generated as three independent JSONL files:

- train.jsonl
- dev.jsonl
- test.jsonl

Each record preserves the original Task fields, including actions and outputs, and adds benchmark, domain, split, task_index, task_id, and source_commit metadata. The task_index is the zero-based index in that original split.

Do not shuffle, merge, or repartition these three splits. Do not deduplicate the Test pair retail-test-0093 / retail-test-0095: it is present in the pinned source and is documented in docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md.

## Build and audit

Run:

    python scripts/prepare_tau_bench_retail.py --output-dir ./build/tau_bench_retail

The command writes three normalized JSONL files, integrity_report.json, and integrity_report.md. CI uploads the generated files as an Actions artifact.

The audit verifies all 35 vendored source files, safely parses Task/Action literals with Python AST (never executes the task source), checks task/output fields, task counts, split-specific IDs, duplicate diagnostics, database/task references, tool names/signatures, Gold Action execution, and deterministic replay.

## Known source-trajectory behavior

The first full audit found 44 domain-level Error results in 1,375 Gold Action calls, across 38 tasks (Train 20, Dev 0, Test 24). These include deliberate incorrect identity/order/product identifiers, insufficient gift-card balance, and order/payment constraints. They are returned by the original tools without Python exceptions. They are preserved, not filtered or repaired.

The original tau-bench reward replays the Gold Actions and compares database state; it does not directly penalize a returned Error string. See docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md before adapting this dataset or interpreting the EvoTool progress-shaping metric.

## Scope and limitations

The upstream tau-bench README warns that this legacy task snapshot is outdated and recommends tau³-bench for new benchmark work. It is pinned here solely for historical reproduction and comparison against work that used this version. Do not present it as the latest tau-bench release.

This step is a data/source integrity audit only. It does not call an LLM, launch vLLM/A800, run an evolutionary optimizer, or measure agent performance.
