# FSPAE-R3 global-anchor / local-block development protocol

Protocol ID: D-079-R3-BLOCK-DEV
Scope: Train/search optimization with the previously inspected D-079 Train/diagnostic role reused only for development feedback.

## Motivation

R2.3 showed that local-pair evolution is not preserving multi-stratum behavior reliably. D-079 diagnostic results expose concentrated failures on D1 timeout recovery and D4 three-fault interactions. A local specialist can contain useful genes for its target cluster, but whole-genome crossover can overwrite unrelated recovery rules when two local specialists are recombined.

## Hypothesis

A global-population anchor combined with target-cluster gene-block inheritance will reduce cross-stratum forgetting. The global parent supplies the whole controller; a local Pareto donor contributes only genes observed in counterexamples from the selected family × fault-stratum cluster. Counterexample-guided mutation is then restricted to that same cluster. Global NSGA-III survivor selection and zero-tolerance hard safety constraints remain unchanged.

## Algorithm

1. Select a target cluster from clusters with observed counterexamples (uniform selection for this pilot).
2. Select a global parent by the existing NSGA-III population tournament.
3. Select a local donor from the target cluster's bounded Pareto archive using its NSGA-III niche counts.
4. Collect the union of decision-state gene keys implicated by the target cluster's counterexamples.
5. Clone the global parent and copy only those keys from the local donor.
6. Apply the existing exact-cluster counterexample mutation.
7. Record block membership, copied keys, global-anchor source, local-donor source, and whether non-target genes were preserved.
8. Use unchanged global NSGA-III environmental selection and hard constraints.

## Required mechanism gates

- Every offspring has a global-population anchor.
- The block-copy operation preserves every non-target gene exactly.
- When a target counterexample mutation occurs, its gene key belongs to the target block.
- Cross-target counterexample mutation count is zero.
- Missing target counterexamples trigger an explicit fallback and are counted.
- Evaluation budget and hard-safety constraints remain unchanged.

## Comparators and endpoints

Compare FSPAE-R3-Block with matched NSGA-III, SBCG-NSGA-III, FSPAE-R1, and FSPAE-R2 using the same D-079 manifest, seeds, initial pools, and episode budget. Report per-seed and paired cluster differences for class success, avoidable harm, hard-safety violations, and decision count. Also report the block-copy audit.

## Interpretation limits

D-079 diagnostic was already inspected in prior experiments. This is a mechanism-development experiment only; it is not held-out or confirmatory evidence. D-079 hand policy now reaches 100% class success and zero avoidable harm/hard-safety violations, so this benchmark is a safety and mechanism regression suite, not a valid basis for claiming a general algorithmic improvement. A promising R3 result must be tested on a newly generated, independently locked challenge before any Validation/Test access.


## Advancement decision after R2.3 / R3-Block

R3-Block mechanism gates passed: the development run recorded 120/120 global anchors, 120/120 block-copy operations preserving non-target genes, 120/120 in-block targeted mutations, and 432 copied genes. Performance gate failed: macro class success was 0.4167 versus matched NSGA-III 0.5810; R4 containment was 0.3333 versus 1.0000; mean decisions were 7.236 versus 4.37. It improved over FSPAE-R2 but did not beat the matched baseline. Do not advance R3-Block to fresh validation or add further D-079 ablations. Freeze D-079 as a regression suite and move to D-080 design.
