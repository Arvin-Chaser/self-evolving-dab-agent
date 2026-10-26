#!/usr/bin/env python3
"""Overlay the bounded G8 six-axis implementation on the verified G7 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g007_candidate_002/repo"
SCOPED = BASE / "g008_candidate_002/scoped_source"
OUT = BASE / "g008_candidate_002/repo"
BINDINGS = BASE / "g008_candidate_002/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g008_research_meta_004/final_raw.txt"
PARENT_SHA = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
RESEARCH_SHA = "065f0f4f6740cf4ab5021c09545922188e9c896a83153e322065a375beeed9e7"
ALLOWED_MODIFIED = {"experiments/run_dab_tool_agent.py"}
ALLOWED_ADDED = {
    "experiments/g008_verification_audit_sidecar.py",
    "experiments/g008_evidence_extractor.py",
    "experiments/g008_interface_contract.py",
    "tests/test_g008_verification_audit_hook.py",
    "tests/test_g008_evidence_extractor.py",
    "tests/test_g008_interface_contract.py",
}
SCOPED_TEST_SHIM = "tests/conftest.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G8 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (bindings["parent_tree_sha256"] != PARENT_SHA
            or bindings["research_sha256"] != RESEARCH_SHA
            or implementation["implementation_status"] != "implemented_not_run"
            or implementation["formal_run"]["performed"] is not False):
        raise RuntimeError("G8 Implementation binding or status differs")
    modified = {
        name for name, parent_digest in bindings["scoped_files"].items()
        if sha(SCOPED / name) != parent_digest
    }
    added = {
        path.relative_to(SCOPED).as_posix()
        for path in SCOPED.rglob("*.py")
        if path.relative_to(SCOPED).as_posix() not in bindings["scoped_files"]
        and path.relative_to(SCOPED).as_posix() != SCOPED_TEST_SHIM
    }
    if modified != ALLOWED_MODIFIED or added != ALLOWED_ADDED:
        raise RuntimeError(f"G8 source delta exceeds admitted boundary: {modified=} {added=}")
    entries = {row["path"].replace("\\", "/"): row for row in implementation["files"]}
    for name in modified | added | {SCOPED_TEST_SHIM}:
        if name not in entries or entries[name]["sha256"].lower() != sha(SCOPED / name):
            raise RuntimeError(f"G8 implementation manifest hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g008_local_candidate_assembly_v1",
        "code_parent": "g007",
        "parent_tree_sha256": PARENT_SHA,
        "research_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": source_tree_hash(OUT),
        "modified_paths": sorted(modified),
        "added_paths": sorted(added),
        "excluded_scoped_test_shim": SCOPED_TEST_SHIM,
        "formal_evaluation_started": False,
    }
    (OUT.parent / "assembly.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
