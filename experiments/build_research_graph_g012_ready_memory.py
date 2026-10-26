#!/usr/bin/env python3
"""Append G12 Research Meta's experiment-ready target without formal promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v10.json"
RESEARCH = BASE / "g012_research_meta_post_interface_003/final_raw.txt"
PACKET = BASE / "research_graph_solution_loop_meta_packet_g012_v3.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_memory_v11.json"
PREVIOUS_SHA = "7d0557b33c0e9a0ceb3eb116acd3e33cd834335b4fb8f4c18b1002dd2cead2d8"
RESEARCH_SHA = "67086825a82f1bd3bcc34297c85410ced236c965085c2ec94723bfc567c0b190"
PACKET_SHA = "a30b8734a82832ef02c43425868b8aa8fb0862f6223382fa4bed4c0b8c08185a"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if any(digest(path) != sha for path, sha in (
        (PREVIOUS, PREVIOUS_SHA), (RESEARCH, RESEARCH_SHA),
        (PACKET, PACKET_SHA), (G11_GRAPH, G11_GRAPH_SHA),
    )):
        raise RuntimeError("G12 ready-memory binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (research.get("schema_version") != "g012_post_interface_research_revision_v2"
            or research.get("selected_target_id") != "research_target:g012:002"
            or research.get("mechanism_id") != "mech_uncertainty_typed_evidence_state_and_gap_action"
            or research.get("state") != "experiment_ready"):
        raise RuntimeError("G12 ready target differs")
    spec = research.get("formal_spec")
    required = {"problem", "hypothesis", "experiment", "measurement_plan",
                "no_task_admission_gates", "claim_boundaries"}
    if not isinstance(spec, dict) or not required <= spec.keys():
        raise RuntimeError("G12 formal research specification is incomplete")
    parent = spec["experiment"]["code_parent"]
    protocol = spec["experiment"]["fixed_protocol"]
    if (parent.get("generation") != 11
            or parent.get("candidate_tree_sha256")
            != "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
            or protocol.get("frozen_task_count") != 56
            or protocol.get("hints") is not False
            or protocol.get("per_task_wall_timeout_seconds") != 1200
            or protocol.get("formal_runs") != 1
            or spec["no_task_admission_gates"].get("gate_status") != "not_yet_passed_by_this_revision"):
        raise RuntimeError("G12 parent, protocol, or gate contract differs")
    facts = set(packet["formal_evolution_layer"]["facts"])
    incubation_ids = {node["id"] for node in packet["research_incubation_layer"]["nodes"]}
    seen_facts = set()
    seen_nodes = set()
    for row in research.get("fact_assessment", []):
        if not isinstance(row.get("statement"), str) or not row["statement"].strip():
            raise RuntimeError("G12 fact assessment statement missing")
        cited_facts = set(row.get("fact_ids", []))
        cited_nodes = set(row.get("incubation_refs", []))
        if not cited_facts <= facts or not cited_nodes <= incubation_ids:
            raise RuntimeError("G12 fact assessment reference differs")
        seen_facts.update(cited_facts)
        seen_nodes.update(cited_nodes)
    required_facts = {
        f"g{generation:03d}_{suffix}"
        for generation in packet["formal_evolution_layer"]["generations"]
        for suffix in packet["formal_evolution_layer"]["fact_suffixes_per_generation"]
    }
    if (not required_facts <= seen_facts
            or not {"research_target:g012:002", "interface_investigation:g012:002",
                    "interface_finding:g012:002"} <= seen_nodes):
        raise RuntimeError("G12 ready output omits research history")
    node_id = "research_target:g012:003"
    incubation = previous["research_incubation_layer"]
    if node_id in {node["id"] for node in incubation["nodes"]}:
        raise RuntimeError("G12 ready target already exists")
    target = research["research_target"]
    prior_target = next(node for node in incubation["nodes"] if node["id"] == "research_target:g012:002")
    nodes = [*incubation["nodes"], {
        "id": node_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": "experiment_ready",
        "mechanism_id": research["mechanism_id"],
        "primary_lens": prior_target["primary_lens"],
        "related_lenses": prior_target["related_lenses"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "why_now": target["why_now"],
        "status": "formal_spec_proposed_admission_not_yet_passed",
        "artifacts": [_artifact(RESEARCH, ROOT)],
    }]
    edges = [*incubation["edges"],
             {"source": node_id, "relation": "revises", "target": "research_target:g012:002"},
             {"source": node_id, "relation": "informed_by", "target": "interface_finding:g012:002"}]
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
        raise RuntimeError("Research Graph memory v11 already differs")
    OUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": "current", "sha256": digest(OUT), "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
