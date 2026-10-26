#!/usr/bin/env python3
"""Materialize the two-layer Research Graph through the G11 interface loop."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
OUT = BASE / "research_graph_memory_v2.json"


def main() -> None:
    initial_path = BASE / "g011_research_meta_002/final_canonical.json"
    manifest_path = BASE / "g011_interface_investigation_001/scoped_source/exploratory_implementation_manifest.json"
    blocked_path = BASE / "g011_interface_investigation_001/scoped_source/BLOCKED.md"
    revision_path = BASE / "g011_research_meta_003/final_raw.txt"
    opportunity_path = BASE / "research_opportunity_registry_v1.json"
    capability_path = BASE / "runtime_interface_capability_map_v1.json"

    initial = json.loads(initial_path.read_text(encoding="utf-8"))["research_target"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = json.loads(revision_path.read_text(encoding="utf-8"))["research_target"]

    nodes = [
        {
            "id": "opportunity_snapshot:g011:bootstrap",
            "kind": "opportunity_snapshot",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "status": "historical_research_context",
            "statement": "Six-axis opportunity memory used to seed G11 incubation selection.",
            "artifacts": [_artifact(opportunity_path, ROOT)],
        },
        {
            "id": "interface_snapshot:g011:bootstrap",
            "kind": "interface_snapshot",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "status": "source_verified_snapshot",
            "statement": "Hash-bound runtime capability snapshot used before G11 interface investigation.",
            "artifacts": [_artifact(capability_path, ROOT)],
        },
        {
            "id": "research_target:g011:001",
            "kind": "research_target",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "state": initial["state"],
            "axis_id": initial["axis_id"],
            "statement": initial["problem"],
            "hypothesis": initial["hypothesis"],
            "status": "investigated_and_revised",
            "artifacts": [_artifact(initial_path, ROOT)],
        },
        {
            "id": "interface_investigation:g011:001",
            "kind": "interface_investigation",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "scope": "source_review_and_no_task_synthetic_prototype",
            "performed_by": "implementation_meta_exploratory_call",
            "status": "completed",
            "test_summary": manifest["tests"]["status"],
            "artifacts": [_artifact(manifest_path, ROOT), _artifact(blocked_path, ROOT)],
        },
        {
            "id": "interface_finding:g011:001",
            "kind": "interface_finding",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "status": "bounded_feasibility_with_general_scope_blocked",
            "statement": manifest["status_interpretation"],
            "established": [
                "Tool-call provenance and model-response turn availability can be checked structurally.",
                "A bounded structured scalar assertion can be checked against uniquely bound in-memory observations.",
                "The observation-only prototype passed synthetic no-leak and inertness checks."
            ],
            "blocked_scope": manifest["blocked_general_scope"],
            "unknowns": manifest["what_remains_unknown"],
            "limitations": [manifest["critical_limitation"]],
            "artifacts": [_artifact(manifest_path, ROOT), _artifact(blocked_path, ROOT)],
        },
        {
            "id": "research_target:g011:002",
            "kind": "research_target",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "state": revision["state"],
            "axis_id": revision["axis_id"],
            "statement": revision["problem"],
            "hypothesis": revision["hypothesis"],
            "status": "current_revised_target",
            "artifacts": [_artifact(revision_path, ROOT)],
        },
    ]
    incubation_edges = [
        {"source": "research_target:g011:001", "relation": "informed_by", "target": "opportunity_snapshot:g011:bootstrap"},
        {"source": "research_target:g011:001", "relation": "bounded_by", "target": "interface_snapshot:g011:bootstrap"},
        {"source": "interface_investigation:g011:001", "relation": "investigates", "target": "research_target:g011:001"},
        {"source": "interface_finding:g011:001", "relation": "derived_from", "target": "interface_investigation:g011:001"},
        {"source": "research_target:g011:002", "relation": "revises", "target": "research_target:g011:001"},
        {"source": "research_target:g011:002", "relation": "informed_by", "target": "interface_finding:g011:001"},
    ]
    cross_layer_edges = [
        {"source": "research_target:g011:001", "relation": "motivated_by", "target": "evidence:g008"},
        {"source": "research_target:g011:001", "relation": "motivated_by", "target": "evidence:g009"},
        {"source": "research_target:g011:001", "relation": "motivated_by", "target": "evidence:g010"},
    ]
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths={generation: graph_path(generation) for generation in range(11)},
        formal_graph_hashes=GRAPH_HASHES,
        incubation_nodes=nodes,
        incubation_edges=incubation_edges,
        cross_layer_edges=cross_layer_edges,
    )
    validate_research_memory(memory, root=ROOT)
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        if existing != memory:
            raise RuntimeError("Research Graph memory exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
