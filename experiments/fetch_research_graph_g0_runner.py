#!/usr/bin/env python3
"""Fetch the exact source of the runner used by the frozen G0 launch."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments/research_graph_baseline_20261016/frozen_g0_runner.py"
REMOTE = "/srv/text2sql/evolution_runtime/half56_v1/run_multi_query_baseline.py"
EXPECTED_SHA = "6bff187bc483d92aa47ebf6471c79383d6e31f701aff2d52b3c5086974cf9baf"
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes",
       "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Frozen G0 runner already fetched; refusing overwrite")
    code = ("import base64,hashlib,json;from pathlib import Path;"
            f"p=Path({REMOTE!r});b=p.read_bytes();"
            "print(json.dumps({'sha256':hashlib.sha256(b).hexdigest(),"
            "'base64':base64.b64encode(b).decode('ascii')}))")
    proc = subprocess.run(SSH, input=code, text=True, encoding="utf-8",
                          capture_output=True, timeout=60, check=False)
    lines = proc.stdout.splitlines()
    if proc.returncode or not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError(f"Remote runner fetch failed: exit {proc.returncode}")
    payload = json.loads(lines[-1])
    data = base64.b64decode(payload["base64"], validate=True)
    if payload["sha256"] != EXPECTED_SHA or hashlib.sha256(data).hexdigest() != EXPECTED_SHA:
        raise RuntimeError("Fetched runner differs from frozen G0 binding")
    with OUTPUT.open("xb") as stream:
        stream.write(data)
    print(json.dumps({"runner_sha256": EXPECTED_SHA, "bytes": len(data)}, sort_keys=True))


if __name__ == "__main__":
    main()
