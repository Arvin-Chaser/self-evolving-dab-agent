#!/usr/bin/env python3
"""Deploy the hash-bound G10 launcher to its isolated binding directory."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/launch_research_graph_g010.py"
SSH = [
    "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes", "root@100.83.10.33",
]
REMOTE_CODE = r'''
import hashlib,json,sys
from pathlib import Path
base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
target=base/"g010_revision001/bindings/launch_research_graph_g010_v2.py"
if not (base/"g010_revision001/bindings/admission.json").is_file():
    raise RuntimeError("G10 staged admission missing")
payload=sys.stdin.buffer.read()
if not payload or target.exists():
    raise RuntimeError("G10 launcher empty or already deployed")
with target.open("xb") as stream:
    stream.write(payload)
print(json.dumps({"status":"launcher_deployed","sha256":hashlib.sha256(payload).hexdigest()},sort_keys=True))
'''


def main() -> None:
    payload = SOURCE.read_bytes()
    wanted = hashlib.sha256(payload).hexdigest()
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f"\"exec(__import__('base64').b64decode('{code}'))\""
    )
    result = subprocess.run(SSH + [remote], input=payload, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-1200:])
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G10 launcher deployment lacked leading disk check")
    outcome = json.loads(lines[-1])
    if outcome["sha256"] != wanted:
        raise RuntimeError("G10 launcher transfer hash differs")
    print(json.dumps(outcome, sort_keys=True))


if __name__ == "__main__":
    main()
