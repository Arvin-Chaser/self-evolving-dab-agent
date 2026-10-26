#!/usr/bin/env python3
"""Overlay bounded G7 Implementation Meta sources on the verified G6 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g006_candidate_001/repo"
SCOPED = BASE / "g007_candidate_002/scoped_source"
OUT = BASE / "g007_candidate_002/repo"
BINDINGS = BASE / "g007_candidate_002/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g007_research_meta_002/final_raw.txt"
PARENT_SHA = "845e0f89f3df104d1fcb0ca564256fe8ca0f92c8880127dc4b3c2d4cfb0244c6"
RESEARCH_SHA = "c505b1fa72984f6f42025ad913690aeab77223e0642cd64560c3ddd76a80a05a"
ALLOWED_MODIFIED = {"experiments/run_dab_tool_agent.py"}
ALLOWED_ADDED = {
    "experiments/g007_last_pre_exec_sidecar.py",
    "experiments/g007_evidence_extractor.py",
    "experiments/g007_interface_contract.py",
    "tests/test_g007_last_pre_exec_sidecar.py",
    "tests/test_g007_evidence_extractor.py",
    "tests/test_g007_interface_contract.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G7 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (bindings["parent_tree_sha256"] != PARENT_SHA
            or bindings["research_sha256"] != RESEARCH_SHA
            or implementation["status"] != "implemented_not_run"
            or implementation["formal_run_performed"] is not False):
        raise RuntimeError("G7 Implementation binding or status differs")
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
        raise RuntimeError("G7 source delta exceeds admitted boundary")
    entries = {row["path"].replace("\\", "/"): row for row in implementation["changed_paths"]}
    if not (modified | added).issubset(entries):
        raise RuntimeError("G7 manifest omits source paths")
    for name in modified | added:
        if entries[name]["sha256"] != sha(SCOPED / name):
            raise RuntimeError(f"G7 manifest source hash differs: {name}")
    for name in set(entries) - modified - added - {"implementation_manifest.json"}:
        if entries[name]["sha256"] != sha(SCOPED / name):
            raise RuntimeError(f"G7 manifest auxiliary hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g007_local_candidate_assembly_v1",
        "code_parent": "g006",
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
