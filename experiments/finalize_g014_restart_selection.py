"""Losslessly validate the one saved G14 restart Research Meta response."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result

BASE = ROOT / "experiments" / "research_graph_baseline_20261016"
OUT = BASE / "g014_restart_research_meta_001"
PACKET = OUT / "active_restart_packet.json"
RAW = OUT / "final_raw.txt"
FINAL = OUT / "final.json"
RECEIPT = OUT / "selection_receipt.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="ascii", newline="\n")


def main() -> int:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    final = json.loads(json.dumps(raw, sort_keys=True, ensure_ascii=True))
    feasibility = final.get("feasibility_after_selection")
    if not isinstance(feasibility, dict):
        raise ValueError("restart feasibility object is missing")
    value = feasibility.get("minimum_de_risking")
    if not isinstance(value, str) or not value:
        raise ValueError("restart normalization is not the expected scalar-to-array repair")
    feasibility["minimum_de_risking"] = [value]
    validate_solution_loop_result(packet, final)
    write_json(FINAL, final)
    target = final.get("research_target") or {}
    write_json(RECEIPT, {
        "schema_version": "g014_restart_research_meta_receipt_v1",
        "status": "validated_after_lossless_structural_normalization",
        "packet_sha256": digest(PACKET),
        "raw_sha256": digest(RAW),
        "final_sha256": digest(FINAL),
        "normalization": "wrapped exact minimum_de_risking scalar in a one-item array",
        "selected_mechanism_id": target.get("mechanism_id"),
        "primary_lens": target.get("primary_lens"),
        "target_state": target.get("state"),
        "code_parent_frozen": False,
        "benchmark_started": False,
        "formal_evaluation_started": False,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
