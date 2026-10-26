#!/usr/bin/env python3
"""Export the hash-bound G13 post-provider-finding Research Meta packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_solution_loop_meta_packet import (
    build_solution_loop_layered_packet,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v15.json"
OUT = BASE / "research_graph_solution_loop_meta_packet_g013_post_finding_v1.json"
MEMORY_SHA = "4206f1706eafbcd12bf318fed01acb0bac6f2a17843f216b310f1af9ad35429b"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(MEMORY) != MEMORY_SHA:
        raise RuntimeError("G13 post-finding memory binding differs")
    memory = json.loads(MEMORY.read_text(encoding="utf-8"))
    refs = memory["formal_evolution_layer"]["generation_refs"]
    if [row["generation"] for row in refs] != list(range(13)):
        raise RuntimeError("G13 post-finding formal history differs")
    graph_paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    graph_hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    packet = build_solution_loop_layered_packet(
        root=ROOT,
        graph_paths=graph_paths,
        graph_hashes=graph_hashes,
        memory_path=MEMORY,
        memory_sha256=MEMORY_SHA,
    )
    if packet["formal_evolution_layer"]["generations"] != list(range(13)):
        raise RuntimeError("G13 post-finding packet omits formal history")
    node_ids = {node["id"] for node in packet["research_incubation_layer"]["nodes"]}
    required = {
        "research_target:g013:001",
        "interface_investigation:g013:001",
        "interface_finding:g013:001",
        "research_target:g013:002",
        "interface_investigation:g013:002",
        "interface_finding:g013:002",
    }
    if not required <= node_ids or len(node_ids) != 26:
        raise RuntimeError("G13 post-finding packet omits the complete finding chain")
    content = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("G13 post-finding packet already differs")
    OUT.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps({"path": str(OUT), "sha256": digest(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
