from copy import deepcopy
from types import SimpleNamespace
import pytest
from treatments.fault_injection import FaultEvent, FaultInjectedExecutor
from treatments.fault_episode_integration import run_faulted_episode

class TinyExecutor:
 def __init__(self,db): self.db=deepcopy(db)
 def execute(self,tool,args): return {"tool":tool,"args":args,"output":"unknown","status":"error"}

def tiny_agent(base):
 class Agent:
  _EPISODE_CACHE={}
  @staticmethod
  def _policy_key(policy): return 11
  @staticmethod
  def env_for(_instance): return TinyExecutor(base)
  @staticmethod
  def run_episode(_client,_policy,instance,_max_steps):
   obs=Agent.env_for(instance).execute("set_status",{"value":"cancelled"})
   return SimpleNamespace(steps=[SimpleNamespace(tool="set_status",observation=obs)],
    predicted_plan=[{"tool":"set_status","args":{"value":"cancelled"}}],
    answer="done",reward=.85,success=False)
 return Agent

def test_executor_uses_per_tool_ordinal_not_global_call_index():
 base={"orders":{"o1":{"status":"pending"}},"users":{},"products":{}}
 def read(db): return "read"
 def write(db,value): db["orders"]["o1"]["status"]=value; return "updated"
 ex=FaultInjectedExecutor(TinyExecutor(base),"task-x",{"read":read,"write":write},
  [FaultEvent("task-x","write",0,"timeout_before_execution",7)])
 assert ex.execute("read",{})["status"]=="success"
 assert ex.execute("write",{"value":"cancelled"})["fault_injected"] is True
 assert ex.execute("write",{"value":"cancelled"})["status"]=="success"
 assert ex.call_counts=={"read":1,"write":2}

@pytest.mark.parametrize("mode,reward,effect",[
 ("timeout_before_execution",0.0,"unchanged"),
 ("timeout_after_commit",1.0,"changed")])
def test_faulted_episode_scores_actual_live_db(mode,reward,effect):
 base={"orders":{"o1":{"status":"pending"}},"users":{},"products":{}}
 def set_status(db,value): db["orders"]["o1"]["status"]=value; return "updated"
 agent=tiny_agent(base)
 instance={"id":"task-live-score","benchmark":"taubench",
  "gold_plan":[{"tool":"set_status","args":{"value":"cancelled"}}],"outputs":[]}
 result=run_faulted_episode(agent,object(),object(),instance,2,
  known_tools={"set_status"},db_loader=lambda:deepcopy(base),tool_map={"set_status":set_status},
  fault_events=[FaultEvent("task-live-score","set_status",0,mode,13)])
 assert result["official_live_score"]["reward"]==reward
 assert result["t1"]["steps"][0]["state_effect"]==effect
 assert result["t1"]["steps"][0]["execution_status"]=="injected_failure"
 assert result["fault_audit"][0]["mode"]==mode
 assert agent._EPISODE_CACHE=={}
