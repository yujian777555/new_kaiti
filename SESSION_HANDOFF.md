# Session handoff — 2026-11-11

## Active repository

`yujian777555/new_kaiti` — sole active workspace for Paper 1.

Historical source: `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`, pinned HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. Do not write to the old repository.

## Paper 1 direction

Working title: **面向状态化工具调用智能体的故障分层 Pareto 档案演化方法**.

Research object: evolving reusable recovery controllers for stateful tool-using LLM Agents. Primary evolutionary baseline: EvoTool (ACL 2026). GEPA is the selection/reflection comparator; DART and Evidence-Guided Recovery are recovery-domain comparators.

Provisional method: FSPAE — bounded Pareto archives per task-family × fault-stratum, coverage-deficit parent selection, class-relevant local objectives, and zero-tolerance hard safety constraints. This is not yet implemented or validated.

## Preserved evidence

- D-078: 42 exploratory runs, 14 arms, 3 seeds; no established evolutionary uplift.
- D-079 v2: 288 Train-only scenarios, 48 clusters, 6 rows/cluster, 3 search + 3 diagnostic; all R1–R4 labels present.
- Manifest SHA-256: `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`.
- D-079 lock is a data-integrity lock only, not permission to run the optimizer or access Validation/Test.
- EvoTool paper specifies G=8/B=3; released default derives 90 generations. Explicit G=8 override works, but the demo data builder mixes official splits and the tau-bench adapter omits the official user-simulator loop. See `docs/08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md`.

## Transfer state

The new repository contains the paper framing, baseline audit, FSPAE hypothesis, D-078/D-079 protocols, D-079 generator/lock/manifest, selected A-3B simulator/controller/EA/SBCG source modules, and selected tests/results. Exact source paths and source commit are recorded in `docs/07_TRANSFER_PROVENANCE.md`.

**Transfer validation:** GitHub Actions run [42965838729](https://github.com/yujian777555/new_kaiti/actions/runs/42965838729) passed: 95 passed, 1 skipped. The D-079 generator regenerated the manifest and matched the committed lock. The only skip is reconstruction from the 10,285,231-byte D-078 raw matrix artifact, not transferred; source SHA is recorded in `docs/07_TRANSFER_PROVENANCE.md`. This is test-suite validation, not an algorithmic uplift result.

## Immediate next steps

1. Complete the split-preserving EvoTool data-preparation design. Do not use the released 150-instance tau-bench demo builder for paper claims.
2. Obtain explicit approval before reading/materializing the official Dev/Test task payloads; this is separate from permission to run a model.
3. After the split/data integrity gate passes, prepare a Qwen3-8B vLLM smoke-test plan. Obtain separate approval before starting A800/vLLM or any real LLM API calls.
4. Reconcile the released-code tau-bench adapter and reward discrepancies; label any reduced offline adaptation honestly.
5. Only after the baseline preflight is accepted, run the authorized baseline and then compare FSPAE against matched NSGA-II/III, current SBCG, EvoTool-style and GEPA-style controls.
6. Do not run formal A-3B optimizer, D-079 Validation/Test, or external benchmark Test without separate reviewed authorization.

## Hard constraints

- Do not claim FSPAE works before evidence.
- Do not use D-079 Train-only data to claim held-out generalization.
- No unsafe candidate may enter a deployment path; hard constraints remain zero tolerance.
- No project mixing.
