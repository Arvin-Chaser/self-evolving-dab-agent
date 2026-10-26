#!/usr/bin/env python3
"""Admit a source-bound G5 diagnostic child before remote preflight."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g005_candidate_001/repo"
ASSEMBLY = BASE / "g005_candidate_001/assembly.json"
IMPLEMENTATION = BASE / "g005_candidate_001/scoped_source/implementation_manifest.json"
RESEARCH = BASE / "g005_research_meta_002/final_raw.txt"
OUT = BASE / "g005_candidate_001/admission.json"
ARCHIVE = BASE / "g005_candidate_001/source.tar.gz"
PARENT_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
CANDIDATE_SHA = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"
GRAPH_SHA = "fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda"
BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
POLICY_SHA = "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G5 admission or archive already exists")
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (
        assembly["parent_tree_sha256"] != PARENT_SHA
        or assembly["candidate_tree_sha256"] != CANDIDATE_SHA
        or assembly["research_sha256"] != RESEARCH_SHA
        or assembly["implementation_manifest_sha256"] != sha(IMPLEMENTATION)
        or source_tree_hash(CHILD) != CANDIDATE_SHA
        or sha(RESEARCH) != RESEARCH_SHA
        or implementation["blocked"] is not False
        or research["experiment"]["code_parent_tree_sha256"] != PARENT_SHA
        or research["experiment"]["intervention_class"] != "diagnostic_instrumentation"
    ):
        raise RuntimeError("G5 source, Research, or Implementation binding differs")
    protocol = research["experiment"]["fixed_protocol"]
    if protocol != {
        "description_mode": "full_db_description_no_hints",
        "frozen_task_count": 56,
        "hints": False,
        "per_task_wall_timeout_seconds": 1200,
        "primary_metric": "completed_and_strict_true_over_all_56",
        "timeouts": "failures_in_fixed_denominator",
    }:
        raise RuntimeError("G5 fixed protocol differs")
    special = {
        "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json": BATCH_SHA,
        "dab_corpus/registry.json": REGISTRY_SHA,
        "prompts/dab/dab_tool_agent_policy_zero_start.txt": POLICY_SHA,
    }
    if any(sha(CHILD / name) != wanted for name, wanted in special.items()):
        raise RuntimeError("G5 frozen input hashes differ")
    from experiments.intent_candidate_workspace import source_tree_manifest

    source_rows = source_tree_manifest(CHILD)
    included = sorted({row["path"] for row in source_rows} | {"AGENTS.md", *special})
    for name in included:
        path = CHILD / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve()):
            raise RuntimeError(f"Unsafe G5 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)
    payload = {
        "schema_version": "dab_research_graph_g005_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "g004",
        "parent_tree_sha256": PARENT_SHA,
        "g4_graph_sha256": GRAPH_SHA,
        "research_result_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": CANDIDATE_SHA,
        "source_archive_sha256": sha(ARCHIVE),
        "source_file_count": len(source_rows),
        "changed_files": {
            name: sha(CHILD / name)
            for name in assembly["modified_paths"] + assembly["added_paths"]
        },
        "batch_sha256": BATCH_SHA,
        "registry_sha256": REGISTRY_SHA,
        "policy_sha256": POLICY_SHA,
        "runner_sha256": sha(CHILD / "experiments/run_multi_query_baseline.py"),
        "agent_sha256": sha(CHILD / "experiments/run_dab_tool_agent.py"),
        "synthetic_contract_tests_passed": 78,
        "mechanical_review": {
            "source_boundary": "one agent runner integration changed and four G5 files added",
            "inertness": "disabled sidecar short-circuits; enabled wrapper preserves dispatch and result",
            "result_writeback": "parent dispatch, tool response, finalization and scoring unchanged",
            "extractor_boundary": "reads G5 sidecar and G4 allowlisted structural sidecar only",
            "cohort_denominator": "observed G5 counts summing to fixed 56, never G4 reference counts",
            "real_upstream_contract": "pending bounded synthetic check",
        },
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
