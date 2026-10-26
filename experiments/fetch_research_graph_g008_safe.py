#!/usr/bin/env python3
"""Fetch only hash-bound, answer-blind G8 Graph and Evidence."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g008_safe_snapshot"
REMOTE = "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph"
EXPECTED = {
    "g008_graph.json": "c769fd157db33e7fe2432285d4e15718307f5c7b91dde91ebcf83b19fbca83e8",
    "g008_evidence.json": "879be6a0e84adeee883098b2a95e7dfe084ffe00626d26a33debeccc02863e3a",
    "g008_specialized_evidence.json": "36a85b25b086bf7aec00c79f06fa181224c12e1a0da17d0a74507f403cab7ba6",
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G8 safe snapshot already exists")
    remote_code = (
        "import base64,hashlib,json\n"
        "from pathlib import Path\n"
        f"base=Path({REMOTE!r})\n"
        f"expected={EXPECTED!r}\n"
        "files={}\n"
        "for name,digest in expected.items():\n"
        "    data=(base/name).read_bytes()\n"
        "    if hashlib.sha256(data).hexdigest()!=digest:\n"
        "        raise RuntimeError('G8 safe artifact hash differs')\n"
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
        raise RuntimeError("G8 safe snapshot transfer failed")
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError("G8 safe snapshot file set differs")
    files = {name: base64.b64decode(encoded) for name, encoded in payload.items()}
    if any(hashlib.sha256(files[name]).hexdigest() != wanted for name, wanted in EXPECTED.items()):
        raise RuntimeError("G8 local safe snapshot hash differs")
    if any(not isinstance(json.loads(data), dict) for data in files.values()):
        raise RuntimeError("G8 safe snapshot is not a JSON object")
    OUT.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": "safe_snapshot_fetched", "hashes": EXPECTED}, sort_keys=True))


if __name__ == "__main__":
    main()
