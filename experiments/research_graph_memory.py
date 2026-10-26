"""Build and validate the two-layer Research Graph memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


FORMAL_KINDS = ("problem", "hypothesis", "experiment", "evidence")
INCUBATION_KINDS = (
    "opportunity_snapshot",
    "interface_snapshot",
    "research_target",
    "interface_investigation",
    "interface_finding",
)
INCUBATION_EVIDENCE_CLASS = "interface_research_not_benchmark_evidence"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, root: Path) -> dict:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Research memory artifact is outside the repository")
    return {
        "path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": digest(resolved),
    }


def build_research_memory(
    *,
    root: Path,
    formal_graph_paths: Mapping[int, Path],
    formal_graph_hashes: Mapping[int, str],
    incubation_nodes: Sequence[dict],
    incubation_edges: Sequence[dict],
    cross_layer_edges: Sequence[dict],
) -> dict:
    generations = sorted(formal_graph_paths)
    if generations != list(range(generations[-1] + 1)):
        raise ValueError("Formal Graph series must be complete from G0")
    if set(formal_graph_hashes) != set(generations):
        raise ValueError("Formal Graph hashes do not match the generation set")

    formal_refs = []
    formal_node_ids = set()
    for generation in generations:
        path = formal_graph_paths[generation]
        if digest(path) != formal_graph_hashes[generation]:
            raise ValueError(f"G{generation} Graph hash differs")
        graph = json.loads(path.read_text(encoding="utf-8"))
        if graph.get("generation") != generation:
            raise ValueError(f"G{generation} Graph generation differs")
        nodes = graph.get("nodes")
        if not isinstance(nodes, list) or {row.get("kind") for row in nodes} != set(FORMAL_KINDS):
            raise ValueError(f"G{generation} formal node kinds differ")
        formal_node_ids.update(row["id"] for row in nodes)
        formal_refs.append({
            "generation": generation,
            "graph": _artifact(path, root),
            "status": graph.get("status"),
            "node_ids": [row["id"] for row in nodes],
        })

    nodes = [dict(row) for row in incubation_nodes]
    node_ids = [row.get("id") for row in nodes]
    if any(not isinstance(value, str) or not value for value in node_ids) or len(node_ids) != len(set(node_ids)):
        raise ValueError("Incubation node IDs must be unique non-empty strings")
    for node in nodes:
        if node.get("kind") not in INCUBATION_KINDS:
            raise ValueError("Unknown incubation node kind")
        if node.get("evidence_class") != INCUBATION_EVIDENCE_CLASS:
            raise ValueError("Incubation node must be marked as non-benchmark evidence")
        if node.get("kind") == "research_target" and node.get("state") not in {
            "interface_investigation", "experiment_ready", "closed"
        }:
            raise ValueError("Research target state differs")

    internal_ids = set(node_ids)
    for edge in incubation_edges:
        if edge.get("source") not in internal_ids or edge.get("target") not in internal_ids:
            raise ValueError("Incubation edge leaves the incubation layer")
        if not isinstance(edge.get("relation"), str) or not edge["relation"]:
            raise ValueError("Incubation edge relation is missing")
    for edge in cross_layer_edges:
        endpoints = {edge.get("source"), edge.get("target")}
        if not (endpoints & internal_ids and endpoints & formal_node_ids):
            raise ValueError("Cross-layer edge must join one node from each layer")
        if not isinstance(edge.get("relation"), str) or not edge["relation"]:
            raise ValueError("Cross-layer edge relation is missing")

    return {
        "schema_version": "research_graph_memory_v2",
        "status": "append_only_two_layer_research_memory",
        "formal_evolution_layer": {
            "authority": "frozen_formal_generation_graphs",
            "node_kinds": list(FORMAL_KINDS),
            "generation_refs": formal_refs,
            "rule": (
                "Each completed generation keeps exactly Problem, Hypothesis, Experiment, and Evidence. "
                "Only this layer contains benchmark Evidence."
            ),
        },
        "research_incubation_layer": {
            "authority": "append_only_interface_research_history",
            "node_kinds": list(INCUBATION_KINDS),
            "evidence_class": INCUBATION_EVIDENCE_CLASS,
            "nodes": nodes,
            "edges": [dict(row) for row in incubation_edges],
            "rule": (
                "Research Meta targets, Implementation Meta interface investigations, verified findings, "
                "and subsequent target revisions are retained here. These nodes describe feasibility and "
                "research state, never benchmark effect or answer correctness."
            ),
        },
        "cross_layer_edges": [dict(row) for row in cross_layer_edges],
        "promotion_rule": (
            "A research target may connect to a formal Experiment only after Research Meta emits an "
            "experiment_ready specification and the implementation passes deterministic admission. "
            "Promotion creates new formal nodes and never rewrites incubation history."
        ),
    }


def validate_research_memory(memory: dict, *, root: Path) -> None:
    if memory.get("schema_version") != "research_graph_memory_v2":
        raise ValueError("Research memory schema differs")
    formal = memory.get("formal_evolution_layer")
    incubation = memory.get("research_incubation_layer")
    if not isinstance(formal, dict) or not isinstance(incubation, dict):
        raise ValueError("Research memory layers are missing")
    refs = formal.get("generation_refs")
    if not isinstance(refs, list) or [row.get("generation") for row in refs] != list(range(len(refs))):
        raise ValueError("Formal generation references are incomplete")
    formal_ids = set()
    for row in refs:
        artifact = row.get("graph", {})
        path = (root / artifact.get("path", "")).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != artifact.get("sha256"):
            raise ValueError("Formal Graph binding differs")
        formal_ids.update(row.get("node_ids", []))

    nodes = incubation.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("Incubation nodes are missing")
    internal_ids = {row.get("id") for row in nodes}
    if None in internal_ids or len(internal_ids) != len(nodes):
        raise ValueError("Incubation node IDs differ")
    for node in nodes:
        if (node.get("kind") not in INCUBATION_KINDS
                or node.get("evidence_class") != INCUBATION_EVIDENCE_CLASS):
            raise ValueError("Incubation node boundary differs")
        for artifact in node.get("artifacts", []):
            path = (root / artifact.get("path", "")).resolve()
            if not path.is_relative_to(root.resolve()) or digest(path) != artifact.get("sha256"):
                raise ValueError("Incubation artifact binding differs")
    for edge in incubation.get("edges", []):
        if edge.get("source") not in internal_ids or edge.get("target") not in internal_ids:
            raise ValueError("Incubation edge differs")
    for edge in memory.get("cross_layer_edges", []):
        endpoints = {edge.get("source"), edge.get("target")}
        if not (endpoints & internal_ids and endpoints & formal_ids):
            raise ValueError("Cross-layer edge differs")
