"""Provider-free tests for Meta-selected, controller-materialized workspaces."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.curated_coding_workspace_contract import build_curated_coding_workspace_contract
from experiments.curated_coding_workspace_materializer import (
    CODING_INPUT_NAME,
    MANIFEST_NAME,
    META_WORKSPACE_REQUEST_SCHEMA_VERSION,
    TASK_NAME,
    prepare_curated_coding_workspace,
)
from experiments.research_graph_role_scoped_wiring import build_local_role_handoff, build_research_meta_session


SOURCE_BINDING = {"source_type": "fixture", "source_id": "fixture:workspace:1"}


def _packet() -> dict:
    return {
        "schema_version": "workspace_fixture_v1",
        "nodes": [
            {"id": "target:1", "kind": "research_target"},
            {"id": "finding:1", "kind": "finding"},
            {"id": "history:1", "kind": "history"},
        ],
        "edges": [
            {"id": "edge:1", "source": "finding:1", "target": "target:1", "relation": "supports"},
            {"id": "edge:2", "source": "history:1", "target": "finding:1", "relation": "context"},
        ],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict, dict, dict, dict]:
    source = tmp_path / "source"
    (source / "experiments").mkdir(parents=True)
    (source / "tests").mkdir()
    (source / "experiments" / "agent.py").write_text("VALUE = 1\n", encoding="ascii")
    (source / "tests" / "test_agent.py").write_text("def test_value(): assert True\n", encoding="ascii")
    research = build_research_meta_session(
        _packet(), source_binding=SOURCE_BINDING,
        packet_validator=lambda packet: packet["schema_version"] == "workspace_fixture_v1",
    )
    handoff = build_local_role_handoff(
        research, role="coding_agent", handoff_id="handoff:coding-agent:1",
        seed_node_ids=["target:1"], depth=1, relation_allowlist=["supports"],
    )
    contract = build_curated_coding_workspace_contract(
        contract_id="contract:coding-agent:1", role="coding_agent",
        task_id="task:workspace:1", task_ref="taskref:workspace:1",
        measurement_plan_id="measurement:workspace:1", measurement_plan_ref="measure:workspace:1",
        packet_sha256=research.packet_sha256, source_binding=SOURCE_BINDING,
        local_handoff_sha256=handoff["handoff_sha256"],
        read_only_source_paths=["coding_workspace/readonly/agent.py"],
        read_only_test_paths=["coding_workspace/readonly/test_agent.py"],
        writable_implementation_paths=["coding_workspace/candidate/patch.py"],
        writable_test_paths=[], writable_helper_paths=[],
    )
    request = {
        "schema_version": META_WORKSPACE_REQUEST_SCHEMA_VERSION,
        "request_id": "request:workspace:1", "contract_sha256": contract["contract_sha256"],
        "coding_task": "Implement the bounded candidate change and run the supplied test.",
        "graph_refs": ["target:1"],
        "selection": [
            {"source_relative_path": "experiments/agent.py", "target_path": "coding_workspace/readonly/agent.py", "category": "source_documents", "reason": "Existing implementation context.", "graph_refs": ["target:1"]},
            {"source_relative_path": "tests/test_agent.py", "target_path": "coding_workspace/readonly/test_agent.py", "category": "test_documents", "reason": "Regression coverage.", "graph_refs": ["finding:1"]},
            {"source_relative_path": "experiments/agent.py", "target_path": "coding_workspace/candidate/patch.py", "category": "candidate_implementation", "reason": "Editable candidate starting point.", "graph_refs": ["target:1"]},
        ],
    }
    anchors = {
        "expected_contract_sha256": contract["contract_sha256"],
        "expected_packet_sha256": research.packet_sha256,
        "expected_source_binding": SOURCE_BINDING,
        "expected_handoff_sha256": handoff["handoff_sha256"],
    }
    return source, tmp_path / "workspace", contract, handoff, request, anchors


def _prepare(tmp_path: Path):
    source, workspace, contract, handoff, request, anchors = _fixture(tmp_path)
    receipt = prepare_curated_coding_workspace(
        source_repository=source, target_workspace=workspace, contract=contract,
        meta_workspace_request=request, local_handoff=handoff,
        controller_source_roots=["experiments", "tests"], **anchors,
    )
    return source, workspace, contract, handoff, request, anchors, receipt


def test_meta_selected_files_are_copied_with_bounded_graph_input_and_manifest(tmp_path: Path) -> None:
    _source, workspace, contract, _handoff, request, _anchors, receipt = _prepare(tmp_path)
    assert receipt["file_count"] == 3
    assert (workspace / "coding_workspace/readonly/agent.py").read_text(encoding="ascii") == "VALUE = 1\n"
    assert (workspace / "coding_workspace/candidate/patch.py").read_text(encoding="ascii") == "VALUE = 1\n"
    bounded = json.loads((workspace / CODING_INPUT_NAME).read_text(encoding="ascii"))
    assert bounded["contract_sha256"] == contract["contract_sha256"]
    assert (workspace / TASK_NAME).read_text(encoding="utf-8").strip() == request["coding_task"]
    manifest = json.loads((workspace / MANIFEST_NAME).read_text(encoding="ascii"))
    request_hash = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    assert manifest["request_sha256"] == request_hash
    assert "signature" not in json.dumps(manifest)
    assert "approval" not in json.dumps(manifest)


@pytest.mark.parametrize("mutator", [
    lambda request: request["selection"].append({"source_relative_path": "experiments/secret.py", "target_path": "coding_workspace/readonly/secret.py", "category": "source_documents", "reason": "Extra.", "graph_refs": ["target:1"]}),
    lambda request: request["selection"].__setitem__(0, {**request["selection"][0], "source_relative_path": "outside/file.py"}),
    lambda request: request["selection"].__setitem__(0, {**request["selection"][0], "graph_refs": []}),
    lambda request: request["selection"].__setitem__(0, {**request["selection"][0], "graph_refs": ["outside:1"]}),
    lambda request: request.__setitem__("contract_sha256", "0" * 64),
])
def test_invalid_meta_selection_fails_before_workspace_creation(tmp_path: Path, mutator) -> None:
    source, workspace, contract, handoff, request, anchors = _fixture(tmp_path)
    mutator(request)
    with pytest.raises(ValueError):
        prepare_curated_coding_workspace(
            source_repository=source, target_workspace=workspace, contract=contract,
            meta_workspace_request=request, local_handoff=handoff,
            controller_source_roots=["experiments", "tests"], **anchors,
        )
    assert not workspace.exists()


def test_contract_requires_exact_meta_selection_coverage(tmp_path: Path) -> None:
    source, workspace, contract, handoff, request, anchors = _fixture(tmp_path)
    request["selection"].pop()
    with pytest.raises(ValueError, match="exactly cover"):
        prepare_curated_coding_workspace(
            source_repository=source, target_workspace=workspace, contract=contract,
            meta_workspace_request=request, local_handoff=handoff,
            controller_source_roots=["experiments", "tests"], **anchors,
        )
    assert not workspace.exists()


def test_existing_target_fails_before_copy(tmp_path: Path) -> None:
    source, workspace, contract, handoff, request, anchors = _fixture(tmp_path)
    workspace.mkdir()
    with pytest.raises(ValueError, match="new separate"):
        prepare_curated_coding_workspace(
            source_repository=source, target_workspace=workspace, contract=contract,
            meta_workspace_request=request, local_handoff=handoff,
            controller_source_roots=["experiments", "tests"], **anchors,
        )


def test_request_copy_does_not_mutate_callers_value(tmp_path: Path) -> None:
    source, workspace, contract, handoff, request, anchors = _fixture(tmp_path)
    original = copy.deepcopy(request)
    prepare_curated_coding_workspace(
        source_repository=source, target_workspace=workspace, contract=contract,
        meta_workspace_request=request, local_handoff=handoff,
        controller_source_roots=["experiments", "tests"], **anchors,
    )
    assert request == original
