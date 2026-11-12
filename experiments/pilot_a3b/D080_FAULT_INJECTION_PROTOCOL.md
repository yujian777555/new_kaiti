# D-080 Stage A — deterministic Retail tool-boundary fault injection

Status: Stage A PASSED in CI run 43151788172. Stage B manifest generator and live-state integration are under CI validation. No LLM, optimizer, paid API, A800, Dev, or Test execution.

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

Passing these tests validates only this tool's observed commit/retry semantics. It does not establish that all Retail tools are idempotent or that a generic recovery controller is safe. Next, validate the six-tool Train-only fault manifest and live-state episode integration. Then run the fixed recovery-policy saturation gate before any evolutionary search. No Validation/Test access.


## Semantic distinction established by the slice

- `cancel_pending_order`: non-repeatable state transition; after-commit retry is rejected and cannot duplicate refund entries.
- `modify_pending_order_address`: idempotent assignment; after-commit retry converges to the same DB state.

This distinction prevents treating all post-commit timeouts with one retry rule. The controller must condition recovery on tool contract and whether the effect may already have committed.


## Stage B: task-linked Train-only manifest and live-state execution

The manifest generator selects 48 disjoint Train tasks: 8 each for cancel, order-address modification, item modification, payment modification, return, and exchange. Each tool receives exactly two examples of each fault mode. Every selected event is checked against a successful state-changing Gold action in the pinned Train trajectory.

The event payload contains task/tool identity, per-tool call ordinal, mode, seed, semantic class, event ID, and a one-way source-row hash. It contains no Gold kwargs or action payload. The manifest and lock bind to the exact Train JSONL SHA-256. Dev/Validation/Test are excluded.

Fault call ordinals are per tool, not global episode call count. A read-back call to get_order_details therefore does not shift the scheduled ordinal for cancel_pending_order.

A fault-aware EvoTool executor returns injected failures as structured tool observations. A new episode runner grades the actual post-fault database state using the pinned official state-equality and required-output rule. It reports the original EvoTool replay-based reward separately; the two are not conflated.

Stage B gates: 48 unique Train tasks; 8 tasks per tool; exactly 2 examples per tool/mode; every scheduled call is a successful state-changing Gold action; no Gold arguments in event payload; live-state scorer distinguishes pre-execution from post-commit timeout. No policy-performance experiment or LLM inference is included.
