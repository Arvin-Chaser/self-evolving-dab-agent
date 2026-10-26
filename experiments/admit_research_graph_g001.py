#!/usr/bin/env python3
"""Answer-blind source admission for the isolated G1 candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g001_candidate_003/repo"
ARCHIVE = BASE / "baseline_source.tar.gz"
RESEARCH = BASE / "g001_research_meta_004/result.json"
OUT = BASE / "g001_candidate_003/admission.json"
EXPECTED_ARCHIVE = "e417bbaf334387c0511bdfeb37dd6788896d595af8389971639394eda8dd8303"
EXPECTED_RESEARCH = "fc8bf2c66be8c53fbe4af12fc5af15d27f460351400fed44a7f9e50805be0459"
EXPECTED_PARENT_TREE = "93e4d9ebf9d8e8b0f4d6b8b356926b7ab7a66a125dc9652d30aac86e930d4eb9"
EXPECTED_G0_RUNNER = "6bff187bc483d92aa47ebf6471c79383d6e31f701aff2d52b3c5086974cf9baf"
ALLOWED = {
    "experiments/run_dab_tool_agent.py",
    "experiments/run_multi_query_baseline.py",
    "prompts/dab/dab_tool_agent_policy_zero_start.txt",
    "tests/test_deadline_reserve_g001.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G1 admission already exists")
    if digest(ARCHIVE) != EXPECTED_ARCHIVE or digest(RESEARCH) != EXPECTED_RESEARCH:
        raise RuntimeError("Frozen source or research decision changed")
    if digest(BASE / "frozen_g0_runner.py") != EXPECTED_G0_RUNNER:
        raise RuntimeError("Actual G0 runner snapshot changed")
    decision = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if decision.get("implementation_ready") is not True or decision["experiment"]["code_parent"] != "root_baseline":
        raise RuntimeError("Research decision does not admit implementation")
    spec = importlib.util.spec_from_file_location("g1_manifest", CHILD / "experiments/intent_candidate_workspace.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(CHILD), key=lambda row: row["path"].lower())
    current = {row["path"]: row["sha256"] for row in rows}
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        baseline = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = member.name.removeprefix("./")
            if path not in current and path != "experiments/run_multi_query_baseline.py":
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError(f"Cannot read archived source: {path}")
            baseline[path] = hashlib.sha256(stream.read()).hexdigest()
    expected_paths = set(baseline) | {"tests/test_deadline_reserve_g001.py"}
    if set(current) != expected_paths:
        raise RuntimeError(f"Candidate source path set changed: {set(current) ^ expected_paths}")
    changed = {path for path in current if current[path] != baseline.get(path)}
    if changed != ALLOWED:
        raise RuntimeError(f"Unexpected candidate edits: {changed ^ ALLOWED}")
    parent_rows = [{"path": path, "sha256": sha} for path, sha in baseline.items()]
    parent_rows.sort(key=lambda row: row["path"].lower())
    if module.source_manifest_hash(parent_rows) != EXPECTED_PARENT_TREE:
        raise RuntimeError("Candidate parent is not the frozen baseline source tree")
    payload = {
        "schema_version": "dab_research_graph_g001_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "root_baseline",
        "parent_tree_sha256": EXPECTED_PARENT_TREE,
        "actual_g0_runner_parent_sha256": EXPECTED_G0_RUNNER,
        "research_result_sha256": EXPECTED_RESEARCH,
        "candidate_tree_sha256": module.source_manifest_hash(rows),
        "changed_files": {path: current[path] for path in sorted(changed)},
        "source_file_count": len(rows),
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
