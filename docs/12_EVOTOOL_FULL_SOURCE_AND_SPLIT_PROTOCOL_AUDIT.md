# Step 5 — full-source and official-split protocol audit

**Date:** 2026-11-12  
**Upstream EvoTool revision:** `SYang2000/ACL_2026_EvoTool@6a82719ea6e22cf23f963078e2527094e50b47f6`  
**Status:** `PRE-RUN BLOCKED`  
**LLM/API/optimizer execution:** none

## 1. Published paper protocol

The ACL 2026 paper, Appendix A.6, states:
- Backbone: Qwen3-8B (also GPT-4.1 for the other backbone).
- Maximum generation budget: `G=8` iterations.
- Mini-batch size: `B=3`.
- Same benchmark-provided tool environments and per-instance interaction budget across baselines.
- Final prompt selected on `S_sel`, then evaluated on the benchmark's official split.

Reference: https://aclanthology.org/2026.acl-long.2016/ (Appendix A.6; Algorithm 1).

## 2. Released-code defaults do not equal the paper's G=8 protocol

Pinned upstream source identities:

| File | Git blob SHA | Relevant behavior |
|---|---|---|
| `run.py` | `372155e786ab935d01d54304722c85655646d6f6` | Calls `load_instances`, then random `split_instances`; passes Test into `evolve` |
| `src/benchmarks.py` | `e7b4bc6b167c932c3fc4bec1e729083d962a47e6` | Loads one `samples.json`; shuffles and slices by `n_train/n_sel/n_test` |
| `src/evolve/loop.py` | `036a3d3f9c1ad14ad08b72ebd51dd27ef61c5515` | Data-derived epoch batches; explicit `generations` override |
| `src/config.py` | `a70ba9cd4415a3e04a834c49dcd6c29630b76b4a` | `generations=0`, `epochs=3`, `batch_size=3`, `log_test_eval=True` defaults |
| `configs/base.yaml` | `2df96e7ea15486fb3a6539817e1c909c1e9e3c54` | Demo defaults: 90/30/30, 3 epochs, max_steps=6 |
| `src/runlog.py` | `8a9f09f2ef3cfd3e90570c4c6a5e726916da68d2` | Stores periodic Test learning-curve points when enabled |
| `src/envs/taubench_env.py` | `0c0fd731714084dfa4fef2584070d286320a229f` | Reads local `taubench_data/{users,orders,products}.json` |

The upstream README explicitly describes its bundled demo subsets as 150 instances per benchmark, with 90/30/30 partitions and three epochs. It also states that the shipped reference evolved policies are Qwen3-4B demo artifacts, not the paper's Qwen3-8B full-benchmark evaluation.

The paper's `G=8` is an explicit total-generation budget in the released loop, not the base config default. The base config's `epochs=3` and `generations=0` derive the number of generations from the size of `S_train`.

## 3. Exact G=8, B=3 interpretation on official Retail Train=500

The pinned `_epoch_batches` function:
1. copies all of `train`,
2. shuffles it once per epoch without replacement,
3. yields mini-batches of size 3.

The loop calculates:

`gens_per_epoch = ceil(500 / 3) = 167`

With explicit `evolve.generations=8`:

`epochs = ceil(8 / 167) = 1`

The loop stops after eight mini-batches. Therefore, each seed uses **24 distinct Train tasks** from the 500-task pool for its eight generation batches. The other 476 Train tasks remain available in the pool but are not consumed by that seed's eight-generation run. This is the code-level interpretation of the paper's G/B budget; it is not a full pass over all 500 tasks.

Important guard: `evolve()` returns immediately when `ev.epochs <= 0`, before it considers the explicit `generations` override. A paper-budget config must therefore set `epochs=1` (or another positive value), `generations=8`, and `batch_size=3`.

The 20 Dev tasks are `S_sel` and are used for population selection and final policy selection. The 115 Test tasks are the official held-out evaluation split.

## 4. Why upstream run.py cannot be used directly

### 4.1 It destroys the official split boundary

The official legacy Retail data are already separated into Train 500 / Dev 20 / Test 115, and this repository's data builder emits separate `train.jsonl`, `dev.jsonl`, and `test.jsonl` files with split-local stable IDs.

Upstream `load_instances()` expects one `samples.json` array. `split_instances()` then shuffles that combined array and slices it according to `n_train`, `n_sel`, and `n_test`. Merging the three official splits and calling this function would mix the original split membership. Setting the counts to 500/20/115 does **not** preserve the upstream split.

The normalized JSONL row shape also differs from EvoTool's unified instance shape. The split-aware adapter must explicitly map:
- `id` ← stable `task_id`
- `query` ← official `instruction`
- `gold_plan` ← each `actions[]` item mapped from `name/kwargs` to `tool/args`
- `outputs` ← official required output strings
- `available_tools` ← tool name/description/parameter schemas from the pinned official Retail tool list
- `benchmark` ← `taubench`

No combined 150-instance demo builder or random split is allowed for Paper 1 claims.

### 4.2 It can read Test during evolution

Upstream `run.py` passes `test` into `evolve()`. `EvolveConfig.log_test_eval` defaults to `True`; when a run log is present, the loop computes a periodic Test score at an epoch boundary. With `G=8`, the global-budget boundary itself triggers that probe. Upstream `run.py` then performs another Test evaluation after choosing `best_policy` on Dev.

Even if the periodic score is logging-only and does not enter selection, it is still an extra Test read before the final policy is frozen. The Paper 1 protocol must not use it.

The safe runner must:
- set `log_test_eval=False`;
- pass `test=None` to `evolve()`;
- not load the Test JSONL before the policy has been frozen on Dev;
- load and score Test once only after a separate explicit evaluation authorization.

### 4.3 The adapter's default DB path is absent

The vendored `TauBenchEnv.load_db()` reads `src/envs/taubench_data/{users,orders,products}.json`. Those files are not present in the current nine-file EvoTool adapter snapshot. The CI conformance harness patches `evotool_env.load_db` to return a deep copy of the pinned official tau-bench DB. Thus the CI proves tool/reward adapter behavior under that patch; it does not prove the adapter's default local DB path is runnable.

A future runner should inject the pinned official `tau_bench.envs.retail.data.load_data` as the adapter's DB loader, or create a separately locked data materialization. Do not silently use an unpinned or mixed DB.

## 5. Remaining environment protocol difference

- Official tau-bench's default `ToolCallingAgent.solve` permits up to 30 Agent steps and runs the user-simulator conversation.
- Released EvoTool uses a single-instruction Planner/Selector/Caller/Synthesizer rollout and `max_steps=6` tool-call steps by default.
- The EvoTool adapter does not run the official user simulator or Wiki interaction.

These are not equivalent interaction budgets. For a faithful released-EvoTool baseline, preserve and label its six-tool-step offline adaptation. If the experiment instead adopts the full official conversation loop or a 30-step budget, declare that as a separate protocol treatment and apply the same environment/interaction budget to all methods. Do not silently combine the two.

## 6. Required split-preserving runner contract

Before any model execution, implement and test a runner that:

1. Reads Train, Dev, and Test JSONL independently; never merges them or calls upstream `split_instances()`.
2. Maps each row to the pinned EvoTool unified instance schema and verifies all split counts, stable IDs, required outputs, tool schemas, and no cross-split overlap.
3. Uses `train=500`, `sel=20`, and a deferred Test loader for `test=115`.
4. Sets `evolve.generations=8`, `evolve.batch_size=3`, and positive `evolve.epochs`; records the eight exact batch IDs per seed (24 unique Train tasks).
5. Sets `evolve.log_test_eval=False` and calls `evolve(..., test=None)`.
6. Selects the final `Theta*` using Dev only. Test is not loaded until after that policy and the protocol are frozen and explicit evaluation authorization is granted.
7. Injects the pinned official DB loader into EvoTool's adapter, with a compatibility test proving identical starting DB hashes.
8. Records model revision, endpoint, seed, generation/batch IDs, max_steps, output evaluator, status treatment, token budget, cache namespace, and rollback information.

## 7. Current authorization

The current authorization remains deterministic source, unit, and conformance work only. No Qwen3 inference, vLLM/A800 startup, paid API calls, evolutionary optimizer run, training, or Test policy scoring has been performed or is authorized by this audit.

## 8. Next milestone

Build the split-preserving loader and safe runner preflight, pin the complete EvoTool source required by the runner, and add tests for:
- exact 500/20/115 split preservation;
- 8 batches × 3 distinct Train IDs per seed;
- Dev-only population and final-policy selection;
- no Test read during evolution or policy selection;
- no periodic Test evaluation;
- official DB loader injection and initial-state hash parity.

After these deterministic gates pass, prepare a separate experiment authorization request. Do not launch the model or optimizer before approval.
