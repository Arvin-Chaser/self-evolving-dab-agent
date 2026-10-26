#!/usr/bin/env python3
"""Export the answer-blind G14 post-interface Research Meta packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_solution_loop_meta_packet import (
    build_solution_loop_layered_packet,
)
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v19.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
G12_GRAPH = BASE / "g012_safe_snapshot/g012_graph.json"
G13_GRAPH = BASE / "g013_safe_snapshot/g013_graph.json"
OUT = BASE / "research_graph_solution_loop_meta_packet_g014_post_interface_v1.json"

MEMORY_SHA = "6415bd199798b4c54100afdb81874bd2eca5049a8e24a8aca4ed6694f3f74504"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"
G12_GRAPH_SHA = "790282ece9c81abad1b239c629cd622681162fcf94523b45c81df9de0fae9076"
G13_GRAPH_SHA = "a231eff12aad1d850b79b89e791bd1c8bd8d43d4941ff28c684cc8a4ff2b32b6"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    expected = {
        MEMORY: MEMORY_SHA,
        G11_GRAPH: G11_GRAPH_SHA,
        G12_GRAPH: G12_GRAPH_SHA,
        G13_GRAPH: G13_GRAPH_SHA,
    }
    for path, wanted in expected.items():
        if digest(path) != wanted:
            raise RuntimeError(f"G14 post-interface packet input differs: {path}")

    paths = {generation: graph_path(generation) for generation in range(11)}
    paths.update({11: G11_GRAPH, 12: G12_GRAPH, 13: G13_GRAPH})
    hashes = {
        **GRAPH_HASHES,
        11: G11_GRAPH_SHA,
        12: G12_GRAPH_SHA,
        13: G13_GRAPH_SHA,
    }
    packet = build_solution_loop_layered_packet(
        root=ROOT,
        graph_paths=paths,
        graph_hashes=hashes,
        memory_path=MEMORY,
        memory_sha256=MEMORY_SHA,
    )
    formal = packet["formal_evolution_layer"]
    incubation = packet["research_incubation_layer"]
    node_ids = {row["id"] for row in incubation["nodes"]}
    required_ids = {
        "research_target:g014:001",
        "interface_investigation:g014:001",
        "interface_finding:g014:001",
    }
    if formal["generations"] != list(range(14)):
        raise RuntimeError("G14 post-interface packet generation series differs")
    if len(incubation["nodes"]) != 30 or not required_ids <= node_ids:
        raise RuntimeError("G14 post-interface incubation history differs")

    rendered = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    forbidden = (
        '"raw_task"',
        '"answer"',
        '"hint"',
        '"validator"',
        '"raw_trace"',
        '"provider_transcript"',
        '"credential"',
    )
    if any(token in rendered for token in forbidden):
        raise RuntimeError("Forbidden content key entered G14 post-interface packet")
    if OUT.exists():
        if OUT.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("G14 post-interface packet already differs")
        status = "already_current"
    else:
        OUT.write_text(rendered, encoding="utf-8", newline="\n")
        status = "created"
    print(json.dumps({
        "status": status,
        "path": str(OUT),
        "sha256": digest(OUT),
        "bytes": OUT.stat().st_size,
        "formal_generations": len(formal["generations"]),
        "incubation_nodes": len(incubation["nodes"]),
        "verified_code_parents": len(formal["verified_code_parents"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
