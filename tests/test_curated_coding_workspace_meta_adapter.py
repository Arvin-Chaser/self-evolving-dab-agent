"""Provider-free tests for the Implementation Meta workspace-plan adapter."""

from __future__ import annotations

import copy

import pytest

from experiments.curated_coding_workspace_meta_adapter import (
    IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION,
    build_workspace_inputs_from_meta_plan,
)
from experiments.curated_coding_workspace_launcher import build_coding_agent_launch_spec
from experiments.curated_coding_workspace_materializer import prepare_curated_coding_workspace
from tests.test_curated_coding_workspace_materializer import SOURCE_BINDING, _packet
from experiments.research_graph_role_scoped_wiring import build_local_role_handoff, build_research_meta_session


def _fixture() -> tuple[dict, dict, dict]:
    research = build_research_meta_session(
        _packet(), source_binding=SOURCE_BINDING,
        packet_validator=lambda packet: packet["schema_version"] == "workspace_fixture_v1",
    )
    handoff = build_local_role_handoff(
        research, role="coding_agent", handoff_id="handoff:coding-agent:adapter",
        seed_node_ids=["target:1"], depth=1, relation_allowlist=["supports"],
    )
    plan = {
        "schema_version": IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION,
        "plan_id": "plan:workspace:1", "coding_task": "Implement the candidate change.",
        "graph_refs": ["target:1"],
        "files": [
            {"source_relative_path": "experiments/agent.py", "category": "source_documents", "target_relative_path": "agent.py", "reason": "Read existing behavior.", "graph_refs": ["target:1"]},
            {"source_relative_path": "experiments/agent.py", "category": "candidate_implementation", "target_relative_path": "patch.py", "reason": "Edit the candidate copy.", "graph_refs": ["finding:1"]},
        ],
    }
    anchors = {"expected_packet_sha256": research.packet_sha256, "expected_source_binding": SOURCE_BINDING, "expected_handoff_sha256": handoff["handoff_sha256"]}
    return handoff, plan, anchors


def test_meta_plan_builds_hash_bound_contract_and_materializer_request() -> None:
    handoff, plan, anchors = _fixture()
    contract, request = build_workspace_inputs_from_meta_plan(
        plan, local_handoff=handoff, contract_id="contract:workspace:adapter",
        task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
        measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter", **anchors,
    )
    assert request["contract_sha256"] == contract["contract_sha256"]
    assert {item["target_path"] for item in request["selection"]} == {
        "coding_workspace/readonly/agent.py", "coding_workspace/candidate/patch.py",
    }


def test_meta_plan_rejects_nonlocal_graph_reference_and_duplicate_target() -> None:
    handoff, plan, anchors = _fixture()
    invalid = copy.deepcopy(plan)
    invalid["files"][0]["graph_refs"] = ["history:1"]
    with pytest.raises(ValueError, match="local Graph"):
        build_workspace_inputs_from_meta_plan(
            invalid, local_handoff=handoff, contract_id="contract:workspace:adapter",
            task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
            measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter", **anchors,
        )


def test_meta_plan_cannot_make_controller_protected_target_writable() -> None:
    handoff, plan, anchors = _fixture()
    protected = copy.deepcopy(plan)
    protected["files"][1]["target_relative_path"] = "experiments/agent.py"
    with pytest.raises(ValueError, match="protected target writable"):
        build_workspace_inputs_from_meta_plan(
            protected, local_handoff=handoff, contract_id="contract:workspace:adapter",
            task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
            measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter",
            protected_writable_target_paths=["experiments/agent.py"], **anchors,
        )


def test_meta_plan_can_seed_a_differently_named_synthetic_test_from_protected_source() -> None:
    handoff, plan, anchors = _fixture()
    synthetic = copy.deepcopy(plan)
    synthetic["files"].append({
        "source_relative_path": "experiments/agent.py", "category": "candidate_tests",
        "target_relative_path": "tests/test_agent_synthetic.py",
        "reason": "Seed an isolated synthetic test.", "graph_refs": ["target:1"],
    })
    _contract, request = build_workspace_inputs_from_meta_plan(
        synthetic, local_handoff=handoff, contract_id="contract:workspace:adapter",
        task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
        measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter",
        protected_writable_target_paths=["experiments/agent.py"], **anchors,
    )
    assert "coding_workspace/candidate/tests/test_agent_synthetic.py" in {
        item["target_path"] for item in request["selection"]
    }


def test_meta_plan_flows_to_materializer_and_dry_run_launcher(tmp_path) -> None:
    handoff, plan, anchors = _fixture()
    contract, request = build_workspace_inputs_from_meta_plan(
        plan, local_handoff=handoff, contract_id="contract:workspace:adapter",
        task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
        measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter", **anchors,
    )
    source = tmp_path / "source"
    (source / "experiments").mkdir(parents=True)
    (source / "experiments" / "agent.py").write_text("VALUE = 1\n", encoding="ascii")
    workspace = tmp_path / "workspace"
    receipt = prepare_curated_coding_workspace(
        source_repository=source, target_workspace=workspace, contract=contract,
        meta_workspace_request=request, local_handoff=handoff,
        expected_contract_sha256=contract["contract_sha256"],
        controller_source_roots=["experiments"], **anchors,
    )
    launch = build_coding_agent_launch_spec(
        workspace=workspace, expected_manifest_sha256=receipt["manifest_sha256"], controller_test_commands=[],
    )
    assert launch["mode"] == "dry-run"
    invalid = copy.deepcopy(plan)
    invalid["files"][1]["category"] = "source_documents"
    invalid["files"][1]["target_relative_path"] = "agent.py"
    with pytest.raises(ValueError, match="duplicate targets"):
        build_workspace_inputs_from_meta_plan(
            invalid, local_handoff=handoff, contract_id="contract:workspace:adapter",
            task_id="task:workspace:adapter", task_ref="taskref:workspace:adapter",
            measurement_plan_id="measurement:workspace:adapter", measurement_plan_ref="measure:workspace:adapter", **anchors,
        )
