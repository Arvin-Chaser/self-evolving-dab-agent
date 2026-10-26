#!/usr/bin/env python3
"""Record the v1 preflight-shape incident and deploy G11 launcher v2."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/launch_research_graph_g011_solution_loop_v2.py"
SSH = [
    "ssh",
    "-i",
    "C:/Users/34934/.ssh/codex_ct104",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "root@100.83.10.33",
]
REMOTE_CODE = r'''
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
base=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
bindings=base/'g011_solution_loop_revision001/bindings'
v1=bindings/'launch_research_graph_g011_solution_loop_v1.py'
target=bindings/'launch_research_graph_g011_solution_loop_v2.py'
incident=bindings/'preflight_incident_001.json'
v1_sha='227017ed908c0440e812ab6c046a10567d6c545f8f4ff15b9f46e4218ff7ad8a'
if not v1.is_file() or hashlib.sha256(v1.read_bytes()).hexdigest()!=v1_sha:
    raise RuntimeError('G11 launcher v1 binding differs')
if target.exists() or incident.exists():
    raise RuntimeError('G11 launcher v2 or incident already exists')
payload=sys.stdin.buffer.read()
if not payload:
    raise RuntimeError('G11 launcher v2 payload empty')
incident_payload={
    'schema_version':'g011_solution_loop_preflight_incident_v1',
    'created_at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'preflight_failed_no_claim_no_evaluation',
    'launcher_v1_sha256':v1_sha,
    'stage':'live_provider_carrier_probe',
    'failure_class':'provider_request_shape_incompatible',
    'http_status':400,
    'safe_detail':'deepseek thinking mode rejected named or required tool_choice; no benchmark task content was sent',
    'basic_model_probe_passed_before_failure':True,
    'real_upstream_no_task_probe_passed_before_failure':True,
    'formal_claim_created':False,
    'formal_evaluation_started':False,
    'resolution':'versioned launcher v2 removes unsupported tool_choice and retains the same no-task carrier validation',
}
with incident.open('x',encoding='utf-8') as stream:
    json.dump(incident_payload,stream,sort_keys=True,indent=2)
    stream.write('\n')
with target.open('xb') as stream:
    stream.write(payload)
print(json.dumps({'status':'launcher_v2_deployed','sha256':hashlib.sha256(payload).hexdigest(),'incident_sha256':hashlib.sha256(incident.read_bytes()).hexdigest()},sort_keys=True))
'''


def main() -> None:
    payload = SOURCE.read_bytes()
    wanted = hashlib.sha256(payload).hexdigest()
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f'"exec(__import__(\'base64\').b64decode(\'{code}\'))"'
    )
    result = subprocess.run(SSH + [remote], input=payload, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-1600:])
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G11 launcher v2 deployment lacked leading disk check")
    outcome = json.loads(lines[-1])
    if outcome.get("sha256") != wanted:
        raise RuntimeError("G11 launcher v2 transfer hash differs")
    print(json.dumps(outcome, sort_keys=True))


if __name__ == "__main__":
    main()
