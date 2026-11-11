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
- Primary evolutionary baseline candidate: **EvoTool (ACL 2026)**. Its paper/code generation-budget discrepancy is documented; reproduction must verify the paper-faithful configuration rather than silently accepting code defaults.
- GEPA is a selection/reflection comparator. DART and Evidence-Guided Recovery are recovery-domain comparators.

## Research workflow

1. Audit the baseline paper and official code.
2. Faithfully reproduce a tractable official benchmark slice before adapting the method.
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
- `DECISION_LOG.md`: dated research decisions and evidence.
- `SESSION_HANDOFF.md`: canonical current state and next actions.
- `NEXT_SESSION_PROMPT.md`: compact continuation instructions.

## Validation status of the transfer

The source files were transferred from a pinned source commit without modifying their contents. **The copied code has not yet been independently re-run in this new repository.** A new GitHub Actions regression workflow is included to validate the transferred subset. Until it passes, treat the migration as a source-preserving transfer, not a verified runnable release.

## Provenance

The initial research snapshot was reviewed from `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3` on 2026-11-11. The old repository was not modified by this initialization.
