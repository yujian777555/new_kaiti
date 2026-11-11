# D-078 — Exploratory Train/Validation pilot protocol

**Status:** Authorized by the user's 2026-11-10 instruction to repair and proceed to experiments.  
**Type:** Exploratory, non-confirmatory development pilot.  
**Historical source:** yujian777555/kaitibaogao, branch pilot-a-stateful-recovery. Active workspace: yujian777555/new_kaiti.

## 1. Purpose

Quickly determine whether the corrected SBCG mechanisms show a promising selection signal against strong evolutionary and non-evolutionary controls before seeking formal advisor MDE approval and final Test authorization.

This pilot is not the formal A-3b confirmatory experiment and cannot support an unbiased generalization or paper-effect claim.

## 2. Data and isolation

- Generate the A-3b synthetic scenario candidate with the existing formal scenario generator.
- Evolution fitness receives **Train only** (expected 8 families × 9 compositions × 3 repeats = 216 scenarios).
- Candidate selection receives **Validation only** (expected 4 families × 9 compositions × 3 repeats = 108 scenarios).
- The optimizer, mutation pool, fitness cache, and generation loop never receive Validation rows.
- Validation is evaluated once after each arm/seed search; no Validation feedback is returned to Train.
- No Test scenario or outcome is passed to an optimizer or evaluator. The generator transiently constructs the locked split for catalog/hash validation, but this pilot only retrieves Train and Validation through the split guard.

## 3. Registered arms

All 14 registered arms are run:

1. Hand FSM
2. Random
3. Rule-based
4. Reflection (deterministic non-LLM proxy)
5. NSGA-II
6. Canonical NSGA-III
7. Matched-objective NSGA-II
8. Matched-objective NSGA-III
9. A
10. AB
11. SBCG-NSGA-III
12. SBCG no-M1
13. SBCG no-M2
14. SBCG no-M3

## 4. Pilot configuration

- Seeds: 411, 522, 633
- Shared initial pool: 60 candidates per seed
- Population: 8
- Generations: 5
- Train episode budget per evolutionary arm: 8 × (5 + 1) × 216 = 10,368
- Fixed-policy arms are evaluated on Validation only.
- Each evolutionary arm performs Train-only search, then a separate Validation candidate evaluation and selection.
- Hard safety constraints remain zero-tolerance and are not traded against objective values.
- Every offspring evaluation record is reused during environmental selection; no second cache lookup is counted.

## 5. Readouts and interpretation

Record per arm/seed:
- Train episodes, unique evaluations, cache hits, evaluation calls;
- Validation candidate count and selected candidate;
- CondRecSucc, AvoidableHarm, UnnecessaryActionCost, CorrectEscalation, DamageContainment;
- duplicate, SLA, and invariant violations;
- mutation-stratum, repair, and new-valid-individual audit where applicable.

Validation metrics are used for candidate selection and are therefore selection-biased. Report them descriptively only. Do not attach confirmatory p-values, claim a statistically established improvement, or treat the selected Validation score as an unbiased estimate of generalization.

A promising result advances to a separately reviewed protocol and requires advisor agreement on MDE, independent review, and explicit authorization before any Test access.

## 6. Stop conditions

Stop the run if:
- the manifest/catalog gate fails;
- Train/Validation split validation fails;
- any Test split enters the runner;
- hard-constraint or evaluator errors invalidate an arm;
- the configured episode budget is exceeded;
- the result cannot be serialized with complete provenance.

No LLM API, A800/ARWM training, Pilot B, UndoBench TEST, ThinkingBox, or final Test evaluation is part of this pilot.


## Repository transfer note

Transferred on 2026-11-11 from `yujian777555/kaitibaogao` branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. This is a historical protocol/evidence snapshot; all future revisions belong in `yujian777555/new_kaiti`.
