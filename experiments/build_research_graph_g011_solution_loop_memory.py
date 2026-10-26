#!/usr/bin/env python3
"""Append the solution-loop target and verified interface finding to memory."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.research_graph_memory import (
    _artifact,
    build_research_memory,
    validate_research_memory,
)
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v2.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_002/final_raw.txt"
INVESTIGATION = BASE / "g011_solution_loop_interface_investigation_001"
SCOPED = INVESTIGATION / "scoped_source"
MANIFEST = SCOPED / "exploratory_implementation_manifest.json"
FINDINGS = SCOPED / "BOUNDED_FINDINGS.md"
VERIFICATION = INVESTIGATION / "independent_verification.json"
OUT = BASE / "research_graph_memory_v3.json"


def main() -> None:
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    target = research["research_target"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verification = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    if (
        target.get("mechanism_id") != "mech_g011_structural_plan_evidence_ledger"
        or target.get("state") != "interface_investigation"
        or manifest.get("status") != "feasible_bounded"
        or verification.get("status") != "artifacts_verified_transport_incomplete"
    ):
        raise RuntimeError("Solution-loop research or interface finding differs")

    nodes = list(previous["research_incubation_layer"]["nodes"])
    nodes.extend(
        [
            {
                "id": "research_target:g011:003",
                "kind": "research_target",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "state": target["state"],
                "mechanism_id": target["mechanism_id"],
                "primary_lens": target["primary_lens"],
                "related_lenses": target["related_lenses"],
                "statement": target["problem"],
                "hypothesis": target["hypothesis"],
                "status": "investigated_with_bounded_finding",
                "artifacts": [_artifact(RESEARCH, ROOT)],
            },
            {
                "id": "interface_investigation:g011:002",
                "kind": "interface_investigation",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "scope": "source_review_and_no_task_synthetic_behavior_prototype",
                "performed_by": "implementation_meta_exploratory_call",
                "status": "completed_artifacts_verified_transport_incomplete",
                "test_summary": "66_passed_independently",
                "transport_note": (
                    "The Meta SSE stream ended on idle timeout after artifacts were written. "
                    "No final model message exists; independent verification covers artifacts only."
                ),
                "artifacts": [
                    _artifact(INVESTIGATION / "input_binding.json", ROOT),
                    _artifact(MANIFEST, ROOT),
                    _artifact(VERIFICATION, ROOT),
                ],
            },
            {
                "id": "interface_finding:g011:002",
                "kind": "interface_finding",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "status": "bounded_substrate_feasible_end_to_end_unverified",
                "statement": manifest["status_interpretation"],
                "established": [
                    "The existing model-authored self-observation path can carry a strict task-agnostic plan/evidence record without creating a new tool primitive.",
                    "Record creation, revision order, provenance availability, truncation, failure, ambiguity, staleness, and unknown fallbacks are deterministically checkable.",
                    "A bounded call_llm guidance path can consume structural unresolved states and alter a synthetic next-action path without forging tool results, answers, or scoring.",
                    "Independent execution passed 66 no-task synthetic tests and matched every manifest output hash.",
                ],
                "blocked_scope": [
                    "General semantic support, contradiction, task relevance, answer correctness, or proof that a model-authored plan is good.",
                    "Claiming that a step/ref-index guidance message chooses the semantically correct query or evidence source.",
                    "Promotion before a safe real record-authoring contract, carrier no-leak review, real runner integration, and real-model behavior specification exist.",
                ],
                "unknowns": manifest["what_remains_unknown"],
                "limitations": [
                    manifest["critical_limitation"],
                    "The synthetic GuidanceAwarePolicy is programmed to react to guidance; real-model compliance and action quality were not tested.",
                    "The Implementation Meta final message was lost to a transport timeout; only independently verified saved artifacts are authoritative.",
                ],
                "artifacts": [
                    _artifact(MANIFEST, ROOT),
                    _artifact(FINDINGS, ROOT),
                    _artifact(VERIFICATION, ROOT),
                ],
            },
        ]
    )
    edges = list(previous["research_incubation_layer"]["edges"])
    edges.extend(
        [
            {
                "source": "research_target:g011:003",
                "relation": "revises",
                "target": "research_target:g011:002",
            },
            {
                "source": "research_target:g011:003",
                "relation": "informed_by",
                "target": "interface_finding:g011:001",
            },
            {
                "source": "interface_investigation:g011:002",
                "relation": "investigates",
                "target": "research_target:g011:003",
            },
            {
                "source": "interface_finding:g011:002",
                "relation": "derived_from",
                "target": "interface_investigation:g011:002",
            },
        ]
    )
    cross_edges = list(previous["cross_layer_edges"])
    cross_edges.extend(
        {
            "source": "research_target:g011:003",
            "relation": "motivated_by",
            "target": f"evidence:g{generation:03d}",
        }
        for generation in (8, 9, 10)
    )
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths={generation: graph_path(generation) for generation in range(11)},
        formal_graph_hashes=GRAPH_HASHES,
        incubation_nodes=nodes,
        incubation_edges=edges,
        cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        if existing != memory:
            raise RuntimeError("Research Graph memory v3 exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(
        json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
