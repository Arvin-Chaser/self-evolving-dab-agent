"""Materialize the accepted G14 workspace in a fresh sibling directory."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.curated_coding_workspace_materializer import prepare_curated_coding_workspace
from experiments.curated_coding_workspace_meta_adapter import build_workspace_inputs_from_meta_plan
from experiments.materialize_g014_restart_interface_candidate_repair001 import (
    CODING_HANDOFF,
    OUT,
    PLAN_PATH,
    ROOT_REGRESSION_TEST,
    digest,
    write_json,
)
from experiments.research_graph_role_scoped_wiring import validate_local_role_handoff


WORKSPACE = ROOT.parent / "g014_restart_interface_candidate_001_workspace_repair003"
RESULT = OUT / "workspace_repair003_receipt.json"
TRANSFER_RECEIPT = OUT / "coding_agent_handoff_repair001_receipt.json"


def main() -> int:
    if WORKSPACE.exists() or RESULT.exists():
        raise RuntimeError("G14 sibling workspace target already exists")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    handoff = json.loads(CODING_HANDOFF.read_text(encoding="utf-8"))
    transfer = json.loads(TRANSFER_RECEIPT.read_text(encoding="utf-8"))
    if transfer.get("status") != "reissued_provider_free" or transfer.get("target_role") != "coding_agent":
        raise ValueError("Coding Agent role-transfer receipt differs")
    checked_handoff = validate_local_role_handoff(
        handoff,
        expected_packet_sha256=handoff["packet_sha256"],
        expected_source_binding=handoff["source_binding"],
        expected_handoff_sha256=transfer["target_handoff_sha256"],
    )
    contract, request = build_workspace_inputs_from_meta_plan(
        plan,
        local_handoff=checked_handoff,
        contract_id="contract:g014:restart:interface:repair003",
        task_id="task:g014:restart:interface:001",
        task_ref="taskref:g014:restart:interface:001",
        measurement_plan_id="measurement:g014:restart:interface:001",
        measurement_plan_ref="measure:g014:restart:interface:001",
        expected_packet_sha256=checked_handoff["packet_sha256"],
        expected_source_binding=checked_handoff["source_binding"],
        expected_handoff_sha256=checked_handoff["handoff_sha256"],
        protected_writable_target_paths=[ROOT_REGRESSION_TEST],
    )
    try:
        prepared = prepare_curated_coding_workspace(
            source_repository=ROOT,
            target_workspace=WORKSPACE,
            contract=contract,
            meta_workspace_request=request,
            local_handoff=checked_handoff,
            expected_contract_sha256=contract["contract_sha256"],
            expected_packet_sha256=checked_handoff["packet_sha256"],
            expected_source_binding=checked_handoff["source_binding"],
            expected_handoff_sha256=checked_handoff["handoff_sha256"],
            controller_source_roots=["experiments", "tests"],
        )
    except ValueError as exc:
        write_json(RESULT, {
            "status": "rejected_before_materialization",
            "reason": str(exc),
            "implementation_meta_plan_sha256": digest(PLAN_PATH),
            "coding_agent_started": False,
            "provider_called": False,
        })
        return 2
    write_json(RESULT, {
        "status": "prepared_provider_free",
        "implementation_meta_plan_sha256": digest(PLAN_PATH),
        "workspace": prepared["workspace"],
        "manifest_sha256": prepared["manifest_sha256"],
        "file_count": prepared["file_count"],
        "coding_agent_started": False,
        "provider_called": False,
        "benchmark_started": False,
        "formal_evaluation_started": False,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
