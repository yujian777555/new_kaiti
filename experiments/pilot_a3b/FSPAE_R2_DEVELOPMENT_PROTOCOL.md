# FSPAE-R2 Train-only development protocol

Protocol ID: D-079-R2.1-FACTORIAL-DEV
Code branch: audit/step3-independent-review
Optimization manifest: D-079 v2, SHA-256 09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca
Scope: synthetic Train/search optimization; previously inspected Train/diagnostic role used for development feedback only.

## Hypothesis

FSPAE-R1 uses archive cardinality as part of target selection and applies counterexample mutation from a global pool. R2 replaces the cardinality proxy with a local performance deficit, selects both parents from the target stratum archive when available, and restricts counterexample-guided mutation to the same family × fault-stratum cluster. If that cluster has no observed counterexample, R2 uses standard mutation rather than borrowing a counterexample from another cluster.

## Algorithm specification

- Target priority: min_archive[0.8 * clip(1 - class_success, 0, 1) + 0.2 * clip(avoidable_harm, 0, 1)].
- Archive cardinality is not an input to the R2 priority.
- Both parents are sampled from the target cluster's feasible local Pareto archive; global tournament is the fail-safe fallback when the local archive is empty.
- Counterexample keys include family, exact cluster, failure signature, and robust class.
- Mutation selection is exact-cluster conditional. No cross-cluster fallback is permitted.
- Global NSGA-III survivor selection and zero-tolerance hard constraints remain unchanged.
- If no target-cluster counterexample exists, use standard mutation and record the fallback explicitly.

## Arms

| Arm | Target scheduler | Parent selection | Mutation source |
|---|---|---|---|
| matched_nsga3 | — | global tournament | standard mutation |
| sbcg_nsga3 | — | global tournament | family/signature/class stratified |
| fspae | legacy archive/performance deficit | local A + global B | global stratified |
| fspae_uniform | uniform | local A + global B | global stratified |
| fspae_r2 | performance deficit | local pair | exact target cluster |
| fspae_r2_global_mut | performance deficit | local pair | global stratified |
| fspae_r2_uniform | uniform | local pair | exact target cluster |
| fspae_r2_uniform_global_mut | uniform | local pair | global stratified |
| fspae_r2_legacy_scheduler | legacy deficit | local pair | exact target cluster |

## Frozen run settings

- Seeds: 411, 522, 633.
- Population: 8.
- Generations: 5.
- Archive capacity: 4 per cluster.
- Search scenarios: 144 (48 clusters × 3 replicates).
- Budget: 6,912 episodes per arm/seed.
- Common initial pool per seed; same representation, simulator, and global survivor selection.
- Diagnostic selection: common Train-search feasible Pareto / family-coverage / worst-family CondRecSucc selector.
- Outcomes: macro class success, R1/R2 CondRecSucc, R3 CorrectEscalation, R4 DamageContainment, avoidable harm, duplicate, SLA and invariant violations, recovery decision count.
- Hard safety: zero tolerance; violations cannot be traded against success.

## Diagnostic-use restriction

The D-079 diagnostic role has already been inspected in the R1 experiment and is therefore not a fresh held-out set. This experiment uses it only to guide development. No Validation/Test payload is constructed or accessed. No LLM API, GPU, A800, or foundation-model training is used.

## Mechanism gates

1. R2 target-parent audit must show local archive sourcing for both parents whenever the target archive is non-empty.
2. Every targeted counterexample mutation must have selected_cluster == target_cluster.
3. Cross-target mutation count must equal zero.
4. No-target counterexample cases must use explicit standard-mutation fallback.
5. Per-arm episode accounting must not exceed the frozen budget.
6. Hard-safety violations remain zero for any candidate admitted to a local archive.
7. Complete the 2×2 target scheduler × mutation-source factorial, including the previously missing uniform-target/global-mutation cell. Compare all four cells per seed and by paired cluster contrasts.

## Advancement rule

Only if the mechanism gates pass and the class-conditional development metrics show a consistent improvement should a new, independently seeded Train-only challenge be generated and locked before the next diagnostic. This development report is not confirmatory evidence and does not authorize Validation/Test access.


## R2.1 factorial completion

The initial R2 experiment tested three of four combinations of target scheduler (performance deficit / uniform) and counterexample mutation source (exact target cluster / global stratified). R2.1 adds the missing uniform-target + global-stratified-mutation cell. Local parent-pair selection, archive capacity, population, generations, search budget, initial pools, and global survivor selection remain unchanged. This is a development-only completion on the previously inspected diagnostic role; it cannot support confirmatory claims. The next fresh challenge must be generated and locked before a one-shot independent diagnostic.


## R3 permission-prefix rollback reachability correction

The R2.1 diagnostic exposed a mismatch between the robust R3 label and semantic repair: permission-state ROLLBACK was being rewritten to ESCALATE even when the public compensation stack contained a committed prefix. This made the required zero-residual path unreachable to evolution. The repair rule is conditional: preserve ROLLBACK only for `OBS_PERMISSION` with `stack=True`; the independent contract validator must accept exactly this guarded case and reject permission-state ROLLBACK when `stack=False`. After rollback, retain PERMISSION as the current blocking observation, so the empty-stack permission rule forces explicit escalation. Other permission-state actions remain fail-closed. A simulator integration test must prove the trace `PERMISSION(stack=True) → ROLLBACK → PERMISSION(stack=False) → ESCALATE` yields R3 success, zero active effects, and zero avoidable harm before any new development run is interpreted.
