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
