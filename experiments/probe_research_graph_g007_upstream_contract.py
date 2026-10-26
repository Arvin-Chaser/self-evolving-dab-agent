#!/usr/bin/env python3
"""Task-free G7 sidecar check against the installed DAB dispatch method."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "experiments/research_graph_baseline_20261016/g007_candidate_002/repo/experiments/g007_last_pre_exec_sidecar.py"
SSH = [
    "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
]
REMOTE_CODE = r'''
import json,logging,sys,tempfile,types
from pathlib import Path
from types import SimpleNamespace

source=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g006_revision001/source')
sys.path.insert(0,str(source))
sys.path.insert(0,'/srv/text2sql/external/DataAgentBench_official')
from common_scaffold import DataAgent as upstream_module

module_name='experiments.g007_last_pre_exec_sidecar'
module=types.ModuleType(module_name)
module.__package__='experiments'
module.__file__='<g007_candidate_in_memory>'
sys.modules[module_name]=module
exec(compile(sys.stdin.buffer.read(),module.__file__,'exec'),module.__dict__)
assert module.SCHEMA_VERSION=='g007_last_pre_exec_sidecar_v001'

class Tool:
    def exec(self,args):
        return {'success':True,'result':{'synthetic':args['value']}}

class Call:
    def __init__(self,identifier,name,arguments):
        self.id=identifier
        self.function=type('Function',(),{'name':name,'arguments':arguments})()
    def model_dump(self):
        return {'id':self.id,'function':{'name':self.function.name}}

with tempfile.TemporaryDirectory(prefix='g007_upstream_contract_') as location:
    sidecar=Path(location)/module.SIDECAR_FILENAME
    module.install_last_pre_exec_sidecar(
        upstream_module,
        SimpleNamespace(g007_last_pre_exec_sidecar=True,g007_sidecar_path=sidecar,
                        disable_self_observation_tool=True,
                        disable_evolved_helper_tools=True),
    )
    agent=upstream_module.DataAgent.__new__(upstream_module.DataAgent)
    agent.logger=logging.getLogger('g007_upstream_contract')
    agent.tools={'synthetic_tool':Tool()}
    agent.messages=[]
    agent.result_storage={}
    agent.file_storage_dir=Path(location)
    agent.tool_log_path=Path(location)/'tool_calls.jsonl'
    agent.final_result=None
    agent.terminate_reason=None
    assert agent._handle_tool_call(Call('positive','synthetic_tool','{"value":7}')) is None
    assert agent.result_storage=={'var_positive':{'synthetic':7}}
    assert agent.messages[-1]['name']=='synthetic_tool'
    before=dict(agent.result_storage)
    assert agent._handle_tool_call(Call('malformed','synthetic_tool','{invalid')) is None
    assert agent.result_storage==before
    assert agent.messages[-1]['tool_call_id']=='malformed'
    assert agent._handle_tool_call(Call('unknown','nonexistent_tool','{}')) is None
    assert agent.result_storage==before
    assert agent.messages[-1]['tool_call_id']=='unknown'
    rows=module.read_sidecar(sidecar)
    assert rows['exists'] is True and len(rows['events'])==6
    assert rows['forbidden_field_count']==0 and not rows['schema_violation']
    raw=sidecar.read_text(encoding='utf-8')
    assert all(sentinel not in raw for sentinel in (
        'synthetic_tool','nonexistent_tool','value','malformed','positive'))
print(json.dumps({'status':'g007_synthetic_upstream_hook_contract_passed',
                  'positive_writeback':True,'malformed_and_unknown_fail_safe':True,
                  'sidecar_events':6,'task_content_used':False},sort_keys=True))
'''


def main() -> None:
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f'"exec(__import__(\'base64\').b64decode(\'{code}\'))"'
    )
    result = subprocess.run(SSH + [remote], input=SIDECAR.read_bytes(),
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2000:])
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("Remote probe lacked leading disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
