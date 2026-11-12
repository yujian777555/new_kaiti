# D-080 Stage A — deterministic Retail tool-boundary fault injection

Status: IMPLEMENTED CANDIDATE; CI validation pending. No LLM, optimizer, paid API, A800, Dev, or Test execution.

## Scope

This is the smallest deterministic semantics slice, not a benchmark result. It wraps unchanged pinned legacy Retail tool callables and injects failures at the tool boundary. Fault events are bound to (task_id, tool_name, call_index, seed), hashed into stable event IDs, and logged with before/after database-state hashes.

Implemented modes:
- `timeout_before_execution`: tool is not invoked; DB must remain unchanged.
- `rate_limit_before_execution`: tool is not invoked; DB must remain unchanged.
- `schema_rejection_before_execution`: tool is not invoked; DB must remain unchanged.
- `timeout_after_commit`: the real tool is invoked; only a successful state-changing call can be followed by an injected timeout. The state change remains committed.

## Real-tool semantic probe

Uses the pinned `cancel_pending_order` and `modify_pending_order_address` implementations with pending orders from the pinned Retail DB:
1. Pre-execution timeout leaves the order and payment history unchanged; a subsequent call may execute.
2. Post-commit timeout leaves the order cancelled and refund history committed.
3. A blind retry is rejected by the real tool because the order is no longer pending; payment history must not receive a second refund.
4. A second real write tool, `modify_pending_order_address`, is tested as an idempotent state assignment: a post-commit timeout followed by the same call leaves the final address and full DB hash unchanged.
5. Rate-limit/schema rejection occur before invocation and leave the DB unchanged.

The wrapper does not simulate partial commits inside a tool, fabricate compensation semantics, sleep, or alter vendor source. It does not decide recovery actions; it supplies deterministic observations for a separate recovery policy.

## Gates

- Gate A1: tests prove no mutation on pre-execution faults.
- Gate A2: tests prove post-commit timeout occurs only after a real state change.
- Gate A3: blind retry does not duplicate the refund in the pinned tool implementation.
- Gate A4: fault events are deterministic and uniquely bound.
- Gate A5: all existing simulator, data-integrity, conformance, T1/T3 and D-079 regression checks remain green.

## Limitations / next step

Passing these tests validates only this tool's observed commit/retry semantics. It does not establish that all Retail tools are idempotent or that a generic recovery controller is safe. Next, add one more semantically distinct write-tool case (e.g. address modification) and a task-linked Train-only deterministic fault manifest. Then run the fixed recovery policy saturation gate before any evolutionary search. No Validation/Test access.


## Semantic distinction established by the slice

- `cancel_pending_order`: non-repeatable state transition; after-commit retry is rejected and cannot duplicate refund entries.
- `modify_pending_order_address`: idempotent assignment; after-commit retry converges to the same DB state.

This distinction prevents treating all post-commit timeouts with one retry rule. The controller must condition recovery on tool contract and whether the effect may already have committed.
