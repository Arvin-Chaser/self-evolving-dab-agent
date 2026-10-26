#!/usr/bin/env python3
"""Stage the verified G3 launcher in the existing isolated binding directory."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "experiments/launch_research_graph_g003.py"
EXPECTED = "98abce2d519a40317f82f77689b6ffc28cfac5646cd2a80d769fb3ae5d1c8118"
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o",
       "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33"]
REMOTE_CODE = r'''
import hashlib,json,sys
from pathlib import Path
base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
g3=base/"g003_revision001"
path=g3/"bindings/launch_research_graph_g003.py"
data=sys.stdin.buffer.read()
if hashlib.sha256(data).hexdigest()!="98abce2d519a40317f82f77689b6ffc28cfac5646cd2a80d769fb3ae5d1c8118":
    raise RuntimeError("G3 launcher transfer hash differs")
if not (g3/"source").is_dir() or not path.parent.is_dir() or path.exists():
    raise RuntimeError("G3 source or bindings absent, or launcher already staged")
with path.open("xb") as stream:
    stream.write(data)
print(json.dumps({"status":"launcher_staged","sha256":hashlib.sha256(path.read_bytes()).hexdigest()},sort_keys=True))
'''


def main() -> None:
    data = LAUNCHER.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise RuntimeError("Local G3 launcher changed")
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = ("df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
              f"\"exec(__import__('base64').b64decode('{code}'))\"")
    proc = subprocess.run(SSH + [remote], input=data, capture_output=True,
                          timeout=30, check=False)
    if proc.returncode:
        raise RuntimeError(f"G3 launcher stage failed: {proc.returncode}: " +
                           proc.stderr.decode("utf-8", errors="replace")[-1000:])
    lines = proc.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G3 launcher stage did not start with disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
