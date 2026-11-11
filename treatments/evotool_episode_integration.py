"""Execute EvoTool's real episode seam with T1 and independently score with T3."""
from contextlib import contextmanager
from treatments.evotool_status import make_status_decomposed_env_factory
from treatments.taubench_official_reward import score_task

@contextmanager
def _temporary_env_factory(agent_module, env_factory):
    original = agent_module.env_for
    agent_module.env_for = env_factory
    try:
        yield
    finally:
        agent_module.env_for = original

def _counts(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))

def run_treated_episode(agent_module, client, policy, instance, max_steps, *,
                        known_tools, db_loader, tool_map):
    """Run one Tau-bench episode with T1; compute T3 without changing T0 reward."""
    if instance.get("benchmark") != "taubench":
        raise ValueError("T1/T3 integration currently supports only taubench instances")
    t1_factory = make_status_decomposed_env_factory(agent_module.env_for, known_tools)
    cache = getattr(agent_module, "_EPISODE_CACHE", None)
    cache_key = None
    previous_cached = None
    if isinstance(cache, dict) and hasattr(agent_module, "_policy_key"):
        cache_key = (agent_module._policy_key(policy), instance.get("id"))
        previous_cached = cache.pop(cache_key, None)
    try:
        with _temporary_env_factory(agent_module, t1_factory):
            episode = agent_module.run_episode(client, policy, instance, max_steps)
    finally:
        if isinstance(cache, dict) and cache_key is not None:
            cache.pop(cache_key, None)
            if previous_cached is not None:
                cache[cache_key] = previous_cached
    t1_steps = []
    for step in episode.steps:
        obs = dict(step.observation)
        if not all(k in obs for k in ("execution_status", "business_outcome", "state_effect")):
            raise RuntimeError("T1 diagnostics missing from an executed tau-bench step")
        t1_steps.append({
            "tool": step.tool, "execution_status": obs["execution_status"],
            "business_outcome": obs["business_outcome"],
            "state_effect": obs["state_effect"], "legacy_status": obs.get("status")})
    t3 = score_task(
        db_loader, tool_map,
        instance.get("gold_plan") or instance.get("gold_actions") or [],
        episode.predicted_plan,
        instance.get("outputs") or instance.get("r_outputs") or [],
        [episode.answer])
    return {
        "episode": episode,
        "t0_legacy_reward": float(episode.reward),
        "t0_legacy_success": bool(episode.success),
        "t1": {
            "step_count": len(t1_steps), "steps": t1_steps,
            "business_outcome_counts": _counts(x["business_outcome"] for x in t1_steps),
            "execution_status_counts": _counts(x["execution_status"] for x in t1_steps),
            "state_effect_counts": _counts(x["state_effect"] for x in t1_steps)},
        "t3": t3,
        "comparison": {
            "t0_legacy_success": bool(episode.success),
            "t3_official_reward": float(t3["reward"]),
            "t0_and_t3_success_match": bool(episode.success) == bool(t3["reward"])},
        "protocol_note": "T3 uses EvoTool's single final synthesizer answer; reduced-adapter scoring, not full multi-turn tau-bench parity."}
