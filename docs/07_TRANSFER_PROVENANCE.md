# Research transfer provenance

**Transfer date:** 2026-11-11  
**New active repository:** `yujian777555/new_kaiti`  
**Historical source repository:** `yujian777555/kaitibaogao`  
**Source branch:** `pilot-a-stateful-recovery`  
**Pinned source HEAD:** `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`

## Transfer rule

This is a source-preserving snapshot of the Paper 1 research state. Historical reports, raw manifests, controller/simulator modules and tests were copied without rewriting their source contents. New research decisions, code changes, experiments, results, and handoffs must be made only in `new_kaiti`.

The old repository remains unchanged and is retained only for historical provenance. This transfer does not delete, rewrite, or merge the old repository.

## Transferred research documents

| New path | Historical source path |
|---|---|
| `docs/01_PAPER1_BASELINE_AND_METHOD_CANDIDATE.md` | `82_PAPER1_BASELINE_AND_METHOD_CANDIDATE.md` |
| `docs/02_EVOTOOL_REPRODUCTION_AUDIT.md` | `83_EVOTOOL_REPRODUCTION_AUDIT.md` |
| `docs/03_MODULE_LEVEL_COMPARISON_AND_FSPAE_HYPOTHESIS.md` | `84_MODULE_LEVEL_COMPARISON_AND_FSPAE_HYPOTHESIS.md` |
| `docs/04_D079_MANIFEST_AUDIT_AND_CLUSTER_FIX.md` | `81_D079_MANIFEST_AUDIT_AND_CLUSTER_FIX.md` |
| `docs/05_D078_EXPLORATORY_PILOT.md` | `79_D078_TRAIN_VALIDATION_EXPLORATORY_PILOT.md` |
| `docs/06_D079_DIAGNOSTIC_PREREGISTRATION.md` | `80_D079_DIAGNOSTIC_AND_CHALLENGE_PREREGISTRATION.md` |

## Transferred implementation subset

- D-079 v2 challenge generator and immutable Train-only manifest lock.
- A-3B stateful controller, verdict/reachability logic, typed task semantics, simulator and split guards.
- SBCG-NSGA-III implementation, runner, experiment wrapper, EA utilities and genome contract validator.
- D-079 diagnostics, formal scenario generator and selected regression tests.
- D-078 exploratory report, D-079 v2 challenge manifest and independent audit outputs.

The source tree may contain additional files not yet transferred. Do not assume this subset is a complete copy of the old repository.

## Integrity and execution caveat

For each copied source file, the Git blob SHA is preserved when the file content is unchanged. The D-079 v2 manifest retains canonical SHA-256 `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`.

The transferred subset passed the new-repository GitHub Actions regression: run [42965838729](https://github.com/yujian777555/new_kaiti/actions/runs/42965838729), 95 passed and 1 skipped. The skip is the D-078 raw matrix reconstruction test because the 10,285,231-byte source artifact was not transferred. The D-079 generator/committed-lock regression passed. This validates the selected copied test subset, not algorithmic performance or the entire historical repository.

## Important historical evidence

- D-078: 42 exploratory runs across 14 arms and 3 seeds; no established EC uplift.
- D-079 v2: 288 Train-only scenarios, 48 family × fault-stratum clusters, 6 scenarios per cluster (3 search + 3 diagnostic), all R1–R4 classes present, no Validation/Test payload or outcome access in the diagnostic generation/audit.
- D-079 v2 lock: `experiments/pilot_a3b/d079_manifest_lock.json`.
- Lock CI on the source repository: workflow run [42953293607](https://github.com/yujian777555/kaitibaogao/actions/runs/42953293607).
- D-079 lock freezes a Train-only manifest; it does not authorize optimizer execution or held-out Test access.


## Large raw artifact not transferred

The D-078 `matrix_results.json` is 10,285,231 bytes. The connected GitHub file reader returned no file content for this large blob, so it was deliberately **not** replaced with an empty file in the new repository. Its original source blob SHA is `19aba8cc02a5a10e7e60766ce7c3423e370c51b4`. The human-readable D-078 report and D-079 post-hoc audit reports were transferred. The corresponding reconstruction test is marked skipped when the raw artifact is absent; restore the exact original blob before treating that test as passed.
