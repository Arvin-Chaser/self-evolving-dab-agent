#!/usr/bin/env python3
"""Bind an answer-free G5 child workspace for G6 Implementation Meta."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g005_candidate_001/repo"
OUT = BASE / "g006_candidate_001"
SOURCE = OUT / "scoped_source"
RESEARCH = BASE / "g006_research_meta_001/final_raw.txt"
PARENT_TREE = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
RESEARCH_SHA = "09ca0c4330b5b591d7a52ecdd084021ee8f7c720de93d33192a615f5dba27677"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G6 scoped workspace exists or Research Meta hash differs")
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    experiment = research["experiment"]
    if (experiment["code_parent_generation"] != "g005"
            or experiment["code_parent_tree_sha256"] != PARENT_TREE
            or [research[part]["id"] for part in ("problem", "hypothesis", "experiment")]
            != ["problem:g006", "hypothesis:g006", "experiment:g006"]):
        raise RuntimeError("G6 research decision or parent binding differs")
    manifest_path = PARENT / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g6_parent_manifest", manifest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G5 parent source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(PARENT), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(rows) != PARENT_TREE:
        raise RuntimeError("G5 parent source tree changed")

    relative_files = [
        "experiments/run_dab_tool_agent.py",
        "experiments/run_multi_query_baseline.py",
        "experiments/g005_provenance_sidecar.py",
        "experiments/g005_evidence_extractor.py",
        "experiments/g004_paired_structural_journal.py",
        "experiments/g004_postrun_structural_sidecar.py",
        "experiments/g004_evidence_extractor.py",
        "experiments/g003_proposed_call_diagnostic.py",
        "experiments/g002_lifecycle_stage.py",
        "external/DataAgentBench_official/common_scaffold/DataAgent.py",
        "tests/test_g005_provenance_sidecar.py",
        "tests/test_g005_evidence_extractor.py",
        "tests/test_g004_paired_structural_journal.py",
        "tests/test_g004_evidence_extractor.py",
        "tests/test_g003_proposed_call_diagnostic.py",
        "tests/test_g002_lifecycle_stage.py",
        "tests/test_deadline_reserve_g001.py",
    ]
    for name in relative_files:
        if not (PARENT / name).is_file():
            raise RuntimeError(f"Scoped source missing: {name}")
    SOURCE.mkdir(parents=True, exist_ok=False)
    bound = {}
    for name in relative_files:
        destination = SOURCE / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PARENT / name, destination)
        bound[name] = sha(PARENT / name)
    (OUT / "parent_source_bindings.json").write_text(
        json.dumps({
            "parent_tree_sha256": PARENT_TREE,
            "research_sha256": RESEARCH_SHA,
            "scoped_files": bound,
            "excluded": ["benchmark inputs", "corpus", "logs", "results", "validators", "credentials"],
        }, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "g006_scoped_workspace_ready", "scoped_file_count": len(bound)}))


if __name__ == "__main__":
    main()
