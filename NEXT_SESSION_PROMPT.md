# Next-session prompt — new_kaiti

You are continuing Paper 1 in **yujian777555/new_kaiti only**. Never write new work to `yujian777555/kaitibaogao`; it is now a historical source repository. Do not mix with `openissue`, `agentfotagent`, `EvoPareto-Agent`, `CausalEvo-DSH`, or `GLEPPO`.

Read first:
1. `SESSION_HANDOFF.md`
2. `DECISION_LOG.md`
3. `docs/07_TRANSFER_PROVENANCE.md`
4. `docs/01_PAPER1_BASELINE_AND_METHOD_CANDIDATE.md`
5. `docs/02_EVOTOOL_REPRODUCTION_AUDIT.md`
6. `docs/03_MODULE_LEVEL_COMPARISON_AND_FSPAE_HYPOTHESIS.md`
7. `docs/08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md`
8. `docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md`
9. `data/taubench_legacy/retail/README.md`

Research status:
- D-078: 42 exploratory runs, 14 arms × 3 seeds; no established EC uplift.
- D-079 v2: frozen Train-only manifest, 288 scenarios, 48 clusters; SHA-256 `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`. This is not execution permission and does not authorize Validation/Test.
- FSPAE: provisional hypothesis only.
- EvoTool: primary evolutionary baseline candidate; paper G=8/B=3, code default 90 generations. The demo data path mixes splits. Pinned legacy Retail data has been built from official Train/Dev/Test (500/20/115); source gate PASS, overall PASS_WITH_CAVEAT. See docs/09. No model baseline yet.

Immediate task:
1. Do not use the mixed 150-instance tau-bench demo builder for paper claims.
2. Use the pinned split-preserving normalized JSONL generated from the vendored source. Preserve the exact Train/Dev/Test boundaries.
3. Reconcile the 44 domain-level Error results with official tau-bench reward semantics; preserve them as source trajectories. Do not silently classify them as corrupt or modify Gold Actions.
4. Reconcile EvoTool's local adapter marking Error-returning tool calls as status=success and the effect on its progress shaping.
5. Restore or clearly disclose the official user-simulator/rules/wiki interaction before calling any adapted baseline paper-faithful.
6. Review the paper's exact sample protocol against official split sizes 500/20/115. No model inference, A800/vLLM, paid API, or optimizer run without separate explicit approval.
7. Update all research decisions, experiment manifests, and handoffs only in new_kaiti.

Maintain the evidence ledger and update the handoff/prompt after each meaningful milestone. Distinguish source-preserving transfer, successful tests, exploratory results, and confirmatory evidence.
