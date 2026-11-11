# D-079 independent diagnostics of D-078

- Scope: D-078 disclosed Validation rows only; no Test scenarios or outcomes are reconstructed.
- Robust labels are reconstructed from the four disclosed Validation families.
- Corrected harm excludes intended active effects after successful completion; duplicates remain harmful.

- Runs: 42 across 14 arms and 3 seeds.
- Validation scenarios: 108 across 4 families.
- Robust/analytic label disagreements: 0.
- Selected FSMs exactly equal to Hand FSM: 32/42.
- Runs whose Validation Pareto front contains Hand FSM: 33/42.

## Per-arm results

| Arm | Hand selected / runs | Hand in Pareto / runs | Unique selected FSMs | Corrected avoidable harm / scenario | Duplicate rate | SLA violation rate |
|---|---:|---:|---:|---:|---:|---:|
| A | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| AB | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| Hand FSM | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| Matched-objective NSGA-II | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| Matched-objective NSGA-III | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| NSGA-II | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| NSGA-III | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| Random | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| Reflection | 0/3 | 0/3 | 0 | n/a | n/a | n/a |
| Rule-based | 0/3 | 0/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| SBCG-NSGA-III | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| SBCG-NSGA-III-no-M1 | 2/3 | 3/3 | 2 | 0.1111 | 0.0000 | 0.0000 |
| SBCG-NSGA-III-no-M2 | 3/3 | 3/3 | 1 | 0.1111 | 0.0000 | 0.0000 |
| SBCG-NSGA-III-no-M3 | 0/3 | 0/3 | 3 | 0.4352 | 0.0000 | 0.0000 |

## Hand FSM class-conditional diagnostics

- R1/R2 CondRecSucc: 1.0000 over 252 scenarios.
- R3 CorrectEscalation: 0.0000 over 36 scenarios.
- R4 DamageContainment: 1.0000 over 36 scenarios.

## Interpretation limits

- Exact Hand selections are selection outcomes, not proof that all optimizers converged to the Hand genome.
- Validation is used for candidate selection in D-078; its metrics remain selection-biased.
- Corrected harm is a post-hoc re-score of stored fields, not a rerun.
- This audit does not establish EC uplift, formal A-3b readiness, or generalization to locked Test.
