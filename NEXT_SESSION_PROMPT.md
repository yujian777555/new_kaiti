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

Research status:
- D-078: 42 exploratory runs, 14 arms × 3 seeds; no established EC uplift.
- D-079 v2: frozen Train-only manifest, 288 scenarios, 48 clusters; SHA-256 `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`. This is not execution permission and does not authorize Validation/Test.
- FSPAE: provisional hypothesis only.
- EvoTool: primary evolutionary baseline candidate; paper G=8/B=3, code default 90 generations. The 150-instance demo data path mixes official splits; the tau-bench adapter omits the official user-simulator loop and has metric/reward discrepancies. See docs/08. No baseline run yet.

Immediate task:
1. Do not use the 150-instance tau-bench demo builder for paper claims.
2. Ask for explicit approval before reading/materializing official Dev/Test task payloads to prepare a split-preserving data path. No Test payload/outcome access without approval.
3. After the data gate passes, prepare Qwen3-8B vLLM smoke preflight; ask separately before launching A800/vLLM or paid API.
4. Reconcile/label the released tau-bench adapter discrepancies; do not call it a full official tau-bench reproduction unless user-simulator, rules/wiki, and reward semantics are restored.
5. Update all research decisions, experiment manifests, and handoffs only in new_kaiti.

Maintain the evidence ledger and update the handoff/prompt after each meaningful milestone. Distinguish source-preserving transfer, successful tests, exploratory results, and confirmatory evidence.
