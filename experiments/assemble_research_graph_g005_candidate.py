#!/usr/bin/env python3
"""Overlay admitted G5 Meta changes on the verified G4 source parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g004_candidate_002/repo"
SCOPED = BASE / "g005_candidate_001/scoped_source"
OUT = BASE / "g005_candidate_001/repo"
BINDINGS = BASE / "g005_candidate_001/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g005_research_meta_002/final_raw.txt"
PARENT_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"
ALLOWED_MODIFIED = {"experiments/run_dab_tool_agent.py"}
ALLOWED_ADDED = {
    "experiments/g005_provenance_sidecar.py",
    "experiments/g005_evidence_extractor.py",
    "tests/test_g005_provenance_sidecar.py",
    "tests/test_g005_evidence_extractor.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G5 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (
        bindings["parent_tree_sha256"] != PARENT_SHA
        or bindings["research_sha256"] != RESEARCH_SHA
        or implementation["research_sha256"] != RESEARCH_SHA
        or implementation["blocked"] is not False
    ):
        raise RuntimeError("G5 Implementation binding or status differs")
    modified = {
        name for name, parent_digest in bindings["scoped_files"].items()
        if sha(SCOPED / name) != parent_digest
    }
    added = {
        path.relative_to(SCOPED).as_posix()
        for path in SCOPED.rglob("*.py")
        if path.relative_to(SCOPED).as_posix() not in bindings["scoped_files"]
    }
    if modified != ALLOWED_MODIFIED or added != ALLOWED_ADDED:
        raise RuntimeError("G5 source delta exceeds admitted boundary")
    entries = {row["path"].replace("\\", "/"): row for row in implementation["changed_paths"]}
    if set(entries) != modified | added:
        raise RuntimeError("G5 manifest source paths differ from full parent delta")
    for name, entry in entries.items():
        if entry["sha256"] != sha(SCOPED / name):
            raise RuntimeError(f"G5 manifest source hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g005_local_candidate_assembly_v1",
        "code_parent": "g004",
        "parent_tree_sha256": PARENT_SHA,
        "research_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": source_tree_hash(OUT),
        "modified_paths": sorted(modified),
        "added_paths": sorted(added),
        "formal_evaluation_started": False,
    }
    (OUT.parent / "assembly.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
