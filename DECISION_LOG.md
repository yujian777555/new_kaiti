# Decision log

## 2026-11-11 — D-001: Establish new active repository

- Decision: `yujian777555/new_kaiti` is the sole active repository for Paper 1.
- The previous `kaitibaogao` repository is historical/read-only for this project; no new commits should be made there.
- A source-preserving snapshot of key documents, manifest, code and exploratory evidence is transferred from source HEAD `33672562ebaeb6c6a533e7e0fd975cbac045b5e3`.
- Do not mix with the user's other Agent/EC repositories.

## 2026-11-11 — D-002: Keep the research question narrow

- Research object: evolutionary optimization of reusable recovery controllers for stateful tool-using LLM Agents.
- Primary evolutionary baseline candidate: EvoTool (ACL 2026).
- GEPA is a selection/reflection comparator; DART and Evidence-Guided Recovery are recovery-domain comparators.
- Proposed method hypothesis: FSPAE, a fault-stratified Pareto archive with coverage-deficit parent selection and zero-tolerance hard safety constraints.
- FSPAE is a hypothesis, not a validated contribution.

## 2026-11-11 — D-003: Preserve negative and exploratory evidence

- D-078 is exploratory and does not establish algorithmic uplift.
- D-079 v2 is a Train-only mechanism-discovery diagnostic; its frozen hash is `09df6babbb6e3222ea57a7f354654636ac2437b7011dbe3f1ac738df894a0bca`.
- The D-079 lock is not execution authorization and does not permit Validation/Test access.
- No paper claim of superiority is allowed until matched-budget comparisons and an independently locked held-out evaluation support it.

## 2026-11-11 — D-004: Baseline reproduction before method claims

- Reproduce EvoTool on a tractable official stateful benchmark slice before adaptation.
- Paper Appendix A.6 configuration says G=8 and B=3; the released code default derives 90 generations. The reproduction must explicitly set and verify G=8, B=3.
- Model weights remain frozen; no foundation-model training is required for the baseline.
