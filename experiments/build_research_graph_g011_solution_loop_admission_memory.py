#!/usr/bin/env python3
"""Append G11 Research Revision 004 and admitted implementation findings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v4.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
IMPLEMENTATION = WORK / "implementation_manifest_revision_002.json"
ASSEMBLY = BASE / "g011_solution_loop_candidate_003/assembly.json"
ADMISSION = BASE / "g011_solution_loop_candidate_003/admission.json"
OUT = BASE / "research_graph_memory_v5.json"

PREVIOUS_SHA256 = "b44810442c46501afb9d54a623a16610968c4fe1432d3019ab1b29beebbb5920"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA256 = "44a7a9508f8f1c68ab0ab70dfb3c820ca8f61eeefe880d1bc37453f614c75675"
ASSEMBLY_SHA256 = "e251b93d3e1d98b2acbb095a8ea133f3e1a9da16f64ebdd3d471dc1837ad48d7"
ADMISSION_SHA256 = "9121bfb8a6797d55086c18f433b067addd3df8f2ed0a950530442c21423ad068"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    expected = {
        PREVIOUS: PREVIOUS_SHA256,
        RESEARCH: RESEARCH_SHA256,
        IMPLEMENTATION: IMPLEMENTATION_SHA256,
        ASSEMBLY: ASSEMBLY_SHA256,
        ADMISSION: ADMISSION_SHA256,
    }
    if any(not path.is_file() or sha256(path) != digest for path, digest in expected.items()):
        raise RuntimeError("G11 admission-memory input binding differs")

    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    target = research["research_target"]
    if (
        target.get("mechanism_id") != "mech_g011_structural_plan_evidence_ledger"
        or target.get("state") != "experiment_ready"
        or research.get("promotion_decision", {}).get("state") != "experiment_ready"
        or implementation.get("formal_candidate") is not True
        or implementation.get("evaluation_run") is not False
        or admission.get("status") != "source_admitted_pending_remote_provider_and_runtime_preflight"
    ):
        raise RuntimeError("G11 Research or admitted implementation state differs")

    nodes = list(previous["research_incubation_layer"]["nodes"])
    nodes.extend(
        [
            {
                "id": "research_target:g011:005",
                "kind": "research_target",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "state": "experiment_ready",
                "mechanism_id": target["mechanism_id"],
                "statement": target["problem"],
                "hypothesis": target["hypothesis"],
                "status": "revision_004_authoritative_contract_source_admitted_pending_remote_preflight",
                "code_parent": research["formal_spec"]["code_parent"],
                "contract_boundary": (
                    "Exact structural schema and freeform carrier; model-authored state is not semantic support. "
                    "The authoring instruction and guidance cap are pre-registered experiment policies."
                ),
                "revision_note": (
                    "Revision 004 corrects Revision 003 by freezing self_observation.freeform and rejecting "
                    "the undeclared nested plan_record carrier. The unrelated report-exclusion sentence is "
                    "non-operative and supplies no launch permission or runtime behavior."
                ),
                "limitations": research["limitations"],
                "artifacts": [_artifact(RESEARCH, ROOT)],
            },
            {
                "id": "interface_investigation:g011:003",
                "kind": "interface_investigation",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "scope": "formal_implementation_repair_and_deterministic_source_admission_without_tasks",
                "performed_by": "implementation_meta_with_two_bounded_same_spec_repairs_and_outer_mechanical_admission",
                "status": "completed_no_formal_run",
                "test_summary": "116_g011_passed_269_candidate_passed_with_exact_five_inherited_parent_failures",
                "artifacts": [
                    _artifact(IMPLEMENTATION, ROOT),
                    _artifact(ASSEMBLY, ROOT),
                    _artifact(ADMISSION, ROOT),
                ],
            },
            {
                "id": "interface_finding:g011:003",
                "kind": "interface_finding",
                "evidence_class": "interface_research_not_benchmark_evidence",
                "status": "formal_candidate_source_admitted_pending_remote_provider_and_runtime_preflight",
                "statement": (
                    "The exact G11 structural ledger is implemented on G7 with an explicit default-off "
                    "multi-query activation path, pre-registered content-blind extractor, and deterministic "
                    "source admission. This establishes implementation conformance only."
                ),
                "established": [
                    "The declared self_observation.freeform carrier and nested-carrier rejection are bound to Research Revision 004.",
                    "The multi-query runner and single-task runner are both disabled by default; one explicit outer flag propagates verbatim to each child.",
                    "All 116 G11 no-task tests pass, and the complete candidate has exactly the same five inherited failures as G7 with no new failures.",
                    "The source archive, candidate tree, implementation manifest, fixed protocol, extractor, no-leak boundary, and change surface are hash-bound before any formal task.",
                ],
                "unknowns": [
                    "Live provider acceptance of the declared freeform tool schema remains for unified preflight.",
                    "Real upstream no-task response-boundary integration remains for unified preflight.",
                    "Real-model record authorship, identifier copying, guidance compliance, and any benchmark effect remain unknown.",
                ],
                "limitations": [
                    "No benchmark task, formal evaluation, answer correctness, semantic support, or causal score effect is established.",
                    "The five inherited G7 tool-failure-recovery test failures are unchanged and explicitly outside the G11 change claim.",
                ],
                "artifacts": [
                    _artifact(IMPLEMENTATION, ROOT),
                    _artifact(ADMISSION, ROOT),
                ],
            },
        ]
    )
    edges = list(previous["research_incubation_layer"]["edges"])
    edges.extend(
        [
            {"source": "research_target:g011:005", "relation": "revises", "target": "research_target:g011:004"},
            {"source": "research_target:g011:005", "relation": "informed_by", "target": "interface_finding:g011:002"},
            {"source": "interface_investigation:g011:003", "relation": "investigates", "target": "research_target:g011:005"},
            {"source": "interface_finding:g011:003", "relation": "derived_from", "target": "interface_investigation:g011:003"},
            {"source": "research_target:g011:005", "relation": "bounded_by", "target": "interface_finding:g011:003"},
        ]
    )
    cross_edges = list(previous["cross_layer_edges"])
    cross_edges.extend(
        {
            "source": "research_target:g011:005",
            "relation": "motivated_by",
            "target": f"evidence:g{generation:03d}",
        }
        for generation in (7, 8, 9, 10)
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
            raise RuntimeError("Research Graph memory v5 exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(json.dumps(memory, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
