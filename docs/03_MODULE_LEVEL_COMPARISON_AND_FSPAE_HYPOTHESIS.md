# Paper 1 — Module-Level Comparison and FSPAE Hypothesis

**Date:** 2026-11-11  
**Status:** algorithmic hypothesis; no new performance experiment has been run.  
**Active repository:** `yujian777555/new_kaiti`. Historical source snapshot: `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`.

## 1. Why the selection module is the best next target

The baseline audit decomposes EvoTool into policy representation, trajectory diagnostics, blame attribution, targeted mutation, acceptance, and population selection. The selection module is the cleanest target for a controlled replacement:

- EvoTool retains instance-wise winners on `S_sel`; every policy winning at least one instance survives, and parent weights follow win frequency.
- GEPA selects from a Pareto frontier of candidates that excel on different task subsets, reflects on full execution traces, and can merge complementary lessons.
- The current SBCG implementation uses NSGA-II/III survivor selection, a feasible global Pareto elite archive, and a per-family CondRecSucc guard. It does not maintain a distinct archive cell for each fault stratum.

This is a more precise research question than “combine Agent and NSGA-III”.

## 2. Empirical motivation — D-078 is a diagnostic, not a positive result

D-078 completed 42 exploratory runs across 14 arms and three seeds. It did **not** establish evolutionary uplift.

The independent D-079 audit found:

- Hand FSM was selected in 32/42 runs.
- Hand FSM appeared in the Validation Pareto front in 33/42 runs.
- Hand FSM achieved R1/R2 CondRecSucc = 1.0 and R4 DamageContainment = 1.0.
- Hand FSM achieved R3 CorrectEscalation = 0.0 over 36 R3 scenarios.
- The no-M3 arm did not solve this problem; it had higher corrected avoidable harm and lower corrected class success.

Interpretation: the current global selection/fitness process does not discover a controller that handles the R3 permission-after-committed-prefix case. The result motivates a new hypothesis; it does not prove that the selection module alone caused the failure.

## 3. Proposed mechanism: Fault-Stratified Pareto Archive Evolution (FSPAE)

### 3.1 Descriptor

For each evaluated scenario, define a descriptor:

`d(x) = (task_family_id, difficulty_stratum, robust_recoverability_class)`.

D-079 v2 provides 48 task-family × fault-stratum clusters (8 families × 6 strata). The class label R1/R2/R3/R4 is separately stored and checked. A cluster contains six Train scenarios: three `search` and three `diagnostic` parameter-seed replicates.

### 3.2 Per-stratum archive

Maintain a bounded archive `A_c` for each cluster `c`. Only candidates that pass genome validation and all zero-tolerance hard constraints may enter:

- duplicate side effects = 0;
- SLA violations = 0;
- invariant violations = 0.

Within a cluster, retain non-dominated feasible candidates under the class-relevant local objective vector:

- R1/R2: conditional recovery success, avoidable harm, unnecessary action cost;
- R3: correct escalation, avoidable harm, unnecessary action cost;
- R4: damage containment, avoidable harm, unnecessary action cost.

Keep a separate global Pareto archive for overall trade-offs. Do not replace hard safety constraints with weighted penalties.

### 3.3 Parent selection

At each generation:

1. Identify the least-covered or worst-performing fault strata.
2. Sample a target stratum using a preregistered coverage-deficit rule.
3. Select a parent from that stratum's feasible Pareto archive using NSGA-III reference-direction niching (or NSGA-II crowding as an ablation).
4. Apply the existing stratified counterexample guidance to choose an implicated FSM gene.
5. Apply a typed, contract-preserving variation and deterministic repair.
6. Evaluate the child under the same episode budget; update both the local stratum archive and the global archive.

This gives the algorithm an explicit mechanism to preserve R3/R4 specialists instead of allowing common R1/R2 outcomes to dominate parent selection.

### 3.4 Why this is not merely GEPA or MAP-Elites

- GEPA's Pareto frontier preserves candidates with complementary task-subset performance; FSPAE makes the archive descriptor explicit in terms of task-family, tool-fault composition, and recoverability class, and adds zero-tolerance effect constraints.
- EvoTool's instance-wise winner selection preserves per-instance specialists; FSPAE preserves per-stratum specialists and directs parent sampling toward coverage deficits.
- Generic MAP-Elites uses behavior descriptors and quality cells; FSPAE's cells are grounded in tool contracts and robust recoverability labels, with class-specific objectives and hard effect constraints.

Novelty remains provisional until a broader quality-diversity and constrained-EA literature audit is complete.

## 4. Baseline and ablation matrix

| Method | Selection/search mechanism | Role |
|---|---|---|
| Hand FSM / Rule | Fixed recovery controller | Lower-cost operational baselines |
| Random / standard GA | Random or standard variation and selection | Search baselines |
| NSGA-II / NSGA-III | Global multiobjective survivor selection | Matched EC baselines |
| Current SBCG-NSGA-III | Five objectives + stratified counterexamples + global archive/family guard | Existing method baseline |
| EvoTool-style adaptation | Trajectory blame + one-gene/module targeted mutation + instance-wise winner selection | Primary Agent-evolution baseline |
| GEPA-style adaptation | Trace reflection + Pareto frontier + candidate merge | Selection/reflection comparator |
| **FSPAE** | Fault-stratified Pareto archive + coverage-deficit parent selection | Proposed method |

Ablations: remove the per-stratum archive; replace coverage-deficit sampling with uniform sampling; remove counterexample guidance; replace NSGA-III niching with NSGA-II crowding; remove typed repair only in an offline diagnostic ablation (never deploy an unsafe candidate).

All methods must share the same genotype, initial pool, evaluation budget, simulator, seeds, and backbone wherever the comparison is intended to isolate the evolutionary mechanism.

## 5. Hypotheses and primary outcomes

- H1: FSPAE improves macro-averaged and worst-stratum recovery outcomes over matched NSGA-II/III and EvoTool-style selection at equal evaluation budget.
- H2: FSPAE improves R3 CorrectEscalation without reducing R1/R2 CondRecSucc or R4 DamageContainment.
- H3: typed contract-preserving variation reduces invalid genomes and hard-safety failures.
- H4: improvements persist under held-out task-family and fault-composition shifts.

Primary endpoint must be frozen before confirmatory Test access. Report cluster-level paired uncertainty (e.g. paired bootstrap over task-family × fault-stratum clusters), seed variability, and class-conditional metrics. D-079 Train-only diagnostics must not be used to claim generalization or confirmatory significance.

## 6. Experimental sequence

1. Complete the faithful EvoTool reproduction described in `02_EVOTOOL_REPRODUCTION_AUDIT.md`. Paper Appendix A.6 states G=8/B=3; the released code default is 90 generations, so use and verify the paper-faithful override rather than the default.
2. After explicit authorization, use D-079 v2 only for Train-only mechanism discovery. It has a committed Train-only manifest lock; the lock is not execution permission.
3. Compare FSPAE against matched NSGA-II/III, current SBCG, EvoTool-style and GEPA-style adaptations on identical budgets.
4. Only after a new split is preregistered and locked, perform Validation selection and a held-out Test evaluation with family/fault shift.
5. Add an external benchmark only after its licenses, split overlap, task semantics, and partial-commit/recovery coverage have been independently audited.

## 7. Stop conditions

Reject or revise FSPAE if it only improves the aggregate mean while worsening R3/R4, increases any hard safety violation, fails to outperform matched NSGA-II/III at equal budget, or loses its gains on the locked shift test. Do not write a positive algorithmic conclusion before these gates pass.


## Repository transfer note

This document is a research-state snapshot transferred on 2026-11-11 from `yujian777555/kaitibaogao` branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. Historical commit IDs and CI links are preserved for provenance; all subsequent edits belong in `yujian777555/new_kaiti`.
