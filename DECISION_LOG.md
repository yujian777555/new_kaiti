# Decision log

## 2026-11-11 — D-001: Establish new active repository

- Decision: `yujian777555/new_kaiti` is the sole active repository for Paper 1.
- The previous `kaitibaogao` repository is historical/read-only for this project; no new commits should be made there.
- A source-preserving snapshot of key documents, manifest, code and exploratory evidence is transferred from source HEAD `33672562ebaeb6c6a533e7e0fd975cbac045b5e3`.
- Do not mix with the user's other Agent/EC repositories.

## 2026-11-11 — D-002: Keep the research question narrow

- Research object: evolutionary optimization of reusable recovery controllers for stateful tool-using LLM Agents.
- Primary evolutionary baseline candidate: EvoTool (ACL 2026).
- GEPA is a selection/reflection comparator; DART and Evidence-Guided Recovery are recovery-domain comparators.
- Proposed method hypothesis: FSPAE, a fault-stratified Pareto archive with coverage-deficit parent selection and zero-tolerance hard safety constraints.
- FSPAE is a hypothesis, not a validated contribution.

## 2026-11-11 — D-003: Preserve negative and exploratory evidence

- D-078 is exploratory and does not establish algorithmic uplift.
- D-079 v2 is a Train-only mechanism-discovery diagnostic; its frozen hash is `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`.
- The D-079 lock is not execution authorization and does not permit Validation/Test access.
- No paper claim of superiority is allowed until matched-budget comparisons and an independently locked held-out evaluation support it.

## 2026-11-11 — D-004: Baseline reproduction before method claims

- Reproduce EvoTool on a tractable official stateful benchmark slice before adaptation.
- Paper Appendix A.6 configuration says G=8 and B=3; the released code default derives 90 generations. The reproduction must explicitly set and verify G=8, B=3.
- Model weights remain frozen; no foundation-model training is required for the baseline.


## 2026-11-11 — D-005: Validate the transferred code in new_kaiti

- New repository CI run [42965838729](https://github.com/yujian777555/new_kaiti/actions/runs/42965838729) completed successfully.
- Regression result: 95 passed, 1 skipped.
- D-079 generator regeneration and committed manifest-lock verification passed.
- The single skip is the D-078 raw matrix reconstruction test because the 10,285,231-byte source `matrix_results.json` was not transferred; its original blob SHA is `19aba8cc02a5a10e7e60766ce7c3423e370c51b4`.
- This is a code-transfer regression result only; it is not evidence that FSPAE improves Agent performance.


## 2026-11-11 — D-006: EvoTool tau-bench preflight is blocked pending split-clean protocol

- Audited EvoTool official code at `6a82719ea6e22cf23f963078e2527094e50b47f6` and legacy tau-bench at `59a200c6d575d595120f1cb70fea53cef0632f6b`.
- Paper Appendix A.6 specifies Qwen3-8B, G=8, B=3. The released config defaults to 90 generations; explicit `evolve.generations=8` controls this.
- The released 150-instance tau-bench demo builder takes Test tasks before Train/Dev, then the loader randomly partitions the combined sample 90/30/30. This is not a split-preserving official evaluation protocol.
- The released tau-bench `run_episode` adapter does not implement the original user-simulator/rules/wiki conversation loop; its local reward also differs in required-output normalization and its search reward adds an undocumented progress term.
- Decision: do not run the demo command or report it as a faithful paper reproduction. Prepare a source-pinned split-preserving baseline protocol. No model inference, A800/vLLM, optimizer run, or held-out outcome evaluation was performed.
- Explicit approval is required before reading/materializing the official Dev/Test task payloads. Separate approval is required before starting Qwen3-8B vLLM or any real LLM API call.
- Full details: `docs/08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md`.


## 2026-11-11 — D-007: Build and audit pinned legacy tau-bench Retail splits

- User authorized reading the official Train/Dev/Test task payloads and building a split-preserving dataset; this authorization did not include model inference or optimizer execution.
- Pinned upstream source: `sierra-research/tau-bench` @ `59a200c6d575d595120f1cb70fea53cef0632f6b`, MIT.
- Vendored 35 source files with exact Git Blob SHA matches, including Train 500, Dev 20, Test 115 task records and all three original retail DB files.
- Parsed 635 tasks and 1,375 Gold Actions; normalized JSONL retains split-local source indices and original outputs/actions. No cross-split exact duplicates or instruction duplicates. One exact within-Test duplicate is retained: `retail-test-0093` and `retail-test-0095`.
- DB: 1,000 orders, 500 users, 50 products, 591 variants, 2,978 order items. Zero DB/task-user referential failures.
- Gold Actions: zero unknown tools, signature mismatches, Python exceptions, or deterministic replay mismatches. There are 44 domain-level Error results across 38 tasks (Train 20, Test 24, Dev 0); inspection shows examples of intentional incorrect identity/order/product identifiers and business-rule rejections. Preserve these source trajectories; do not treat every Error string as data corruption.
- The official legacy reward compares post-action database state and required outputs; it does not directly penalize a returned Error string. The EvoTool adapter marks non-exception Error strings as status=success, which can affect its shaped progress term and must be reconciled.
- Overall data gate: `PASS_WITH_CAVEAT`. Full audit: `docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md`.
- No LLM, A800/vLLM, paid API, optimizer, or policy evaluation was run.


### D-007 CI acceptance addendum — 2026-11-11

- CI run [42981617704](https://github.com/yujian777555/new_kaiti/actions/runs/42981617704) completed successfully at code/data commit `805b48ad51122e8bd577a07996c2e84a9dd38989`.
- Transferred simulator/controller tests: 95 passed, 1 skipped. The skip is the previously documented unavailable D-078 raw matrix artifact reconstruction.
- New pinned Retail data tests: 2 passed. Split-preserving dataset build and Actions artifact upload also passed.
- Audit report confirms `PASS_WITH_CAVEAT`, source integrity PASS, Gold Action contract PASS with 44 domain-level rejection diagnostics.
- Artifact: `tau-bench-legacy-retail-805b48ad51122e8bd577a07996c2e84a9dd38989`, ID `13836929695`, expires 2026-12-11.
- This CI result validates data preparation and regression tests only. It is not model inference, a baseline run, optimizer evidence, or algorithmic uplift.
- D-006's earlier restriction on reading official Dev/Test payloads was superseded by the user's subsequent explicit authorization for Step 2 data preparation. That authorization did not include model inference, optimizer execution, or policy scoring.


## D-009 — 2026-11-11: deterministic official/EvoTool conformance harness

- Added `scripts/audit_evotool_tau_bench_conformance.py` and `tests/test_evotool_tau_bench_conformance.py`.
- CI [42987687316](https://github.com/yujian777555/new_kaiti/actions/runs/42987687316): success; conformance 8 passed; existing regression 95 passed/1 skipped.
- Verified 9 pinned EvoTool source files. Adapted split counts Train/Dev/Test = 500/20/115.
- Compared 1,375 Gold Action calls: return mismatches 0, exception mismatches 0, full DB state mismatches 0, product mutations 0; domain-level Error results 44 on each side.
- Compared 635 exact Gold tasks: official reward failures 0, EvoTool Gold success failures 0, outcome mismatches 0. This does not prove policy rollout or conversation-protocol parity.
- Synthetic probes: case-insensitive, comma-normalized, and multiple-response outputs pass official reward but fail EvoTool exact-final-answer check.
- Error-status probe: returned domain Error is marked `success`; progress 1.0 vs 0.5 if rejection were treated as failed business execution; weighted 0.3 shaping component delta 0.15.
- Confirmed interaction deviations: no official user simulator loop/wiki in EvoTool; max steps 30 official vs 6 EvoTool; official full-state hash vs EvoTool orders/users projection (no products mutations observed in the pinned 1,375 action calls).
- Gate: `PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS`. Keep legacy EvoTool unchanged. Any corrected-status/full-conversation implementation must be a separate treatment.
- No LLM, model, API, A800/vLLM, optimizer, training, or policy evaluation.
- Full report: `docs/10_EVOTOOL_TAUBENCH_ADAPTER_CONFORMANCE_AUDIT.md`.



## D-010 — 2026-11-11: strengthen independent conformance evidence before baseline execution

- Independent review of Step 3 found that the initial Action History assertion checked only the number of records, not the ordered action/kwargs sequence. It also found no direct comparison of official Env.reset() with EvoTool fresh-instance DB isolation, and no environment-wrapper dispatch probes.
- Step 3-R1 adds exact Action History comparison for all 635 Gold tasks, reset/copy isolation checks, and actual environment dispatch probes for a successful action, a domain-level rejection, an unknown tool, and a missing required argument.
- The conformance runner now requires a passing integrity_report.json, the exact pinned tau-bench source commit, 42 verified source files, and matching SHA-256 hashes for Train/Dev/Test normalized JSONL before it reports parity.
- The CI dataset-builder command no longer uses || true.
- Expected wrapper deviations are explicit: unknown-tool messages and malformed-argument exception serialization differ between official Env and EvoTool. These are protocol findings, not a reason to mutate the legacy snapshot.
- Do not blindly reclassify every Error: result as status=error. Keep legacy EvoTool unchanged. A corrected treatment must distinguish function execution status from business outcome and justify any new shaping metric.
- Official 30 conversational loop turns and EvoTool 6 planner substeps are different units; do not compare the numeric caps directly.
- No LLM/API/A800/vLLM/optimizer/training/policy-performance run was authorized or performed.


### D-010 verification update

The first Step 3-R1 implementation passed CI on 2026-11-11: run 42992221354, 95 passed/1 skipped transferred regression tests and 11 dataset/conformance tests. Artifact 13841803539 preserves the machine-readable report and normalized splits. Exact Action History matched for all 635 Gold tasks; reset/copy isolation passed; expected dispatch deviations were detected. The follow-up commit improves the human-readable report and adds a report-rendering regression test.


## D-011 — 2026-11-11: separate execution status from business outcome

- Step 3-R1 passed CI run 42993445630 on code/report commit e248486d38933e62a51367f66489e18fc22877fb: 95 passed/1 skipped transferred regression tests and 12 dataset/conformance tests.
- The final report includes exact Action History (635 checked, 0 mismatches), reset/copy isolation PASS, and dispatch PASS_WITH_KNOWN_DEVIATIONS. Artifact 13842368239 expires 2026-12-11.
- A representative Gold Action returns a business-level rejection ("insufficient gift card balance") but is still a valid Gold trajectory under the official state-based reward. Therefore, changing every returned Error string to execution failure is invalid.
- Treatment protocol: T0 immutable EvoTool legacy; T1 status decomposition for diagnostics only (execution status, business outcome, state effect) while preserving legacy reward; T2 business-outcome-aware shaping is NOT READY without task-aware labels; T3 official-reward-aligned scorer is a separate evaluator treatment; T4 full conversational tau-bench loop is a separate protocol.
- Do not call T1 an algorithmic improvement or T2 validated. No model/API/A800/vLLM/optimizer/training/policy-performance run was performed.
- Full protocol: docs/11_EVOTOOL_STATUS_AND_REWARD_TREATMENT_PROTOCOL.md.


### D-011 repository state addendum

- Treatment protocol: docs/11_EVOTOOL_STATUS_AND_REWARD_TREATMENT_PROTOCOL.md.
- Latest code/report commit e248486d38933e62a51367f66489e18fc22877fb passed CI run 42993445630.
- Latest branch HEAD 478e8171f54bbf8ca7ad5ea69c2acdfaf7de3845 adds only the treatment design and handoff/prompt updates. Its docs-only CI run is 42994690443.
- PR #1 remains draft/open; main remains at cf83f08da748f3b7889465c3b19432e6389ca7b7.
