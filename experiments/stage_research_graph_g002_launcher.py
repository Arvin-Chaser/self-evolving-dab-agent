#!/usr/bin/env python3
"""Stage the audited G2 launcher without touching the frozen candidate source."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "experiments/launch_research_graph_g002.py"
EXPECTED = "0dc4b0f925777d963b9c48839cb14e98b6914acb76971995fb63b2c241d020d4"
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33"]
REMOTE = r'''
import hashlib,json,sys
from pathlib import Path
base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
g2=base/"g002_revision001"
path=g2/"bindings/launch_research_graph_g002.py"
data=sys.stdin.buffer.read()
if hashlib.sha256(data).hexdigest()!="0dc4b0f925777d963b9c48839cb14e98b6914acb76971995fb63b2c241d020d4":
    raise RuntimeError("G2 launcher transfer hash differs")
if not (g2/"source").is_dir() or not path.parent.is_dir() or path.exists():
    raise RuntimeError("G2 source/bindings missing or launcher already staged")
with path.open("xb") as stream:
    stream.write(data)
print(json.dumps({"status":"launcher_staged","sha256":hashlib.sha256(path.read_bytes()).hexdigest()},sort_keys=True))
'''


def main() -> None:
    data = LAUNCHER.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise RuntimeError("Local G2 launcher changed")
    remote = "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c '" + REMOTE.replace("'", "'\"'\"'") + "'"
    proc = subprocess.run(SSH + [remote], input=data, capture_output=True, timeout=30)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-1200:])
    lines = proc.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G2 stage SSH did not begin with disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
