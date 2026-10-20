#!/usr/bin/env python3
"""Export the current two-layer Research Graph as a Research Meta input packet."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.research_graph_layered_meta_packet import build_layered_meta_packet
from experiments.research_graph_memory import digest
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v2.json"
OUT = BASE / "research_graph_layered_meta_packet_v1.json"


def main() -> None:
    packet = build_layered_meta_packet(
        root=ROOT,
        graph_paths={generation: graph_path(generation) for generation in range(11)},
        graph_hashes=GRAPH_HASHES,
        memory_path=MEMORY,
        memory_sha256=digest(MEMORY),
    )
    rendered = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists():
        if OUT.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("Layered Research Meta packet exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
