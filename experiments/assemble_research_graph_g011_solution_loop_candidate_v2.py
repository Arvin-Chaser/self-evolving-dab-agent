#!/usr/bin/env python3
"""Assemble the repaired G11 solution-loop candidate from the frozen G7 parent."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g007_candidate_002/repo"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
SCOPED = WORK / "candidate"
IMPLEMENTATION = WORK / "implementation_manifest_revision_001.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
OUT = BASE / "g011_solution_loop_candidate_002/repo"
ASSEMBLY = OUT.parent / "assembly.json"

PARENT_SHA256 = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
SCOPED_SHA256 = "2bad7999f98d3359a0407724b3aba66a0b83e6e11aa69e00e5e8a47f05a6277b"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA256 = "5f484ff5278b35d43a4f2dfbf21c0c27b354c91c4b5019428abe9f01bc42eaba"

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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.parent.exists():
        raise RuntimeError("G11 repaired candidate already exists; refusing overwrite")
    if (
        source_tree_hash(PARENT) != PARENT_SHA256
        or source_tree_hash(SCOPED) != SCOPED_SHA256
        or sha256(RESEARCH) != RESEARCH_SHA256
        or sha256(IMPLEMENTATION) != IMPLEMENTATION_SHA256
    ):
        raise RuntimeError("G11 parent, repaired candidate, Research, or implementation hash differs")

    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (
        implementation.get("formal_candidate") is not True
        or implementation.get("evaluation_run") is not False
        or implementation.get("formal_run_performed") is not False
        or implementation.get("candidate_tree", {}).get("after_repair_sha256") != SCOPED_SHA256
        or research.get("promotion_decision", {}).get("state") != "experiment_ready"
        or research.get("candidate_or_evaluation_authorized") is not False
        or research.get("formal_spec", {}).get("runtime_channel", {}).get("payload_location")
        != "self_observation.freeform"
    ):
        raise RuntimeError("G11 repaired implementation or Research binding differs")

    expected_paths = MODIFIED | ADDED
    claimed = {
        row["path"].removeprefix("candidate/"): row["after_sha256"].lower()
        for row in implementation["changed_files"]
        if not row["path"].startswith("candidate/external/")
    }
    if set(claimed) != expected_paths:
        raise RuntimeError("G11 repaired implementation path boundary differs")
    for name, digest in claimed.items():
        if sha256(SCOPED / name) != digest:
            raise RuntimeError(f"G11 repaired implementation hash differs: {name}")
    if any(not (PARENT / name).is_file() for name in MODIFIED):
        raise RuntimeError("G11 modified parent source is missing")
    if any((PARENT / name).exists() for name in ADDED):
        raise RuntimeError("G11 added path already exists in parent")

    shutil.copytree(
        PARENT,
        OUT,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".tmp", "b", "*.pyc"),
    )
    for name in sorted(expected_paths):
        destination = OUT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, destination)

    candidate_sha256 = source_tree_hash(OUT)
    if candidate_sha256 != SCOPED_SHA256:
        raise RuntimeError("Assembled repaired G11 source tree differs from scoped candidate")
    record = {
        "schema_version": "g011_solution_loop_candidate_assembly_v2",
        "status": "assembled_pending_independent_admission",
        "code_parent": "g007",
        "parent_tree_sha256": PARENT_SHA256,
        "research_sha256": RESEARCH_SHA256,
        "implementation_manifest_sha256": IMPLEMENTATION_SHA256,
        "candidate_tree_sha256": candidate_sha256,
        "modified_paths": sorted(MODIFIED),
        "added_paths": sorted(ADDED),
        "excluded_test_dependency": {
            "path": "external/DataAgentBench_official/common_scaffold/DataAgent.py",
            "sha256": "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a",
            "reason": "local inherited-test dependency; not part of the active source tree or deployment overlay",
        },
        "research_contract_note": {
            "text": "The unrelated run-permission-token sentence is non-operative and is not used as launch permission, runtime behavior, or Evidence.",
            "runtime_or_protocol_effect": False,
        },
        "formal_evaluation_started": False,
    }
    ASSEMBLY.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
