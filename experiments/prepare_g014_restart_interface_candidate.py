"""Prepare the local Graph handoff for one G14 restart interface candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.research_graph_memory import validate_research_memory
from experiments.research_graph_role_scoped_wiring import (
    build_local_role_handoff,
    build_research_meta_session,
)

MEMORY = ROOT / "experiments/research_graph_baseline_20261016/research_graph_memory_g014_restart_active_v1.json"
MEMORY_SHA256 = "002df66f43bd90dc3bd7a076a2c8a99b12970eb7916cb1e3c53a00c39a6a125d"
OUT = ROOT / "experiments/g014_restart_interface_candidate_001"
TARGET = "research_target:g014:restart:001"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise RuntimeError("G14 restart candidate preparation already exists")
    if digest(MEMORY) != MEMORY_SHA256:
        raise RuntimeError("active restart Graph hash differs")
    memory = json.loads(MEMORY.read_text(encoding="utf-8"))
    validate_research_memory(memory, root=ROOT)
    session = build_research_meta_session(
        memory,
        source_binding={"source_type": "validated_graph_memory_file", "source_id": f"sha256:{MEMORY_SHA256}"},
        packet_validator=lambda value: validate_research_memory(dict(value), root=ROOT),
    )
    handoff = build_local_role_handoff(
        session, role="implementation_meta", handoff_id="handoff:g014:restart:interface:001",
        seed_node_ids=[TARGET], depth=1, relation_allowlist=["informed_by", "motivated_by"],
    )
    OUT.mkdir()
    (OUT / "local_handoff.json").write_text(json.dumps(handoff, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    (OUT / "prepare_receipt.json").write_text(json.dumps({
        "schema_version": "g014_restart_candidate_prepare_v1", "status": "prepared_provider_free",
        "active_memory_sha256": MEMORY_SHA256, "target_id": TARGET,
        "handoff_sha256": handoff["handoff_sha256"], "packet_sha256": handoff["packet_sha256"],
        "target_state": "interface_investigation", "provider_called": False,
        "benchmark_started": False, "formal_evaluation_started": False,
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
