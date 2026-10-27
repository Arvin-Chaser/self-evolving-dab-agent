"""Build the active G14 restart Graph view without rewriting v19 history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result

BASE = ROOT / "experiments" / "research_graph_baseline_20261016"
PREVIOUS = BASE / "research_graph_memory_v17.json"
PREVIOUS_SHA256 = "176d91bca69138088353be80735c9ce8c93d36bf8b661ca57d10cd3bf88cd648"
PACKET = BASE / "g014_restart_research_meta_001/active_restart_packet.json"
RESULT = BASE / "g014_restart_research_meta_001/final.json"
OUT = BASE / "research_graph_memory_g014_restart_active_v1.json"
RECEIPT = BASE / "g014_restart_research_meta_001/active_memory_receipt.json"
TARGET_ID = "research_target:g014:restart:001"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_same_or_new(path: Path, value: dict) -> None:
    text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"refusing to overwrite differing artifact: {path}")
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    if digest(PREVIOUS) != PREVIOUS_SHA256:
        raise RuntimeError("pre-G14 memory binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    validate_solution_loop_result(packet, result)
    target = result.get("research_target")
    if not isinstance(target, dict) or target.get("state") != "interface_investigation":
        raise RuntimeError("restart target is not an interface investigation")
    selected = [row for row in result["mechanism_candidates"] if row["mechanism_id"] == target["mechanism_id"]]
    if len(selected) != 1 or result["mechanism_ranking"][0]["mechanism_id"] != target["mechanism_id"]:
        raise RuntimeError("restart selection does not bind the rank-one candidate")
    incubation = previous["research_incubation_layer"]
    target_node = {
        "id": TARGET_ID, "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": target["state"], "mechanism_id": target["mechanism_id"],
        "statement": target["problem"], "hypothesis": target["hypothesis"],
        "status": "active_restart_selected_for_no_task_interface_investigation",
        "primary_lens": target["primary_lens"], "related_lenses": target["related_lenses"],
        "de_risk_questions": target["de_risk_questions"], "no_task_checks": target["no_task_checks"],
        "interface_gaps": target["interface_gaps"], "why_now": target["why_now"],
        "limitations": result.get("limitations", []),
        "artifacts": [_artifact(RESULT, ROOT), _artifact(PACKET, ROOT)],
    }
    edges = [*incubation["edges"], *({"source": TARGET_ID, "relation": "informed_by", "target": ref} for ref in selected[0]["incubation_refs"])]
    generations = sorted({int(fact_id[1:4]) for fact_id in selected[0]["fact_ids"]})
    cross_edges = [*previous["cross_layer_edges"], *({"source": TARGET_ID, "relation": "motivated_by", "target": f"evidence:g{generation:03d}"} for generation in generations)]
    refs = previous["formal_evolution_layer"]["generation_refs"]
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths={row["generation"]: ROOT / row["graph"]["path"] for row in refs},
        formal_graph_hashes={row["generation"]: row["graph"]["sha256"] for row in refs},
        incubation_nodes=[*incubation["nodes"], target_node], incubation_edges=edges,
        cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    write_same_or_new(OUT, memory)
    write_same_or_new(RECEIPT, {
        "schema_version": "g014_restart_active_memory_receipt_v1",
        "status": "active_restart_graph_built",
        "active_memory": {"path": str(OUT.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(OUT)},
        "base_memory": {"path": str(PREVIOUS.relative_to(ROOT)).replace("\\", "/"), "sha256": PREVIOUS_SHA256},
        "historical_v19_retained": True,
        "excluded_from_active_graph": ["research_target:g014:001", "interface_investigation:g014:001", "interface_finding:g014:001"],
        "active_target_id": TARGET_ID,
        "mechanism_id": target["mechanism_id"],
        "state": target["state"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
