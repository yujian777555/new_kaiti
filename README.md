# Agent × Evolutionary Computation — Paper 1

This repository is the **sole active workspace** for the first short paper on Agent × Evolutionary Computation.

## Working title

**面向状态化工具调用智能体的故障分层 Pareto 档案演化方法**  
*Fault-Stratified Pareto Archive Evolution for Recovery Policies in Stateful Tool-Using Agents*

Research object: recovery-policy evolution for stateful tool-using LLM agents under ambiguous tool outcomes, partial commits, non-idempotent actions, compensation limits, and cross-tool fault interactions.

The foundation-model weights are initially frozen. The LLM is accessed through an API or OpenAI-compatible inference endpoint; model training is not a prerequisite for Paper 1.

## Current scientific status — 2026-11-11

- **No positive algorithmic uplift has been established.**
- D-078 was an exploratory 14-arm × 3-seed pilot. It did not establish that the existing SBCG/NSGA-III approach outperforms strong baselines.
- D-079 v2 is a Train-only diagnostic challenge manifest. Canonical SHA-256: `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`. It is not execution authorization and is not a held-out test set.
- The provisional method hypothesis is **Fault-Stratified Pareto Archive Evolution (FSPAE)**. It has not yet been implemented or validated as a successful method.
- Primary evolutionary baseline candidate: **EvoTool (ACL 2026)**. The released 150-instance demo path mixes official splits and is prohibited for paper claims. A pinned legacy Retail dataset has now been built from the exact Train/Dev/Test sources (500/20/115); source integrity passes with documented domain-rejection and duplicate caveats. See `docs/08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md` and `docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md`. No model baseline has been run.
- GEPA is a selection/reflection comparator. DART and Evidence-Guided Recovery are recovery-domain comparators.

## Research workflow

1. Audit the baseline paper and official code; record implementation discrepancies.
2. Preserve and validate the split-pinned legacy tau-bench Retail data; do not use the mixed 150-instance demo subset for paper claims.
3. Identify a specific mechanism limitation, not merely a different application domain.
4. Implement the proposed evolutionary mechanism with matched baselines and ablations.
5. Use Train-only diagnostics for mechanism discovery.
6. Preregister Validation/Test, lock splits and metrics, then evaluate held-out generalization.
7. Write the paper only after evidence supports the claims.

## Repository rules

- This repository supersedes `yujian777555/kaitibaogao` as the active workspace for this paper.
- Do not write new paper work to the old repository. It remains an untouched historical source/archive.
- Do not mix this paper with `openissue`, `agentfotagent`, `EvoPareto-Agent`, `CausalEvo-DSH`, or `GLEPPO`.
- Preserve source commit IDs, artifact hashes, model/provider settings, seeds, budgets, and split boundaries.
- Never describe exploratory results as confirmatory evidence.
- Hard safety constraints are not exchangeable for task success.
- Update `DECISION_LOG.md`, `SESSION_HANDOFF.md`, and `NEXT_SESSION_PROMPT.md` as the project changes.

## Structure

- `docs/`: paper framing, literature/baseline audit, method specification, experimental protocol, provenance.
- `experiments/pilot_a3b/`: transferred Train-only generator, manifest lock, simulator/controller, SBCG code and regression tests.
- `experiments/pilot_a_recovery/`: transferred simulator contract source used by the A-3b pilot.
- `experiments/pilot_a3b/results/`: immutable exploratory reports and the D-079 v2 manifest/audit.
- `vendor/tau_bench/`: source-preserving MIT snapshot of the pinned legacy Retail benchmark files.
- `data/taubench_legacy/retail/`: source lock, dataset build instructions, and generated split artifact protocol.
- `DECISION_LOG.md`: dated research decisions and evidence.
- `SESSION_HANDOFF.md`: canonical current state and next actions.
- `NEXT_SESSION_PROMPT.md`: compact continuation instructions.

## Validation status of the transfer

The source files were transferred from a pinned source commit without modifying their contents. **The copied subset has passed its first new-repository regression run:** GitHub Actions run [42965838729](https://github.com/yujian777555/new_kaiti/actions/runs/42965838729), with 95 passed and 1 skipped. The skip is the D-078 raw matrix reconstruction test because the 10,285,231-byte `matrix_results.json` could not be transferred by the file reader; its source blob SHA is recorded in `docs/07_TRANSFER_PROVENANCE.md`. The D-079 generator/committed-lock regression passed. This validates the transferred test subset, not FSPAE performance.

## Provenance

The initial research snapshot was reviewed from `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3` on 2026-11-11. The old repository was not modified by this initialization.

## D-088 takeover status — 2026-11-12

- Current remote `main` was re-queried at `caa2fed180c5d6efc48478962e5f23a099d960a5`; new work is isolated on `codex/d088-step1-takeover`.
- D-087 historical evidence was copied from historical commit `916b371ebc10825752d85b31e1ede5c6827c2cb3` into `data/historical/d087/` with byte-level SHA-256 verification. See `data/historical/d087/D087_PROVENANCE.json`.
- Independent raw-ledger recomputation confirms D-087 `REPLICATION_FAILED / NO-GO`: 1,040 rows, 30 candidate failures, all at repeat 4 and 24-decision forced abort, with zero candidate hard-constraint violations.
- `docs/13_D087_FAILURE_MECHANISM_AUDIT.md` separates five counterfactually repairable failure classes from the `rv03` R3 repeat-4 25-step lower bound. No new algorithmic uplift, model training, LLM/API call, or Test scoring has been run.
