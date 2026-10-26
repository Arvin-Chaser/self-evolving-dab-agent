#!/usr/bin/env python3
"""Fetch only hash-bound, answer-blind reconciled G10 Graph and Evidence."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g010_safe_snapshot"
REMOTE = "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph"
EXPECTED = {
    "g010_graph.json": "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a",
    "g010_evidence.json": "40e0b8aa30fa74d0ab6b9c8e3f4b06084d8943a8bf85f1e9fc0e0d9878f346f6",
    "g010_specialized_evidence.json": "dcb6a0152f5f74efee74f7b4336e2ce6cb6be21635f345da64d9d0d802825db3",
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G10 safe snapshot already exists")
    remote_code = (
        "import base64,hashlib,json\n"
        "from pathlib import Path\n"
        f"base=Path({REMOTE!r})\n"
        f"expected={EXPECTED!r}\n"
        "files={}\n"
        "for name,digest in expected.items():\n"
        "    data=(base/name).read_bytes()\n"
        "    if hashlib.sha256(data).hexdigest()!=digest:\n"
        "        raise RuntimeError('G10 safe artifact hash differs')\n"
        "    files[name]=base64.b64encode(data).decode('ascii')\n"
        "print(json.dumps(files,sort_keys=True))\n"
    )
    command = [
        "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104",
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
        "df -hT /srv/text2sql && /srv/text2sql/.venv/bin/python -",
    ]
    result = subprocess.run(command, input=remote_code, text=True, encoding="utf-8",
                            capture_output=True, check=False, timeout=60)
    if result.returncode or not result.stdout.splitlines()[0].startswith("Filesystem"):
        raise RuntimeError("G10 safe snapshot transfer failed")
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError("G10 safe snapshot file set differs")
    files = {name: base64.b64decode(encoded) for name, encoded in payload.items()}
    if any(hashlib.sha256(files[name]).hexdigest() != wanted for name, wanted in EXPECTED.items()):
        raise RuntimeError("G10 local safe snapshot hash differs")
    if any(not isinstance(json.loads(data), dict) for data in files.values()):
        raise RuntimeError("G10 safe snapshot is not a JSON object")
    OUT.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": "safe_snapshot_fetched", "hashes": EXPECTED}, sort_keys=True))


if __name__ == "__main__":
    main()
