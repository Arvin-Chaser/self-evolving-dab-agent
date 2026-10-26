#!/usr/bin/env python3
"""Append the validated G13 post-interface decision to research memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_g013_post_interface_meta import PACKET, validate


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v13.json"
RESEARCH = BASE / "g013_research_meta_post_interface_002/final_raw.txt"
OUT = BASE / "research_graph_memory_v14.json"
PREVIOUS_SHA = "e44ab7a0fbefa3e8689f37663d33c231dfb7318c0fcc82f17fa733c269170f94"
PACKET_SHA = "69f6ed15d6d536987d17ac647af22409e4385273281d64f7e60a88de618f1fdd"
RESEARCH_SHA = "10ea715d6c05a7c0c5fd1b489ec5933e4a274c6765e473c1a36bce21fc783f39"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    expected = ((PREVIOUS, PREVIOUS_SHA), (PACKET, PACKET_SHA), (RESEARCH, RESEARCH_SHA))
    if any(digest(path) != value for path, value in expected):
        raise RuntimeError("G13 post-interface memory input differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    validate(packet, research)
    if research["state"] != "interface_investigation":
        raise RuntimeError("G13 post-interface result is not the expected investigation branch")

    incubation = previous["research_incubation_layer"]
    node_id = "research_target:g013:002"
    if node_id in {node["id"] for node in incubation["nodes"]}:
        raise RuntimeError("G13 revised target already exists")
    target = research["research_target"]
    node = {
        "id": node_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": research["state"],
        "mechanism_id": research["mechanism_id"],
        "primary_lens": target["primary_lens"],
        "related_lenses": target["related_lenses"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "why_now": target["why_now"],
        "de_risk_questions": target["de_risk_questions"],
        "no_task_checks": target["no_task_checks"],
        "interface_gaps": target["interface_gaps"],
        "next_interface_investigation": research["next_interface_investigation"],
        "status": "revised_after_first_finding_requires_provider_boundary_investigation",
        "artifacts": [_artifact(RESEARCH, ROOT)],
    }
    nodes = [*incubation["nodes"], node]
    edges = [
        *incubation["edges"],
        {"source": node_id, "relation": "revises", "target": "research_target:g013:001"},
        {"source": node_id, "relation": "informed_by", "target": "interface_finding:g013:001"},
    ]
    refs = previous["formal_evolution_layer"]["generation_refs"]
    paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=paths,
        formal_graph_hashes=hashes,
        incubation_nodes=nodes,
        incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    content = json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("Research Graph memory v14 already differs")
    OUT.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": "post_interface_investigation_required",
        "path": str(OUT),
        "sha256": digest(OUT),
        "incubation_nodes": len(nodes),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
