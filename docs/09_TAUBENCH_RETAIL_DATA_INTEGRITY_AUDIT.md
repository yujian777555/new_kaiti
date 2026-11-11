# Step 2 — Legacy tau-bench Retail split-preserving data audit

**Date:** 2026-11-11  
**Overall status:** PASS_WITH_CAVEAT  
**Source-integrity gate:** PASS  
**Gold-action execution gate:** PASS_WITH_DOMAIN_REJECTIONS  
**Active repository:** yujian777555/new_kaiti only.

## 1. Scope and authorization

The user explicitly authorized reading the official legacy tau-bench Train, Dev, and Test task payloads and building a split-preserving dataset with source, task, database, and Gold Action integrity checks.

Completed in this step:

- Read and vendored the exact source task files, retail DB, and original retail tool modules.
- Preserved Train, Dev, and Test as separate source files and normalized JSONL outputs.
- Verified 35 vendored source files against upstream Git blob SHA-1 values.
- Parsed Task/Action records safely with Python AST; task source was never executed.
- Checked task/user and database referential integrity.
- Replayed all 1,375 Gold Actions on independent copies of the original retail DB and checked deterministic replay.
- Generated normalized JSONL and an integrity report as a GitHub Actions artifact.

Not done:

- No LLM or model inference.
- No A800/vLLM launch.
- No paid API calls.
- No optimizer or evolutionary experiment.
- No Test performance scoring or policy comparison.
- No edits to official task actions, outputs, DB, or tool source.

## 2. Immutable source pin

- Repository: https://github.com/sierra-research/tau-bench
- Commit: \`59a200c6d575d595120f1cb70fea53cef0632f6b\`
- License: MIT
- Vendored files: 35; every Git blob SHA matches the pinned source.
- Task source files:
  - Train: \`tasks_train.py\`, blob \`4fe71adafdbae7b6683f9d5beb65275172699bb6\`
  - Dev: \`tasks_dev.py\`, blob \`aa5acf7f771b6e903bf795e436e03ee6ebe2c03d\`
  - Test: \`tasks_test.py\`, blob \`d0e4936ef9d523c04debf4ecd9f6d92eb39923a0\`
- Database files:
  - orders: \`77e34535e4cde09c21be706452947d267e74448f\`
  - products: \`dcde9b1beeea329cee6ce28d6b1e414a5284db3a\`
  - users: \`47ce9b4231a2881951a451d9bafc67c0c45f4403\`

The pinned upstream README warns that this legacy benchmark snapshot is outdated and recommends tau³-bench for new work. This exact snapshot is retained for historical reproduction only; it must not be described as the latest tau-bench release.

## 3. Split-preserving normalized dataset

| Split | Tasks | Gold Actions | Tasks with required outputs | Required output strings | Empty action lists | Normalized JSONL bytes |
|---|---:|---:|---:|---:|---:|---:|
| Train | 500 | 768 | 0 | 0 | 0 | 415,845 |
| Dev | 20 | 25 | 0 | 0 | 1 | 17,908 |
| Test | 115 | 582 | 37 | 62 | 2 | 137,248 |
| **Total** | **635** | **1,375** | **37** | **62** | **3** | **571,001** |

All 635 tasks contain the original outputs field. Empty outputs are preserved as empty lists; no outputs were reconstructed from instruction text or silently fabricated.

Stable task IDs are based on the original zero-based index within each split:

- \`retail-train-0000\` … \`retail-train-0499\`
- \`retail-dev-0000\` … \`retail-dev-0019\`
- \`retail-test-0000\` … \`retail-test-0114\`

No cross-split exact-task duplicates or identical-instruction groups were found. One exact duplicate exists within Test: \`retail-test-0093\` and \`retail-test-0095\` have the same annotator, user ID, instruction, Gold Actions, and outputs. Both are retained because the source split is immutable; do not deduplicate silently.

Normalized JSONL SHA-256 values:

| File | SHA-256 |
|---|---|
| train.jsonl | \`6c00f19764fdba236d72f0396eb5bd739c1288c47fe59c549dd58e1045389e1d\` |
| dev.jsonl | \`c626f83fd280b704209c090afb5032ff2bd3e7398f56b1f153629f5b006feaa3\` |
| test.jsonl | \`e9e3d9fb4706544997115fd84271b9a596c819a15cf3ab295cc46199ff6da904\` |

## 4. Database and task reference checks

Pinned retail database:

| Object | Count |
|---|---:|
| Orders | 1,000 |
| Users | 500 |
| Products | 50 |
| Product variants | 591 |
| Order items | 2,978 |

Results:

- Order-to-user referential failures: 0.
- Order-item-to-product failures: 0.
- Order-item-to-product-variant failures: 0.
- Task user IDs missing from the DB: 0.

## 5. Gold Action execution and domain-level rejections

All 1,375 Gold Actions were resolved to one of the 16 pinned official retail tools. There were:

- Unknown tool names: 0.
- Python signature mismatches: 0.
- Python invocation exceptions: 0.
- Deterministic replay mismatches: 0.
- Domain-level tool results beginning with \`Error:\`: 44, across 38 tasks.

Split distribution:

| Split | Domain-level rejections |
|---|---:|
| Train | 20 |
| Dev | 0 |
| Test | 24 |
| **Total** | **44** |

Error categories:

| Tool result | Count |
|---|---:|
| Insufficient gift-card balance to pay for new item | 8 |
| Insufficient gift-card balance to pay for order | 9 |
| Insufficient gift-card balance to pay for price difference | 4 |
| Non-delivered order cannot be exchanged | 1 |
| Order not found | 4 |
| Payment method must be original payment method or gift card | 2 |
| Product not found | 6 |
| User not found | 10 |
| **Total** | **44** |

These are **domain-level rejections**, not Python exceptions or broken tool signatures. Inspection of the Test source shows that several are explicit challenge trajectories: the user gives an incorrect email or ZIP first and then corrects it; omits the W prefix from an order ID; or confuses product IDs and item IDs. Insufficient funds and order-status rejections also exercise business constraints. Do not relabel all such cases as corrupted data.

The official legacy \`Env.calculate_reward\` replays the task's Gold Actions on a fresh DB and compares the resulting state hash; it does not directly fail a task merely because a tool returned an \`Error:\` string. Required output strings are checked separately when present. Thus these rejection results are part of the original benchmark's state-based reference semantics and must be preserved.

**Important EvoTool implementation note:** the released EvoTool local tau-bench adapter marks a tool result as \`status="success"\` whenever the tool function returns without raising, even when the returned text begins with \`Error:\`. Its shaped progress term counts \`status=="success"\` as successful execution. This does not alter the official state-based reward, but it can affect the additional progress shaping used during evolution. Reconcile and report this code behavior before calling the adapted run paper-faithful.

## 6. Gate decision

- Source integrity: **PASS**.
- Task parsing and split preservation: **PASS**.
- Database referential integrity: **PASS**.
- Gold Action tool/signature/invocation contract: **PASS**.
- Gold Action deterministic replay: **PASS**.
- Domain-level rejection diagnostics: **PASS_WITH_DOMAIN_REJECTIONS**.
- Overall data-preparation gate: **PASS_WITH_CAVEAT**.

No source task was changed, no task was filtered, and the Test duplicate was not removed. The audit supports using the pinned legacy Retail task snapshot with the original reward semantics, provided the caveats above are disclosed. It does not establish that EvoTool's released adapter is a faithful full tau-bench environment.

## 7. Generated artifact and reproducibility

The workflow generates:

- \`train.jsonl\`
- \`dev.jsonl\`
- \`test.jsonl\`
- \`integrity_report.json\`
- \`integrity_report.md\`

The current repository CI uploads these as an Actions artifact. The source lock is \`data/taubench_legacy/retail/source_lock.json\`; the builder is \`scripts/prepare_tau_bench_retail.py\`; regression tests are \`tests/test_tau_bench_retail_dataset.py\`.

Build command:

\`\`\`bash
python scripts/prepare_tau_bench_retail.py --output-dir ./build/tau_bench_retail
\`\`\`

## 8. Next step

Do not launch Qwen3-8B yet. First build and verify a split-preserving EvoTool adapter that:

1. Loads these three JSONL files without cross-split shuffling.
2. Reproduces the official retail tool state transitions and the original state-hash plus required-output reward.
3. Makes the treatment of returned \`Error:\` strings explicit and reports the effect on EvoTool's shaped progress term.
4. Restores or explicitly documents the missing official user-simulator, rules, and wiki interaction.
5. Uses Train for evolution, Dev for selection, and Test only once after the policy and protocol are frozen, unless the paper's exact split protocol requires a documented alternative.

Only after that adapter and protocol pass independent review should a separate model-inference authorization be requested.
