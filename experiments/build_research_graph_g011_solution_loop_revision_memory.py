#!/usr/bin/env python3
"""Append the experiment-ready G11 ledger contract to incubation memory."""

from __future__ import annotations

import hashlib
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
PREVIOUS = BASE / "research_graph_memory_v3.json"
PREVIOUS_SHA256 = "9ae977d4a246314f286f2e5f1b8d61c67a372c5d11a72b11efb1602450654662"
REVISION_001 = BASE / "g011_research_meta_solution_loop_revision_001/final_raw.txt"
REVISION_002 = BASE / "g011_research_meta_solution_loop_revision_002/final_raw.txt"
REVISION_003 = BASE / "g011_research_meta_solution_loop_revision_003/final_raw.txt"
REVISION_003_SHA256 = "913ca8820208b6ee40ec91f268436c95e626412994e0c4cd88e78acddee9a28a"
OUT = BASE / "research_graph_memory_v4.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if sha(PREVIOUS) != PREVIOUS_SHA256 or sha(REVISION_003) != REVISION_003_SHA256:
        raise RuntimeError("G11 memory or experiment-ready Research revision hash differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    revision = json.loads(REVISION_003.read_text(encoding="utf-8"))
    target = revision["research_target"]
    decision = revision["promotion_decision"]
    spec = revision["formal_spec"]
    if (
        target.get("mechanism_id") != "mech_g011_structural_plan_evidence_ledger"
        or target.get("state") != "experiment_ready"
        or decision.get("state") != "experiment_ready"
        or not isinstance(spec, dict)
        or revision.get("candidate_or_evaluation_authorized") is not False
    ):
        raise RuntimeError("G11 experiment-ready Research contract differs")

    nodes = list(previous["research_incubation_layer"]["nodes"])
    nodes.append(
        {
            "id": "research_target:g011:004",
            "kind": "research_target",
            "evidence_class": "interface_research_not_benchmark_evidence",
            "state": "experiment_ready",
            "mechanism_id": target["mechanism_id"],
            "statement": target["problem"],
            "hypothesis": target["hypothesis"],
            "status": "formal_contract_ready_pending_implementation_admission",
            "code_parent": spec["code_parent"],
            "contract_boundary": (
                "Exact tested record schema is preserved. The fixed authoring instruction "
                "and guidance cap are new pre-registered experiment policies, not interface facts."
            ),
            "revision_history": [
                "revision_001 retained but failed its outer validator because an empty experiment-ready interface_gaps array was rejected",
                "revision_002 passed the outer validator but independent review found an unimplemented authoring overlay and prototype-cap labeling inconsistency",
                "revision_003 repaired both contract inconsistencies and is the authoritative experiment-ready revision",
            ],
            "limitations": revision["limitations"],
            "artifacts": [
                _artifact(REVISION_001, ROOT),
                _artifact(REVISION_002, ROOT),
                _artifact(REVISION_003, ROOT),
            ],
        }
    )
    edges = list(previous["research_incubation_layer"]["edges"])
    edges.extend(
        [
            {
                "source": "research_target:g011:004",
                "relation": "revises",
                "target": "research_target:g011:003",
            },
            {
                "source": "research_target:g011:004",
                "relation": "bounded_by",
                "target": "interface_finding:g011:002",
            },
        ]
    )
    cross_edges = list(previous["cross_layer_edges"])
    cross_edges.extend(
        {
            "source": "research_target:g011:004",
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
            raise RuntimeError("Research Graph memory v4 exists with different content")
        print(json.dumps({"status": "already_current", "path": str(OUT)}, sort_keys=True))
        return
    OUT.write_text(
        json.dumps(memory, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "created", "path": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
