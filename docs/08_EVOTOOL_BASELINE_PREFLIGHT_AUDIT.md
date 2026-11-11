# Step 1 — EvoTool baseline reproduction preflight audit

**Date:** 2026-11-11  
**Status:** `PREFLIGHT_BLOCKED` — do not launch the baseline run yet.  
**Active repository:** `yujian777555/new_kaiti` only.

## Executive decision

The published EvoTool algorithm settings can be identified and the generation-budget mismatch can be controlled. However, the released repository's small tau-bench demo builder does **not** preserve the official Train/Dev/Test boundaries, and its tau-bench adapter is not the full conversational tau-bench environment. Therefore, running the 150-instance demo command and reporting its result as a faithful reproduction of the ACL 2026 paper would be scientifically invalid.

The next step is a split-preserving, source-pinned data/preflight design. No model inference, A800/vLLM launch, paid API call, optimizer run, or held-out outcome evaluation was performed in this audit.

## 1. Primary sources pinned

### EvoTool paper

- ACL Anthology: https://aclanthology.org/2026.acl-long.2016/
- DOI: `10.18653/v1/2026.acl-long.2016`
- PDF: https://aclanthology.org/2026.acl-long.2016.pdf
- Paper settings explicitly stated in Appendix A.6: frozen Qwen3-8B / GPT-4.1 backbones, maximum generation budget `G=8`, mini-batch `B=3`.
- Published Qwen3-8B tau-bench values: Retail 35.9, Airline 15.7, average 25.8. A retail-only run cannot reproduce the reported tau-bench average.

### Official EvoTool implementation

- Repository: https://github.com/SYang2000/ACL_2026_EvoTool
- Pinned source HEAD: `6a82719ea6e22cf23f963078e2527094e50b47f6`
- License: MIT
- Audited file identities:
  - `SPEC.md`: `421acafa9a8439a8ed6efb5e2e0edf6f2146f11c`
  - `configs/base.yaml`: `2df96e7ea15486fb3a6539817e1c909c1e9e3c54`
  - `src/config.py`: `a70ba9cd4415a3e04a834c49dcd6c29630b76b4a`
  - `src/evolve/loop.py`: `036a3d3f9c1ad14ad08b72ebd51dd27ef61c5515`
  - `src/evolve/select.py`: `f514568a286f90192cb463ac16012dee47f2c74f`
  - `scripts/data/build_taubench.py`: `878ad722f82f96db5c338054e3e67d2cd687e0a1`
  - `src/benchmarks.py`: `e7b4bc6b167c932c3fc4bec1e729083d962a47e6`
  - `src/policy/agent.py`: `421ac00fc3d7004466f73ed939297a0b27c10837`
  - `src/envs/taubench_env.py`: `0c0fd731714084dfa4fef2584070d286320a229f`
  - `src/metrics.py`: `e28bc8fd73107be43f4c83453e677d630f00fa40`

### Legacy tau-bench source

- Repository: https://github.com/sierra-research/tau-bench
- Pinned source HEAD inspected for metadata: `59a200c6d575d595120f1cb70fea53cef0632f6b`
- License: MIT
- Current upstream README warns that the old tau-bench tasks are outdated and directs users to tau³-bench. For historical ACL 2026 reproduction, do not silently replace the legacy benchmark with tau³; pin and disclose the legacy task snapshot.
- Task-file identities at the pinned source:
  - `tasks_train.py`: 500 task literals, Git blob `4fe71adafdbae7b6683f9d5beb65275172699bb6`
  - `tasks_dev.py`: 20 task literals, Git blob `aa5acf7f771b6e903bf795e436e03ee6ebe2c03d`
  - `tasks_test.py`: 115 task literals, Git blob `d0e4936ef9d523c04debf4ecd9f6d92eb39923a0`
- The three vendored retail DB files in EvoTool have the same Git blob SHAs as the corresponding files at this pinned tau-bench source:
  - orders: `77e34535e4cde09c21be706452947d267e74448f`
  - products: `dcde9b1beeea329cee6ce28d6b1e414a5284db3a`
  - users: `47ce9b4231a2881951a451d9bafc67c0c45f4403`

## 2. What is faithful and controllable

1. Paper Appendix A.6 specifies `G=8` and `B=3`.
2. The released code defaults to `n_train=90`, `n_sel=30`, `n_test=30`, `batch_size=3`, `epochs=3`; this derives 90 generations, not 8.
3. The code exposes `evolve.generations`. The explicit override `evolve.generations=8` makes the loop stop after exactly eight generations. This resolves the generation-count mismatch, provided the run log verifies eight completed generations.
4. The paper's base weights remain frozen. The released config uses Qwen3-8B, temperature 0.0, max output 512 tokens, and an 8192-token vLLM context.
5. The code supports disabling periodic Test probes with `evolve.log_test_eval=false`. This must be set so the held-out Test split is evaluated only once after evolution.

## 3. Blocking findings

### B1 — Demo data builder mixes official splits (critical)

The released `scripts/data/build_taubench.py` selects up to 150 tasks from the source files in this order:

1. `tasks_test.py`
2. `tasks_train.py`
3. `tasks_dev.py`

It then writes one combined `samples.json`. `src/benchmarks.py::split_instances` shuffles that combined list and randomly partitions it 90/30/30. The builder's docstring also describes a different source order from the actual source list.

This means the demo subset is not a split-preserving Train/selection/Test dataset. In particular, official Test tasks can enter the evolutionary Train or selection sets. **Do not use this 150-instance demo subset for a paper-level reproduction or a held-out generalization claim.**

The EvoTool README explicitly describes these 150-instance data files as demo subsets and says the paper uses the full official benchmarks. The tau-bench demo builder only covers Retail, not the Retail+Airline result reported in the paper.

### B2 — Released tau-bench adapter is not the full conversational benchmark (critical)

The official legacy tau-bench environment loads a selected task split and runs an agent against the user simulator, tool environment, domain rules, and wiki. In contrast, the released EvoTool `run_episode` path takes one task instruction, produces a plan, calls Selector/Caller in a fixed sequence, and synthesizes an answer. It does not run the official user-simulator conversation loop or provide the official domain rules/wiki to the policy.

The code does execute the vendored retail DB and tool logic, so it is a stateful offline task adapter; it should not be described as a full reproduction of the original multi-turn tau-bench interaction.

### B3 — Tau-bench reward implementation differs in details (high)

The original tau-bench reward compares a hash of the environment data after the predicted and gold actions and checks required output strings case-insensitively after comma normalization. EvoTool's local adapter compares only the mutable `orders`/`users` portions and checks required strings as case-sensitive exact substrings. The mutable-state comparison may be equivalent for the current retail tools if `products` is strictly read-only, but the output-string normalization is observably different.

The required-output sidecar builder also maps unmatched instructions to an empty output list rather than failing closed. Its data verification script uses `answer=None`, which checks DB state but bypasses required-output validation. A reproduction must report exact output-string coverage and fail if any source task's required outputs are lost.

### B4 — Search reward contains an undocumented shaping term (high)

The paper defines the task-dependent reward in terms of benchmark success metrics. The released code uses `0.7 * binary_success + 0.3 * progress`, where progress combines tool-sequence F1 and execution-success fraction. This shaped reward controls child acceptance and population selection, while the headline metric is binary success rate. Treat this as a paper/code discrepancy until reconciled; do not silently substitute the shaped score for Pass@1.

### B5 — Periodic held-out Test probing is enabled by default (medium)

`run.py` passes Test instances into the evolution loop, and `log_test_eval` defaults to true. The Test score is logging-only and does not enter selection, but repeated Test inspection is undesirable in a strict confirmatory protocol. Set `evolve.log_test_eval=false`; report the final held-out Test result once, after evolution and policy selection are frozen.

### B6 — Model, seed, and budget provenance need explicit locking (medium)

The paper names Qwen3-8B, G=8, B=3, but the reproduction record must additionally pin the exact Hugging Face model revision, official code SHA, tau-bench source SHA, DB/tool hashes, temperature, max context, max output tokens, maximum interaction steps, seed, and all split manifests. Do not use a moving model or dataset reference.

## 4. Decision and next protocol

**Decision: do not run the current 150-instance demo command.** It cannot support a valid paper reproduction.

Proposed split-preserving protocol, pending explicit authorization to access the official split payloads:

- `S_train`: official tau-bench Retail Train split.
- `S_sel`: official tau-bench Retail Dev split.
- `S_test`: official tau-bench Retail Test split.
- Preserve the original split boundaries; never shuffle tasks across these boundaries.
- Load `Task.outputs` directly while parsing each task; do not reconstruct outputs by instruction-text joins.
- Pin the legacy tau-bench source commit and hash every task, tool, and DB input.
- Verify every gold plan against the local DB evaluator and verify 100% required-output extraction coverage.
- Use Qwen3-8B with frozen weights, `G=8`, `B=3`, temperature 0.0, and the pinned model revision.
- Disable periodic Test probes; access Test only after evolution and selection are frozen.
- Label this accurately as a **split-preserving reproduction of the released EvoTool implementation on legacy tau-bench Retail** unless the full official user-simulator interaction and reward semantics are also restored. It is not the full four-benchmark ACL paper reproduction.

A later separate phase may restore the official tau-bench user simulator/rules/wiki and evaluate the Airline domain. Do not expand scope before the Retail pipeline is validated.

## 5. Authorization gate

This audit did not launch vLLM, access model weights, call any LLM API, run an optimizer, or evaluate held-out outcomes. The next step that reads and materializes official Dev/Test task payloads requires explicit approval. A800/vLLM smoke and formal eight-generation runs require a separate explicit approval after the split/data preflight passes.

## 6. Source links

- Paper: https://aclanthology.org/2026.acl-long.2016/
- Paper Appendix A.6 PDF: https://aclanthology.org/2026.acl-long.2016.pdf
- EvoTool official code: https://github.com/SYang2000/ACL_2026_EvoTool/tree/6a82719ea6e22cf23f963078e2527094e50b47f6
- EvoTool demo builder: https://github.com/SYang2000/ACL_2026_EvoTool/blob/6a82719ea6e22cf23f963078e2527094e50b47f6/scripts/data/build_taubench.py
- EvoTool split logic: https://github.com/SYang2000/ACL_2026_EvoTool/blob/6a82719ea6e22cf23f963078e2527094e50b47f6/src/benchmarks.py
- EvoTool episode adapter: https://github.com/SYang2000/ACL_2026_EvoTool/blob/6a82719ea6e22cf23f963078e2527094e50b47f6/src/policy/agent.py
- EvoTool local tau reward: https://github.com/SYang2000/ACL_2026_EvoTool/blob/6a82719ea6e22cf23f963078e2527094e50b47f6/src/envs/taubench_env.py
- Legacy tau-bench README: https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/README.md
- Legacy tau-bench environment reward: https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs/base.py
