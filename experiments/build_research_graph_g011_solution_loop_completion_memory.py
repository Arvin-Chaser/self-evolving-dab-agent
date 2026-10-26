#!/usr/bin/env python3
"""Append the completed G11 formal Graph and incubation promotion edge."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v5.json"
GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_memory_v6.json"
PREVIOUS_SHA = "0c83c560e7c94522ca2b618f7cec6b8b7a81c833c6e054ff0f18dfa7d1d481bf"
GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(PREVIOUS) != PREVIOUS_SHA or digest(GRAPH) != GRAPH_SHA:
        raise RuntimeError("G11 memory or formal Graph binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    if (graph.get("generation") != 11 or graph.get("status") != "four_nodes_complete"
            or [node.get("kind") for node in graph.get("nodes", [])]
            != ["problem", "hypothesis", "experiment", "evidence"]
            or graph["nodes"][3].get("specialized_status") != "untested"):
        raise RuntimeError("G11 completed formal Graph differs")
    cross_edges = list(previous["cross_layer_edges"])
    promotion = {
        "source": "research_target:g011:005",
        "relation": "promoted_to",
        "target": "experiment:g011",
    }
    if promotion in cross_edges:
        raise RuntimeError("G11 promotion edge already exists in previous memory")
    cross_edges.append(promotion)
    paths = {generation: graph_path(generation) for generation in range(11)}
    paths[11] = GRAPH
    hashes = {**GRAPH_HASHES, 11: GRAPH_SHA}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=paths,
        formal_graph_hashes=hashes,
        incubation_nodes=previous["research_incubation_layer"]["nodes"],
        incubation_edges=previous["research_incubation_layer"]["edges"],
        cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    if OUT.exists():
        if json.loads(OUT.read_text(encoding="utf-8")) != memory:
            raise RuntimeError("Research Graph memory v6 exists with different content")
        status = "already_current"
    else:
        OUT.write_text(json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        status = "created"
    print(json.dumps({
        "status": status, "path": str(OUT), "sha256": digest(OUT),
        "formal_generation_count": len(memory["formal_evolution_layer"]["generation_refs"]),
        "promotion_edge": promotion,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
