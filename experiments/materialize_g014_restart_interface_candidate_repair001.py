"""Materialize the accepted G14 restart workspace without launching an agent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.curated_coding_workspace_materializer import prepare_curated_coding_workspace
from experiments.run_g014_restart_implementation_meta_repair001 import (
    OUT,
    PLAN_PATH,
    ROOT_REGRESSION_TEST,
)
from experiments.curated_coding_workspace_meta_adapter import build_workspace_inputs_from_meta_plan
from experiments.research_graph_role_scoped_wiring import (
    reissue_implementation_handoff_for_coding_agent,
)


WORKSPACE = OUT / "workspace_repair002"
RESULT = OUT / "workspace_repair002_receipt.json"
CODING_HANDOFF = OUT / "coding_agent_handoff_repair001.json"
TRANSFER_RECEIPT = OUT / "coding_agent_handoff_repair001_receipt.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    if WORKSPACE.exists() or RESULT.exists():
        raise RuntimeError("G14 replacement workspace already exists")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    implementation_handoff = json.loads((OUT / "local_handoff.json").read_text(encoding="utf-8"))
    preparation = json.loads((OUT / "prepare_receipt.json").read_text(encoding="utf-8"))
    if CODING_HANDOFF.exists() or TRANSFER_RECEIPT.exists():
        raise RuntimeError("G14 Coding Agent role-transfer artifact already exists")
    handoff = reissue_implementation_handoff_for_coding_agent(
        implementation_handoff,
        handoff_id="handoff:g014:restart:interface:001:coding-agent",
        expected_packet_sha256=preparation["packet_sha256"],
        expected_source_binding=implementation_handoff["source_binding"],
        expected_implementation_handoff_sha256=preparation["handoff_sha256"],
    )
    write_json(CODING_HANDOFF, handoff)
    write_json(TRANSFER_RECEIPT, {
        "status": "reissued_provider_free",
        "source_role": "implementation_meta",
        "source_handoff_sha256": preparation["handoff_sha256"],
        "target_role": "coding_agent",
        "target_handoff_sha256": handoff["handoff_sha256"],
        "local_view_sha256": handoff["local_view_sha256"],
        "coding_agent_started": False,
        "provider_called": False,
    })
    contract, request = build_workspace_inputs_from_meta_plan(
        plan,
        local_handoff=handoff,
        contract_id="contract:g014:restart:interface:repair001",
        task_id="task:g014:restart:interface:001",
        task_ref="taskref:g014:restart:interface:001",
        measurement_plan_id="measurement:g014:restart:interface:001",
        measurement_plan_ref="measure:g014:restart:interface:001",
        expected_packet_sha256=preparation["packet_sha256"],
        expected_source_binding=handoff["source_binding"],
        expected_handoff_sha256=handoff["handoff_sha256"],
        protected_writable_target_paths=[ROOT_REGRESSION_TEST],
    )
    try:
        prepared = prepare_curated_coding_workspace(
            source_repository=ROOT,
            target_workspace=WORKSPACE,
            contract=contract,
            meta_workspace_request=request,
            local_handoff=handoff,
            expected_contract_sha256=contract["contract_sha256"],
            expected_packet_sha256=preparation["packet_sha256"],
            expected_source_binding=handoff["source_binding"],
            expected_handoff_sha256=handoff["handoff_sha256"],
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
