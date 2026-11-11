# Paper 1 — Baseline Audit and Method Candidate

**Status:** research candidate only; novelty and empirical uplift are not approved.  
**Active repository:** `yujian777555/new_kaiti`. Historical evidence source: `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`.

## 1. Working title

**Chinese:** 面向状态化工具调用智能体的契约约束恢复策略演化方法  
**English:** Contract-Aware Evolution of Recovery Policies for Stateful Tool-Using Agents

## 2. Research question

For an LLM agent operating a stateful, multi-step tool workflow, how can an evolutionary algorithm discover reusable recovery controllers that handle ambiguous outcomes, partial commits, non-idempotent actions, compensation limits, and cross-tool fault interactions while respecting hard safety constraints?

The paper is about **evolving the recovery policy/controller**, not training a new foundation model and not merely adding NSGA-III to an Agent.

## 3. Baseline selection

### Primary evolutionary baseline: EvoTool (ACL 2026)

- Paper: https://aclanthology.org/2026.acl-long.2016/
- Official implementation: https://github.com/SYang2000/ACL_2026_EvoTool
- It evolves a modular tool-use policy (Planner, Selector, Caller, Synthesizer) with trajectory-grounded blame attribution, feedback-guided targeted mutation, and diversity-aware population selection.
- It evaluates ToolBench, RestBench, tau-Bench, and BFCL, including stateful long-horizon tool use.
- It is the primary paper to reproduce because it is a recent ACL Long Paper with accessible official code and an explicit evolutionary optimization loop.

### Closest representation comparator: EvoFSM (2026 preprint)

- Paper: https://arxiv.org/abs/2601.09465
- It evolves explicit FSM Flow and Skill through critic-guided constrained operations and self-evolving memory.
- It is highly relevant to the controller representation, but the cited GitHub repository was not retrievable through the connected GitHub source during this audit. Treat it as related work until the code is independently verified.

### Recovery-domain comparators

| Work | What it contributes | Role in this paper |
|---|---|---|
| DART (2026) — https://arxiv.org/abs/2605.23311 | Semantic recoverability, reviewed boundaries, instance-aligned checkpoints, admissible rollback | Strong recovery-runtime baseline and formal comparison |
| Evidence-Guided Recovery (2026) — https://arxiv.org/abs/2610.41453 | Observation-contingent planning and effect-history adjudication for ambiguous outcomes and partial execution | Direct problem comparator; distinguish planning from cross-task evolutionary policy search |
| EvoUndo (2026) — https://arxiv.org/abs/2608.28363 | Recoverability-constrained self-evolution of agent harness mutations | Adjacent self-evolution work; different object from workflow recovery policy |
| ToolMisuseBench (2026) — https://arxiv.org/abs/2604.01508 | Offline deterministic tool-misuse and recovery benchmark | Candidate external benchmark after split/license audit |
| AgentRx (Findings EMNLP 2026) — https://aclanthology.org/2026.findings-emnlp.598/ | Evidence-grounded failure localization and attribution | Candidate diagnostic comparator/trajectory-labeling tool |
| Failing Tools (OpenReview submission) — https://openreview.net/pdf/2be5795add6ec19f401efc71c99e69f5dea50e1c.pdf | Runtime fault injection for stateful tool APIs | Related benchmark; publication/code status must be checked |

## 4. Provisional research gap

Do **not** claim that this is the first use of evolutionary algorithms for Agent recovery, the first FSM-based self-evolving Agent, or the first recoverability-aware Agent.

The provisional gap is narrower:

> Existing evolutionary Agent methods optimize prompt modules or general workflow structure; recovery runtimes such as DART and evidence-guided planning methods define admissible recovery decisions but do not search a reusable recovery-controller population across task-family and fault-composition distributions. We will test whether contract-aware evolutionary search can discover better reusable finite-state recovery policies under partial observability and hard effect constraints.

This claim remains provisional until the full related-work audit and baseline reproduction are complete.

## 5. Candidate method — not yet validated

A candidate **Contract-Aware Counterexample-Guided Evolution (CACGE)** method may contain:

1. **Typed FSM genotype:** observation guards, actions, bounded controller memory, and explicit compensation state.
2. **Contract-preserving variation:** crossover/mutation followed by deterministic semantic repair; e.g. prevent an unverified retry after an ambiguous non-idempotent outcome, reject type-incompatible actions, and remove unreachable/dead transitions.
3. **Stratified counterexample guidance:** group failures by public fault signature × tool contract × recoverability class; target underperforming clusters rather than repeatedly sampling easy cases.
4. **Safety-first multiobjective selection:** hard violations determine feasibility first; then optimize class-conditional recovery, avoidable harm, unnecessary actions, R3 correct escalation, and R4 damage containment. Hard safety must never be traded for task success.

The primary algorithmic contrast should be the combined method versus standard NSGA-II under the same genotype, initialization, simulator budget, and seeds. Separate A-only and B-only ablations are required. NSGA-III, standard GA, random search, Hand FSM, Rule, Reflection, and EvoTool-style blame/targeted mutation are secondary controls. DART and evidence-guided planning are recovery-domain comparators.

## 6. Required experiments

1. **Faithful baseline reproduction:** reproduce EvoTool on one official benchmark slice (prefer tau-Bench because it is stateful), with the official model/configuration, seeds, and evaluation budget. Do not call an adaptation a faithful reproduction.
2. **Mechanism-discovery diagnostics:** repair and freeze the D-079 Train-only manifest, then run only after the repository's authorization gate permits it. D-079 is not confirmatory and cannot support held-out generalization claims.
3. **Confirmatory evaluation:** use a new locked Test split with task-family shift, fault-composition shift, and joint shift; report class-conditional outcomes and cluster-level paired uncertainty.
4. **External validation:** audit ToolMisuseBench and/or Failing Tools for licenses, split overlap, and whether their semantics actually cover partial commits and recoverability. Add a real LLM-backed agent evaluation only after explicit authorization and a clean preflight.

## 7. Metrics and success criteria

- R1/R2: conditional task recovery success (R2 must complete after compensation).
- R3: correct escalation/stop with zero avoidable residual.
- R4: damage containment at the minimum reachable residual; do not demand impossible zero residual.
- Global safety: duplicate-effect rate, observed invariant violations, avoidable residual harm.
- Efficiency: action count, wait count, simulator episodes, unique evaluations, wall-clock, token/API cost.
- Generalization: task-family, fault-stratum, and joint-shift results.

A paper-level EC improvement claim requires the combined method to outperform matched NSGA-II on the preregistered primary endpoint, with paired uncertainty excluding no effect, without worsening hard safety metrics. If not, revise or reject the method.

## 8. Current evidence and restrictions

- D-078 completed 42 exploratory runs across 14 arms and 3 seeds; it did not establish EC uplift. The independent D-079 audit found strong selection of the Hand FSM on Validation, including a 0.0000 R3 correct-escalation rate for that Hand FSM.
- The D-079 v1 candidate manifest failed a cluster-ID consistency audit and is not locked. See `04_D079_MANIFEST_AUDIT_AND_CLUSTER_FIX.md`.
- No paper result section may claim improvement yet.
- No formal A-3b, locked Test, external benchmark Test, A800/ARWM, or real LLM API run is authorized by the current D-079 protocol. Do not bypass this boundary.

## 9. Initial target venues

For an EC-centered method paper, first assess GECCO and IEEE CEC; also consider Swarm and Evolutionary Computation or Applied Soft Computing depending on the strength of the algorithmic result. Agent/NLP venues are secondary options if the paper's strongest contribution becomes the Agent recovery benchmark or system evaluation rather than the evolutionary method.


## 10. Module-level comparison revision — 2026-11-11

GEPA (ICLR 2026 Oral; https://arxiv.org/abs/2507.19457; https://github.com/gepa-ai/gepa) is added as the selection/reflection comparator. Its documented loop selects from a Pareto frontier of candidates that excel on different task subsets, reflects on full execution traces, mutates using accumulated lessons, and can merge complementary candidates.

The current hypothesis is narrowed from generic CACGE to a more specific **Fault-Stratified Pareto Archive Evolution (FSPAE)** selection mechanism. The intended archive descriptor is task-family × fault-stratum (48 Train clusters in D-079 v2), with recoverability class retained as a separate audited field. This is a proposed mechanism, not a validated result. See `03_MODULE_LEVEL_COMPARISON_AND_FSPAE_HYPOTHESIS.md`.

The existing SBCG implementation already has five objectives, zero-tolerance safety constraints, a family × failure-signature × safety-class counterexample pool, and a global Pareto elite archive with a per-family CondRecSucc guard. The new hypothesis is specifically to preserve and sample **per fault-stratum Pareto specialists**, rather than relying only on a global population and per-family CondRecSucc guard.


## Repository transfer note

This document is a research-state snapshot transferred on 2026-11-11 from `yujian777555/kaitibaogao` branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. Historical commit IDs and CI links are preserved for provenance; all subsequent edits belong in `yujian777555/new_kaiti`.
