# Step 4 implementation — T1 status decomposition and T3 official scorer

**Date:** 2026-11-11  
**Status:** IMPLEMENTED — deterministic Train-only validation passed in CI; no policy experiment.

## 1. Deliverables

- T1 module: treatments/evotool_status.py
- T3 module: treatments/taubench_official_reward.py
- Deterministic audit: scripts/audit_evotool_treatments.py
- Unit and integration tests: tests/test_evotool_treatments.py
- CI workflow: Paper 1 regression workflow includes the audit and tests.

The vendored EvoTool and official tau-bench source snapshots are unchanged. T0 remains the original baseline.

## 2. T1 — status decomposition

T1 wraps an existing executor and preserves the original result fields (tool, args, output, status) byte-for-byte/value-for-value. It adds:

- execution_status: returned, raised_exception, unknown_tool, or unknown.
- business_outcome: accepted, rejected, no_match, not_applicable, or unknown.
- state_effect: changed, unchanged, or unknown.
- tool_observation: exact raw output.
- state_before_sha256 and state_after_sha256.

The mapping is deliberately conservative and tool-aware. A missing user/order/product from a lookup tool is no_match. Other Error returns from a known tool are recorded as rejected. The original status remains untouched: a normally returned Error string is still execution_status=returned and legacy status=success. The module also provides make_status_decomposed_env_factory(), which can wrap the tau-bench executor factory for an explicitly enabled T1 run without editing vendor files.

T1 does not change the original metrics.progress function, evaluator, success criterion, or reward. The Train-only audit compares the legacy and wrapped executors on identical database copies for all 768 Train Gold Action calls and verifies result fields, DB state, progress and episode reward.

## 3. T3 — official reward scorer

T3 is a separate scorer module. It reproduces the pinned official Retail reward:

1. Replay gold actions on a fresh DB, skipping terminal tools during gold replay.
2. Compare the complete DB hash using the official to_hashable + SHA-256 representation. This includes orders, users, and products.
3. Require every required output string to occur in at least one response message, case-insensitively, after removing commas from the response message only.
4. Return binary reward 1 only when both state and output checks pass.

The API supports a live candidate DB (score_official_task) or deterministic candidate action replay (score_task). It accepts all response messages. Passing only EvoTool's single synthesizer answer remains a reduced-adapter approximation of the official multi-response interaction protocol.

The Train-only audit compares T3 against the pinned official Env.calculate_reward on all 500 Train Gold tasks, using official tool implementations. No Dev/Test policy scoring or tuning occurs.

## 4. Deterministic validation

The CI audit must report:

- T1: 500 Train tasks / 768 Gold Action calls; 20 domain Error returns; zero legacy-field, DB-state, progress or episode-reward mismatches.
- T3: 500 Train Gold tasks; zero official reward mismatches; zero gold/candidate full-state hash mismatches.
- Unit tests cover no-match versus rejection, exception versus unknown tool, state effects, unchanged legacy status, full DB hashing including product-only changes, exact comma/case normalization, multiple response messages, all-required-output semantics, and terminal-tool replay.

These are implementation/conformance checks only. They are not policy performance results and do not establish algorithmic uplift.

## 5. Limitations and next gate

- T1's initial business-outcome taxonomy is diagnostic, not a validated reward-label ontology. T2 remains blocked.
- T3 is a scorer parity module; it does not restore the full user-simulator/wiki conversational loop.
- The existing EvoTool lane produces one final synthesizer answer. The scorer supports multiple messages, but the integration protocol must supply them to claim full conversational parity.
- No model inference, paid API, A800/vLLM startup, optimizer execution, training, or policy-performance evaluation was performed or authorized.

Next: independently review T1/T3 implementation and CI results. Only after that review should any separately authorized model/optimizer experiment be considered.


### CI correction — script entry-point import

The first CI attempt (run 43008576540) passed dataset construction and the Step 3 conformance audit, then failed when invoking scripts/audit_evotool_treatments.py directly: Python placed the scripts directory, not the repository root, at sys.path[0]. The audit entry point now inserts the repository root before importing the shared scripts package. This is an execution-path fix, not a change to T1/T3 semantics.


### Audit runtime refinement

T1 now hashes the JSON-backed DB before and after execution without deep-copying the entire database on every call; a deep-copy fallback is retained only for non-JSON delegates. The Train audit reuses two executor objects and resets their DB snapshots per task. T3 and the official reference environment reuse the already integrity-checked pinned DB through deep-copy loaders rather than rereading JSON files thousands of times. These are execution-cost optimizations only; score and diagnostic semantics are unchanged.
