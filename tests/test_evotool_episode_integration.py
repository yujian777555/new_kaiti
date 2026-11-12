from copy import deepcopy
from types import SimpleNamespace
from treatments.evotool_episode_integration import run_treated_episode

class TinyExecutor:
    def __init__(self, db): self.db = deepcopy(db)
    def execute(self, tool, args):
        if tool == "set_status":
            self.db["orders"]["o1"]["status"] = args["value"]
            output, status = "updated", "success"
        else: output, status = "Error: unknown tool", "error"
        return {"tool": tool, "args": args, "output": output, "status": status}

def test_episode_integration_runs_t1_and_parallel_t3_without_overwriting_t0():
    base_db = {"orders": {"o1": {"status": "pending"}}, "users": {}, "products": {}}
    def set_status(db, value):
        db["orders"]["o1"]["status"] = value
        return "updated"
    class FakeAgent:
        _EPISODE_CACHE = {}
        @staticmethod
        def _policy_key(policy): return 123
        @staticmethod
        def env_for(instance): return TinyExecutor(base_db)
        @staticmethod
        def run_episode(client, policy, instance, max_steps):
            observation = FakeAgent.env_for(instance).execute("set_status", {"value": "cancelled"})
            step = SimpleNamespace(tool="set_status", observation=observation)
            return SimpleNamespace(steps=[step],
                predicted_plan=[{"tool": "set_status", "args": {"value": "cancelled"}}],
                answer="done", reward=0.85, success=True)
    instance = {"id": "smoke-1", "benchmark": "taubench",
        "gold_plan": [{"tool": "set_status", "args": {"value": "cancelled"}}], "outputs": []}
    result = run_treated_episode(FakeAgent, object(), object(), instance, 2,
        known_tools={"set_status"}, db_loader=lambda: deepcopy(base_db),
        tool_map={"set_status": set_status})
    obs = result["episode"].steps[0].observation
    assert obs["status"] == "success"
    assert obs["execution_status"] == "returned"
    assert obs["business_outcome"] == "accepted"
    assert obs["state_effect"] == "changed"
    assert result["t0_legacy_reward"] == 0.85
    assert result["t0_legacy_success"] is True
    assert result["t3"]["reward"] == 1.0
    assert result["comparison"]["t0_and_t3_success_match"] is True
    assert FakeAgent.env_for(instance).__class__ is TinyExecutor
    assert FakeAgent._EPISODE_CACHE == {}
