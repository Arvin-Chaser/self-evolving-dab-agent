#!/usr/bin/env python3
"""Export full formal history and G12's second interface finding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_solution_loop_meta_packet import build_solution_loop_layered_packet
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v10.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_solution_loop_meta_packet_g012_v3.json"
MEMORY_SHA = "7d0557b33c0e9a0ceb3eb116acd3e33cd834335b4fb8f4c18b1002dd2cead2d8"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(MEMORY) != MEMORY_SHA or digest(G11_GRAPH) != G11_GRAPH_SHA:
        raise RuntimeError("G12 second post-interface packet binding differs")
    paths = {generation: graph_path(generation) for generation in range(11)}
    paths[11] = G11_GRAPH
    packet = build_solution_loop_layered_packet(
        root=ROOT, graph_paths=paths,
        graph_hashes={**GRAPH_HASHES, 11: G11_GRAPH_SHA},
        memory_path=MEMORY, memory_sha256=MEMORY_SHA,
    )
    if packet["formal_evolution_layer"]["generations"] != list(range(12)):
        raise RuntimeError("G12 packet omits a formal generation")
    node_ids = {node["id"] for node in packet["research_incubation_layer"]["nodes"]}
    if not {"research_target:g012:002", "interface_investigation:g012:002",
            "interface_finding:g012:002"} <= node_ids:
        raise RuntimeError("G12 packet omits the second finding")
    content = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if "g011_nonadoption_diagnosis" in content:
        raise RuntimeError("Human diagnosis entered Research Meta packet")
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("G12 second revision packet already differs")
    OUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": "current", "sha256": digest(OUT), "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
