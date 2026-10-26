#!/usr/bin/env python3
"""Append the bounded, rejected G14 interface finding to research memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import (
    _artifact,
    build_research_memory,
    validate_research_memory,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v18.json"
OUT = BASE / "research_graph_memory_v19.json"
REVIEW = BASE / "g014_interface_investigation_003/independent_failure_review.json"
MANIFESTS = [
    BASE / f"g014_interface_investigation_{number:03d}/scoped_source/exploratory_implementation_manifest.json"
    for number in (1, 2, 3)
]
EXPECTED = {
    PREVIOUS: "51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b",
    REVIEW: "c4c8c947b0a2b04ad0b822b50693c44f0f5206014e20fcd8a1b9118993766a51",
    MANIFESTS[0]: "8f8c42f0997f78f637d549f37abae9d165200bc0eae5697b1002814433d38ee4",
    MANIFESTS[1]: "d4c9b6ed8cc4f73b90455b29145172b644d8ff53cfb718b5aa3d9f9d83f0b5ad",
    MANIFESTS[2]: "22d1e78f44c54fd2143b758c473d3eb677f8c087b208009618d71233d9c4a04b",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    for path, expected in EXPECTED.items():
        if digest(path) != expected:
            raise RuntimeError(f"G14 rejected-finding input differs: {path}")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    if review.get("status") != "rejected_bounded_stop_return_to_research_control":
        raise RuntimeError("G14 rejected review status differs")
    if review.get("mechanism_id") != "mech_progressive_query_probing":
        raise RuntimeError("G14 rejected review mechanism differs")
    if [row.get("independent_test_result") for row in review["artifact_chain"]] != [
        "40 passed", "64 passed", "100 passed"
    ]:
        raise RuntimeError("G14 rejected review test chain differs")

    incubation = previous["research_incubation_layer"]
    existing = {node["id"] for node in incubation["nodes"]}
    investigation_id = "interface_investigation:g014:001"
    finding_id = "interface_finding:g014:001"
    if investigation_id in existing or finding_id in existing:
        raise RuntimeError("G14 rejected finding is already appended")

    investigation = {
        "id": investigation_id,
        "kind": "interface_investigation",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "performed_by": "codex_bounded_synthetic_interface_investigation",
        "scope": "synthetic_no_task_progressive_query_probe_interface",
        "status": "completed_but_rejected_after_three_bounded_revisions",
        "test_summary": ["40_passed_rejected", "64_passed_rejected", "100_passed_rejected"],
        "provider_request_count": 0,
        "benchmark_run": False,
        "database_accessed": False,
        "formal_candidate_created": False,
        "artifacts": [_artifact(path, ROOT) for path in MANIFESTS] + [_artifact(REVIEW, ROOT)],
    }
    finding = {
        "id": finding_id,
        "kind": "interface_finding",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "status": "rejected_bounded_stop_return_to_research_control",
        "statement": (
            "Three bounded no-task revisions passed their scoped suites but failed independent "
            "interface admission: boolean/integer aliases and caller-controlled cap/deadline "
            "bounds, direct public dataclass construction, and finally numeric-subclass "
            "comparison behavior each bypassed the claimed fail-closed policy boundary."
        ),
        "verified": review["independently_passed_boundaries"],
        "contradicted": [row["finding"] for row in review["failed_reviews"]],
        "unknown": review["unpassed_or_unknown"],
        "claim_boundary": {
            "benchmark_evidence": False,
            "formal_candidate": False,
            "formal_experiment": False,
            "real_model_behavior_proven": False,
            "causal_benefit_proven": False,
        },
        "artifacts": [_artifact(REVIEW, ROOT), *[_artifact(path, ROOT) for path in MANIFESTS]],
    }
    nodes = [*incubation["nodes"], investigation, finding]
    edges = [
        *incubation["edges"],
        {"source": investigation_id, "relation": "investigates", "target": "research_target:g014:001"},
        {"source": finding_id, "relation": "derived_from", "target": investigation_id},
    ]
    refs = previous["formal_evolution_layer"]["generation_refs"]
    graph_paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    graph_hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=graph_paths,
        formal_graph_hashes=graph_hashes,
        incubation_nodes=nodes,
        incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    content = json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("Research Graph memory v19 already differs")
    OUT.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": "g014_rejected_interface_finding_appended",
        "path": str(OUT),
        "sha256": digest(OUT),
        "formal_generations": len(refs),
        "incubation_nodes": len(nodes),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
