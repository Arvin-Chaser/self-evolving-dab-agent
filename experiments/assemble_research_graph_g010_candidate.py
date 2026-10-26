#!/usr/bin/env python3
"""Overlay the bounded G10 checklist implementation on the verified G9 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g009_candidate_001/repo"
SCOPED = BASE / "g010_candidate_001/scoped_source"
OUT = BASE / "g010_candidate_001/repo"
BINDINGS = BASE / "g010_candidate_001/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g010_research_meta_001/final_raw.txt"
PARENT_SHA = "206c4f5186a66d72b851aa888eb75d975d5ce2085970a322881997b119f16d0d"
RESEARCH_SHA = "0cb3441497459a042c98b0f403dddb4515146912f8852c003c2f50dd0a70c49e"
ALLOWED_MODIFIED = {
    "experiments/run_dab_tool_agent.py",
    "experiments/g009_verification_turn_gate_sidecar.py",
}
ALLOWED_ADDED = {
    "experiments/g010_evidence_reconciliation_gate.py",
    "experiments/g010_evidence_extractor.py",
    "tests/test_g010_evidence_reconciliation_hook.py",
    "tests/test_g010_evidence_extractor.py",
    "tests/test_g010_runner_integration.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G10 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (bindings["parent_tree_sha256"] != PARENT_SHA
            or bindings["research_sha256"] != RESEARCH_SHA
            or implementation["implementation_status"] != "implemented"
            or implementation["blocked"] is not False
            or implementation["formal_run_performed"] is not False
            or implementation["research_sha256"] != RESEARCH_SHA
            or implementation["parent_tree_sha256"] != PARENT_SHA):
        raise RuntimeError("G10 Implementation binding or status differs")
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
        raise RuntimeError(f"G10 source delta exceeds boundary: {modified=} {added=}")
    if (set(implementation["paths"]["modified"]) != modified
            or set(implementation["paths"]["added"]) != added):
        raise RuntimeError("G10 implementation path claims differ")
    for name in modified | added:
        if implementation["sha256"].get(name, "").lower() != sha(SCOPED / name):
            raise RuntimeError(f"G10 implementation hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g010_local_candidate_assembly_v1",
        "code_parent": "g009",
        "parent_tree_sha256": PARENT_SHA,
        "research_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": source_tree_hash(OUT),
        "modified_paths": sorted(modified),
        "added_paths": sorted(added),
        "formal_evaluation_started": False,
    }
    (OUT.parent / "assembly.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
