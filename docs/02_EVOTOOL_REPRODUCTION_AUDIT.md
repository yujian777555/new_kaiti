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

The code exposes `evolve.generations` as an explicit generation-budget override. The generation-budget override command (only after a split-preserving dataset and environment adapter are prepared) is:

```bash
python run.py --config configs/evotool.yaml --benchmark taubench \
  --override evolve.generations=8 evolve.batch_size=3 llm.model_name=Qwen3-8B
```

An eight-generation run alone does not make this a paper-faithful reproduction. The released demo builder mixes official task splits, and the released tau-bench adapter is not the full conversational benchmark. See `08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md`; do not run the 150-instance demo path or make paper-level claims from it. Before any baseline run, establish split-preserving inputs, reconcile the evaluator, and verify the exact generation count in the run log. The paper reports Qwen3-8B tau-bench Pass@1 of 25.8 average (Retail 35.9, Airline 15.7). A single tau-bench slice is a **partial reproduction**, not a full reproduction of the four-benchmark paper.

## 4. Reproduction sequence

1. Reproduce the Qwen3-8B tau-bench slice with `G=8, B=3` and the official split/configuration.
2. Compare with the published Qwen3-8B tau-bench values (35.9 Retail, 15.7 Airline, 25.8 average); record exact denominators, seeds, model revision, code SHA, and deviations.
3. If the first slice is within a preregistered tolerance, reproduce the remaining official benchmark slices before claiming full baseline reproduction.
4. Only then adapt EvoTool to the stateful recovery environment, keeping backbone, instances, per-instance action budget, and total evaluation budget matched.
5. Report the adapted EvoTool as a new comparison method, not as the official EvoTool result.

## 5. Current authorization boundary

No model reproduction has been run. The user has authorized reading and materializing official legacy Retail Train/Dev/Test task payloads for data preparation; this is complete and documented in `docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md`. That authorization does not cover held-out policy scoring, A800/vLLM, real LLM API calls, or optimizer execution. Obtain separate approval before any model inference or experiment. Foundation-model weights remain frozen; no training is required for the baseline.

## 6. References

- Paper: https://aclanthology.org/2026.acl-long.2016/
- Official code: https://github.com/SYang2000/ACL_2026_EvoTool
- Implementation specification: https://github.com/SYang2000/ACL_2026_EvoTool/blob/main/SPEC.md


## Repository transfer note

This document is a research-state snapshot transferred on 2026-11-11 from `yujian777555/kaitibaogao` branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`. Historical commit IDs and CI links are preserved for provenance; all subsequent edits belong in `yujian777555/new_kaiti`.


## 7. Critical preflight correction — 2026-11-11

The initial audit's generation-budget finding remains valid, but the proposed 150-instance tau-bench path is not suitable for a faithful reproduction. The builder takes tasks from Test before Train/Dev and the generic loader randomly repartitions the combined list. The released agent adapter also omits the official user-simulator/rules/wiki interaction. Full findings and the revised protocol are in `08_EVOTOOL_BASELINE_PREFLIGHT_AUDIT.md`.

**Current status: no baseline run has been performed.** Explicit approval is required before materializing official Dev/Test task payloads, and separate approval is required before model inference or A800/vLLM.


## 8. Split-preserving Retail data audit completed

The official legacy Retail task sources and DB/tool files are now vendored under `vendor/tau_bench/`, locked by `data/taubench_legacy/retail/source_lock.json`, and normalized by `scripts/prepare_tau_bench_retail.py`. Train/Dev/Test remain separate (500/20/115 tasks). The source integrity gate passes with documented domain-rejection and duplicate caveats. See `docs/09_TAUBENCH_RETAIL_DATA_INTEGRITY_AUDIT.md`.

This does not resolve the full user-simulator/rules/wiki or reward/status-parity differences in the released EvoTool adapter. No model baseline has been run.
