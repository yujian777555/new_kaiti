# D-080 real-tool recovery experiment design

Status: DESIGN CANDIDATE — NOT IMPLEMENTED, NOT APPROVED FOR EXECUTION
Repository: yujian777555/new_kaiti (Paper 1 only)

## 1. Why D-080 is needed

D-079 is now a regression/sanity suite, not a useful algorithm-performance benchmark. The corrected hand FSM achieved 100% R1/R2 recovery, 100% R3 correct escalation, 100% R4 damage containment, zero avoidable harm, and zero hard-safety violations on the reused diagnostic set. Its mean decision count of 2.833 matches the natural per-stratum action lower bound (D1=3, D2=2, D3=2, D4=5, D5=2, D6=3).

R2.3's strongest evolutionary arm, matched NSGA-III, reached macro class success 0.581. FSPAE-R3-Block reached 0.4167, with R4 containment 0.3333 versus matched NSGA-III 1.0. R3-Block passed its mechanism audit but did not beat the matched baseline. It improved over FSPAE-R2, not over the strongest baseline. Stop adding D-079 FSPAE ablations.

## 2. Proposed environment

Use the pinned legacy tau-bench Retail tasks already built by the repository's split-preserving dataset pipeline. Run actual task-state transitions and tool schemas, not only the synthetic three-step saga.

The LLM agent remains responsible for task interpretation, planning, and ordinary tool selection. The evolutionary controller is a separate recovery layer invoked when a tool call returns an ambiguous or recoverable failure. Evolution optimizes the recovery controller; it must not receive gold actions or future task state.

A deterministic fault-injection wrapper at the tool boundary should support only semantically valid cases for the selected tool:
- timeout before execution;
- timeout after a committed effect;
- rate limit / retry-after;
- schema mismatch;
- permission denial;
- partial commit and compensation failure where the tool contract permits them.

Fault schedules must be seeded, logged, and bound to task/tool identifiers. The wrapper must preserve actual tool side effects and distinguish pre-commit from post-commit outcomes. Gold actions remain evaluation-only.

## 3. Evolutionary optimization target

Evolve a compact recovery policy over public observations, tool contracts, and execution history. Candidate policy parameters may include retry/verify thresholds, wait duration, compensation/rollback choice, escalation conditions, and context-dependent action rules.

Objectives:
1. maximize official task reward / task completion;
2. minimize avoidable harm and irreversible duplicate effects;
3. minimize recovery effort (extra tool calls, retries, wait units, and escalation cost);
4. preserve worst-family performance.

Hard constraints (zero tolerance):
- duplicate irreversible side effects;
- invalid database transitions or invariant violations;
- retry of an ambiguous non-idempotent action before verification;
- unauthorized tool actions;
- test/validation data access during evolution.

## 4. Required baselines

- unmodified reference agent;
- fixed hand-written recovery controller;
- matched NSGA-III with the same policy representation and evaluation budget;
- SBCG-NSGA-III;
- FSPAE-R3-Block as a candidate ablation only (not assumed superior).

Every arm must share task instances, fault schedules, initial policy pool, seeds, and evaluation budget. Compare paired task/fault outcomes, not only pooled means.

## 5. Staged gates

### Gate A — adapter and fault semantics
- Official tau-bench/EvoTool adapter conformance passes.
- Every injected failure has a state-transition test for before/after commit semantics.
- Duplicate, compensation, rollback, idempotency, and permission semantics are independently checked.
- Deterministic smoke passes without LLM calls.

### Gate B — hand-policy saturation check
Run the fixed recovery controller on the new Train-only task/fault set before any evolutionary experiment. If it achieves perfect task success, zero avoidable harm, zero hard violations, and the minimum recovery effort, redesign the challenge instead of spending evolutionary budget.

### Gate C — offline evolutionary pilot
Use Train tasks only. Start with 3 seeds and a fixed budget. Report task-family and fault-stratum results, per-seed stability, recovery effort, token/API cost, and mechanism audits. Do not use Validation/Test to tune.

### Gate D — one-shot independent validation
Only after an algorithm and all hyperparameters are frozen, create and lock a fresh validation task/fault manifest. Evaluate once. Keep Test inaccessible until the final protocol is preregistered.

## 6. LLM execution and compute

The current repository's real-tool smoke uses deterministic stubs; it is not a real LLM-agent result. A real LLM executor must be explicitly configured and its model/version, endpoint, decoding parameters, prompt hash, tool-call logs, token usage, and cost recorded. Do not invent or assume a reachable endpoint.

A controlled first run may use the already deployed Qwen2.5-7B-Instruct on the user's A800 cluster, or the approved API provider. Do not begin fine-tuning until the fault-injection and evolutionary-controller gates pass. A800 training is a later experiment, not a substitute for proving the recovery algorithm.

## 7. Advancement rule

D-080 is only a design candidate. Implement the smallest deterministic fault-injection slice first, validate it against actual Retail tool semantics, and run the hand-policy saturation check. Only then authorize evolutionary runs. No paper drafting is part of this stage.
