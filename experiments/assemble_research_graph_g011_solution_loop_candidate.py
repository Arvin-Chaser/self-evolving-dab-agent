#!/usr/bin/env python3
"""Overlay the admitted-scope G11 ledger implementation on the full G7 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g007_candidate_002/repo"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
SCOPED = WORK / "candidate"
IMPLEMENTATION = WORK / "implementation_manifest.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
OUT = BASE / "g011_solution_loop_candidate_001/repo"
ASSEMBLY = OUT.parent / "assembly.json"

PARENT_SHA256 = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
SCOPED_SHA256 = "54b00d2ef02acc937921c3276239876d4ed195b8988fb17d10d12680ac464e1a"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA256 = "c9cb355a8c7c84b3ed3c160ea7dc0dfaff0ab1371e9a3db296aabd342b290ef8"

MODIFIED = {"experiments/run_dab_tool_agent.py"}
ADDED = {
    "experiments/g011_admission_checks.py",
    "experiments/g011_evidence_extractor.py",
    "experiments/g011_interface_contract.py",
    "experiments/g011_plan_evidence_record.py",
    "experiments/g011_runtime_plan_evidence.py",
    "prompts/dab/g011_plan_evidence_authoring_policy.txt",
    "tests/g011_support.py",
    "tests/test_g011_evidence_extractor.py",
    "tests/test_g011_interface_contract.py",
    "tests/test_g011_plan_evidence_record.py",
    "tests/test_g011_runtime_plan_evidence.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.parent.exists():
        raise RuntimeError("G11 solution-loop candidate already exists")
    if (
        source_tree_hash(PARENT) != PARENT_SHA256
        or source_tree_hash(SCOPED) != SCOPED_SHA256
        or sha(RESEARCH) != RESEARCH_SHA256
        or sha(IMPLEMENTATION) != IMPLEMENTATION_SHA256
    ):
        raise RuntimeError("G11 parent, scoped candidate, Research, or implementation hash differs")
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (
        implementation.get("formal_candidate") is not True
        or implementation.get("formal_run_performed") is not False
        or research.get("promotion_decision", {}).get("state") != "experiment_ready"
        or research.get("candidate_or_evaluation_authorized") is not False
        or research.get("formal_spec", {}).get("runtime_channel", {}).get("payload_location")
        != "self_observation.freeform"
    ):
        raise RuntimeError("G11 implementation status or revised Research carrier differs")
    claimed = {
        row["path"].removeprefix("candidate/"): row["sha256"].lower()
        for row in implementation["changed_files"]
    }
    if set(claimed) != MODIFIED | ADDED:
        raise RuntimeError("G11 implementation path boundary differs")
    for name, digest in claimed.items():
        if sha(SCOPED / name) != digest:
            raise RuntimeError(f"G11 implementation hash differs: {name}")
    if any(not (PARENT / name).is_file() for name in MODIFIED):
        raise RuntimeError("G11 modified parent source is missing")
    if any((PARENT / name).exists() for name in ADDED):
        raise RuntimeError("G11 added path already exists in parent")

    shutil.copytree(
        PARENT,
        OUT,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".pytest_tmp*", "*.pyc"),
    )
    for name in sorted(MODIFIED | ADDED):
        destination = OUT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, destination)
    candidate_sha = source_tree_hash(OUT)
    if candidate_sha != SCOPED_SHA256:
        raise RuntimeError("Assembled G11 source tree differs from scoped candidate")
    record = {
        "schema_version": "g011_solution_loop_candidate_assembly_v1",
        "status": "assembled_pending_mechanical_admission",
        "code_parent": "g007",
        "parent_tree_sha256": PARENT_SHA256,
        "research_sha256": RESEARCH_SHA256,
        "implementation_manifest_sha256": IMPLEMENTATION_SHA256,
        "candidate_tree_sha256": candidate_sha,
        "modified_paths": sorted(MODIFIED),
        "added_paths": sorted(ADDED),
        "formal_evaluation_started": False,
    }
    ASSEMBLY.write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
