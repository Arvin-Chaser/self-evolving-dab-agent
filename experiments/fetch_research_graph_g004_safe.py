#!/usr/bin/env python3
"""Fetch only hash-bound, answer-blind G4 Graph and Evidence for Research Meta."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g004_safe_snapshot"
REMOTE = "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph"
EXPECTED = {
    "g004_graph.json": "fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda",
    "g004_evidence.json": "6d3c05712996d04c36c56a77f48bf270bb8b37fd61e56d205f8011b691ba2d6d",
    "g004_specialized_evidence.json": "f5cb3040d87b05d3fe6728bad9cb11331f24bb0192fa3e5b67e9e8961c3c1c01",
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G4 safe snapshot already exists")
    remote_code = (
        "import base64,hashlib,json\n"
        "from pathlib import Path\n"
        f"base=Path({REMOTE!r})\n"
        f"expected={EXPECTED!r}\n"
        "files={}\n"
        "for name,digest in expected.items():\n"
        "    data=(base/name).read_bytes()\n"
        "    if hashlib.sha256(data).hexdigest()!=digest:\n"
        "        raise RuntimeError('G4 safe artifact hash differs')\n"
        "    files[name]=base64.b64encode(data).decode('ascii')\n"
        "print(json.dumps(files,sort_keys=True))\n"
    )
    command = [
        "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -",
    ]
    result = subprocess.run(command, input=remote_code, text=True, encoding="utf-8",
                            capture_output=True, check=False, timeout=60)
    if result.returncode or not result.stdout.splitlines()[0].startswith("Filesystem"):
        raise RuntimeError("G4 safe snapshot transfer failed")
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError("G4 safe snapshot file set differs")
    files = {name: base64.b64decode(encoded) for name, encoded in payload.items()}
    if any(hashlib.sha256(files[name]).hexdigest() != wanted for name, wanted in EXPECTED.items()):
        raise RuntimeError("G4 local safe snapshot hash differs")
    if any(not isinstance(json.loads(data), dict) for data in files.values()):
        raise RuntimeError("G4 safe snapshot is not a JSON object")
    OUT.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": "safe_snapshot_fetched", "hashes": EXPECTED}, sort_keys=True))


if __name__ == "__main__":
    main()
