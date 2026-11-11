# Step 4 — EvoTool status and reward treatment protocol

**Date:** 2026-11-11  
**Status:** DESIGN ONLY — no adapter, reward, model, or optimizer implementation in this document.

## 1. Why a single "corrected status" is not justified

The pinned legacy adapter uses \`status="success"\` when a tool function returns without raising. A returned string beginning with \`Error:\` is therefore still recorded as a normal function return.

That field is an execution/transport signal, not a semantic claim that the requested business operation succeeded. The Step 3-R1 dispatch probe demonstrates this on a real Train Gold Action:

- Tool: \`modify_pending_order_payment\`.
- Result: \`Error: insufficient gift card balance to pay for the order\`.
- Official and EvoTool observations match exactly.
- Both environments leave the DB unchanged.
- EvoTool reports \`status="success"\` because the function returned normally.
- This action is part of the frozen Gold trajectory; exact Gold reward replay still passes.

Across the pinned dataset, 44 Gold Action calls return domain-level \`Error:\` strings (Train 20, Dev 0, Test 24). Automatically changing all of them to failed execution would conflate at least three distinct cases: a valid negative lookup, a business-rule rejection, and an actual tool invocation exception. It could penalize legitimate Gold trajectories.

## 2. Treatment definitions

| ID | Treatment | Change from legacy | Status |
|---|---|---|---|
| T0 | EvoTool Legacy | None. Preserve the pinned upstream adapter, status semantics, progress metric and reward. | Required reference |
| T1 | Status-Decomposed Diagnostic | Add separate diagnostic fields for execution status, business outcome and state effect. Keep legacy status and reward unchanged. | Proposed; deterministic instrumentation only |
| T2 | Business-Outcome-Aware Shaping | Change the progress/reward formula using task-aware business outcome labels. | Not ready; labels and validity study required |
| T3 | Official-Reward-Aligned Scorer | Separate evaluator treatment using full DB state and official required-output normalization. Do not modify the legacy policy or its source snapshot. | Proposed evaluator treatment |
| T4 | Full Conversational tau-bench | Restore the official user-simulator/tool/wiki interaction loop. This is a separate environment/protocol, not a small status correction. | Separate protocol; not yet implemented |

### T0 — EvoTool Legacy

- Pin the exact released EvoTool source snapshot and adapter lock.
- Preserve the current \`status\`, progress calculation, reward weights and planner/selector/caller/synthesizer pipeline.
- Label it as a reduced/offline stateful Retail adapter, not a faithful full conversational tau-bench reproduction.
- Do not patch the vendored legacy source to make it agree with a new treatment.

### T1 — Status-Decomposed Diagnostic

Add fields alongside the legacy field; do not replace it:

- \`execution_status\`: \`returned\`, \`raised_exception\`, or \`unknown_tool\`.
- \`business_outcome\`: \`accepted\`, \`rejected\`, \`no_match\`, \`not_applicable\`, or \`unknown\`.
- \`state_effect\`: \`changed\`, \`unchanged\`, or \`unknown\`.
- \`tool_observation\`: preserve the raw tool output without normalization or deletion.

The business-outcome mapping must be tool-aware. For example, \`Error: user not found\` is a \`no_match\` observation; \`Error: insufficient gift card balance\` is a business-rule \`rejected\` outcome. Neither means that the Python invocation failed. A no-match result may be useful evidence for the Agent's next decision.

**T1 must preserve the T0 reward exactly.** It is a diagnostic decomposition, not an algorithmic improvement and not a new success metric. The purpose is to make future analysis possible without corrupting the legacy baseline.

### T2 — Business-Outcome-Aware Shaping

Do not implement this yet. A simple rule such as \`Error:\` → negative progress is rejected.

Before T2 can be considered, it needs:

1. A task-aware annotation schema separating expected negative observations from failed business operations.
2. A documented mapping for every Retail tool and error family.
3. Inter-annotator or deterministic rule validation for ambiguous outcomes.
4. An ablation that isolates the business-outcome term from tool-sequence progress.
5. A demonstration that valid Gold negative lookups/rejections are not penalized.
6. Train-only development and a locked held-out evaluation protocol; no Test tuning.

Without these conditions, T2 would inject an arbitrary reward preference rather than correct the legacy implementation.

### T3 — Official-Reward-Aligned Scorer

This changes the evaluator, not the Agent's tool-execution status:

- Compare the full DB state, not only orders/users.
- Match required outputs using the pinned official normalization rules (case-insensitive comparison and comma removal from response content).
- Keep the one-final-answer limitation explicit. The EvoTool synthesizer does not produce the official sequence of conversational response messages.
- Maintain the same scorer across all algorithm arms in a future comparison.
- Keep T0's scorer untouched and report T0/T3 results separately.

T3 is a scorer-parity treatment; it is not evidence that EvoTool's interaction protocol is fully reproduced.

### T4 — Full Conversational Protocol

Restoring the official user simulator, wiki and multi-turn tool loop is a separate environment integration. It must be budgeted and tested as its own protocol. Do not combine T4 with T1 or T3 and then attribute any performance difference to status handling.

## 3. Recommended experimental separation

For any future deterministic or model-based comparison, keep the axes separate:

- **Policy/source axis:** T0 legacy versus any new evolutionary controller.
- **Instrumentation axis:** T0 fields versus T1 diagnostic fields.
- **Evaluator axis:** legacy EvoTool scorer versus T3 official-aligned scorer.
- **Interaction axis:** reduced/offline adapter versus T4 full conversation.

Do not create a single arm that simultaneously changes status, progress reward, output matching, DB hashing and interaction protocol. Such a comparison would not identify which change caused an observed difference.

## 4. Current decision

1. Keep T0 immutable.
2. T1 is the only status-related change currently justified; it must not alter reward.
3. T2 is blocked pending task-aware outcome labels and validation.
4. T3 may be implemented as a separate deterministic scorer module with its own tests.
5. T4 remains a separate environment/protocol decision.
6. None of these definitions authorizes model inference, API calls, A800/vLLM startup, optimizer execution, training or policy-performance evaluation.

## 5. Next implementation gate

If implementation is approved, do it in separate modules and tests:

- T1: unit tests for normal returns, business rejection, no-match, raised exceptions and unknown tools; assert the legacy reward is bit-for-bit unchanged.
- T3: deterministic scorer tests for full-state mutations, case variation, comma normalization and required-output handling; retain explicit tests for the one-answer versus multi-response limitation.
- Preserve the pinned dataset, Gold Actions, DB, and upstream source snapshots.
- Update the evidence ledger and handoff with exact source/result SHAs and CI artifacts.

**No algorithmic uplift is claimed. No model or optimizer experiment has been run.**
