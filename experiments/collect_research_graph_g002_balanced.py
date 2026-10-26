#!/usr/bin/env python3
"""Collect all G2 outcome cohorts as hash-bound, answer-blind structural counts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from experiments.run_research_graph_g001_meta_v2 import sha, write_new


BASE = Path(__file__).resolve().parents[1] / "experiments/research_graph_baseline_20261016"
OUT = BASE / "g002_balanced_behavior_v1.json"
GRAPH_SHA = "38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54"
SUMMARY_SHA = "d18d1650670d5ed362c3a0920053e60f9243adbb3cafb4e3375ad11cf50ddd02"
MANIFEST_SHA = "bd8083f263254fff2e4e8cfa68bc577220928fecd0809ed88c1a781df02003f1"
COHORTS = ("strict_pass", "strict_fail", "strict_unknown", "timeout_failure")
METRICS = ("tasks", "traces", "llm_requests", "llm_responses", "tool_calls",
           "tool_failures", "tasks_with_tool_failure", "tasks_with_no_tool_call",
           "return_answer_calls", "tasks_with_return_answer")
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]

REMOTE_CODE = r'''
import hashlib,json
from collections import Counter
from pathlib import Path

base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
run=base/"g002_revision001/evaluation/baseline_g002_lifecycle_nohint_56_v1"
graph=base/"graph/g002_graph.json"
summary=run/"multi_query_summary.json"
manifest=base/"graph/g002_trace_manifest.json"
expected={
    graph:"38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54",
    summary:"d18d1650670d5ed362c3a0920053e60f9243adbb3cafb4e3375ad11cf50ddd02",
    manifest:"bd8083f263254fff2e4e8cfa68bc577220928fecd0809ed88c1a781df02003f1",
}
def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

if any(digest(path)!=value for path,value in expected.items()):
    raise RuntimeError("Frozen G2 source hash differs")
g=json.loads(graph.read_text(encoding="utf-8"))
s=json.loads(summary.read_text(encoding="utf-8"))
m=json.loads(manifest.read_text(encoding="utf-8"))
e=g["nodes"][-1]
rows=s["per_query_feedback"]
entries=m["entries"]
if (g.get("status")!="four_nodes_complete" or e.get("kind")!="evidence" or
        len(rows)!=56 or len(entries)!=56):
    raise RuntimeError("G2 frozen coverage differs")

names={"list_db","query_db","return_answer","execute_python","get_schema"}
metrics={name:Counter() for name in
         ("strict_pass","strict_fail","strict_unknown","timeout_failure")}
tool_failures=Counter()
for index,(row,entry) in enumerate(zip(rows,entries)):
    status=row["status"]
    if status=="timeout":
        group="timeout_failure"
    elif status=="completed":
        verdict=row.get("strict_match_passed")
        group="strict_pass" if verdict is True else "strict_fail" if verdict is False else "strict_unknown"
    else:
        raise RuntimeError("Unexpected G2 terminal status")
    if entry["batch_index"]!=index or entry["terminal_status"]!=status:
        raise RuntimeError("Trace manifest order or status differs")
    stats=metrics[group]
    stats["tasks"]+=1
    run_dir=Path(row["run_dir"]).resolve()
    if not run_dir.is_relative_to(run.resolve()):
        raise RuntimeError("Task run path escapes G2 run")
    trace=run_dir/"full_execution_trace.jsonl"
    if status=="timeout":
        if trace.is_file() or entry.get("trace_sha256") is not None:
            raise RuntimeError("Unexpected timeout full trace")
        continue
    if not trace.is_file() or digest(trace)!=entry["trace_sha256"]:
        raise RuntimeError("Completed trace path or hash differs")
    stats["traces"]+=1
    events=Counter()
    task_failures=0
    terminal_calls=0
    with trace.open(encoding="utf-8") as stream:
        for line in stream:
            event=json.loads(line)
            kind=event.get("event_type")
            if kind not in {"llm_request","llm_response","tool_call_start","tool_call_end","agent_termination"}:
                raise RuntimeError("Unexpected event type")
            events[kind]+=1
            if kind=="tool_call_end":
                name=event.get("tool_name")
                name=name if name in names else "other_tool"
                if name=="return_answer":
                    terminal_calls+=1
                if event.get("success") is not True:
                    tool_failures[name]+=1
                    task_failures+=1
            # Messages, arguments, results, answer text, and validator data are never accessed.
    if events["tool_call_start"]!=events["tool_call_end"] or events["agent_termination"]!=1:
        raise RuntimeError("Completed trace structural closure differs")
    stats["llm_requests"]+=events["llm_request"]
    stats["llm_responses"]+=events["llm_response"]
    stats["tool_calls"]+=events["tool_call_end"]
    stats["tool_failures"]+=task_failures
    stats["tasks_with_tool_failure"]+=int(task_failures>0)
    stats["tasks_with_no_tool_call"]+=int(events["tool_call_end"]==0)
    stats["return_answer_calls"]+=terminal_calls
    stats["tasks_with_return_answer"]+=int(terminal_calls>0)

if ([(name,metrics[name]["tasks"]) for name in metrics]!=
        [("strict_pass",30),("strict_fail",21),("strict_unknown",3),("timeout_failure",2)] or
        sum(value["traces"] for value in metrics.values())!=54 or
        e["strict_pass_count"]!=30 or e["timeout_failure_count"]!=2 or
        e["strict_verdict_missing_completed_count"]!=3):
    raise RuntimeError("G2 cohort counts differ from frozen Evidence")
print(json.dumps({
    "schema_version":"g002_balanced_behavior_answer_blind_v1",
    "answer_blind":True,
    "source_hashes":{"g2_graph_sha256":digest(graph),
                     "g2_summary_sha256":digest(summary),
                     "g2_trace_manifest_sha256":digest(manifest)},
    "frozen_task_count":56,
    "cohorts":{name:dict(metrics[name]) for name in metrics},
    "tool_failures_by_name":dict(tool_failures),
    "limitations":[
        "Tool success flags do not identify causal obstruction or answer correctness.",
        "Two timeout tasks lack full normalized traces; this sidecar does not infer their final in-flight work.",
        "Three completed strict verdicts remain unknown within the fixed denominator.",
        "Between-generation outcome changes are from unpaired runs and are not causal effects.",
    ],
},sort_keys=True))
'''


def validate_output(value: dict) -> None:
    if (set(value) != {"schema_version", "answer_blind", "source_hashes",
                       "frozen_task_count", "cohorts", "tool_failures_by_name",
                       "limitations"} or
            value["schema_version"] != "g002_balanced_behavior_answer_blind_v1" or
            value["answer_blind"] is not True or value["frozen_task_count"] != 56 or
            value["source_hashes"] != {
                "g2_graph_sha256": GRAPH_SHA, "g2_summary_sha256": SUMMARY_SHA,
                "g2_trace_manifest_sha256": MANIFEST_SHA,
            } or set(value["cohorts"]) != set(COHORTS)):
        raise RuntimeError("G2 balanced output schema or frozen binding differs")
    for name, expected in zip(COHORTS, (30, 21, 3, 2)):
        row = value["cohorts"][name]
        if (not isinstance(row, dict) or not set(row) <= set(METRICS) or
                row.get("tasks") != expected or
                any(type(count) is not int or count < 0 or count > 100000
                    for count in row.values()) or
                row.get("traces", 0) != (0 if name == "timeout_failure" else expected) or
                row.get("tasks_with_tool_failure", 0) > expected or
                row.get("tasks_with_no_tool_call", 0) > expected or
                row.get("tasks_with_return_answer", 0) > expected or
                row.get("tool_failures", 0) > row.get("tool_calls", 0) or
                row.get("return_answer_calls", 0) > row.get("tool_calls", 0)):
            raise RuntimeError("G2 balanced cohort counts differ")
    allowed = {"list_db", "query_db", "return_answer", "execute_python",
               "get_schema", "other_tool"}
    if (not isinstance(value["tool_failures_by_name"], dict) or
            any(name not in allowed or type(count) is not int or count < 0
                for name, count in value["tool_failures_by_name"].items()) or
            sum(value["tool_failures_by_name"].values()) !=
            sum(value["cohorts"][name].get("tool_failures", 0) for name in COHORTS) or
            not isinstance(value["limitations"], list) or
            any(not isinstance(item, str) or not item.strip() or
                re.search(r"(?:query_id|answer_text|raw_message)", item, re.I)
                for item in value["limitations"])):
        raise RuntimeError("G2 balanced output contains an unsafe aggregate")


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G2 balanced sidecar already exists")
    proc = subprocess.run(SSH, input=REMOTE_CODE, text=True, encoding="utf-8",
                          capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"G2 balanced extraction failed: exit {proc.returncode}; "
                           f"stderr={proc.stderr[-700:]}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G2 SSH did not start with disk check")
    result = json.loads(lines[-1])
    validate_output(result)
    write_new(OUT, result)
    print(json.dumps({"status": "collected", "sidecar_sha256": sha(OUT),
                      "cohort_task_counts": {name: result["cohorts"][name]["tasks"]
                                             for name in COHORTS}}, sort_keys=True))


if __name__ == "__main__":
    main()
