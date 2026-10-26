#!/usr/bin/env python3
"""Fetch only finalized, hash-bound G11 anonymous Graph artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "experiments/research_graph_baseline_20261016/g011_solution_loop_safe_snapshot"
REMOTE = "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph"
EXPECTED = {
    "g011_solution_loop_evidence_input_manifest.json": "ce3f8c4f92f06416224b87744c52eb2c28efc61c5dfafb059c7828471e5d0b9f",
    "g011_solution_loop_specialized_evidence.json": "58ad93d6e25dd4e9e5ab0a0364a75b0a28142a927d6fcc744238b932ffd5d129",
    "g011_solution_loop_evidence.json": "05794e42ae2e1513e7356cba6857fbca611d679f390c4b3feba2f5e8a3e59ae4",
    "g011_solution_loop_graph.json": "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4",
}
REMOTE_SCRIPT = '''
import base64
import json
from pathlib import Path
base = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph")
names = (
    "g011_solution_loop_evidence_input_manifest.json",
    "g011_solution_loop_specialized_evidence.json",
    "g011_solution_loop_evidence.json",
    "g011_solution_loop_graph.json",
)
print(json.dumps({name: base64.b64encode((base / name).read_bytes()).decode("ascii") for name in names}, sort_keys=True))
'''


def main() -> None:
    result = subprocess.run(
        [
            "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "root@100.83.10.33",
            "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -",
        ],
        input=REMOTE_SCRIPT, text=True, capture_output=True, check=True,
    )
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError("G11 safe artifact set differs")
    decoded = {name: base64.b64decode(value, validate=True) for name, value in payload.items()}
    for name, content in decoded.items():
        if hashlib.sha256(content).hexdigest() != EXPECTED[name]:
            raise RuntimeError(f"G11 safe artifact hash differs: {name}")
        json.loads(content)
    DEST.mkdir(parents=True, exist_ok=True)
    for name, content in decoded.items():
        path = DEST / name
        if path.exists():
            if path.read_bytes() != content:
                raise RuntimeError(f"G11 snapshot exists with different bytes: {name}")
        else:
            with path.open("xb") as stream:
                stream.write(content)
    print(json.dumps({"status": "safe_snapshot_verified", "files": EXPECTED}, sort_keys=True))


if __name__ == "__main__":
    main()
