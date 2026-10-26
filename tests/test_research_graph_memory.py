"""Checks for the two-layer Research Graph memory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.research_graph_layered_meta_packet import build_layered_meta_packet
from experiments.research_graph_memory import validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "experiments/research_graph_baseline_20261016/research_graph_memory_v2.json"


def test_memory_keeps_formal_and_incubation_evidence_distinct():
    memory = json.loads(MEMORY.read_text(encoding="utf-8"))
    validate_research_memory(memory, root=ROOT)
    assert len(memory["formal_evolution_layer"]["generation_refs"]) == 11
    incubation = memory["research_incubation_layer"]
    assert {row["kind"] for row in incubation["nodes"]} >= {
        "research_target", "interface_investigation", "interface_finding"
    }
    assert all(
        row["evidence_class"] == "interface_research_not_benchmark_evidence"
        for row in incubation["nodes"]
    )
    assert any(row["relation"] == "revises" for row in incubation["edges"])
    assert any(row["relation"] == "motivated_by" for row in memory["cross_layer_edges"])


def test_layered_packet_binds_both_layers():
    import hashlib

    wanted = hashlib.sha256(MEMORY.read_bytes()).hexdigest()
    packet = build_layered_meta_packet(
        root=ROOT,
        graph_paths={generation: graph_path(generation) for generation in range(11)},
        graph_hashes=GRAPH_HASHES,
        memory_path=MEMORY,
        memory_sha256=wanted,
    )
    assert packet["formal_evolution_layer"]["generations"] == list(range(11))
    assert packet["research_incubation_layer"]["authority"] == "append_only_interface_research_history"
    assert packet["selection_policy"]["prompt_is_neutral"] is True


def test_incubation_artifact_tampering_is_rejected(tmp_path: Path):
    memory = json.loads(MEMORY.read_text(encoding="utf-8"))
    memory["research_incubation_layer"]["nodes"][0]["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Incubation artifact binding differs"):
        validate_research_memory(memory, root=ROOT)
