#!/usr/bin/env python3
"""Bind the repaired G4 diagnostic to its verified G3 parent and fixed protocol."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g004_candidate_002/repo"
ASSEMBLY = BASE / "g004_candidate_002/assembly.json"
IMPLEMENTATION = BASE / "g004_candidate_001/scoped_source/implementation_manifest.json"
RESEARCH = BASE / "g004_research_meta_002/final_raw.txt"
OUT = BASE / "g004_candidate_002/admission.json"
ARCHIVE = BASE / "g004_candidate_002/source.tar.gz"
PARENT_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"
CANDIDATE_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
RESEARCH_SHA = "d7f4fc0d479db2371ed9dcc706b288c7450edb3897eb5eed91fd684dde1ec332"
GRAPH_SHA = "039fc4fbc51410d87f7adc6e0c9017fb963d7979e9b10bce22f1c38949e67f29"
BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
POLICY_SHA = "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G4 admission or source archive already exists")
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (
        assembly["parent_tree_sha256"] != PARENT_SHA
        or assembly["candidate_tree_sha256"] != CANDIDATE_SHA
        or assembly["research_sha256"] != RESEARCH_SHA
        or assembly["implementation_manifest_sha256"] != digest(IMPLEMENTATION)
        or source_tree_hash(CHILD) != CANDIDATE_SHA
        or digest(RESEARCH) != RESEARCH_SHA
        or implementation["repair_attempt"] != 2
        or implementation["blocked"] is not False
        or research["experiment"]["code_parent_tree_sha256"] != PARENT_SHA
        or research["experiment"]["intervention_class"] != "diagnostic_instrumentation"
    ):
        raise RuntimeError("G4 source, Research, or Implementation binding differs")
    protocol = research["experiment"]["fixed_protocol"]
    if (
        protocol["frozen_task_count"] != 56
        or protocol["hints"] is not False
        or protocol["per_task_wall_timeout_seconds"] != 1200
        or protocol["formal_runs"] != 1
        or protocol["probe_run"] is not False
        or protocol["answer_validator_or_heldout_access"] is not False
    ):
        raise RuntimeError("G4 fixed protocol differs")
    special = {
        "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json": BATCH_SHA,
        "dab_corpus/registry.json": REGISTRY_SHA,
        "prompts/dab/dab_tool_agent_policy_zero_start.txt": POLICY_SHA,
    }
    if any(digest(CHILD / name) != wanted for name, wanted in special.items()):
        raise RuntimeError("G4 frozen inputs differ")
    # The scoped test suite is run independently before this one-shot admission.
    from experiments.intent_candidate_workspace import source_tree_manifest

    source_rows = source_tree_manifest(CHILD)
    included = sorted({row["path"] for row in source_rows} | {"AGENTS.md", *special})
    for name in included:
        path = CHILD / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve()):
            raise RuntimeError(f"Unsafe G4 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)
    payload = {
        "schema_version": "dab_research_graph_g004_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "g003",
        "parent_tree_sha256": PARENT_SHA,
        "g3_graph_sha256": GRAPH_SHA,
        "research_result_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": digest(IMPLEMENTATION),
        "candidate_tree_sha256": CANDIDATE_SHA,
        "source_archive_sha256": digest(ARCHIVE),
        "source_file_count": len(source_rows),
        "changed_files": {
            name: digest(CHILD / name)
            for name in assembly["modified_paths"] + assembly["added_paths"]
        },
        "batch_sha256": BATCH_SHA,
        "registry_sha256": REGISTRY_SHA,
        "policy_sha256": POLICY_SHA,
        "runner_sha256": digest(CHILD / "experiments/run_multi_query_baseline.py"),
        "agent_sha256": digest(CHILD / "experiments/run_dab_tool_agent.py"),
        "synthetic_contract_tests_passed": 47,
        "mechanical_review": {
            "source_boundary": "only two runner files changed and five G4 files added",
            "inertness": "hook returns or rethrows the parent's result; journal output is never read by the agent",
            "result_writeback": "parent dispatch, tool response, finalization, and scoring remain unchanged",
            "extractor_boundary": "reads only paired journal and allowlisted normalized structural sidecar",
            "source_absence": "missing postrun tool source is incomplete, not a zero-match negative",
            "real_upstream_contract": "pending bounded remote synthetic check",
        },
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
