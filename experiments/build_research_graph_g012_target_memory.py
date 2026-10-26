#!/usr/bin/env python3
"""Append the independently selected G12 target to Research Graph incubation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v6.json"
RESEARCH = BASE / "g012_research_meta_solution_loop_002/final_raw.txt"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_memory_v7.json"
PREVIOUS_SHA = "f544d7d0f419707faa37043d0c55e8a9c307aad9b735a087079f7811308a281d"
RESEARCH_SHA = "dbec815cb166728bfabf9f3fface219bccce0da72ffd58e23e1c5e6f0967eefc"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if any(digest(path) != expected for path, expected in (
        (PREVIOUS, PREVIOUS_SHA), (RESEARCH, RESEARCH_SHA), (G11_GRAPH, G11_GRAPH_SHA)
    )):
        raise RuntimeError("G12 target-memory input binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    target = research.get("research_target")
    if not isinstance(target, dict) or target.get("state") != "interface_investigation":
        raise RuntimeError("G12 research target state differs")
    candidates = [row for row in research["mechanism_candidates"]
                  if row["mechanism_id"] == target["mechanism_id"]]
    if len(candidates) != 1 or research["mechanism_ranking"][0]["mechanism_id"] != target["mechanism_id"]:
        raise RuntimeError("G12 selected mechanism differs from rank one")
    selected = candidates[0]
    node_id = "research_target:g012:001"
    node = {
        "id": node_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": "interface_investigation",
        "mechanism_id": target["mechanism_id"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "status": "selected_for_no_task_interface_investigation",
        "primary_lens": target["primary_lens"],
        "related_lenses": target["related_lenses"],
        "de_risk_questions": target["de_risk_questions"],
        "no_task_checks": target["no_task_checks"],
        "interface_gaps": target["interface_gaps"],
        "limitations": research.get("limitations", []),
        "artifacts": [_artifact(RESEARCH, ROOT)],
    }
    incubation = previous["research_incubation_layer"]
    known_ids = {item["id"] for item in incubation["nodes"]}
    if node_id in known_ids or any(ref not in known_ids for ref in selected["incubation_refs"]):
        raise RuntimeError("G12 incubation reference differs")
    internal_edges = list(incubation["edges"])
    internal_edges.extend({"source": node_id, "relation": "informed_by", "target": ref}
                          for ref in selected["incubation_refs"])
    cited_generations = sorted({int(fact_id[1:4]) for fact_id in selected["fact_ids"]})
    cross_edges = list(previous["cross_layer_edges"])
    cross_edges.extend({"source": node_id, "relation": "motivated_by",
                        "target": f"evidence:g{generation:03d}"}
                       for generation in cited_generations)
    graph_paths = {generation: graph_path(generation) for generation in range(11)}
    graph_paths[11] = G11_GRAPH
    memory = build_research_memory(
        root=ROOT, formal_graph_paths=graph_paths,
        formal_graph_hashes={**GRAPH_HASHES, 11: G11_GRAPH_SHA},
        incubation_nodes=[*incubation["nodes"], node],
        incubation_edges=internal_edges, cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    if OUT.exists():
        if json.loads(OUT.read_text(encoding="utf-8")) != memory:
            raise RuntimeError("Research Graph memory v7 exists with different content")
        status = "already_current"
    else:
        OUT.write_text(json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        status = "created"
    print(json.dumps({"status": status, "sha256": digest(OUT), "path": str(OUT),
                      "target_id": node_id, "motivated_by_generations": cited_generations}, sort_keys=True))


if __name__ == "__main__":
    main()
