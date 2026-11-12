# Paper narrative audit — 2026-11-11

## Scope

No complete manuscript draft (.tex, .docx, or paper-ready section set) is currently present in this repository. This audit reviews the existing paper-planning and experiment-facing prose in docs/01, docs/03, docs/05, docs/06, docs/11, docs/12, and the current D-079 v2 CI artifact. The quoted governance statements remain useful in internal audit documents; they should not be copied verbatim into the manuscript.

The publication principle means leading with the strongest verified contribution and stating scope precisely. It does not permit changing metric definitions, omitting a preregistered failure class, or turning exploratory results into confirmatory evidence.

## Phrase-by-phrase defensive-writing audit

| Existing wording / location | Diagnosis | Manuscript-ready replacement or action |
|---|---|---|
| docs/01: "research candidate only; novelty and empirical uplift are not approved" | Internal project status, not paper prose. It opens by disqualifying the work. | "We study evolutionary synthesis of reusable recovery controllers for stateful tool-using agents under partial commits and hard effect constraints." |
| docs/01: "Do NOT claim that this is the first..." | Defensive author instruction. | Omit from manuscript. State the bounded gap positively: "We focus on task-family/fault-composition-aware controller search under zero-tolerance effect constraints." |
| docs/01: "This claim remains provisional..." | Self-undermining when copied into an introduction. | "Prior methods optimize general tool-use modules or runtime recovery decisions; this study examines evolutionary search over reusable recovery controllers indexed by task and fault composition." Support with mechanism-level comparisons; avoid unsupported "first" claims. |
| docs/01: "Candidate method — not yet validated" | Design-document status label. | In Methods, use present tense: "FSPAE maintains bounded feasible Pareto archives for each task-family × fault-stratum cell..." Put performance evidence in Results. |
| docs/01: "Novelty remains provisional..." | Internal literature-audit reminder. | Omit from manuscript. Explain concrete differences from GEPA, EvoTool, and quality-diversity methods with citations and a comparison table. |
| docs/01: "If not, revise or reject the method" | Internal stop rule. | Omit from manuscript; retain as a research decision gate. |
| docs/03: "D-078 is a diagnostic, not a positive result" | Defensive framing and project-history language. | If D-078 is needed: "The pilot exposed a class-coverage gap: a controller with strong R1/R2 recovery can still fail to escalate correctly on R3 permission faults." Cite per-class counts. Otherwise omit D-078. |
| docs/03: "The result motivates a new hypothesis; it does not prove that..." | Meta-commentary about what evidence cannot prove. | "This motivates testing whether fault-stratum-specific archives and target-aware parent selection improve class-conditional recovery while preserving hard safety." |
| docs/03: "Why this is not merely GEPA or MAP-Elites" | Negative positioning ("not merely") is defensive. | Rename "Mechanism-level distinction from GEPA and MAP-Elites"; state positive differences: tool-contract descriptors, recoverability-aware class objectives, and zero-tolerance effect feasibility. |
| docs/03: "Novelty remains provisional until..." | Internal gate. | Omit from manuscript; retain a complete related-work comparison and a narrowly scoped contribution claim. |
| docs/03: "Stop conditions" / "Do not write a positive algorithmic conclusion..." | Internal decision policy. | Keep in the experiment protocol. The paper reports the frozen primary endpoint and estimates without author-side verdict language. |
| docs/05: "cannot support an unbiased generalization or paper-effect claim" | Accurate internal boundary, defensive if copied to the paper. | "D-078 is used for mechanism discovery; generalization is evaluated on a separately locked task-family/fault-composition shift split." |
| docs/06: "no new optimizer run is authorized..." | Authorization status, not scientific content. | Omit from manuscript. Describe locked dataset construction and search/evaluation separation in Experimental Setup. |
| docs/06: "do not issue confirmatory p-values or claim a paper-level effect" | Internal statistical guardrail. | "We report cluster-paired descriptive intervals for the Train-only mechanism study; confirmatory inference is reserved for the independently locked evaluation." |
| docs/11: "T1 is ... not an algorithmic improvement" | Correct engineering status, not manuscript prose. | If T1 is discussed: "T1 separates tool execution, business outcome, and state effect while preserving the legacy observation and reward, enabling outcome-aware analysis." Do not list T1 as an algorithmic contribution unless studied as one. |
| docs/11: "Do not implement this yet" / "T2 is blocked..." | Workflow instructions. | Omit from manuscript. Describe reward shaping only after its label ontology and validity study are complete. |
| docs/12: "These are implementation/conformance checks only. They are not policy performance results..." | Repeated caveat. | "We verify the treatment adapter against pinned official tool and reward semantics before comparing policies, isolating algorithmic effects from adapter discrepancies." |
| docs/12: "No algorithmic uplift is claimed..." | Internal status. | Omit from manuscript. Report policy-performance results using the preregistered endpoints. |
| D-079 v2 artifact: "Exploratory mechanism diagnostic; not confirmatory" | Necessary experiment classification, but not abstract prose. | "D-079 is a Train-only mechanism-discovery protocol with disjoint search and diagnostic parameter-seed replicates across 48 task-family × fault-stratum clusters." |
| D-079 v2 artifact: "No confirmatory p-values are reported" | Defensive as a standalone Results sentence. | Report descriptive cluster-paired estimates and intervals; reserve confirmatory claims for the locked external evaluation. |
| D-079 v2 artifact: "No result here alone supports a paper-level uplift claim" | Internal conclusion, not manuscript prose. | Omit from abstract/conclusion. Make no positive performance claim until the confirmatory endpoint supports it. |

## D-079 v2 evidence that constrains the narrative

The current CI artifact is the v2 artifact with manifest SHA-256 \`09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca\`. The older repository report with manifest SHA \`cafdc52e...\` is a different diagnostic and must not be merged into the v2 result table.

| Method | Macro class success | R1/R2 CondRec | R3 correct escalation | R4 damage containment | Avoidable harm | Hard safety |
|---|---:|---:|---:|---:|---:|---|
| Matched NSGA-III | 0.1910 | 0.2396 | 0.0000 | 0.3333 | 0.7569 | PASS |
| SBCG-NSGA-III | 0.1944 | 0.2500 | 0.0000 | 0.3333 | 0.6875 | PASS |
| FSPAE | 0.0556 | 0.1667 | 0.0000 | 0.0000 | 0.6458 | PASS |
| FSPAE-Uniform | 0.0625 | 0.1875 | 0.0000 | 0.0000 | 0.6389 | PASS |
| Hand FSM | 0.2604 | 0.7812 | 0.0000 | 0.0000 | 0.4375 | FAIL |
| Rule-based | 0.2604 | 0.7812 | 0.0000 | 0.0000 | 0.4375 | FAIL |
| Reflection proxy | 0.1771 | 0.5312 | 0.0000 | 0.0000 | 1.0417 | FAIL |

The defensible scientific statement is that this synthetic domain exposes a separation between R1/R2 recovery and R3/R4 handling, while the hard-feasibility gate distinguishes admissible evolutionary controllers from fixed baselines. It does not establish FSPAE uplift. The paired descriptive class-success difference is FSPAE−SBCG = −0.1111 (95% cluster-bootstrap interval [−0.1597, −0.0694]) and FSPAE−matched NSGA-III = −0.1042 ([−0.1458, −0.0625]).

## Mechanism diagnosis for the next algorithm revision

Code review of \`experiments/pilot_a3b/fspae_runner.py\` identifies a testable design issue:

1. Every candidate is evaluated on all 144 Train/search scenarios, so all 48 strata receive the same candidate-evaluation exposure.
2. The scheduler calls \`1 - archive_size/capacity\` a coverage deficit. Archive cardinality is the number of retained non-dominated candidates, not the number of evaluations or search exposure. A small archive can indicate dominance, not missing coverage.
3. The target stratum affects parent A, but parent B is selected globally and counterexample mutation is aggregated across all strata. The target label therefore does not directly condition the mutation operator.
4. In the v2 artifact, deficit mode selected 19–22 distinct clusters per seed (40 target selections), while uniform mode selected 26–29. This is descriptive evidence that the current deficit score concentrates parent sourcing more narrowly than uniform sampling.

The next algorithmic hypothesis is **target-conditioned variation**: select a target stratum using a calibrated performance deficit, select a parent from that stratum's archive, and choose the counterexample/mutation locus from the same stratum. Keep global survivor selection and all hard safety constraints fixed. First verify the target-to-mutation dataflow with unit tests and a Train/search-only mechanism test; do not reuse the already inspected diagnostic role as confirmatory evidence.

## Recommended paper narrative

**Problem:** stateful agents encounter ambiguous tool outcomes and partial commits, where a successful tool return can still represent a rejected business operation or an unsafe state transition.

**Gap:** existing evolutionary tool-use methods and recovery runtimes do not directly test whether task-family/fault-composition-conditioned search can discover reusable recovery controllers under hard effect constraints.

**Method:** evolve typed recovery FSMs with target-conditioned counterexample variation and feasible Pareto selection over class-relevant objectives.

**Evaluation responsibility:** (1) adapter conformance isolates measurement correctness; (2) Train-only mechanism study tests target-conditioned search; (3) locked task-family/fault-composition shift evaluation tests generalization; (4) external benchmark tests transfer after semantic and license audit.

**Claim discipline:** the abstract and conclusion may state only the strongest result that survives the locked confirmatory evaluation. No performance advantage is asserted from the current D-079 v2 artifact.
