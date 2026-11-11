# D-079 locked Train-only algorithm diagnostic

- Exploratory mechanism diagnostic; not confirmatory and not formal A-3b.
- Manifest content SHA-256: `cafdc52e037c08ca8cd95c0546014bab6dd27e9bd6d28122afb90f28b3cd1efa`
- Manifest file SHA-256: `0072550d432d306d4c02912bebaaa4a4756edb33a68c962cf59e9fb198d6c152`
- Scenario ID SHA-256: `4d7b19605155bdbfde61216ecfda6019f09d78a76fa7162fd16c18496114ec99`
- Robust label source: observation-based-AND-OR-robust-reachability
- Runs: 42; search/diagnostic scenarios: 144/144
- Validation/Test/LLM/A800: not used.

| Algorithm | Runs | Search episodes | Diagnostic episodes | CondRec | R3 correct | R4 containment | Avoidable harm | Action cost | Constraint violation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3 | 6912.0 | 1152.0 | 0.0781 | 0.0000 | 0.0000 | 0.6354 | 9.1250 | 0.0000 |
| AB | 3 | 6384.0 | 1152.0 | 0.0938 | 0.0000 | 1.0000 | 0.3125 | 5.5521 | 0.0000 |
| Hand FSM | 3 | 0.0 | 144.0 | 0.7812 | 0.0000 | 0.0000 | 0.4375 | 3.4688 | 0.1458 |
| Matched-objective NSGA-II | 3 | 6912.0 | 1152.0 | 0.2396 | 0.0000 | 0.3333 | 0.7569 | 9.3160 | 0.0000 |
| Matched-objective NSGA-III | 3 | 6912.0 | 1152.0 | 0.2396 | 0.0000 | 0.3333 | 0.7569 | 9.3160 | 0.0000 |
| NSGA-II | 3 | 6912.0 | 1152.0 | NA | NA | NA | NA | NA | NA |
| NSGA-III | 3 | 6912.0 | 1152.0 | NA | NA | NA | NA | NA | NA |
| Random | 3 | 6912.0 | 1152.0 | NA | NA | NA | NA | NA | NA |
| Reflection | 3 | 0.0 | 144.0 | 0.5312 | 0.0000 | 0.0000 | 1.0417 | 4.0312 | 0.8125 |
| Rule-based | 3 | 0.0 | 144.0 | 0.7812 | 0.0000 | 0.0000 | 0.4375 | 3.4688 | 0.1458 |
| SBCG-NSGA-III | 3 | 6576.0 | 912.0 | 0.2292 | 0.0000 | 0.6667 | 0.3472 | 3.7083 | 0.0000 |
| SBCG-NSGA-III-no-M1 | 3 | 6720.0 | 576.0 | 0.4896 | 0.0000 | 0.6667 | 0.4444 | 6.8299 | 0.0000 |
| SBCG-NSGA-III-no-M2 | 3 | 6912.0 | 1104.0 | 0.3854 | 0.0000 | 0.0000 | 0.7014 | 9.9583 | 0.0000 |
| SBCG-NSGA-III-no-M3 | 3 | 6576.0 | 1152.0 | 0.2500 | 0.0000 | 0.3333 | 0.6875 | 13.7222 | 0.0000 |

## Paired exploratory contrasts

Seed-paired differences with 10,000 bootstrap draws are descriptive only; no confirmatory p-values are issued.

| Contrast | Metric | Mean difference | 95% exploratory bootstrap CI | N seeds |
|---|---|---:|---|---:|
| SBCG_minus_Hand|cond_rec | cond_rec | -0.552083 | [-0.781250, -0.312500] | 3 |
| SBCG_minus_Hand|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_Hand|damage_containment | damage_containment | 0.666667 | [0.000000, 1.000000] | 3 |
| SBCG_minus_Hand|avoidable_harm | avoidable_harm | -0.090278 | [-0.250000, 0.083333] | 3 |
| SBCG_minus_Hand|action_cost | action_cost | 0.239583 | [0.031250, 0.531250] | 3 |
| SBCG_minus_Hand|recovery_cost | recovery_cost | 0.333333 | [0.000000, 0.500000] | 3 |
| SBCG_minus_Hand|constraint_violation | constraint_violation | -0.145833 | [-0.145833, -0.145833] | 3 |
| SBCG_minus_Rule|cond_rec | cond_rec | -0.552083 | [-0.781250, -0.312500] | 3 |
| SBCG_minus_Rule|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_Rule|damage_containment | damage_containment | 0.666667 | [0.000000, 1.000000] | 3 |
| SBCG_minus_Rule|avoidable_harm | avoidable_harm | -0.090278 | [-0.250000, 0.083333] | 3 |
| SBCG_minus_Rule|action_cost | action_cost | 0.239583 | [0.031250, 0.531250] | 3 |
| SBCG_minus_Rule|recovery_cost | recovery_cost | 0.333333 | [0.000000, 0.500000] | 3 |
| SBCG_minus_Rule|constraint_violation | constraint_violation | -0.145833 | [-0.145833, -0.145833] | 3 |
| SBCG_minus_Reflection|cond_rec | cond_rec | -0.302083 | [-0.531250, -0.062500] | 3 |
| SBCG_minus_Reflection|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_Reflection|damage_containment | damage_containment | 0.666667 | [0.000000, 1.000000] | 3 |
| SBCG_minus_Reflection|avoidable_harm | avoidable_harm | -0.694444 | [-0.854167, -0.520833] | 3 |
| SBCG_minus_Reflection|action_cost | action_cost | -0.322917 | [-0.531250, -0.031250] | 3 |
| SBCG_minus_Reflection|recovery_cost | recovery_cost | 0.333333 | [0.000000, 0.500000] | 3 |
| SBCG_minus_Reflection|constraint_violation | constraint_violation | -0.812500 | [-0.812500, -0.812500] | 3 |
| SBCG_minus_matched_NSGAII|cond_rec | cond_rec | -0.010417 | [-0.187500, 0.156250] | 3 |
| SBCG_minus_matched_NSGAII|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_matched_NSGAII|damage_containment | damage_containment | 0.333333 | [0.000000, 1.000000] | 3 |
| SBCG_minus_matched_NSGAII|avoidable_harm | avoidable_harm | -0.409722 | [-0.583333, -0.312500] | 3 |
| SBCG_minus_matched_NSGAII|action_cost | action_cost | -5.607639 | [-7.875000, -2.718750] | 3 |
| SBCG_minus_matched_NSGAII|recovery_cost | recovery_cost | -7.166667 | [-11.000000, 0.000000] | 3 |
| SBCG_minus_matched_NSGAII|constraint_violation | constraint_violation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_matched_NSGAIII|cond_rec | cond_rec | -0.010417 | [-0.187500, 0.156250] | 3 |
| SBCG_minus_matched_NSGAIII|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_matched_NSGAIII|damage_containment | damage_containment | 0.333333 | [0.000000, 1.000000] | 3 |
| SBCG_minus_matched_NSGAIII|avoidable_harm | avoidable_harm | -0.409722 | [-0.583333, -0.312500] | 3 |
| SBCG_minus_matched_NSGAIII|action_cost | action_cost | -5.607639 | [-7.875000, -2.718750] | 3 |
| SBCG_minus_matched_NSGAIII|recovery_cost | recovery_cost | -7.166667 | [-11.000000, 0.000000] | 3 |
| SBCG_minus_matched_NSGAIII|constraint_violation | constraint_violation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM1|cond_rec | cond_rec | -0.260417 | [-0.531250, -0.093750] | 3 |
| SBCG_minus_noM1|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM1|damage_containment | damage_containment | 0.000000 | [-1.000000, 1.000000] | 3 |
| SBCG_minus_noM1|avoidable_harm | avoidable_harm | -0.097222 | [-0.604167, 0.166667] | 3 |
| SBCG_minus_noM1|action_cost | action_cost | -3.121528 | [-9.125000, 1.093750] | 3 |
| SBCG_minus_noM1|recovery_cost | recovery_cost | -0.666667 | [-1.500000, 0.000000] | 3 |
| SBCG_minus_noM1|constraint_violation | constraint_violation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM2|cond_rec | cond_rec | -0.156250 | [-0.437500, 0.000000] | 3 |
| SBCG_minus_noM2|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM2|damage_containment | damage_containment | 0.666667 | [0.000000, 1.000000] | 3 |
| SBCG_minus_noM2|avoidable_harm | avoidable_harm | -0.354167 | [-0.458333, -0.166667] | 3 |
| SBCG_minus_noM2|action_cost | action_cost | -6.250000 | [-9.218750, -2.562500] | 3 |
| SBCG_minus_noM2|recovery_cost | recovery_cost | 0.500000 | [0.000000, 1.000000] | 3 |
| SBCG_minus_noM2|constraint_violation | constraint_violation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM3|cond_rec | cond_rec | -0.020833 | [-0.343750, 0.468750] | 3 |
| SBCG_minus_noM3|correct_escalation | correct_escalation | 0.000000 | [0.000000, 0.000000] | 3 |
| SBCG_minus_noM3|damage_containment | damage_containment | 0.333333 | [0.000000, 1.000000] | 3 |
| SBCG_minus_noM3|avoidable_harm | avoidable_harm | -0.340278 | [-0.520833, -0.187500] | 3 |
| SBCG_minus_noM3|action_cost | action_cost | -10.013889 | [-17.750000, -3.468750] | 3 |
| SBCG_minus_noM3|recovery_cost | recovery_cost | -7.333333 | [-11.000000, -0.500000] | 3 |
| SBCG_minus_noM3|constraint_violation | constraint_violation | 0.000000 | [0.000000, 0.000000] | 3 |

These results do not establish EC uplift, Hand superiority, formal A-3b readiness, or Test generalization.

