# Step 5 — T1/T3 episode integration

The new treatments/evotool_episode_integration.py invokes the vendored agent module's run_episode() through its existing env_for seam. It injects T1 for the episode, restores the original factory in finally, and evicts/restores only the exact policy/instance cache key so a cached T0 episode cannot bypass instrumentation.

T3 independently scores the episode's predicted action list and final synthesizer answer against the frozen Gold plan using pinned official tool implementations. The original episode.reward and episode.success are not overwritten. Output includes T0 reward, T1 per-step diagnostics, T3 reward, and success agreement.

A deterministic integration smoke test checks T1 fields, unchanged T0 reward, independent T3 scoring, factory restoration, and cache isolation. It is not a model-backed performance result; no API/GPU/optimizer/held-out split is used.

Next: after CI passes, run a deterministic real-tool episode with planner/selector/caller/synthesizer responses stubbed, then a small Train-only model-backed pilot only with explicit authorization.
