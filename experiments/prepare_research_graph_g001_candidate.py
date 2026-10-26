#!/usr/bin/env python3
"""Create one isolated G1 child from the frozen G0 source archive."""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
ARCHIVE = BASE / "baseline_source.tar.gz"
TARGET = BASE / "g001_candidate_003/repo"
EXPECTED_ARCHIVE_SHA = "e417bbaf334387c0511bdfeb37dd6788896d595af8389971639394eda8dd8303"
FROZEN_RUNNER = BASE / "frozen_g0_runner.py"
EXPECTED_RUNNER_SHA = "6bff187bc483d92aa47ebf6471c79383d6e31f701aff2d52b3c5086974cf9baf"


def main() -> None:
    if TARGET.exists():
        raise RuntimeError("G1 candidate already exists; refusing overwrite")
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != EXPECTED_ARCHIVE_SHA:
        raise RuntimeError("Frozen baseline archive hash differs")
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        all_members = archive.getmembers()
        for member in all_members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir())):
                raise RuntimeError("Unsafe baseline archive member")
        members = []
        for member in all_members:
            parts = PurePosixPath(member.name).parts
            parts = tuple(part for part in parts if part != ".")
            if (not parts or parts[0] in {"adapters", "prompts", "meta_agent", "tests", "external", "dab_corpus"}
                    or parts[0] in {"AGENTS.md", "llm_client.py"}
                    or (parts[0] == "experiments" and len(parts) <= 2)):
                members.append(member)
        TARGET.mkdir(parents=True, exist_ok=False)
        archive.extractall(TARGET, members=members, filter="data")
    if hashlib.sha256(FROZEN_RUNNER.read_bytes()).hexdigest() != EXPECTED_RUNNER_SHA:
        raise RuntimeError("Actual G0 runner snapshot differs")
    shutil.copy2(FROZEN_RUNNER, TARGET / "experiments/run_multi_query_baseline.py")
    print(json.dumps({"candidate": str(TARGET), "archive_sha256": EXPECTED_ARCHIVE_SHA,
                      "runner_parent_sha256": EXPECTED_RUNNER_SHA,
                      "member_count": len(members)}, sort_keys=True))


if __name__ == "__main__":
    main()
