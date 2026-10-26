#!/usr/bin/env python3
"""Task-free G11 gate check against the installed DataAgent interface."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/research_graph_baseline_20261016/g011_candidate_001/repo/experiments"
SSH = [
    "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
]
REMOTE_CODE = r'''
import json,logging,sys,tempfile,types
from pathlib import Path
from types import SimpleNamespace

parent=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g009_revision001/source')
sys.path.insert(0,str(parent))
sys.path.insert(0,'/srv/text2sql/external/DataAgentBench_official')
from common_scaffold import DataAgent as upstream
from experiments import g008_verification_audit_sidecar as g8
from experiments import g009_verification_turn_gate_sidecar as g9

module=types.ModuleType('experiments.g011_minimum_evidence_gate_sidecar')
module.__package__='experiments'
module.__file__='<g011_candidate_in_memory>'
sys.modules[module.__name__]=module
exec(compile(sys.stdin.read(),module.__file__,'exec'),module.__dict__)
g11=module
assert g11.SCHEMA_VERSION=='g011_minimum_evidence_gate_sidecar_v001'

class Tool:
    def __init__(self): self.calls=0
    def exec(self,args):
        self.calls+=1
        return {'success':True,'result':{'synthetic':True}}

class Call:
    def __init__(self,identifier,name,arguments):
        self.id=identifier
        self.function=type('Function',(),{'name':name,'arguments':arguments})()
    def model_dump(self):
        return {'id':self.id,'type':'function','function':{
            'name':self.function.name,'arguments':self.function.arguments}}

class Response:
    def __init__(self,calls):
        self.tool_calls=calls
        self.content=None

with tempfile.TemporaryDirectory(prefix='g011_upstream_contract_') as location:
    folder=Path(location)
    g8.install_verification_audit(upstream,SimpleNamespace(
        g008_verification_audit=True,g008_sidecar_path=folder/g8.SIDECAR_FILENAME))
    args=SimpleNamespace(g009_verification_turn_gate=True,
                         g009_sidecar_path=folder/g9.SIDECAR_FILENAME,
                         g011_minimum_evidence_gate=True,
                         g011_sidecar_path=folder/g11.SIDECAR_FILENAME)
    g9.install_verification_turn_gate(upstream,args)
    g11.install_minimum_evidence_gate(upstream,args)

    def agent():
        value=upstream.DataAgent.__new__(upstream.DataAgent)
        value.logger=logging.getLogger('g011_upstream_contract')
        value.tools={'return_answer':Tool(),'synthetic_tool':Tool()}
        value.messages=[]
        value.result_storage={}
        value.file_storage_dir=folder
        value.tool_log_path=folder/'tool_calls.jsonl'
        value.final_result=None
        value.terminate_reason=None
        value.llm_call_count=1
        value.max_iterations=8
        value._g008_verification_audit_recorder=g8.VerificationAuditRecorder(
            folder/g8.SIDECAR_FILENAME,enabled=True)
        return value

    sentinel='SYNTHETIC_ANSWER_SENTINEL'
    zero=agent()
    zero.handle_reponse(Response([
        Call('first','return_answer',json.dumps({'answer':sentinel})),
        Call('same','return_answer',json.dumps({'answer':sentinel})),
    ]))
    assert zero.final_result is None and zero.result_storage=={}
    assert [row['tool_call_id'] for row in zero.messages[1:]]==['first','same']
    assert zero.messages[1]['content']==g11.GATE_PROMPT
    assert zero.messages[2]['content']==g11.SAME_RESPONSE_SUPPRESSION_PROMPT
    zero.llm_call_count=2
    zero.handle_reponse(Response([Call('tool','synthetic_tool','{}')]))
    assert zero.tools['synthetic_tool'].calls==1
    zero.llm_call_count=3
    zero.handle_reponse(Response([Call('later','return_answer',json.dumps({'answer':sentinel}))]))
    assert zero.final_result==sentinel and zero.terminate_reason=='return_answer'
    recorder=zero._g011_minimum_evidence_gate_recorder
    assert recorder.write_task_summary(terminate_reason=zero.terminate_reason)
    parsed=g11.read_sidecar(folder/g11.SIDECAR_FILENAME)
    assert parsed['exists'] and not parsed['schema_violation']
    assert parsed['forbidden_field_count']==0
    assert sentinel not in (folder/g11.SIDECAR_FILENAME).read_text(encoding='utf-8')
    assert all(set(row)==g11.FROZEN_SCHEMA_FIELDS for row in parsed['rows'])

    positive=agent()
    positive.handle_reponse(Response([Call('pre','synthetic_tool','{}')]))
    assert positive.tools['synthetic_tool'].calls==1
    positive.llm_call_count=2
    positive.handle_reponse(Response([Call('positive','return_answer',json.dumps({'answer':sentinel}))]))
    assert positive.final_result is None
    assert positive.messages[-1]['content']==g9.AUDIT_PROMPT
    positive.llm_call_count=3
    positive.handle_reponse(Response([Call('positive-later','return_answer',json.dumps({'answer':sentinel}))]))
    assert positive.final_result==sentinel
print(json.dumps({'status':'g011_synthetic_upstream_hook_contract_passed',
                  'zero_count_gate':True,'positive_count_parent_path':True,
                  'same_response_suppressed':True,'later_turn_dispatched':True,
                  'answer_content_persisted':False,'task_content_used':False},sort_keys=True))
'''


def main() -> None:
    payload = (SOURCE / "g011_minimum_evidence_gate_sidecar.py").read_bytes()
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f'"exec(__import__(\'base64\').b64decode(\'{code}\'))"'
    )
    result = subprocess.run(SSH + [remote], input=payload, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2000:])
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("Remote probe lacked leading disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
