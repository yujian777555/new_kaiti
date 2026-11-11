# Step 3 — EvoTool × legacy tau-bench Retail conformance result

**Date:** 2026-11-11  
**CI:** [42987687316](https://github.com/yujian777555/new_kaiti/actions/runs/42987687316)  
**Overall gate:** `PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS`  
**Model inference / API / optimizer:** none / 0 / 0.

## Reproducible harness

- Runner: `scripts/audit_evotool_tau_bench_conformance.py`
- Tests: `tests/test_evotool_tau_bench_conformance.py`
- Official tau-bench source: `sierra-research/tau-bench` @ `59a200c6d575d595120f1cb70fea53cef0632f6b`.
- EvoTool source: `SYang2000/ACL_2026_EvoTool` @ `6a82719ea6e22cf23f963078e2527094e50b47f6`.
- EvoTool source lock: 9 files verified.
- The harness injects a deterministic fake user transport into the pinned official Env to exercise the real `step()` and `calculate_reward()` methods without an LLM/provider call.
- Adapted split manifests are generated separately for Train 500, Dev 20, Test 115; 16 tools per split.

## CI results

- Existing transferred regression: 95 passed, 1 skipped.
- New conformance suite: 8 passed.
- Official/EvoTool tool implementations compared over 1,375 Gold Action calls:
  - tool sets equal;
  - return mismatches: 0;
  - exception mismatches: 0;
  - full DB state mismatches: 0;
  - product mutations: 0;
  - domain-level Error returns: 44 on both sides.
- Official reward replay compared on 635 Gold tasks:
  - official gold reward failures: 0;
  - EvoTool gold success failures: 0;
  - official/EvoTool Gold outcome mismatches: 0.
- Exact ordered Action History is checked across all 635 Gold tasks: candidate actions, response action(s) unless a terminal tool ran, then non-terminal Gold Actions replayed by official `calculate_reward()`.
- Official `Env.reset()` and EvoTool fresh-instance DB isolation are checked against the same pinned DB snapshot.
- Environment dispatch probes cover one successful Gold action, one domain-level `Error:` return, an unknown tool, and a missing required argument. Expected unknown-tool/exception serialization differences are retained as known deviations.

## Important interpretation

**Tool implementation parity and exact-Gold reward parity pass on this pinned dataset. Full interaction-protocol parity does not.**

The zero Gold mismatch result is expected on exact reference trajectories; it does not erase these measured differences:

1. Output semantics probes:
   - case variation: official reward 1.0, EvoTool false;
   - comma normalization: official reward 1.0, EvoTool false;
   - multiple conversation responses: official reward 1.0, EvoTool false because EvoTool checks one final answer string.
2. EvoTool counts a tool function returning a domain-level `Error:` as `status=success`. On a representative one-step case, progress is 1.0 under current status and 0.5 if business rejection is counted as an error; the 0.3 shaped-reward component differs by 0.15.
3. Official tau-bench runs a conversational user-simulator/tool loop; EvoTool uses Planner → Selector → Caller → Synthesizer. It does not reset/step the official simulator or inject the retail wiki into the same loop.
4. Official tool-calling max steps is 30; EvoTool base config max steps is 6.
5. Official reward hashes the full DB; EvoTool compares orders/users. On all 1,375 pinned Gold Actions no products mutation occurred, so this projection is equivalent for this audited tool set, but not a general guarantee.
6. Official Env stores a rules list; default ToolCallingAgent uses wiki and tool schemas rather than passing the separate rules list.

## Decision

- Keep the official EvoTool snapshot unchanged as the legacy baseline treatment.
- Do not label the current adapter a faithful full tau-bench conversational reproduction.
- Any corrected Error-status/progress treatment or restored full conversation adapter must be a separately named method/arm with an explicit protocol.
- No inference, optimizer, training, A800/vLLM, paid API, or policy-performance evaluation was run.
- Next: independent review of the harness and its fake-user semantics; then decide whether to implement separate `evotool_legacy` and `evotool_status_corrected` arms. Do not start model/optimizer runs without separate approval.

## Artifact

The workflow uploads the normalized splits plus `evotool_train.jsonl`, `evotool_dev.jsonl`, `evotool_test.jsonl`, and the machine-readable/Markdown conformance report. Use the artifact from run 42987687316; do not infer local files from its title.


## Independent review — Step 3-R1

The first conformance report correctly established tool-function parity on the frozen Gold Action set, but an independent source review found that two claims needed stronger executable evidence: the Action History probe compared only sequence length, and the harness did not directly compare official Env.reset() with EvoTool's constructor-based fresh DB isolation. The earlier direct tool-function comparison also did not exercise each environment's dispatch wrapper.

Step 3-R1 strengthens the harness without changing either pinned upstream implementation:

- Exact ordered Action History comparison is performed for all 635 tasks, including action names and kwargs. Candidate terminal actions suppress the response turn; official reward replay then appends each non-terminal Gold Action.
- Reset/copy isolation checks compare official Env.reset() and independently constructed EvoTool environments against the pinned DB. EvoTool exposes fresh initialization through TauBenchEnv() rather than a separate reset() method.
- Dispatch probes compare a successful action and a domain-level rejection through the actual environment wrappers. They also explicitly record the known differences for unknown tools and missing required arguments.
- The conformance runner now requires the dataset integrity report to pass, verifies the pinned official source commit and 42 source-file checks, and rechecks all three normalized split hashes before producing a conformance result.
- CI no longer suppresses the dataset-builder exit code with || true.

Interpretation remains deliberately narrow: exact Gold replay is a source/reward conformance check, not a policy-performance experiment. The Train-only successful-action dispatch probe is a deterministic implementation test, not a policy score. The official conversational user-simulator loop is still absent from EvoTool; this project continues to label the adapter as a reduced/offline treatment.

### Metric design decision

Do not redefine every returned Error: as a failed tool execution. The legacy adapter's status="success" means the function returned without raising; it does not mean the requested business operation succeeded. A future corrected treatment should preserve the legacy field for reproducibility and add separate fields such as execution_status and business_outcome. Any new progress/reward formula must be justified independently; an Error: response can be a valid observation (for example, a lookup proving that a user or product does not exist) rather than automatically a negative task outcome.

### Step-limit interpretation

The official max_num_steps=30 counts turns in a conversational action loop, including response turns. EvoTool max_steps=6 truncates planner substeps before selector/caller execution. Report the values, but do not describe them as directly comparable step budgets or as a 5x protocol gap.


### Step 3-R1 CI verification

- PR: https://github.com/yujian777555/new_kaiti/pull/1
- Initial Step 3-R1 commit: 5b85db116e909af9e46024fc9e22e29ec7ab6e9a
- CI run: https://github.com/yujian777555/new_kaiti/actions/runs/42992221354 — SUCCESS.
- Transferred regression: 95 passed, 1 skipped.
- Dataset + conformance tests: 11 passed.
- Overall conformance gate: PASS_WITH_KNOWN_PROTOCOL_DEVIATIONS.
- Exact Action History: 635/635 checked, 0 ordered-sequence mismatches.
- Reset/copy isolation: PASS.
- Dispatch: successful and domain-rejection calls matched in output/state; unknown-tool and missing-argument serialization differences were detected as expected.
- Artifact ID: 13841803539 (expires 2026-12-11).
