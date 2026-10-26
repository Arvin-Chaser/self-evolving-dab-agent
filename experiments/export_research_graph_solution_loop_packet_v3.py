#!/usr/bin/env python3
"""Export the post-interface solution-loop Research Meta packet."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.research_graph_memory import digest
from experiments.research_graph_solution_loop_meta_packet import (
    build_solution_loop_layered_packet,
)
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
MEMORY = BASE / "research_graph_memory_v3.json"
OUT = BASE / "research_graph_solution_loop_meta_packet_v3.json"


def main() -> None:
    packet = build_solution_loop_layered_packet(
        root=ROOT,
        graph_paths={generation: graph_path(generation) for generation in range(11)},
        graph_hashes=GRAPH_HASHES,
        memory_path=MEMORY,
        memory_sha256=digest(MEMORY),
    )
    packet["schema_version"] = "research_graph_solution_loop_post_interface_packet_v3"
    packet["research_phase"] = {
        "mode": "selected_mechanism_post_interface_revision",
        "selected_target_id": "research_target:g011:003",
        "selected_investigation_id": "interface_investigation:g011:002",
        "selected_finding_id": "interface_finding:g011:002",
        "allowed_revision_states": ["interface_investigation", "experiment_ready", "closed"],
        "implementation_or_evaluation_authorized": False,
    }
    rendered = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists():
        if OUT.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("Post-interface packet exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
