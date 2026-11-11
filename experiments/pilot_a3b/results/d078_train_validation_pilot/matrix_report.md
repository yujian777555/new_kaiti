# SBCG 14-arm Train/Validation exploratory pilot

- Matrix version: sbcg-14-arm-train-validation-v1
- Status: EXECUTED_NO_TEST
- Seeds: [411, 522, 633]
- Arms: 14; runs: 42
- Train scenarios: 216
- Validation scenarios: 108
- Population / generations: 8 / 5
- Train episode budget per evolutionary arm: 10368

**Interpretation:** Validation is used for candidate selection. These selected Validation metrics are exploratory selection metrics, not an unbiased final generalization estimate. No Test payload or Test outcomes are used.

| Algorithm | Seed | Train episodes | Validation episodes | Pareto candidates | Selection | CondRecSucc | Avoidable harm | Action cost | Hard violations |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Hand FSM | 411 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Random | 411 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Rule-based | 411 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Reflection | 411 | 0 | 108 | 0 | HOLD | NA | NA | NA | 0.0000 |
| NSGA-II | 411 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| NSGA-III | 411 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-II | 411 | 10368 | 864 | 8 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-III | 411 | 10368 | 864 | 8 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| A | 411 | 10368 | 864 | 6 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| AB | 411 | 9720 | 864 | 6 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III | 411 | 10152 | 1080 | 9 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M1 | 411 | 9072 | 1404 | 13 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M2 | 411 | 10368 | 1188 | 10 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M3 | 411 | 10368 | 864 | 4 | SELECTED | 0.0000 | 0.5278 | 4.0000 | 0.0000 |
| Hand FSM | 522 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Random | 522 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Rule-based | 522 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Reflection | 522 | 0 | 108 | 0 | HOLD | NA | NA | NA | 0.0000 |
| NSGA-II | 522 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| NSGA-III | 522 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-II | 522 | 10368 | 864 | 7 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-III | 522 | 10368 | 864 | 6 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| A | 522 | 10368 | 864 | 4 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| AB | 522 | 9504 | 864 | 6 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III | 522 | 10368 | 1836 | 12 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M1 | 522 | 10368 | 1836 | 7 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M2 | 522 | 10368 | 1188 | 7 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M3 | 522 | 10152 | 864 | 7 | SELECTED | 0.0000 | 0.1944 | 3.7500 | 0.0000 |
| Hand FSM | 633 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Random | 633 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Rule-based | 633 | 0 | 108 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Reflection | 633 | 0 | 108 | 0 | HOLD | NA | NA | NA | 0.0000 |
| NSGA-II | 633 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| NSGA-III | 633 | 10368 | 864 | 1 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-II | 633 | 10368 | 864 | 7 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| Matched-objective NSGA-III | 633 | 10368 | 864 | 7 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| A | 633 | 10368 | 864 | 4 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| AB | 633 | 10368 | 864 | 5 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III | 633 | 10152 | 1188 | 10 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M1 | 633 | 9936 | 1512 | 9 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M2 | 633 | 10368 | 1080 | 9 | SELECTED | 1.0000 | 2.4444 | 4.3929 | 0.0000 |
| SBCG-NSGA-III-no-M3 | 633 | 10368 | 864 | 7 | SELECTED | 0.3929 | 1.5000 | 16.8214 | 0.0000 |

## Scope and limits

- This is a non-confirmatory development pilot on the generated synthetic A-3b Train/Validation simulator.
- Train is used for evolutionary fitness; Validation is used once after each arm's Train search to select a candidate.
- Validation metrics are subject to selection optimism and must not be presented as unbiased generalization performance.
- No Test scenarios are passed to the optimization or evaluation runners; no Test outcomes are read.
- Reflection is a deterministic proxy, not an LLM call.
- This run does not authorize formal A-3b, Test access, or a confirmatory paper claim.
