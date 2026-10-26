#!/usr/bin/env python3
"""Freeze the validated G13 contract and append its experiment-ready target."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_g013_post_finding_meta import PACKET, validate


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v15.json"
INVALID = BASE / "g013_research_meta_post_finding_001/final_raw.txt"
RESEARCH = BASE / "g013_research_meta_post_finding_002/final_raw.txt"
CONTRACT = BASE / "g013_formal_research_contract.json"
OUT = BASE / "research_graph_memory_v16.json"
PREVIOUS_SHA = "4206f1706eafbcd12bf318fed01acb0bac6f2a17843f216b310f1af9ad35429b"
PACKET_SHA = "40c6b556a561e54c1beb71484783c8f873c4ab8d86eac24bca3aa325640cc393"
INVALID_SHA = "17dcbde71f9b6c3adbb0d4f76d207fb02bac90230da30bb027f468f8961d8695"
RESEARCH_SHA = "0e01fa9290e8ecf722a3e3092e60b74c335b15f439811774cb0c4bb4210bf3b1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_same_or_new(path: Path, value: object) -> None:
    content = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def normalized_invalid(value: dict) -> dict:
    normalized = json.loads(json.dumps(value))
    formal = normalized["formal_spec"]
    old = formal["fixed_protocol"]
    formal["fixed_protocol"] = {
        "task_count": old["frozen_task_count"],
        "hint_mode": old["description_mode"],
        "wall_timeout_seconds_per_task": old["per_task_wall_timeout_seconds"],
        "primary_metric": "strict_pass_over_56",
        "arms": old["arms"],
    }
    measurement = formal["measurement_plan"]
    measurement["structural_binding_endpoint"] = measurement.pop(
        "separate_structural_binding_endpoint"
    )
    return normalized


def main() -> None:
    expected = (
        (PREVIOUS, PREVIOUS_SHA), (PACKET, PACKET_SHA),
        (INVALID, INVALID_SHA), (RESEARCH, RESEARCH_SHA),
    )
    if any(not path.is_file() or digest(path) != sha for path, sha in expected):
        raise RuntimeError("G13 post-finding finalization input differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    invalid = json.loads(INVALID.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    validate(packet, research)
    if research["state"] != "experiment_ready":
        raise RuntimeError("G13 post-finding result is not experiment-ready")
    if normalized_invalid(invalid) != research:
        raise RuntimeError("G13 revision changed more than the audited serialization")

    contract = {
        "schema_version": "g013_formal_research_contract_v1",
        "status": "experiment_ready_not_implemented_or_admitted",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": research["selected_target_id"],
        "mechanism_id": research["mechanism_id"],
        "packet_sha256": PACKET_SHA,
        "research_meta_output_sha256": RESEARCH_SHA,
        "interface_bindings": {
            "first_findings_sha256": "745fe68e7d62bd590e89681bee8e47065bdc0430aab6c0a836ebde207b9bc7f6",
            "first_manifest_sha256": "f5fd8fa52df71196f101686c33f2569f22e28a354ab08b97e44eeeb6f3391db7",
            "first_verification_sha256": "8f95b4cfc9c8a29f1e2419e45382a766446c3dce3ccc1449ed5e1b6468003f6b",
            "second_receipt_sha256": "1eb66dcabf19bfad3802a54095bf480e0ea546fe6694a65f3015795cca8d0963",
            "second_findings_sha256": "2e6ada16d49a46a12b605a35b2931f61527c3966a7a1e85532e494a6b243f89b",
            "second_manifest_sha256": "9e5fca88d8ae5c23ea155bf564a0a4ab9793c0a3b4a11ce2b6361fad3a63da73",
            "second_verification_sha256": "3f1b9512085b9475f7feff6da14124683ce528be9f9904356c27b0bf8135bcdb",
        },
        "research_target": research["research_target"],
        "formal_spec": research["formal_spec"],
        "limitations": research["limitations"],
        "claim_boundary": {
            "implementation_created": False,
            "admission_passed": False,
            "formal_experiment_run": False,
            "benchmark_evidence": False,
            "causal_benefit_proven": False,
            "candidate_or_evaluation_authorized_by_meta": False,
        },
    }
    write_same_or_new(CONTRACT, contract)

    incubation = previous["research_incubation_layer"]
    node_id = "research_target:g013:003"
    if node_id in {node["id"] for node in incubation["nodes"]}:
        raise RuntimeError("G13 experiment-ready target already exists")
    target = research["research_target"]
    parent = research["formal_spec"]["code_parent"]
    node = {
        "id": node_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": "experiment_ready",
        "mechanism_id": research["mechanism_id"],
        "primary_lens": target["primary_lens"],
        "related_lenses": target["related_lenses"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "why_now": target["why_now"],
        "code_parent": parent,
        "status": "formal_contract_frozen_implementation_not_started",
        "artifacts": [_artifact(RESEARCH, ROOT), _artifact(CONTRACT, ROOT)],
    }
    nodes = [*incubation["nodes"], node]
    edges = [
        *incubation["edges"],
        {"source": node_id, "relation": "revises", "target": "research_target:g013:002"},
        {"source": node_id, "relation": "informed_by", "target": "interface_finding:g013:002"},
    ]
    refs = previous["formal_evolution_layer"]["generation_refs"]
    paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=paths,
        formal_graph_hashes=hashes,
        incubation_nodes=nodes,
        incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    write_same_or_new(OUT, memory)
    print(json.dumps({
        "status": contract["status"],
        "contract_path": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "memory_path": str(OUT),
        "memory_sha256": digest(OUT),
        "code_parent_generation": parent["generation"],
        "code_parent_sha256": parent["candidate_tree_sha256"],
        "incubation_nodes": len(nodes),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
