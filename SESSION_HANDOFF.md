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
- EvoTool paper/code mismatch: paper G=8/B=3; released defaults derive 90 generations. Use explicit G=8 and verify run logs.

## Transfer state

The new repository contains the paper framing, baseline audit, FSPAE hypothesis, D-078/D-079 protocols, D-079 generator/lock/manifest, selected A-3B simulator/controller/EA/SBCG source modules, and selected tests/results. Exact source paths and source commit are recorded in `docs/07_TRANSFER_PROVENANCE.md`.

**Important:** copied code has not yet been independently executed from this repository. The first task is to run the new CI suite, repair missing dependencies/imports in this repository only, and verify the D-079 manifest regeneration against the frozen hash.

## Immediate next steps

1. Inspect the new repository tree and confirm all transferred files are present.
2. Run the new regression workflow on the copied subset; fix failures in `new_kaiti` only.
3. Verify the D-079 generator reproduces the locked SHA exactly.
4. Then prepare the EvoTool Qwen3-8B tau-Bench reproduction preflight.
5. Ask for explicit approval before starting A800/vLLM, real LLM API calls, formal A-3B optimizer runs, or any Validation/Test access.
6. After baseline reproduction, implement FSPAE as an isolated, testable algorithmic change and compare against matched NSGA-II/III, current SBCG, EvoTool-style and GEPA-style controls.

## Hard constraints

- Do not claim FSPAE works before evidence.
- Do not use D-079 Train-only data to claim held-out generalization.
- No unsafe candidate may enter a deployment path; hard constraints remain zero tolerance.
- No project mixing.
