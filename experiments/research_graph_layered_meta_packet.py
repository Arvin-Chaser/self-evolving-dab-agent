"""Build the Research Meta packet from both authoritative Research Graph layers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from experiments.research_graph_balanced_meta_packet import build_balanced_packet
from experiments.research_graph_memory import digest, validate_research_memory


def build_layered_meta_packet(
    *,
    root: Path,
    graph_paths: Mapping[int, Path],
    graph_hashes: Mapping[int, str],
    memory_path: Path,
    memory_sha256: str,
) -> dict:
    if digest(memory_path) != memory_sha256:
        raise ValueError("Two-layer Research Graph memory hash differs")
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    validate_research_memory(memory, root=root)
    formal = build_balanced_packet(graph_paths, graph_hashes)
    refs = memory["formal_evolution_layer"]["generation_refs"]
    if [row["graph"]["sha256"] for row in refs] != [
        formal["graph_sha256"][f"g{generation:03d}"] for generation in formal["generations"]
    ]:
        raise ValueError("Formal packet and Research Graph memory bindings differ")
    return {
        "schema_version": "research_graph_layered_meta_packet_v1",
        "research_memory_sha256": memory_sha256,
        "formal_evolution_layer": formal,
        "research_incubation_layer": memory["research_incubation_layer"],
        "cross_layer_edges": memory["cross_layer_edges"],
        "promotion_rule": memory["promotion_rule"],
        "selection_policy": {
            "prompt_is_neutral": True,
            "formal_evidence_and_interface_findings_are_distinct": True,
            "implementation_convenience_is_not_research_value": True,
            "incubation_history_is_append_only": True,
        },
    }

