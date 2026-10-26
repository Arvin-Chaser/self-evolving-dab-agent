#!/usr/bin/env python3
"""Export the G0-G11 two-layer, answer-blind G12 Research Meta packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_solution_loop_meta_packet import build_solution_loop_layered_packet
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v6.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_solution_loop_meta_packet_g012_v1.json"
MEMORY_SHA = "f544d7d0f419707faa37043d0c55e8a9c307aad9b735a087079f7811308a281d"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(MEMORY) != MEMORY_SHA or digest(G11_GRAPH) != G11_GRAPH_SHA:
        raise RuntimeError("G12 Research Graph input binding differs")
    paths = {generation: graph_path(generation) for generation in range(11)}
    paths[11] = G11_GRAPH
    packet = build_solution_loop_layered_packet(
        root=ROOT,
        graph_paths=paths,
        graph_hashes={**GRAPH_HASHES, 11: G11_GRAPH_SHA},
        memory_path=MEMORY,
        memory_sha256=MEMORY_SHA,
    )
    if packet["formal_evolution_layer"]["generations"] != list(range(12)):
        raise RuntimeError("G12 packet does not cover G0-G11")
    rendered = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if "g011_nonadoption_diagnosis" in rendered:
        raise RuntimeError("Human diagnostic entered Research Meta packet")
    if OUT.exists():
        if OUT.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("G12 packet exists with different content")
        status = "already_current"
    else:
        OUT.write_text(rendered, encoding="utf-8")
        status = "created"
    print(json.dumps({"status": status, "path": str(OUT), "sha256": digest(OUT),
                      "generations": len(packet["formal_evolution_layer"]["generations"]),
                      "incubation_nodes": len(packet["research_incubation_layer"]["nodes"])}, sort_keys=True))


if __name__ == "__main__":
    main()
