#!/usr/bin/env python3
"""Admit the isolated G2 lifecycle candidate against frozen G1 and Meta."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g001_candidate_003/repo"
CHILD = BASE / "g002_candidate_001/repo"
META = BASE / "g002_research_meta_004/canonical_result.json"
GRAPH = BASE / "g001_graph.json"
OUT = BASE / "g002_candidate_001/admission.json"
ARCHIVE = BASE / "g002_candidate_001/source.tar.gz"
EXPECTED_PARENT = "8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d"
EXPECTED_META = "56d5a3b376a335cca3f4289ee955addaa5ae017a6d7c3b14915bfe9b2b5411e3"
EXPECTED_GRAPH = "c8d35afeb677d018c76711737df8c30b468e1574c18d7450702188a857196b9b"
EXPECTED_BATCH = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
EXPECTED_REGISTRY = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
ALLOWED_DELTA = {
    "experiments/g002_lifecycle_stage.py",
    "experiments/run_dab_tool_agent.py",
    "experiments/run_multi_query_baseline.py",
    "tests/test_g002_lifecycle_stage.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest(root: Path):
    spec = importlib.util.spec_from_file_location("g2_manifest", root / "experiments/intent_candidate_workspace.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Source manifest module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(root), key=lambda row: row["path"].lower())
    return module, rows


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G2 admission or source archive already exists")
    if sha(META) != EXPECTED_META or sha(GRAPH) != EXPECTED_GRAPH:
        raise RuntimeError("Frozen Meta or G1 Graph changed")
    proposal = json.loads(META.read_text(encoding="utf-8"))
    if (proposal.get("research_ready") is not True
            or proposal.get("implementation_ready") is not True
            or proposal["experiment"]["code_parent"] != "g001_deadline_reserve"):
        raise RuntimeError("G2 Meta does not admit this code parent")
    module, parent_rows = source_manifest(PARENT)
    _, child_rows = source_manifest(CHILD)
    if module.source_manifest_hash(parent_rows) != EXPECTED_PARENT:
        raise RuntimeError("G1 code parent changed")
    parent = {row["path"]: row["sha256"] for row in parent_rows}
    child = {row["path"]: row["sha256"] for row in child_rows}
    changed = {path for path in set(parent) | set(child) if parent.get(path) != child.get(path)}
    if changed != ALLOWED_DELTA or (set(child) - set(parent)) != {
            "experiments/g002_lifecycle_stage.py", "tests/test_g002_lifecycle_stage.py"}:
        raise RuntimeError(f"G2 source delta differs: {sorted(changed)}")
    batch = CHILD / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
    registry = CHILD / "dab_corpus/registry.json"
    if sha(batch) != EXPECTED_BATCH or sha(registry) != EXPECTED_REGISTRY:
        raise RuntimeError("G2 frozen batch or registry differs")
    included = sorted(set(child) | {
        "AGENTS.md", "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json",
        "dab_corpus/registry.json"})
    for name in included:
        path = CHILD / name
        if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve())):
            raise RuntimeError(f"Unsafe G2 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)
    payload = {
        "schema_version": "dab_research_graph_g002_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "g001_deadline_reserve",
        "parent_tree_sha256": EXPECTED_PARENT,
        "g1_graph_sha256": EXPECTED_GRAPH,
        "research_result_sha256": EXPECTED_META,
        "candidate_tree_sha256": module.source_manifest_hash(child_rows),
        "source_archive_sha256": sha(ARCHIVE),
        "changed_files": {name: child[name] for name in sorted(changed)},
        "source_file_count": len(child_rows),
        "batch_sha256": EXPECTED_BATCH,
        "registry_sha256": EXPECTED_REGISTRY,
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
