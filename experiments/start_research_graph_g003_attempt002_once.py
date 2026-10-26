#!/usr/bin/env python3
"""Provide the approved credential to the unique G3 attempt 2 launcher."""

from __future__ import annotations

import json
import subprocess

from experiments.dab_meta_runtime import meta_environment


SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33"]
REMOTE = (
    "df -hT /srv/text2sql; "
    "/srv/text2sql/.venv/bin/python "
    "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/"
    "g003_revision001/bindings/launch_research_graph_g003_attempt002.py"
)


def main() -> None:
    key = meta_environment("deepseek-standalone-dab").get("DEEPSEEK_API_KEY", "")
    if not key or any(character.isspace() for character in key):
        raise RuntimeError("DeepSeek credential unavailable or malformed")
    result = subprocess.run(SSH + [REMOTE], input=key + "\n", text=True,
                            capture_output=True, timeout=90, check=False)
    print(result.stdout, end="")
    if result.returncode:
        print(json.dumps({"status": "launch_failed", "returncode": result.returncode,
                          "stderr": result.stderr[-1200:]}, sort_keys=True))
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
