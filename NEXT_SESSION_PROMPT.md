# Next-session prompt — new_kaiti

You are continuing Paper 1 in **yujian777555/new_kaiti only**. Never write new work to `yujian777555/kaitibaogao`; it is now a historical source repository. Do not mix with `openissue`, `agentfotagent`, `EvoPareto-Agent`, `CausalEvo-DSH`, or `GLEPPO`.

Read first:
1. `SESSION_HANDOFF.md`
2. `DECISION_LOG.md`
3. `docs/07_TRANSFER_PROVENANCE.md`
4. `docs/01_PAPER1_BASELINE_AND_METHOD_CANDIDATE.md`
5. `docs/02_EVOTOOL_REPRODUCTION_AUDIT.md`
6. `docs/03_MODULE_LEVEL_COMPARISON_AND_FSPAE_HYPOTHESIS.md`

Research status:
- D-078: 42 exploratory runs, 14 arms × 3 seeds; no established EC uplift.
- D-079 v2: frozen Train-only manifest, 288 scenarios, 48 clusters; SHA-256 `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`. This is not execution permission and does not authorize Validation/Test.
- FSPAE: provisional hypothesis only.
- EvoTool: primary evolutionary baseline candidate; paper G=8/B=3, code default 90 generations. Do not claim faithful reproduction unless the explicit paper configuration is used and verified.

Immediate task:
1. CI transfer validation has passed: run 42965838729, 95 passed, 1 skipped. The D-079 generator/committed-lock regression passed. The only skip is D-078 raw matrix reconstruction because the 10.3 MB matrix_results.json was not transferred; source SHA is in docs/07_TRANSFER_PROVENANCE.md.
2. Decide whether the large D-078 artifact should be restored to enable that test.
3. Prepare EvoTool Qwen3-8B tau-Bench reproduction preflight; do not launch A800/vLLM or paid API without explicit approval.
5. Do not run formal A-3B optimizer, Validation/Test, or external Test without a separate reviewed authorization.

Maintain the evidence ledger and update the handoff/prompt after each meaningful milestone. Distinguish source-preserving transfer, successful tests, exploratory results, and confirmatory evidence.
