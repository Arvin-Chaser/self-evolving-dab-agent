#!/usr/bin/env python3
"""Probe the staged G3 wrapper against the actual upstream dispatch method."""

from __future__ import annotations

import json
import subprocess


SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o",
       "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]
REMOTE = r'''
import json,logging,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
source=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g003_revision001/source")
sys.path.insert(0,str(source))
from experiments.run_dab_tool_agent import import_upstream_data_agent,install_self_observation_tool
from experiments.g003_proposed_call_diagnostic import ProposedCallRecorder
upstream=Path("/srv/text2sql/external/DataAgentBench_official")
module=__import__("importlib").import_module("common_scaffold.DataAgent") if str(upstream) in sys.path else None
if module is None:
    import_upstream_data_agent(upstream)
    module=__import__("importlib").import_module("common_scaffold.DataAgent")
Original=module.DataAgent
install_self_observation_tool(module,SimpleNamespace(disable_self_observation_tool=False))
Wrapped=module.DataAgent
class Tool:
    def exec(self,args):
        return {"success":args.get("value")!=0,"result":{"ok":args.get("value")!=0}}
class Call:
    def __init__(self,identifier,name,arguments):
        self.id=identifier
        self.function=SimpleNamespace(name=name,arguments=arguments)
    def model_dump(self):
        return {"id":self.id,"function":{"name":self.function.name,
                                         "arguments":self.function.arguments}}
def setup(cls,root):
    agent=cls.__new__(cls)
    agent.logger=logging.getLogger("g3_probe")
    agent.messages=[]
    agent.tools={"query_db":Tool(),"return_answer":Tool()}
    agent.final_result=None
    agent.terminate_reason=None
    agent.result_storage={}
    agent.file_storage_dir=root
    agent.tool_log_path=root/"tool_calls.jsonl"
    if cls is Wrapped:
        agent._g003_proposed_calls=ProposedCallRecorder(root/"g003_proposed_calls.jsonl")
    return agent
calls=[Call("one","query_db",'{"value":1}'),
       Call("two","query_db",'{"value":0}'),
       Call("three","query_db",'{"value":1}'),
       Call("four","query_db","{broken"),
       Call("five","absent_tool","{}"),
       Call("six","return_answer",'{"answer":"synthetic","value":1}')]
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory)
    original_dir=base/"original"; wrapped_dir=base/"wrapped"
    original_dir.mkdir();wrapped_dir.mkdir()
    original=setup(Original,original_dir)
    wrapped=setup(Wrapped,wrapped_dir)
    for call in calls:
        left=original._handle_tool_call(call)
        right=wrapped._handle_tool_call(call)
        if left!=right:
            raise RuntimeError("G3 wrapper return differs from upstream")
    for field in ("messages","final_result","terminate_reason","result_storage"):
        if getattr(original,field)!=getattr(wrapped,field):
            raise RuntimeError("G3 wrapper changed upstream state: "+field)
    sidecar=wrapped_dir/"g003_proposed_calls.jsonl"
    rows=[json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    allowed={"step_index","signal_category","repeat_count","eligible_step_count","coverage_status"}
    if (len(rows)!=len(calls) or any(set(row)!=allowed for row in rows) or
        [row["signal_category"] for row in rows]!=
        ["nonrepeat","nonrepeat","repeat","unknown","nonrepeat","nonrepeat"]):
        raise RuntimeError("G3 structural sidecar differs")
    print(json.dumps({"status":"upstream_dispatch_equivalent",
                      "positive_and_negative_calls":len(calls),
                      "sidecar_records":len(rows),"raw_content_exported":False},sort_keys=True))
'''


def main() -> None:
    proc = subprocess.run(SSH, input=REMOTE, text=True, encoding="utf-8",
                          capture_output=True, timeout=60, check=False)
    if proc.returncode:
        raise RuntimeError(f"G3 upstream probe failed: {proc.returncode}: " + proc.stderr[-1200:])
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G3 upstream probe did not start with disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
