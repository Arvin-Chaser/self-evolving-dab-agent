#!/usr/bin/env python3
"""Archive the frozen G3 Meta extractor without changing candidate source."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/research_graph_baseline_20261016/g003_evidence_impl_meta_001/workspace/evidence_extractor.py'
DESTINATION = '/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph/g003_evidence_extractor_v1.py'
EXPECTED_SHA = '8d0567ba5b83154abdd01c4f1f862fbbf06385084a8af1e8fe4a151807c32dd8'


def main() -> None:
    payload = SOURCE.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_SHA:
        raise RuntimeError('G3 Meta extractor changed after verification')
    encoded = base64.b64encode(payload).decode('ascii')
    remote = (
        'import base64, hashlib, json\n'
        'from pathlib import Path\n'
        f'path = Path({DESTINATION!r})\n'
        f'expected = {EXPECTED_SHA!r}\n'
        f'data = base64.b64decode({encoded!r})\n'
        'if path.exists() or hashlib.sha256(data).hexdigest() != expected:\n'
        '    raise RuntimeError("G3 extractor exists or transfer hash differs")\n'
        'with path.open("xb") as stream:\n'
        '    stream.write(data)\n'
        'print(json.dumps({"status": "extractor_archived", "sha256": '
        'hashlib.sha256(path.read_bytes()).hexdigest()}, sort_keys=True))\n'
    )
    command = [
        'ssh', '-i', 'C:/Users/34934/.ssh/codex_ct104',
        '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
        'root@100.83.10.33',
        'df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -',
    ]
    result = subprocess.run(command, input=remote, text=True, encoding='utf-8',
                            capture_output=True, check=False)
    print(result.stdout, end='')
    if result.returncode:
        raise RuntimeError('G3 extractor archive failed without replacing existing files')


if __name__ == '__main__':
    main()
