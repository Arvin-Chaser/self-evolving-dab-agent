#!/usr/bin/env python3
"""Collect one hash-bound, answer-blind G2 timeout dispatch sidecar."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from experiments.run_research_graph_g001_meta_v2 import sha, write_new


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g002_timeout_dispatch_v2.json"
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]
REMOTE_CODE = r'''
import ast,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path

base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
run=base/"g002_revision001/evaluation/baseline_g002_lifecycle_nohint_56_v1"
graph=base/"graph/g002_graph.json"
summary=run/"multi_query_summary.json"
manifest=base/"graph/g002_trace_manifest.json"
agent=base/"g002_revision001/source/experiments/run_dab_tool_agent.py"
upstream=Path("/srv/text2sql/external/DataAgentBench_official/common_scaffold/DataAgent.py")

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def records(path):
    out=[]
    torn=0
    size=path.stat().st_size
    with path.open("rb") as stream:
        for raw in stream:
            try:
                row=json.loads(raw)
            except (ValueError,UnicodeDecodeError):
                if stream.tell()!=size or torn:
                    raise RuntimeError("Malformed nonterminal event row")
                torn=len(raw)
                continue
            if not isinstance(row,dict):
                raise RuntimeError("Event row is not an object")
            out.append(row)
    return out,torn

def epoch(value):
    if isinstance(value,str) and len(value)==15 and value[8]=="_":
        try:
            return datetime.strptime(value,"%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None
    if isinstance(value,bool) or not isinstance(value,(float,int)):
        return None
    value=float(value)
    return value if math.isfinite(value) and 1500000000<=value<=2500000000 else None

if (digest(graph)!="38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54" or
        digest(summary)!="d18d1650670d5ed362c3a0920053e60f9243adbb3cafb4e3375ad11cf50ddd02" or
        digest(manifest)!="bd8083f263254fff2e4e8cfa68bc577220928fecd0809ed88c1a781df02003f1" or
        digest(agent)!="31d1b3fdbb21f6313b5e8f0a1ca2eacd6096ac2922cfe5abacec5218cdd1a66a"):
    raise RuntimeError("Frozen G2 source binding differs")
g=json.loads(graph.read_text(encoding="utf-8"))
s=json.loads(summary.read_text(encoding="utf-8"))
t=json.loads(manifest.read_text(encoding="utf-8"))
rows=s["per_query_feedback"]
if g["nodes"][-1]["timeout_failure_count"]!=2 or len(rows)!=56 or len(t["entries"])!=56:
    raise RuntimeError("G2 timeout cohort differs")
dab_root=Path(s["execution_context"]["dab_root"]).resolve()
if not dab_root.is_dir():
    raise RuntimeError("Frozen DAB root missing")

agent_tree=ast.parse(agent.read_text(encoding="utf-8"))
upstream_tree=ast.parse(upstream.read_text(encoding="utf-8"))
agent_functions={node.name for node in agent_tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
data_agent=next((node for node in upstream_tree.body if isinstance(node,ast.ClassDef) and node.name=="DataAgent"),None)
methods={node.name for node in data_agent.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))} if data_agent else set()
if "install_deadline_reserve_signal" not in agent_functions or not {"call_llm","_handle_tool_call","handle_reponse"}<=methods:
    raise RuntimeError("Expected static dispatch boundaries absent")

cases=[]
for index,row in enumerate(rows,1):
    if row["status"]!="timeout":
        continue
    if row.get("run_exit_code")!=124 or row.get("query_timeout_stage")!="run":
        raise RuntimeError("Unexpected G2 timeout protocol")
    domain,sep,name=row["query_id"].partition("/")
    if not sep or not domain or not name:
        raise RuntimeError("Malformed frozen task locator")
    upstream_run=(dab_root/("query_"+domain)/name/"logs/data_agent"/row["run_id"]).resolve()
    if not upstream_run.is_relative_to(dab_root):
        raise RuntimeError("Upstream log locator escapes DAB root")
    llm_path=upstream_run/"llm_calls.jsonl"
    tool_path=upstream_run/"tool_calls.jsonl"
    lifecycle=run/"lifecycle"/f"q{index:02d}.json"
    if not llm_path.is_file() or not tool_path.is_file() or not lifecycle.is_file():
        raise RuntimeError("G2 timeout partial log or lifecycle missing")
    if max(llm_path.stat().st_mtime,tool_path.stat().st_mtime,lifecycle.stat().st_mtime)>summary.stat().st_mtime+5:
        raise RuntimeError("G2 timeout evidence changed after summary")
    llm_rows,llm_torn=records(llm_path)
    tool_rows,tool_torn=records(tool_path)
    marker=json.loads(lifecycle.read_text(encoding="utf-8"))
    if marker.get("answer_blind") is not True or marker.get("last_stage")!="task_summary_written":
        raise RuntimeError("G2 timeout lifecycle protocol differs")
    events=[]
    for event in llm_rows:
        start,end=epoch(event.get("start_time")),epoch(event.get("end_time"))
        if start is not None and end is not None and end>=start:
            events.append(("llm",start,end))
    for event in tool_rows:
        start,end=epoch(event.get("start")),epoch(event.get("end"))
        if start is not None and end is not None and end>=start:
            events.append(("tool",start,end))
    terminal=lifecycle.stat().st_mtime
    recent=[event for event in events if 0<=terminal-event[1]<=120]
    last=max(events,key=lambda event:event[2]) if events else None
    cases.append({
        "anonymous_timeout_index":len(cases)+1,
        "llm_record_count":len(llm_rows),"tool_record_count":len(tool_rows),
        "timed_completed_event_count":len(events),
        "completed_events_within_120s_of_terminal":len(recent),
        "llm_completed_within_120s_of_terminal":sum(e[0]=="llm" for e in recent),
        "tool_completed_within_120s_of_terminal":sum(e[0]=="tool" for e in recent),
        "last_completed_event_kind":last[0] if last else None,
        "last_completed_event_seconds_before_terminal":round(terminal-last[2],3) if last else None,
        "recorded_event_span_sec":round(max(e[2] for e in events)-min(e[1] for e in events),3) if events else None,
        "torn_tail_bytes":{"llm":llm_torn,"tool":tool_torn},
        "source_hashes":{"llm_calls_sha256":digest(llm_path),"tool_calls_sha256":digest(tool_path),
                         "lifecycle_sha256":digest(lifecycle)},
    })
if len(cases)!=2:
    raise RuntimeError("G2 timeout case count differs")
print(json.dumps({
    "schema_version":"g002_timeout_dispatch_answer_blind_v2",
    "source_hashes":{"g2_graph_sha256":digest(graph),"g2_summary_sha256":digest(summary),
                     "g2_trace_manifest_sha256":digest(manifest),"g2_agent_sha256":digest(agent),
                     "upstream_agent_sha256":digest(upstream)},
    "static_boundaries":{"reserve_wrapper_present":True,"call_llm_present":True,
                         "handle_response_present":True,"handle_tool_call_present":True},
    "timeout_case_count":2,"cases":cases,
    "scope":"Only event types, timing, counts, lifecycle stages, AST method names, and source hashes; no messages, arguments, results, errors, task IDs, or answer text exported.",
    "limitations":[
        "Lifecycle file mtime is a terminal proxy, not the exact monotonic deadline; timestamp comparison is approximate.",
        "Completed-call logs omit any unfinished final call and cannot prove a dispatch boundary existed at 120 seconds remaining.",
        "Static methods establish potential hook sites, not safe semantics for a new dispatch-time policy.",
    ],
},sort_keys=True))
'''


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G2 timeout dispatch sidecar already exists")
    proc = subprocess.run(SSH, input=REMOTE_CODE, text=True, encoding="utf-8",
                          capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"G2 timeout dispatch extraction failed: exit {proc.returncode}; "
                           f"stderr={proc.stderr[-1200:]}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G2 dispatch SSH did not start with disk check")
    result = json.loads(lines[-1])
    if result.get("timeout_case_count") != 2:
        raise RuntimeError("G2 dispatch extraction count differs")
    write_new(OUT, result)
    print(json.dumps({"status": "collected", "sidecar_sha256": sha(OUT),
                      "cases": result["cases"], "static_boundaries": result["static_boundaries"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
