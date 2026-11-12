"""Run fault-injected EvoTool episodes and score actual live DB state."""
from contextlib import contextmanager
from treatments.evotool_status import StatusDecomposedExecutor
from treatments.fault_injection import FaultInjectedExecutor, state_sha256
from treatments.taubench_official_reward import score_official_task

@contextmanager
def _temporary_env_factory(agent, factory):
 original=agent.env_for; agent.env_for=factory
 try: yield
 finally: agent.env_for=original

def _counts(items):
 out={}
 for x in items: out[x]=out.get(x,0)+1
 return dict(sorted(out.items()))

def run_faulted_episode(agent,client,policy,instance,max_steps,*,known_tools,db_loader,tool_map,fault_events=()):
 if instance.get("benchmark")!="taubench": raise ValueError("D-080 currently supports tau-bench only")
 task_id=instance.get("id") or instance.get("task_id")
 if not task_id: raise ValueError("stable task id required")
 holder={}; base_factory=agent.env_for
 def env_factory(item):
  delegate=base_factory(item)
  if item.get("benchmark")!="taubench": return delegate
  wrapped=FaultInjectedExecutor(delegate,task_id,tool_map,fault_events)
  holder["executor"]=wrapped
  return StatusDecomposedExecutor(wrapped,known_tools)
 cache=getattr(agent,"_EPISODE_CACHE",None); key=None; previous=None
 if isinstance(cache,dict) and hasattr(agent,"_policy_key"):
  key=(agent._policy_key(policy),instance.get("id")); previous=cache.pop(key,None)
 try:
  with _temporary_env_factory(agent,env_factory):
   episode=agent.run_episode(client,policy,instance,max_steps)
 finally:
  if isinstance(cache,dict) and key is not None:
   cache.pop(key,None)
   if previous is not None: cache[key]=previous
 if "executor" not in holder: raise RuntimeError("fault-aware executor was not created")
 executor=holder["executor"]; steps=[]
 for step in episode.steps:
  obs=dict(step.observation)
  if not all(k in obs for k in ("execution_status","business_outcome","state_effect")):
   raise RuntimeError("T1 diagnostics missing")
  steps.append({"tool":step.tool,"execution_status":obs["execution_status"],
   "business_outcome":obs["business_outcome"],"state_effect":obs["state_effect"],
   "legacy_status":obs.get("status"),"fault_injected":bool(obs.get("fault_injected",False)),
   "fault_mode":obs.get("fault_mode"),"fault_phase":obs.get("fault_phase")})
 live=score_official_task(db_loader,tool_map,
  instance.get("gold_plan") or instance.get("gold_actions") or [],
  executor.db,instance.get("outputs") or instance.get("r_outputs") or [],
  [episode.answer])
 return {"episode":episode,"t0_legacy_reward":float(episode.reward),
  "t0_legacy_success":bool(episode.success),
  "t1":{"step_count":len(steps),"steps":steps,
   "business_outcome_counts":_counts(x["business_outcome"] for x in steps),
   "execution_status_counts":_counts(x["execution_status"] for x in steps),
   "state_effect_counts":_counts(x["state_effect"] for x in steps)},
  "fault_audit":list(executor.fault_audit),"tool_call_counts":executor.call_counts,
  "live_state_sha256":state_sha256(executor.db),"official_live_score":live,
  "protocol_note":"T0 is EvoTool replay-based reward; D-080 official_live_score grades the actual post-fault DB."}
