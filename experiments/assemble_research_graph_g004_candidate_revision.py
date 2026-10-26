#!/usr/bin/env python3
"""Assemble a new G4 child from the repaired scoped Meta output."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g003_candidate_001/repo"
SCOPED = BASE / "g004_candidate_001/scoped_source"
OUT_BASE = BASE / "g004_candidate_002"
OUT = OUT_BASE / "repo"
BINDINGS = BASE / "g004_candidate_001/parent_source_bindings.json"
IMPLEMENTATION = SCOPED / "implementation_manifest.json"
RESEARCH = BASE / "g004_research_meta_002/final_raw.txt"
PARENT_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"
RESEARCH_SHA = "d7f4fc0d479db2371ed9dcc706b288c7450edb3897eb5eed91fd684dde1ec332"
ALLOWED_MODIFIED = {
    "experiments/run_dab_tool_agent.py",
    "experiments/run_multi_query_baseline.py",
}
ALLOWED_ADDED = {
    "experiments/g004_paired_structural_journal.py",
    "experiments/g004_postrun_structural_sidecar.py",
    "experiments/g004_evidence_extractor.py",
    "tests/test_g004_paired_structural_journal.py",
    "tests/test_g004_evidence_extractor.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT_BASE.exists():
        raise RuntimeError("G4 repaired candidate already exists")
    if source_tree_hash(PARENT) != PARENT_SHA or digest(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G4 parent or frozen Research hash differs")
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    if (
        bindings["parent_tree_sha256"] != PARENT_SHA
        or implementation["parent_tree_sha256"] != PARENT_SHA
        or implementation["research_sha256"] != RESEARCH_SHA
        or implementation["repair_attempt"] != 2
        or implementation["blocked"] is not False
    ):
        raise RuntimeError("G4 repaired Implementation binding differs")
    changed = {
        name for name, old_hash in bindings["scoped_files"].items()
        if digest(SCOPED / name) != old_hash
    }
    added = {
        path.relative_to(SCOPED).as_posix() for path in SCOPED.rglob("*.py")
        if path.relative_to(SCOPED).as_posix() not in bindings["scoped_files"]
    }
    if changed != ALLOWED_MODIFIED or added != ALLOWED_ADDED:
        raise RuntimeError("G4 repaired changes exceed the admitted source boundary")
    entries = {
        row["path"]: row for row in implementation["changed_paths"]
        if row["path"] != "implementation_manifest.json"
    }
    if set(entries) != changed | added:
        raise RuntimeError("G4 manifest source paths differ")
    for name, entry in entries.items():
        if entry["sha256"] != digest(SCOPED / name):
            raise RuntimeError(f"G4 manifest source hash differs: {name}")
        if name in changed and entry.get("parent_sha256") != digest(PARENT / name):
            raise RuntimeError(f"G4 parent file hash differs: {name}")
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp"))
    for name in sorted(changed | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    record = {
        "schema_version": "g004_local_candidate_assembly_v1",
        "code_parent": "g003",
        "parent_tree_sha256": PARENT_SHA,
        "research_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": digest(IMPLEMENTATION),
        "candidate_tree_sha256": source_tree_hash(OUT),
        "modified_paths": sorted(changed),
        "added_paths": sorted(added),
        "formal_evaluation_started": False,
    }
    with (OUT_BASE / "assembly.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
