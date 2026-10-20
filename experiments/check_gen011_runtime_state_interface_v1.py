"""Model-free check that a Gen11 candidate's declared state exists on its Agent.

Run only after the independent Meta source preflight. This checks the actual
installed candidate wrapper with synthetic tools, without a benchmark task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.intent_candidate_workspace import source_tree_hash

SCRIPT = r'''
import copy,json,tempfile
from pathlib import Path
from tests.test_dab_progress_contract_delivery import installed_agent
from experiments.dab_progress_contract import runtime_state_contract
repo=Path.cwd()
report=json.loads((repo/'candidate_workspace_report.json').read_bytes())
declared=report['runtime_state_contract']
assert declared==runtime_state_contract(),'report and source contracts differ'
fields=declared['persistent_fields']
assert isinstance(fields,list) and len(fields)<=100
with tempfile.TemporaryDirectory(dir=str(repo/'.meta_tmp')) as folder:
    source=installed_agent(Path(folder))
    target=installed_agent(Path(folder))
    for field in fields:
        name,kind=field['name'],field['type']
        assert hasattr(source,name),'Actual candidate field missing: '+name
        value=copy.deepcopy(getattr(source,name))
        if kind=='string_set':
            assert isinstance(value,set) and all(isinstance(x,str) for x in value),name
        else:
            assert kind=='json',name
            json.dumps(value,allow_nan=True)
        setattr(target,name,copy.deepcopy(value))
        assert getattr(target,name)==value,'State did not round-trip: '+name
    runtime_verified=False
    if (repo/'experiments/dab_deepseek_candidate_runtime_v2.py').is_file():
        from experiments import dab_deepseek_candidate_runtime_v2 as runtime
        runtime.CONTRACT=runtime.validate_contract(declared)
        packed=runtime.pack(source)
        runtime.restore_fields(target,packed)
        assert runtime.pack(target)==packed,'Runtime pack/restore differs'
        runtime_verified=True
print(json.dumps({'passed':True,'declared_fields':len(fields),'actual_agent_fields_verified':len(fields),'runtime_pack_restore_verified':runtime_verified,'synthetic_agent_only':True,'model_calls':0,'database_calls':0}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    if not (repo / 'candidate_workspace_report.json').is_file() or not (
        repo / 'tests/test_dab_progress_contract_delivery.py').is_file():
        raise RuntimeError('Candidate source or synthetic fixture missing')
    temporary = repo / '.meta_tmp'
    temporary.mkdir(exist_ok=True)
    env = os.environ.copy()
    for key in ('DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'CRS_API_KEY',
                'DAB_RESEARCH_API_CONFIG', 'PYTHONPATH'):
        env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary))
    run = subprocess.run([sys.executable, '-B', '-c', SCRIPT], cwd=repo,
                         env=env, capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=90)
    result = {'schema': 'gen011_candidate_runtime_state_interface_v1',
              'passed': run.returncode == 0,
              'candidate_source_sha256': source_tree_hash(repo),
              'candidate_report_sha256': hashlib.sha256(
                  (repo / 'candidate_workspace_report.json').read_bytes()).hexdigest(),
              'returncode': run.returncode,
              'stdout': run.stdout[-1500:], 'stderr': run.stderr[-2500:],
              'model_calls': 0, 'database_calls': 0}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
