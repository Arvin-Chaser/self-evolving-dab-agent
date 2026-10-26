#!/usr/bin/env python3
"""Append the validated G14 Research Meta target to incubation memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import (
    _artifact,
    build_research_memory,
    validate_research_memory,
)
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PACKET = BASE / "research_graph_solution_loop_meta_packet_g014_v1.json"
RESEARCH = BASE / "g014_research_meta_solution_loop_003/final_raw.txt"
PREVIOUS = BASE / "research_graph_memory_v17.json"
OUT = BASE / "research_graph_memory_v18.json"

PACKET_SHA = "0e4525b5f8378f536eb68fa36125d076f319b08ecd6dc60a80625a4824711b04"
RESEARCH_SHA = "5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad"
PREVIOUS_SHA = "176d91bca69138088353be80735c9ce8c93d36bf8b661ca57d10cd3bf88cd648"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def write_same_or_new(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    expected = {PACKET: PACKET_SHA, RESEARCH: RESEARCH_SHA, PREVIOUS: PREVIOUS_SHA}
    for path, wanted in expected.items():
        if digest(path) != wanted:
            raise RuntimeError(f"G14 target input binding differs: {path}")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_solution_loop_result(packet, research)
    validate_research_memory(previous, root=ROOT)

    target = research.get("research_target")
    if not isinstance(target, dict) or target.get("state") != "interface_investigation":
        raise RuntimeError("G14 target is not an interface investigation")
    if research["mechanism_ranking"][0]["mechanism_id"] != target["mechanism_id"]:
        raise RuntimeError("G14 target is not rank one")
    selected = [
        row for row in research["mechanism_candidates"]
        if row["mechanism_id"] == target["mechanism_id"]
    ]
    if len(selected) != 1:
        raise RuntimeError("G14 selected candidate differs")

    target_id = "research_target:g014:001"
    incubation = previous["research_incubation_layer"]
    if target_id in {row["id"] for row in incubation["nodes"]}:
        raise RuntimeError("G14 target ID already exists")
    target_node = {
        "id": target_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": target["state"],
        "mechanism_id": target["mechanism_id"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "status": "selected_for_no_task_interface_investigation",
        "primary_lens": target["primary_lens"],
        "related_lenses": target["related_lenses"],
        "de_risk_questions": target["de_risk_questions"],
        "no_task_checks": target["no_task_checks"],
        "interface_gaps": target["interface_gaps"],
        "why_now": target["why_now"],
        "limitations": research.get("limitations", []),
        "artifacts": [_artifact(RESEARCH, ROOT), _artifact(PACKET, ROOT)],
    }
    edges = [*incubation["edges"]]
    edges.extend(
        {"source": target_id, "relation": "informed_by", "target": ref}
        for ref in selected[0]["incubation_refs"]
    )
    cross_edges = [*previous["cross_layer_edges"]]
    generations = sorted({int(fact_id[1:4]) for fact_id in selected[0]["fact_ids"]})
    cross_edges.extend(
        {"source": target_id, "relation": "motivated_by", "target": f"evidence:g{generation:03d}"}
        for generation in generations
    )
    refs = previous["formal_evolution_layer"]["generation_refs"]
    graph_paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    graph_hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=graph_paths,
        formal_graph_hashes=graph_hashes,
        incubation_nodes=[*incubation["nodes"], target_node],
        incubation_edges=edges,
        cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    rendered = json_text(memory)
    write_same_or_new(OUT, rendered)
    print(
        json.dumps(
            {
                "status": "g014_research_target_appended",
                "target_id": target_id,
                "mechanism_id": target["mechanism_id"],
                "target_state": target["state"],
                "memory_path": str(OUT),
                "memory_sha256": digest(OUT),
                "formal_generations": len(refs),
                "incubation_nodes": len(memory["research_incubation_layer"]["nodes"]),
                "next": "bounded_no_task_interface_investigation",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
