#!/usr/bin/env python3
"""Overlay mechanically bounded G11 implementation on verified G9 source."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g009_candidate_001/repo"
SCOPED = BASE / "g011_candidate_001/scoped_source"
OUT = BASE / "g011_candidate_001/repo"
BINDINGS = BASE / "g011_candidate_001/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g011_research_meta_001/final_raw.txt"
PARENT_SHA = "206c4f5186a66d72b851aa888eb75d975d5ce2085970a322881997b119f16d0d"
RESEARCH_SHA = "1a86be51e0c706b3112b44f9307f5d83ccfa4a8b35c37aaaa1076960193ff2bb"
ALLOWED_MODIFIED = {"experiments/run_dab_tool_agent.py"}
ALLOWED_ADDED = {
    "experiments/g011_minimum_evidence_gate_sidecar.py",
    "experiments/g011_evidence_extractor.py",
    "experiments/g011_interface_contract.py",
    "tests/test_g011_minimum_evidence_gate_hook.py",
    "tests/test_g011_evidence_extractor.py",
    "tests/test_g011_interface_contract.py",
    "tests/test_g011_integration.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G11 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (bindings["parent_tree_sha256"] != PARENT_SHA
            or bindings["research_sha256"] != RESEARCH_SHA
            or implementation["status"] != "implemented"
            or implementation["blocked"] is not False
            or implementation["research_sha256"] != RESEARCH_SHA
            or implementation["parent_tree_sha256"] != PARENT_SHA):
        raise RuntimeError("G11 implementation binding or status differs")
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
        raise RuntimeError(f"G11 source delta exceeds boundary: {modified=} {added=}")
    claims = {row["path"]: row["sha256"] for row in implementation["paths"]}
    if set(claims) != modified | added or any(claims[name] != sha(SCOPED / name) for name in claims):
        raise RuntimeError("G11 implementation file claims differ")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g011_local_candidate_assembly_v1", "code_parent": "g009",
        "parent_tree_sha256": PARENT_SHA, "parent_graph_sha256": "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a",
        "research_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": source_tree_hash(OUT),
        "modified_paths": sorted(modified), "added_paths": sorted(added),
        "formal_evaluation_started": False,
    }
    (OUT.parent / "assembly.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
