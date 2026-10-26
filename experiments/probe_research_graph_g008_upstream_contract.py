#!/usr/bin/env python3
"""Task-free G8 return_answer contract check against the installed DAB class."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "experiments/research_graph_baseline_20261016/g008_candidate_002/repo/experiments/g008_verification_audit_sidecar.py"
SSH = [
    "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
]
REMOTE_CODE = r'''
import json,logging,sys,tempfile,types
from pathlib import Path
from types import SimpleNamespace

source=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g007_revision001/source')
sys.path.insert(0,str(source))
sys.path.insert(0,'/srv/text2sql/external/DataAgentBench_official')
from common_scaffold import DataAgent as upstream_module

module_name='experiments.g008_verification_audit_sidecar'
module=types.ModuleType(module_name)
module.__package__='experiments'
module.__file__='<g008_candidate_in_memory>'
sys.modules[module_name]=module
exec(compile(sys.stdin.buffer.read(),module.__file__,'exec'),module.__dict__)
assert module.SCHEMA_VERSION=='g008_verification_audit_sidecar_v001'

class Tool:
    def exec(self,args):
        return {'success':True,'result':{'synthetic':True}}

class Call:
    def __init__(self,identifier,name,arguments):
        self.id=identifier
        self.function=type('Function',(),{'name':name,'arguments':arguments})()
    def model_dump(self):
        return {'id':self.id,'type':'function','function':{
            'name':self.function.name,'arguments':self.function.arguments}}

class Response:
    def __init__(self,call):
        self.tool_calls=[call]
        self.content=None

with tempfile.TemporaryDirectory(prefix='g008_upstream_contract_') as location:
    sidecar=Path(location)/module.SIDECAR_FILENAME
    module.install_verification_audit(
        upstream_module,
        SimpleNamespace(g008_verification_audit=True,g008_sidecar_path=sidecar),
    )
    agent=upstream_module.DataAgent.__new__(upstream_module.DataAgent)
    agent.logger=logging.getLogger('g008_upstream_contract')
    agent.tools={'return_answer':Tool(),'synthetic_tool':Tool()}
    agent.messages=[]
    agent.result_storage={}
    agent.file_storage_dir=Path(location)
    agent.tool_log_path=Path(location)/'tool_calls.jsonl'
    agent.final_result=None
    agent.terminate_reason=None
    agent.llm_call_count=1
    agent.max_iterations=5
    sentinel='SYNTHETIC_ANSWER_SENTINEL'
    agent.handle_reponse(Response(Call('first','return_answer',json.dumps({'answer':sentinel}))))
    assert agent.final_result is None
    assert [row['role'] for row in agent.messages]==['assistant','tool']
    assert agent.messages[-1]['tool_call_id']=='first'
    assert agent.messages[-1]['content']==module.AUDIT_PROMPT
    assert agent.result_storage=={}
    agent.llm_call_count=2
    agent.handle_reponse(Response(Call('second','return_answer',json.dumps({'answer':sentinel}))))
    assert agent.final_result==sentinel and agent.terminate_reason=='return_answer'
    assert [row['role'] for row in agent.messages]==['assistant','tool','assistant','tool']
    assert agent.messages[-1]['tool_call_id']=='second'
    recorder=agent._g008_verification_audit_recorder
    assert recorder.write_task_summary(terminate_reason=agent.terminate_reason)
    parsed=module.read_sidecar(sidecar)
    assert parsed['exists'] and parsed['forbidden_field_count']==0
    assert not parsed['schema_violation'] and len(parsed['rows'])==3
    assert sentinel not in sidecar.read_text(encoding='utf-8')
    assert all(set(row)==module.FROZEN_SCHEMA_FIELDS for row in parsed['rows'])
print(json.dumps({'status':'g008_synthetic_upstream_hook_contract_passed',
                  'first_intercepted':True,'later_dispatched':True,
                  'tool_call_ids_paired':True,'answer_content_persisted':False,
                  'task_content_used':False},sort_keys=True))
'''


def main() -> None:
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f'"exec(__import__(\'base64\').b64decode(\'{code}\'))"'
    )
    result = subprocess.run(SSH + [remote], input=HOOK.read_bytes(),
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2000:])
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("Remote probe lacked leading disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
