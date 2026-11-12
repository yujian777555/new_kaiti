#!/usr/bin/env python3
"""Build and validate a split-pure D-080 Train-only real-tool fault manifest."""
from __future__ import annotations
import argparse, hashlib, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.prepare_tau_bench_retail import install_vendored_runtime
from treatments.fault_injection import FaultEvent, state_sha256

SOURCE_COMMIT="59a200c6d575d595120f1cb70fea53cef0632f6b"
GENERATOR_VERSION="d080-train-fault-manifest-v1"
SEED_BASE=2026111201
PER_TOOL_TASKS=8
TARGET_TOOLS={
 "cancel_pending_order":"nonrepeatable_cancel_with_refund",
 "modify_pending_order_address":"idempotent_order_address_assignment",
 "modify_pending_order_items":"nonrepeatable_item_change_with_payment_effect",
 "modify_pending_order_payment":"nonrepeatable_payment_switch_with_refund",
 "return_delivered_order_items":"one_shot_return_state_transition",
 "exchange_delivered_order_items":"one_shot_exchange_state_transition",
}
FAULT_MODES=("timeout_before_execution","rate_limit_before_execution",
             "schema_rejection_before_execution","timeout_after_commit")

def canonical(value):
 return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

def sha(value): return hashlib.sha256(value).hexdigest()
def clone(value): return json.loads(json.dumps(value))

def load_rows(dataset_dir):
 raw=(Path(dataset_dir)/"train.jsonl").read_bytes()
 rows=[json.loads(x) for x in raw.decode().splitlines() if x.strip()]
 if len(rows)!=500 or any(x.get("split")!="train" for x in rows):
  raise ValueError("expected exactly 500 Train-only rows")
 if any(x.get("source_commit")!=SOURCE_COMMIT for x in rows):
  raise ValueError("Train source commit mismatch")
 if len({x["task_id"] for x in rows})!=500: raise ValueError("duplicate Train task IDs")
 return rows,sha(raw)

def find_candidates(rows,base_db,tool_map):
 found=defaultdict(list)
 for row in rows:
  db=clone(base_db); ordinals=defaultdict(int); seen=set()
  for action in row.get("actions",[]):
   tool=action["name"]; ordinal=ordinals[tool]; ordinals[tool]+=1
   before=state_sha256(db)
   try: output=tool_map[tool](db,**(action.get("kwargs") or {}))
   except Exception: continue
   if (tool in TARGET_TOOLS and tool not in seen
       and not (isinstance(output,str) and output.startswith("Error:"))
       and before!=state_sha256(db)):
    found[tool].append({
     "task_id":row["task_id"],"task_index":int(row["task_index"]),
     "tool_name":tool,"call_index":ordinal,
     "semantic_class":TARGET_TOOLS[tool],
     "task_record_sha256":sha(canonical(row)),
    })
    seen.add(tool)
 return found

def validate_manifest(manifest,rows,tool_map,base_db):
 problems=[]
 if manifest.get("protocol_id")!="D-080" or manifest.get("source_split")!="train" or manifest.get("train_only") is not True:
  problems.append("protocol/split metadata invalid")
 if manifest.get("target_tools")!=TARGET_TOOLS or manifest.get("fault_modes")!=list(FAULT_MODES):
  problems.append("target tools or fault modes mismatch")
 for key in ("dev_included","validation_included","test_included","test_outcomes_read"):
  if manifest.get(key) is not False: problems.append(f"{key} must be false")
 if manifest.get("manifest_sha256")!=sha(canonical({k:v for k,v in manifest.items() if k!="manifest_sha256"})):
  problems.append("manifest content hash mismatch")
 rowmap={r["task_id"]:r for r in rows}; used=set(); keys=set()
 counts=Counter(); modes=Counter()
 allowed={"task_id","task_index","tool_name","call_index","semantic_class","task_record_sha256","mode","seed","event_id"}
 for e in manifest.get("events",[]):
  if set(e)!=allowed:
   problems.append("event schema mismatch or Gold argument leakage"); continue
  tid=e["task_id"]; tool=e["tool_name"]
  if tid not in rowmap: problems.append(f"non-Train task {tid}"); continue
  row=rowmap[tid]
  if e["task_index"]!=row["task_index"] or e["task_record_sha256"]!=sha(canonical(row)):
   problems.append(f"source row binding mismatch {tid}")
  if tool not in TARGET_TOOLS or e["semantic_class"]!=TARGET_TOOLS.get(tool):
   problems.append(f"tool semantic mismatch {tid}")
  key=(tid,tool,e["call_index"])
  if key in keys: problems.append(f"duplicate event key {key}")
  keys.add(key)
  if tid in used: problems.append(f"task assigned more than once {tid}")
  used.add(tid)
  try:
   expected=FaultEvent(tid,tool,e["call_index"],e["mode"],e["seed"]).event_id
   if expected!=e["event_id"]: problems.append(f"event ID mismatch {tid}")
  except Exception as exc: problems.append(f"invalid event {tid}: {exc}")
  counts[tool]+=1; modes[(tool,e["mode"])]+=1
  # Confirm scheduled per-tool ordinal is a valid state-changing Gold call.
  db=clone(base_db); ords=defaultdict(int); selected=False
  for action in row.get("actions",[]):
   name=action["name"]; ordinal=ords[name]; ords[name]+=1
   before=state_sha256(db)
   try: output=tool_map[name](db,**(action.get("kwargs") or {}))
   except Exception: continue
   if (name==tool and ordinal==e["call_index"]
       and not (isinstance(output,str) and output.startswith("Error:"))
       and before!=state_sha256(db)):
    selected=True
  if not selected: problems.append(f"scheduled action not state-changing {tid}/{tool}")
 if len(manifest.get("events",[]))!=48 or manifest.get("event_count")!=48:
  problems.append("event count must be 48")
 if len(used)!=48 or manifest.get("unique_task_count")!=48:
  problems.append("unique task count must be 48")
 for tool in TARGET_TOOLS:
  if counts[tool]!=8: problems.append(f"expected 8 tasks for {tool}")
  for mode in FAULT_MODES:
   if modes[(tool,mode)]!=2: problems.append(f"expected 2 {mode} events for {tool}")
 if problems: raise ValueError("D-080 manifest invalid: "+"; ".join(problems))
 return {"ok":True,"event_count":len(keys),"unique_task_count":len(used),
         "per_tool_counts":dict(sorted(counts.items()))}

def build_manifest(dataset_dir):
 rows,dataset_hash=load_rows(dataset_dir)
 tool_classes,load_data=install_vendored_runtime()
 tool_map={t.get_info()["function"]["name"]:t.invoke for t in tool_classes}
 missing=set(TARGET_TOOLS)-set(tool_map)
 if missing: raise ValueError(f"missing tools {sorted(missing)}")
 candidates=find_candidates(rows,load_data(),tool_map)
 used=set(); events=[]; summary={}
 for ti,(tool,semantic) in enumerate(TARGET_TOOLS.items()):
  eligible=[x for x in candidates[tool] if x["task_id"] not in used]
  eligible.sort(key=lambda x:sha(f"{SEED_BASE+ti}|{tool}|{x['task_id']}".encode()))
  selected=eligible[:PER_TOOL_TASKS]
  if len(selected)!=PER_TOOL_TASKS:
   raise ValueError(f"only {len(selected)} disjoint valid Train tasks for {tool}")
  used.update(x["task_id"] for x in selected)
  schedule=list(FAULT_MODES)*2
  random.Random(SEED_BASE+100*ti).shuffle(schedule)
  tool_events=[]
  for slot,(candidate,mode) in enumerate(zip(selected,schedule)):
   seed=SEED_BASE+1000*ti+slot
   ev=FaultEvent(candidate["task_id"],tool,candidate["call_index"],mode,seed)
   item={**candidate,"mode":mode,"seed":seed,"event_id":ev.event_id}
   events.append(item); tool_events.append(item)
  summary[tool]={"semantic_class":semantic,"task_count":len(tool_events),
                 "mode_counts":dict(sorted(Counter(x["mode"] for x in tool_events).items()))}
 events.sort(key=lambda x:(x["tool_name"],x["task_id"]))
 manifest={
  "schema_version":1,"protocol_id":"D-080","generator_version":GENERATOR_VERSION,
  "source_commit":SOURCE_COMMIT,"source_split":"train","source_train_rows":500,
  "source_train_jsonl_sha256":dataset_hash,"seed_base":SEED_BASE,
  "target_tools":TARGET_TOOLS,"fault_modes":list(FAULT_MODES),
  "per_tool_task_count":PER_TOOL_TASKS,"event_count":len(events),
  "unique_task_count":len(used),"per_tool_summary":summary,"events":events,
  "train_only":True,"dev_included":False,"validation_included":False,
  "test_included":False,"test_outcomes_read":False,
 }
 manifest["manifest_sha256"]=sha(canonical(manifest))
 validate_manifest(manifest,rows,tool_map,load_data())
 return manifest

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--dataset-dir",required=True,type=Path)
 p.add_argument("--output-dir",required=True,type=Path)
 a=p.parse_args(); manifest=build_manifest(a.dataset_dir)
 a.output_dir.mkdir(parents=True,exist_ok=True)
 raw=json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
 (a.output_dir/"d080_fault_manifest.json").write_text(raw,encoding="utf-8")
 lock={
  "lock_version":"d080-train-fault-manifest-lock-v1",
  "status":"LOCKED_TRAIN_ONLY_DEVELOPMENT",
  "manifest_file_sha256":sha(raw.encode()),
  "manifest_content_sha256":manifest["manifest_sha256"],
  "event_ids_sha256":sha(canonical(sorted(x["event_id"] for x in manifest["events"]))),
  "event_count":manifest["event_count"],"unique_task_count":manifest["unique_task_count"],
  "source_train_jsonl_sha256":manifest["source_train_jsonl_sha256"],
  "dev_included":False,"validation_included":False,"test_included":False,"test_outcomes_read":False,
 }
 (a.output_dir/"d080_fault_manifest_lock.json").write_text(
  json.dumps(lock,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report={"status":"PASS_TRAIN_ONLY_MANIFEST","manifest_sha256":manifest["manifest_sha256"],
         "event_count":48,"unique_task_count":48,"per_tool_summary":manifest["per_tool_summary"],
         "lock":lock}
 (a.output_dir/"d080_fault_manifest_report.json").write_text(
  json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
