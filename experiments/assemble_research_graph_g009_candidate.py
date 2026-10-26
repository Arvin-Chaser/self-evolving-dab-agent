#!/usr/bin/env python3
"""Overlay the bounded G9 implementation on the verified G8 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g008_candidate_002/repo"
SCOPED = BASE / "g009_candidate_001/scoped_source"
OUT = BASE / "g009_candidate_001/repo"
BINDINGS = BASE / "g009_candidate_001/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g009_research_meta_001/final_raw.txt"
PARENT_SHA = "adeefdde02075bc4ea458f6a74ad1c418dd096e92acd1b262ccb25537bcf4105"
RESEARCH_SHA = "919b07ed74339d84e338da7ac30a3942196775d542da587b413fcf6702d15581"
ALLOWED_MODIFIED = {"experiments/run_dab_tool_agent.py"}
ALLOWED_ADDED = {
    "experiments/g009_verification_turn_gate_sidecar.py",
    "experiments/g009_evidence_extractor.py",
    "experiments/g009_interface_contract.py",
    "tests/test_g009_verification_turn_gate_hook.py",
    "tests/test_g009_evidence_extractor.py",
    "tests/test_g009_interface_contract.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G9 child exists or parent/Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (bindings["parent_tree_sha256"] != PARENT_SHA
            or bindings["research_sha256"] != RESEARCH_SHA
            or implementation["status"] != "implemented_synthetic_verified_not_evaluated"
            or implementation["blocked"] is not False
            or implementation["formal_run_performed"] is not False):
        raise RuntimeError("G9 Implementation binding or status differs")
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
        raise RuntimeError(f"G9 source delta exceeds admitted boundary: {modified=} {added=}")
    entries = {row["path"].replace("\\", "/"): row for row in implementation["files"]}
    for name in modified | added:
        if name not in entries or entries[name]["sha256"].lower() != sha(SCOPED / name):
            raise RuntimeError(f"G9 implementation manifest hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*"))
    for name in sorted(modified | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g009_local_candidate_assembly_v1",
        "code_parent": "g008",
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
