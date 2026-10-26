#!/usr/bin/env python3
"""Bind an answer-free G4 child workspace for G5 Implementation Meta."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g004_candidate_002/repo"
OUT = BASE / "g005_candidate_001"
SOURCE = OUT / "scoped_source"
RESEARCH = BASE / "g005_research_meta_002/final_raw.txt"
PARENT_TREE = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError("G5 scoped workspace exists or Research Meta hash differs")
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    experiment = research["experiment"]
    if (
        experiment["code_parent_generation"] != "g004"
        or experiment["code_parent_tree_sha256"] != PARENT_TREE
        or [research[part]["id"] for part in ("problem", "hypothesis", "experiment")]
        != ["problem:g005", "hypothesis:g005", "experiment:g005"]
    ):
        raise RuntimeError("G5 research decision or parent binding differs")
    manifest_path = PARENT / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g5_parent_manifest", manifest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G4 parent source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(PARENT), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(rows) != PARENT_TREE:
        raise RuntimeError("G4 parent source tree changed")

    relative_files = [
        "experiments/run_dab_tool_agent.py",
        "experiments/run_multi_query_baseline.py",
        "experiments/g003_proposed_call_diagnostic.py",
        "experiments/g004_paired_structural_journal.py",
        "experiments/g004_postrun_structural_sidecar.py",
        "experiments/g004_evidence_extractor.py",
        "experiments/g002_lifecycle_stage.py",
        "external/DataAgentBench_official/common_scaffold/DataAgent.py",
        "tests/test_g004_paired_structural_journal.py",
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
        json.dumps(
            {
                "parent_tree_sha256": PARENT_TREE,
                "research_sha256": RESEARCH_SHA,
                "scoped_files": bound,
                "excluded": ["benchmark inputs", "corpus", "logs", "results", "validators", "credentials"],
            },
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "g005_scoped_workspace_ready", "scoped_file_count": len(bound)}))


if __name__ == "__main__":
    main()
