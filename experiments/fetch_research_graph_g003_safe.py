#!/usr/bin/env python3
"""Fetch only verified, answer-blind G3 Graph and Evidence for the next Meta."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/research_graph_baseline_20261016/g003_safe_snapshot'
REMOTE = '/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph'
EXPECTED = {
    'g003_graph.json': '039fc4fbc51410d87f7adc6e0c9017fb963d7979e9b10bce22f1c38949e67f29',
    'g003_evidence.json': 'f43459e0776f847b121e00417764a8963d24af06766d31737b278e04590ec5a7',
    'g003_specialized_evidence_attempt002_v2.json': '45e2ef06a60783a5d5de2a37f81003a2113573f66aca976cee34288d2018283c',
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError('G3 safe snapshot already exists')
    remote_code = (
        'import base64, hashlib, json\n'
        'from pathlib import Path\n'
        f'base = Path({REMOTE!r})\n'
        f'expected = {EXPECTED!r}\n'
        'files = {}\n'
        'for name, digest in expected.items():\n'
        '    data = (base / name).read_bytes()\n'
        '    if hashlib.sha256(data).hexdigest() != digest:\n'
        '        raise RuntimeError("G3 safe artifact hash differs")\n'
        '    files[name] = base64.b64encode(data).decode("ascii")\n'
        'print(json.dumps(files, sort_keys=True))\n'
    )
    command = ['ssh', '-i', 'C:/Users/34934/.ssh/codex_ct104',
               '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               'root@100.83.10.33',
               'df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -']
    result = subprocess.run(command, input=remote_code, text=True, encoding='utf-8',
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('G3 safe snapshot transfer failed')
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError('G3 safe snapshot file set differs')
    files = {name: base64.b64decode(encoded) for name, encoded in payload.items()}
    if any(hashlib.sha256(files[name]).hexdigest() != digest
           for name, digest in EXPECTED.items()):
        raise RuntimeError('G3 local safe snapshot hash differs')
    for data in files.values():
        value = json.loads(data)
        if not isinstance(value, dict):
            raise RuntimeError('G3 safe snapshot is not a JSON object')
    OUT.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open('xb') as stream:
            stream.write(data)
    print(json.dumps({'status': 'safe_snapshot_fetched',
                      'hashes': EXPECTED}, sort_keys=True))


if __name__ == '__main__':
    main()
