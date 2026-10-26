#!/usr/bin/env python3
"""Bind the exploratory G3 candidate to G2 source and the revised Meta."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_manifest, source_manifest_hash
from experiments.run_research_graph_g003_constrained import verified_interface
from experiments.run_research_graph_g003_exploratory_meta import fact_cards
from experiments.validate_research_graph_g003_exploratory import validate_exploratory_research


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g002_candidate_001/repo"
CHILD = BASE / "g003_candidate_001/repo"
META = BASE / "g003_research_meta_012/result.json"
GRAPH = BASE / "g002_graph.json"
OUT = BASE / "g003_candidate_001/admission.json"
ARCHIVE = BASE / "g003_candidate_001/source.tar.gz"
EXPECTED_PARENT = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"
EXPECTED_META = "9e2297d1f6281092c7200409f5c0038de2533b40e92e75e4032956cc1cec54fb"
EXPECTED_GRAPH = "38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54"
EXPECTED_CHANGED = {
    "experiments/g003_proposed_call_diagnostic.py",
    "experiments/run_dab_tool_agent.py",
    "tests/test_g003_proposed_call_diagnostic.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G3 admission or archive already exists")
    if sha(META) != EXPECTED_META or sha(GRAPH) != EXPECTED_GRAPH:
        raise RuntimeError("G3 research or parent Graph differs")
    proposal = json.loads(META.read_text(encoding="utf-8"))
    validate_exploratory_research(proposal, fact_cards(), verified_interface())
    if (proposal["experiment_spec_ready"] is not True or
            proposal["experiment"]["code_parent"] != "g002_lifecycle_stage"):
        raise RuntimeError("G3 research does not bind G2 code parent")
    parent_rows = source_tree_manifest(PARENT)
    child_rows = source_tree_manifest(CHILD)
    parent = {row["path"]: row["sha256"] for row in parent_rows}
    child = {row["path"]: row["sha256"] for row in child_rows}
    changed = {path for path in set(parent) | set(child)
               if parent.get(path) != child.get(path)}
    if (source_manifest_hash(parent_rows) != EXPECTED_PARENT or
            changed != EXPECTED_CHANGED or
            set(child) - set(parent) != EXPECTED_CHANGED - set(parent)):
        raise RuntimeError("G3 candidate source delta differs")
    batch = CHILD / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
    registry = CHILD / "dab_corpus/registry.json"
    policy = CHILD / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
    runner = CHILD / "experiments/run_multi_query_baseline.py"
    if (sha(batch) != "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7" or
            sha(registry) != "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff" or
            sha(policy) != "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797" or
            sha(runner) != "7e8cd381690bee6551f6ee2047a1abdf1b1993433fa03edfdd36ce3804573549"):
        raise RuntimeError("G3 frozen protocol source differs")
    included = sorted(set(child) | {
        "AGENTS.md", "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json",
        "dab_corpus/registry.json"})
    for name in included:
        path = CHILD / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve()):
            raise RuntimeError(f"Unsafe G3 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)
    payload = {
        "schema_version": "dab_research_graph_g003_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "g002_lifecycle_stage",
        "parent_tree_sha256": EXPECTED_PARENT,
        "g2_graph_sha256": EXPECTED_GRAPH,
        "research_result_sha256": EXPECTED_META,
        "candidate_tree_sha256": source_manifest_hash(child_rows),
        "source_archive_sha256": sha(ARCHIVE),
        "changed_files": {name: child[name] for name in sorted(changed)},
        "source_file_count": len(child_rows),
        "batch_sha256": sha(batch), "registry_sha256": sha(registry),
        "policy_sha256": sha(policy), "runner_sha256": sha(runner),
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
