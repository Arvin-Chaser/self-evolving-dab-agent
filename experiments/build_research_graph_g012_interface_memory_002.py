#!/usr/bin/env python3
"""Append G12's second independently verified interface finding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v9.json"
WORK = BASE / "g012_interface_investigation_002"
SCOPED = WORK / "scoped_source"
MANIFEST = SCOPED / "exploratory_implementation_manifest.json"
FINDINGS = SCOPED / "BOUNDED_FINDINGS.md"
VERIFICATION = WORK / "independent_verification.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT = BASE / "research_graph_memory_v10.json"
PREVIOUS_SHA = "a518cbd3f23531e690712df2de1747f4c173fc9de1aa3fa0c128064460dec74c"
VERIFICATION_SHA = "2318e1aaa71d2b66a3bffea2c195f920197d79025abed59b3f5790e34705ea24"
G11_GRAPH_SHA = "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(PREVIOUS) != PREVIOUS_SHA or digest(VERIFICATION) != VERIFICATION_SHA:
        raise RuntimeError("G12 second finding input binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verification = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    if (manifest.get("selected_target_id") != "research_target:g012:002"
            or manifest.get("not_formal_candidate") is not True
            or verification.get("status") != "verified_conditional_action_interface_real_model_unknown"):
        raise RuntimeError("G12 second finding differs")
    investigation_id = "interface_investigation:g012:002"
    finding_id = "interface_finding:g012:002"
    incubation = previous["research_incubation_layer"]
    if {investigation_id, finding_id} & {node["id"] for node in incubation["nodes"]}:
        raise RuntimeError("G12 second finding already present")
    nodes = [*incubation["nodes"], {
        "id": investigation_id,
        "kind": "interface_investigation",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "scope": "source_review_and_no_task_structured_action_interface_prototype",
        "performed_by": "implementation_meta_exploratory_call",
        "status": "completed_independently_verified",
        "test_summary": "41_passed_independently",
        "artifacts": [_artifact(WORK / "input_binding.json", ROOT),
                      _artifact(MANIFEST, ROOT), _artifact(VERIFICATION, ROOT)],
    }, {
        "id": finding_id,
        "kind": "interface_finding",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "status": "conditional_action_interface_real_model_unknown",
        "statement": (
            "A structured unresolved-state view reaches the synthetic model-facing boundary and "
            "supports programmed action differentiation against generic guidance; real model adoption "
            "and provider acceptance remain untested."
        ),
        "established": verification["established"],
        "open_gaps": verification["open_gaps"],
        "remaining_unknowns": manifest["remaining_unknowns"],
        "claim_boundary": verification["claim_boundary"],
        "artifacts": [_artifact(MANIFEST, ROOT), _artifact(FINDINGS, ROOT),
                      _artifact(VERIFICATION, ROOT)],
    }]
    edges = [*incubation["edges"],
             {"source": investigation_id, "relation": "investigates", "target": "research_target:g012:002"},
             {"source": finding_id, "relation": "derived_from", "target": investigation_id}]
    paths = {generation: graph_path(generation) for generation in range(11)}
    paths[11] = G11_GRAPH
    memory = build_research_memory(
        root=ROOT, formal_graph_paths=paths,
        formal_graph_hashes={**GRAPH_HASHES, 11: G11_GRAPH_SHA},
        incubation_nodes=nodes, incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    content = json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("Research Graph memory v10 already differs")
    OUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": "current", "sha256": digest(OUT), "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
