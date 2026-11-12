# Step 4 — independent review of the conformance harness and status-treatment design

**Date:** 2026-11-12  
**Repository:** `yujian777555/new_kaiti` only  
**Review status:** `ACCEPT_WITH_SCOPE_LIMITS`  
**Model inference / API / optimizer:** none / 0 / 0

## 1. Review conclusion

The Step 3 harness is suitable for deterministic, offline verification of the pinned Retail tool implementations, the official `Env` state/reward plumbing, and the specific EvoTool adapter semantics it exercises.

It is **not** a test of a task-conditioned customer simulator, a complete conversational Agent rollout, or the entire EvoTool evolutionary implementation. Its fake user is a scripted termination transport. The current parity gate must therefore remain:

`PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS`

The review does not authorize model inference, A800/vLLM startup, paid API calls, optimizer execution, training, or policy-performance evaluation.

## 2. Pinned source paths and identities

| Component | Pinned path | Git blob SHA |
|---|---|---|
| Official Env and reward | `vendor/tau_bench/tau_bench/envs/base.py` | `2461c3ebaf696757e0ce405bdb20376de88b0143` |
| Official Retail Env | `vendor/tau_bench/tau_bench/envs/retail/env.py` | `fc4874c7ab7b6b23cc35a35388b45d0f1f9c2907` |
| Official ToolCallingAgent | `vendor/tau_bench/tau_bench/agents/tool_calling_agent.py` | `f8cfdbac52d24d2323e923cdb25e6b667d4db9f8` |
| Official user simulator | `vendor/tau_bench/tau_bench/envs/user.py` | `eb9ee841eee4c098353cb0447e4a4bf560d8b5f6` |
| Official types | `vendor/tau_bench/tau_bench/types.py` | `66f3b60e7b0cdf573f66b16573057cf3211c241b` |
| EvoTool policy episode | `vendor/evotool/src/policy/agent.py` | `421ac00fc3d7004466f73ed939297a0b27c10837` |
| EvoTool Retail adapter | `vendor/evotool/src/envs/taubench_env.py` | `0c0fd731714084dfa4fef2584070d286320a229f` |
| EvoTool Retail tools | `vendor/evotool/src/envs/taubench_tools.py` | `5788e31a585343507741f6ba44961003d824ae80` |
| EvoTool progress metric | `vendor/evotool/src/metrics.py` | `e28bc8fd73107be43f4c83453e677d630f00fa40` |
| EvoTool success evaluator | `vendor/evotool/src/evaluators.py` | `5fd2f092b251e05d6cd66267051aa07deae5cad3` |

Additional upstream EvoTool files were inspected at the same pinned revision `6a82719ea6e22cf23f963078e2527094e50b47f6`, but are not vendored in the current repository lock:

| Component | Upstream path | Git blob SHA |
|---|---|---|
| Blamer trajectory rendering | `src/evolve/blame.py` | `788a60987380e5394044c817e4e3d81aefa1d081` |
| Status-based diagnostics | `src/evolve/diagnostics.py` | `c1abdbde9235807371abbc814984d497e45f24b5` |
| Trajectory-guided mutation | `src/evolve/mutate.py` | `d3b2c9f04c139ddce69975de2ab36d9c55527741` |
| Prompt module rendering | `src/policy/modules.py` | `0d7de352449f878644f67a754031077da074ae56` |
| Evolution loop | `src/evolve/loop.py` | `036a3d3f9c1ad14ad08b72ebd51dd27ef61c5515` |
| Population selection | `src/evolve/select.py` | `f514568a286f90192cb463ac16012dee47f2c74f` |
| Configuration | `src/config.py` | `a70ba9cd4415a3e04a834c49dcd6c29630b76b4a` |

The tau-bench source lock covers 42 official source files. The EvoTool lock covers the nine vendored adapter/config files; it does **not** vendor the complete optimizer implementation. The upstream pinned revision also contains `src/policy/modules.py` (`0d7de352449f878644f67a754031077da074ae56`), `src/evolve/loop.py` (`036a3d3f9c1ad14ad08b72ebd51dd27ef61c5515`), `src/evolve/select.py` (`f514568a286f90192cb463ac16012dee47f2c74f`), and `src/config.py` (`a70ba9cd4415a3e04a834c49dcd6c29630b76b4a`), but these are not part of the current vendored lock. A runnable, full-source reproduction still requires a separately pinned complete source checkout or an expanded source lock.

## 3. What the fake user actually does

The harness replaces `tau_bench.envs.user.load_user` with `_DeterministicUser` when importing the real pinned `Env` class.

- `reset(instruction)` stores the instruction and returns the fixed string `Deterministic test customer.`
- `step(agent_content)` records the Agent content but does not interpret it, echo it, or generate a task-conditioned reply. It returns the next scripted response, normally `continue` followed by `###STOP###`.
- `get_total_cost()` always returns zero.
- `_official_score` discards the initial reset observation, manually replays the supplied candidate Gold Actions, and manually sends the supplied Agent response text through `Action(name="respond")`.

This is a **scripted transport/termination shim**, not a simulated customer. It does not execute `LLMUserSimulationEnv.build_system_prompt`, does not call LiteLLM, and does not test whether a user simulator reveals information incrementally or decides correctly when a task is complete.

What it does test is narrower and useful: the pinned `Env.reset`, `Env.step`, `Env.calculate_reward`, response-action handling, stop-token termination, terminal-tool termination, and required-output checks can run deterministically without a provider.

The official `LLMUserSimulationEnv` is different: its reset builds an instruction-conditioned system prompt and calls `completion`; each step appends the Agent's message and calls `completion` again. No such call was made in this audit.

## 4. Verified official and EvoTool execution semantics

### Official tau-bench

1. `MockRetailDomainEnv` selects the original split and passes the pinned Retail tools, DB loader, wiki, and rules to `Env`.
2. `Env.reset` reloads a fresh DB, clears the action history, selects the task, and calls `user.reset(instruction)`.
3. `Env.step` dispatches tool actions to the official tool class. A `respond` action calls `user.step(content)`; the episode terminates if the returned observation contains `###STOP###`. Retail also marks `transfer_to_human_agents` as terminal.
4. `ToolCallingAgent.solve` uses the wiki as its system prompt, feeds tool observations back as tool messages and user-simulator observations back as user messages, and defaults to at most 30 Agent steps.
5. `Env.calculate_reward` hashes the full DB after the candidate actions, reloads the DB, replays the Gold Actions, and compares full-state hashes. If required outputs exist, it checks them across all recorded `respond` actions using case-insensitive matching after comma removal from response content.

The Retail Env stores a separate rules list, but the default `ToolCallingAgent` constructor receives the wiki and tool schemas, not that rules list.

### EvoTool

1. `run_episode` executes Planner → Selector → Caller → tool executor → Synthesizer.
2. The adapter is a stateful, single-instruction Retail DB executor; it does not call the official `Env.reset`, `Env.step`, user simulator, or Wiki prompt.
3. The Selector's state summary and Synthesizer's `_render_step` render tool output text, not the status field.
4. The status field **does** enter the Blamer's `_trajectory_text` as `[status]`, and enters the Mutator's trajectory packet when `use_trajectory=true`. `diagnostics.extract_diagnostics` also branches on status (currently it treats `status="error"` as a Caller event). Therefore, changing the raw status affects credit assignment and mutation evidence as well as progress scoring.
5. `metrics.progress` computes `0.5 × tool-sequence F1 + 0.5 × status-success fraction`; `run_episode` combines binary task success and progress as `0.7 × success + 0.3 × progress`. The optional `route_episode` helper also counts only `status="error"` in its tie-break. A full outcome-aware treatment must define its behavior in diagnostics and this optional helper rather than merely changing the progress metric.

## 5. Review findings and limits

| Finding | Assessment | Consequence |
|---|---|---|
| Scripted fake user does not simulate a customer | Intentional harness boundary, now made explicit and directly tested | Do not claim user-simulator parity |
| Gold reward replay uses actual `Env.step` and `calculate_reward` | Verified for deterministic Gold Action replays | Supports official reward-plumbing parity, not a live Agent rollout |
| 1,375 tool comparisons call the official and EvoTool tool functions directly | Verified but limited to the exact Gold Action arguments | Do not describe this as exhaustive arbitrary-input/tool-dispatch testing |
| Protocol audit uses source-text probes and a hard-coded official 30-step default | Useful source audit, not a dynamic execution proof | Keep source SHAs and manual code-path review alongside its flags |
| EvoTool full optimizer source is not vendored | Reproduction blocker before an optimizer run | Pin/checkout the complete upstream revision before execution |
| Official output normalization, multi-response handling, max steps, and full DB projection differ | Known protocol deviations | Keep these separate from the status-only comparison |

The existing 1,375-call parity result is exact-trace coverage: it demonstrates agreement on the pinned Gold Action inputs, not all possible argument values, malformed calls, or unknown tool names. The current exception-mismatch count must likewise be interpreted within those tested calls.

## 6. Separate status/outcome treatments

The official tau-bench environment does not expose EvoTool's `status` field. It returns observation text and computes task reward from state and required outputs. A returned `Error:` string is therefore not an official status category. The treatment should preserve two orthogonal facts:

- **Execution status:** whether the Python tool function returned normally (`success`) or raised/was unknown (`error`).
- **Operation outcome:** whether a normal return represents an accepted operation or a tool/business rejection.

Do not overwrite execution status with a mixed business-outcome label. Add an orthogonal `operation_outcome` field in the treatment implementation.

### Arm L — `EVOTOOL_LEGACY`

- Preserve the pinned EvoTool adapter and all source behavior unchanged.
- A tool function that returns normally receives `status="success"`, even if its returned text begins with `Error:`.
- Python exceptions and unknown tools retain the original `status="error"`.
- Preserve the original `progress` and `0.7/0.3` reward formula.

### Arm R1 — `EVOTOOL_OUTCOME_AWARE_SELECTION`

- Derive `operation_outcome="rejected"` for a normal return whose output begins exactly with `Error:`; use `accepted` for other normal returns and `unknown` for execution exceptions/unknown tools.
- Keep the raw `Step.observation.status` unchanged. Blamer, Mutator, and diagnostics therefore see the legacy execution-status evidence.
- Compute an outcome-aware progress/selection score using `operation_outcome`, while preserving a separate legacy `diagnostic_reward` for the Blamer and Mutator. The evolution loop uses the outcome-aware selection reward for representative-episode choice, parent/child acceptance, and population selection; the diagnostic prompts continue to receive the legacy reward.
- This requires explicit separate reward channels; simply changing `Episode.reward` is not sufficient because the current Blamer and Mutator also consume it.
- This arm isolates the effect of outcome-aware fitness/selection from changes in blame and mutation evidence.

### Arm R2 — `EVOTOOL_FULL_OUTCOME_AWARE`

- Add the same orthogonal `operation_outcome` field, but expose it to the Blamer and Mutator trajectory text and to structured diagnostics.
- Add a distinct diagnostic event for a returned business/tool rejection; do not mislabel it as a Python exception. The Blamer can decide whether the rejection indicates a Caller, Planner, or expected intermediate action.
- Use outcome-aware progress and reward consistently for search, blame, and mutation.
- Update optional `route_episode` tie-breaking to distinguish execution exceptions from returned operation rejections.
- This arm tests whether explicit outcome evidence improves credit assignment and targeted mutation beyond the reward-only effect.

The current deterministic replay added to the harness is a **progress-only sensitivity calculation** for R1. It computes `metrics.progress` twice on the same Gold Action traces, placing `returned_error` only in a temporary copy of the metric input. It does not modify the adapter observation, run Blamer/Mutator, or simulate either full optimizer treatment.

### Why the distinction matters

The source audit found 44 normal-return `Error:` observations across 38 official Gold tasks (Train 20, Dev 0, Test 24). All 635 exact Gold Action trajectories passed the official reward replay. Some returned errors are deliberate intermediate observations, such as an incorrect identity/order/product identifier that the task trajectory later corrects; others expose genuine business constraints.

Therefore, neither R1 nor R2 is the official metric correction. They are hypotheses about how evolutionary search should interpret returned operation rejections. Arm R2 can also change blame attribution and mutation targets, so it must not be interpreted as a pure fitness ablation.

For an episode with `n` tool calls and `k` returned-error calls, if the tool sequence is otherwise identical, the R1 progress-only weighted shaping difference is:

`0.3 × 0.5 × (k/n) = 0.15 × (k/n)`.

## 7. Fair comparison and contamination controls

- Keep the original vendored EvoTool files and source lock unchanged.
- Run L and R as separate named treatments. The cleanest implementation is a separate process per arm; alternatively, include the treatment ID in every episode-cache key.
- This is important because upstream `_EPISODE_CACHE` is global and its key is only policy hash plus instance ID. Running both arms in one process without cache isolation can reuse an episode scored under the other arm.
- Use the same model revision, temperature, prompts, seeds, generation budget, batch size, task manifests, and action-step cap. For R1, isolate reward channels so Blamer/Mutator inputs remain legacy; for R2, deliberately expose operation outcomes to those modules.
- For the status-only ablation, keep EvoTool's current output evaluator unchanged. Correcting case/comma/multiple-response output semantics or restoring the official conversation loop must be a separate treatment; otherwise the status effect is confounded.
- Keep Train for evolution, Dev for selection, and Test held out for one final evaluation after policy and protocol freeze. The present authorization does not permit any of those model/optimizer runs.

## 8. Next gates

1. Complete CI acceptance for the fake-user contract tests and progress-only sensitivity replay.
2. Preserve Legacy as the primary historical baseline; implement R1 and R2 only as separately named, independently cached treatments.
3. Pin the complete upstream EvoTool source needed for the optimizer and audit its config/split-loading path before any execution.
4. Reconcile `G=8, B=3` with the full 500/20/115 official splits and document the exact sampling budget. Do not use the mixed 150-instance demo builder.
5. Prepare a separate inference/optimizer authorization request with exact model revision, split use, seeds, budget, metrics, stop rules, and rollback. Until that approval exists, run deterministic source/unit tests only.
