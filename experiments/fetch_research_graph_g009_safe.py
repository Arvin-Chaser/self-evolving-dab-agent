#!/usr/bin/env python3
"""Fetch only hash-bound, answer-blind G9 Graph and Evidence."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g009_safe_snapshot"
REMOTE = "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph"
EXPECTED = {
    "g009_graph.json": "e49a7c765eef8aea4dd4bc295dfc907f7cf0fa743df41efff94fb4b9e31d0abd",
    "g009_evidence.json": "ea71d0414338e4b8e6a03028e509c86406923f35859feebbf8b61a866dec5178",
    "g009_specialized_evidence.json": "7d10131dcfefdf44ed34e5adae5699794c9f3f52c86ab0372fbd8abb55135259",
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G9 safe snapshot already exists")
    remote_code = (
        "import base64,hashlib,json\n"
        "from pathlib import Path\n"
        f"base=Path({REMOTE!r})\n"
        f"expected={EXPECTED!r}\n"
        "files={}\n"
        "for name,digest in expected.items():\n"
        "    data=(base/name).read_bytes()\n"
        "    if hashlib.sha256(data).hexdigest()!=digest:\n"
        "        raise RuntimeError('G9 safe artifact hash differs')\n"
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
        raise RuntimeError("G9 safe snapshot transfer failed")
    payload = json.loads(result.stdout.splitlines()[-1])
    if set(payload) != set(EXPECTED):
        raise RuntimeError("G9 safe snapshot file set differs")
    files = {name: base64.b64decode(encoded) for name, encoded in payload.items()}
    if any(hashlib.sha256(files[name]).hexdigest() != wanted for name, wanted in EXPECTED.items()):
        raise RuntimeError("G9 local safe snapshot hash differs")
    if any(not isinstance(json.loads(data), dict) for data in files.values()):
        raise RuntimeError("G9 safe snapshot is not a JSON object")
    OUT.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": "safe_snapshot_fetched", "hashes": EXPECTED}, sort_keys=True))


if __name__ == "__main__":
    main()
