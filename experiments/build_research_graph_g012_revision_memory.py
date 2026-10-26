#!/usr/bin/env python3
"""Append the post-interface G12 Research Meta revision to incubation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v8.json"
RESEARCH = BASE / "g012_research_meta_post_interface_001/final_raw.txt"
PACKET = BASE / "research_graph_solution_loop_meta_packet_g012_v2.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_memory_v9.json"
PREVIOUS_SHA = "55c41e8b7e242543c8342120a3e42fdffcdfa4b34445a75e35a41825e49ba71b"
RESEARCH_SHA = "3124fcb7d12ab5a48436654451043fdcd1be27fe1897b53ed53eaa26d3467c72"
PACKET_SHA = "ff73fafaf3763a0ad9f28575d6fa1cb27df22c08a13f67446443b990a10c1a9f"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if any(digest(path) != expected for path, expected in (
        (PREVIOUS, PREVIOUS_SHA), (RESEARCH, RESEARCH_SHA),
        (PACKET, PACKET_SHA), (G11_GRAPH, G11_GRAPH_SHA),
    )):
        raise RuntimeError("G12 post-interface memory input differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (research.get("schema_version") != "g012_post_interface_research_revision_v1"
            or research.get("selected_target_id") != "research_target:g012:001"
            or research.get("mechanism_id") != "mech_uncertainty_typed_evidence_state_and_gap_action"
            or research.get("state") != "interface_investigation"
            or research.get("formal_spec") is not None):
        raise RuntimeError("G12 revision is not an interface-investigation result")
    facts = set(packet["formal_evolution_layer"]["facts"])
    node_ids = {node["id"] for node in packet["research_incubation_layer"]["nodes"]}
    assessments = research.get("fact_assessment")
    if not isinstance(assessments, list) or not assessments:
        raise RuntimeError("G12 fact assessment missing")
    seen_facts = set()
    seen_nodes = set()
    for row in assessments:
        if not isinstance(row.get("statement"), str) or not row["statement"].strip():
            raise RuntimeError("G12 fact assessment statement missing")
        cited_facts = set(row.get("fact_ids", []))
        cited_nodes = set(row.get("incubation_refs", []))
        if not cited_facts <= facts or not cited_nodes <= node_ids:
            raise RuntimeError("G12 fact assessment citation differs")
        seen_facts.update(cited_facts)
        seen_nodes.update(cited_nodes)
    required_facts = {
        f"g{generation:03d}_{suffix}"
        for generation in packet["formal_evolution_layer"]["generations"]
        for suffix in packet["formal_evolution_layer"]["fact_suffixes_per_generation"]
    }
    if (not required_facts <= seen_facts
            or not {"research_target:g012:001", "interface_investigation:g012:001",
                    "interface_finding:g012:001"} <= seen_nodes):
        raise RuntimeError("G12 revision omits formal or investigation evidence")
    node_id = "research_target:g012:002"
    incubation = previous["research_incubation_layer"]
    if node_id in {node["id"] for node in incubation["nodes"]}:
        raise RuntimeError("G12 revised target already present")
    target = research["research_target"]
    selected = next(node for node in incubation["nodes"] if node["id"] == "research_target:g012:001")
    nodes = [*incubation["nodes"], {
        "id": node_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": research["state"],
        "mechanism_id": research["mechanism_id"],
        "primary_lens": selected["primary_lens"],
        "related_lenses": selected["related_lenses"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "why_now": target["why_now"],
        "de_risk_questions": target["de_risk_questions"],
        "unresolved_interfaces": research["unresolved_interfaces"],
        "status": "revised_after_bounded_interface_finding_not_experiment_ready",
        "artifacts": [_artifact(RESEARCH, ROOT)],
    }]
    edges = [*incubation["edges"],
             {"source": node_id, "relation": "revises", "target": "research_target:g012:001"},
             {"source": node_id, "relation": "informed_by", "target": "interface_finding:g012:001"}]
    paths = {generation: graph_path(generation) for generation in range(11)}
    paths[11] = G11_GRAPH
    memory = build_research_memory(
        root=ROOT, formal_graph_paths=paths,
        formal_graph_hashes={**GRAPH_HASHES, 11: G11_GRAPH_SHA},
        incubation_nodes=nodes, incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    content = json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("Research Graph memory v9 already differs")
    OUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": "current", "sha256": digest(OUT), "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
