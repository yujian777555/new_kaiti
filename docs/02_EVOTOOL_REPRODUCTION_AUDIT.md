# EvoTool Baseline Reproduction Audit

**Date:** 2026-11-11  
**Purpose:** implement the baseline-reproduction stage of the paper workflow.  
**Primary source:** EvoTool, ACL 2026 Long Paper.

## 1. Source identity

- Paper: https://aclanthology.org/2026.acl-long.2016/
- Official code: https://github.com/SYang2000/ACL_2026_EvoTool
- Code branch: `main`
- Source HEAD checked: `6a82719ea6e22cf23f963078e2527094e50b47f6`
- License: MIT (official repository).

## 2. Source-code decomposition

| Component | Source | Actual responsibility | Comparison target |
|---|---|---|---|
| Policy representation | `src/policy/modules.py`, `src/policy/agent.py` | Four fixed-interface prompt modules: Planner, Selector, Caller, Synthesizer | Prompt-module genotype vs executable recovery-FSM genotype |
| Trajectory diagnostics | `src/evolve/diagnostics.py` | Extract advisory module events from trajectory and gold references | Rule-event coverage and failure-class attribution |
| Blamer | `src/evolve/blame.py` | LLM reads full representative episode and assigns one blamed module; rule blame is parse-failure fallback | Single-module credit assignment vs typed counterexample attribution |
| Mutator | `src/evolve/mutate.py` | LLM edits exactly one blamed module using optional trajectory evidence and critique | Natural-language prompt mutation vs contract-preserving typed FSM operators |
| Population selection | `src/evolve/select.py` | Instance-wise winner retention on `S_sel`; parent weights proportional to win frequency | Winner-frequency diversity vs class-conditional Pareto selection |
| Evolution loop | `src/evolve/loop.py` | Sample parent, execute mini-batch, select representative episode, blame, mutate, accept if child beats parent, then select on `S_sel` | Same-budget matched search and acceptance controls |
| Environment/evaluator | `src/env/`, `src/envs/`, `src/evaluators.py` | Offline tool executors and benchmark-specific scoring; tau-bench uses a stateful retail DB | State-transition, side-effect and recovery semantics |

EvoTool is not NSGA-II/III. It is gradient-free, LLM-guided, population-based policy evolution with localized mutation and instance-wise diversity retention.

## 3. Paper configuration versus released-code defaults

Paper Appendix A.6 reports GPT-4.1 and Qwen3-8B backbones, maximum generation budget `G=8`, and mini-batch size `B=3`.

The released `configs/base.yaml` defaults to `n_train=90`, `n_sel=30`, `n_test=30`, `batch_size=3`, and `epochs=3`, which derives 90 generations under `SPEC.md §8`. The README also describes the default as 90 generations. Therefore, **running the default config is not a faithful reproduction of the paper's stated G=8 budget**.

The code exposes `evolve.generations` as an explicit generation-budget override. The paper-faithful candidate command for the Qwen3-8B tau-bench slice is:

```bash
python run.py --config configs/evotool.yaml --benchmark taubench \
  --override evolve.generations=8 evolve.batch_size=3 llm.model_name=Qwen3-8B
```

Before calling this a reproduction, verify that exactly eight generations executed, the task splits are disjoint, the model and temperature match, and the evaluator is the official tau-bench database-state plus required-output check. The paper reports Qwen3-8B tau-bench Pass@1 of 25.8 average (Retail 35.9, Airline 15.7). A single tau-bench slice is a **partial reproduction**, not a full reproduction of the four-benchmark paper.

## 4. Reproduction sequence

1. Reproduce the Qwen3-8B tau-bench slice with `G=8, B=3` and the official split/configuration.
2. Compare with the published Qwen3-8B tau-bench values (35.9 Retail, 15.7 Airline, 25.8 average); record exact denominators, seeds, model revision, code SHA, and deviations.
3. If the first slice is within a preregistered tolerance, reproduce the remaining official benchmark slices before claiming full baseline reproduction.
4. Only then adapt EvoTool to the stateful recovery environment, keeping backbone, instances, per-instance action budget, and total evaluation budget matched.
5. Report the adapted EvoTool as a new comparison method, not as the official EvoTool result.

## 5. Current authorization boundary

No reproduction has been run. The current D-079 protocol does not authorize A800/ARWM, real LLM API, or formal optimizer execution. Do not launch vLLM, call a paid API, or access held-out Test until the user explicitly approves a separate baseline-reproduction preflight. Foundation-model weights remain frozen; no training is required for the baseline.

## 6. References

- Paper: https://aclanthology.org/2026.acl-long.2016/
- Official code: https://github.com/SYang2000/ACL_2026_EvoTool
- Implementation specification: https://github.com/SYang2000/ACL_2026_EvoTool/blob/main/SPEC.md


## Repository transfer note

This document is a research-state snapshot transferred on 2026-11-11 from `yujian777555/kaitibaogao` branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. Historical commit IDs and CI links are preserved for provenance; all subsequent edits belong in `yujian777555/new_kaiti`.
