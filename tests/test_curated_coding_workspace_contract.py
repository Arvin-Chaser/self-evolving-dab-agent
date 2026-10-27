"""Focused provider-free tests for the future curated workspace contract."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from experiments.curated_coding_workspace_contract import (
    BOUNDED_INPUT_SCHEMA_VERSION,
    CONTRACT_SCHEMA_VERSION,
    authorize_workspace_path,
    build_bounded_coding_input,
    build_curated_coding_workspace_contract,
    normalise_workspace_path,
    validate_bounded_coding_input,
    validate_curated_coding_workspace_contract,
)
from experiments.research_graph_role_scoped_wiring import (
    build_local_role_handoff,
    build_research_meta_session,
    validate_controller_local_role_handoff,
    validate_local_role_handoff,
)


SOURCE = {"source_type": "validated_packet_file", "source_id": "sha256:" + "a" * 64}


def _packet() -> dict:
    return {
        "schema_version": "test_graph_v1",
        "nodes": [
            {"id": "target:1", "kind": "research_target"},
            {"id": "finding:1", "kind": "interface_finding"},
            {"id": "outside:1", "kind": "historical_result"},
        ],
        "edges": [
            {"id": "edge:1", "source": "finding:1", "target": "target:1", "relation": "investigates"},
            {"id": "edge:2", "source": "outside:1", "target": "finding:1", "relation": "precedes"},
        ],
    }


def _handoff(role: str = "coding_agent") -> tuple[object, dict]:
    research = build_research_meta_session(
        _packet(), source_binding=SOURCE, packet_validator=lambda packet: packet["schema_version"] == "test_graph_v1"
    )
    return research, build_local_role_handoff(
        research, role=role, handoff_id=f"handoff:{role}:1", seed_node_ids=["target:1"],
        depth=1, relation_allowlist=["investigates"],
    )


def _contract(role: str = "coding_agent", **overrides) -> tuple[dict, dict]:
    research, handoff = _handoff(role)
    values = {
        "contract_id": f"contract:{role}:1", "role": role,
        "task_id": "task:curated-workspace:1", "task_ref": "taskref:curated-workspace:1",
        "measurement_plan_id": "measurement:provider-free:1", "measurement_plan_ref": "measure:provider-free:1",
        "packet_sha256": research.packet_sha256, "source_binding": SOURCE,
        "local_handoff_sha256": handoff["handoff_sha256"],
        "read_only_source_paths": ["coding_workspace/readonly/research_graph_role_scoped_wiring.py"],
        "read_only_test_paths": ["coding_workspace/readonly/test_research_graph_role_scoped_wiring.py"],
        "writable_implementation_paths": ["coding_workspace/candidate/candidate_workspace.py"],
        "writable_test_paths": ["coding_workspace/candidate/test_candidate_workspace.py"],
        "writable_helper_paths": ["coding_workspace/helpers/candidate_helper.py"],
    }
    values.update(overrides)
    return build_curated_coding_workspace_contract(**values), handoff


def _input(contract: dict, handoff: dict) -> dict:
    binding = contract["graph_binding"]
    return build_bounded_coding_input(
        contract, handoff, expected_packet_sha256=binding["packet_sha256"],
        expected_source_binding=binding["source_binding"], expected_handoff_sha256=binding["local_handoff_sha256"],
        expected_role=contract["role"], expected_contract_sha256=contract["contract_sha256"],
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _rehash_handoff(handoff: dict) -> None:
    handoff["local_view_sha256"] = _sha256(handoff["local_view"])
    for receipt in handoff["receipts"]:
        receipt["local_view_sha256"] = handoff["local_view_sha256"]
    handoff["coverage_receipt"]["local_view_sha256"] = handoff["local_view_sha256"]
    body = {key: value for key, value in handoff.items() if key != "handoff_sha256"}
    handoff["handoff_sha256"] = _sha256(body)


def _rehash_contract(contract: dict) -> None:
    body = {key: value for key, value in contract.items() if key != "contract_sha256"}
    contract["contract_sha256"] = _sha256(body)


def test_valid_contract_is_hash_bound_default_deny_and_root_scoped() -> None:
    contract, handoff = _contract()
    checked = validate_curated_coding_workspace_contract(
        contract, expected_contract_id="contract:coding_agent:1", expected_task_id="task:curated-workspace:1",
        expected_role="coding_agent", expected_packet_sha256=contract["graph_binding"]["packet_sha256"],
        expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"],
        expected_contract_sha256=contract["contract_sha256"],
    )
    assert checked["schema_version"] == CONTRACT_SCHEMA_VERSION
    assert checked["task"] == {"task_id": "task:curated-workspace:1", "task_ref": "taskref:curated-workspace:1", "frozen": True}
    assert checked["default_access"] == "deny"
    assert authorize_workspace_path(contract, path="coding_workspace/candidate/candidate_workspace.py", access="write", expected_contract_sha256=contract["contract_sha256"], expected_packet_sha256=contract["graph_binding"]["packet_sha256"], expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])["category"] == "candidate_implementation"


def test_bounded_input_preserves_only_bound_references_paths_and_local_handoff() -> None:
    contract, handoff = _contract("implementation_meta")
    payload = _input(contract, handoff)
    binding = contract["graph_binding"]
    assert validate_bounded_coding_input(payload, contract, expected_packet_sha256=binding["packet_sha256"], expected_source_binding=SOURCE, expected_handoff_sha256=binding["local_handoff_sha256"], expected_role="implementation_meta", expected_contract_sha256=contract["contract_sha256"]) == payload
    assert payload["schema_version"] == BOUNDED_INPUT_SCHEMA_VERSION
    assert "outside:1" not in str(payload)
    assert set(payload) == {"schema_version", "role", "contract_id", "contract_sha256", "task", "measurement_plan", "workspace_scope", "local_graph"}


def test_p1_local_handoff_records_budget_full_cardinality_and_rejects_full_scope() -> None:
    research, handoff = _handoff()
    view = handoff["local_view"]
    assert view["scope_budget"]["max_nodes"] >= view["local_graph_cardinality"]["nodes"]
    assert view["local_graph_cardinality"] == {"nodes": 2, "edges": 1, "relations": 1}
    assert view["full_graph_cardinality"] == {"nodes": 3, "edges": 2, "relations": 2}
    with pytest.raises(ValueError, match="strictly smaller"):
        research.graph.build_local_view(seed_node_ids=["target:1"], depth=4, relation_allowlist=["investigates", "precedes"])
    broken = copy.deepcopy(handoff)
    broken["local_view"]["scope_budget"]["max_nodes"] = 99
    with pytest.raises(ValueError, match="view hash"):
        validate_local_role_handoff(broken, expected_packet_sha256=research.packet_sha256, expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])


@pytest.mark.parametrize("field,value", [
    ("task_ref", '{"nodes":["hidden"]}'),
    ("measurement_plan_ref", "x" * 129),
    ("task_id", "task/contains/path"),
])
def test_p2_task_and_measurement_are_small_opaque_references(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _contract(**{field: value})


def test_p2_path_lists_have_count_and_total_byte_budgets() -> None:
    too_many = [f"coding_workspace/candidate/file{index}.py" for index in range(13)]
    with pytest.raises(ValueError, match="path-count budget"):
        _contract(writable_implementation_paths=too_many)
    oversized = ["coding_workspace/candidate/" + "a" * 150 + str(index) + ".py" for index in range(12)]
    with pytest.raises(ValueError, match="path-byte budget"):
        _contract(writable_implementation_paths=oversized)


@pytest.mark.parametrize("field,path", [
    ("read_only_source_paths", "experiments/source.py"),
    ("read_only_test_paths", "outputs/test.py"),
    ("writable_implementation_paths", "coding_workspace/readonly/candidate.py"),
    ("writable_test_paths", "coding_workspace/helpers/test.py"),
    ("writable_helper_paths", "coding_workspace/candidate/helper.py"),
])
def test_p3_each_permission_category_has_only_its_positive_root(field: str, path: str) -> None:
    with pytest.raises(ValueError, match="must stay under"):
        _contract(**{field: [path]})


def test_p3_unlisted_paths_remain_denied_without_a_sensitive_path_blacklist() -> None:
    contract, handoff = _contract()
    anchors = {"expected_contract_sha256": contract["contract_sha256"], "expected_packet_sha256": contract["graph_binding"]["packet_sha256"], "expected_source_binding": SOURCE, "expected_handoff_sha256": handoff["handoff_sha256"]}
    with pytest.raises(ValueError, match="not allowlisted"):
        authorize_workspace_path(contract, path="coding_workspace/readonly/unlisted.py", access="read", **anchors)
    with pytest.raises(ValueError, match="not allowlisted"):
        authorize_workspace_path(contract, path="coding_workspace/readonly/research_graph_role_scoped_wiring.py", access="write", **anchors)
    with pytest.raises(ValueError, match="defensively rejected"):
        _contract(writable_implementation_paths=["coding_workspace/candidate/.ssh/key.py"])


@pytest.mark.parametrize("path", [
    "coding_workspace/candidate/Candidate.py", "coding_workspace/candidate/candidate.py ",
    "coding_workspace\\candidate\\candidate.py", "coding_workspace/candidate/../candidate.py",
    "C:/coding_workspace/candidate/candidate.py",
])
def test_p4_noncanonical_case_or_platform_aliases_are_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        normalise_workspace_path(path)


def test_p4_authorization_uses_exact_not_casefolded_paths() -> None:
    contract, handoff = _contract()
    with pytest.raises(ValueError):
        authorize_workspace_path(contract, path="coding_workspace/candidate/CANDIDATE_WORKSPACE.py", access="write", expected_contract_sha256=contract["contract_sha256"], expected_packet_sha256=contract["graph_binding"]["packet_sha256"], expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])


def test_p1_rehashed_forged_handoff_and_contract_fail_at_controller_and_consumer_gates() -> None:
    research, handoff = _handoff()
    contract, _ = _contract()
    forged = copy.deepcopy(handoff)
    forged["local_view"]["full_graph_cardinality"] = {"nodes": 4, "edges": 3, "relations": 3}
    forged["graph_slice"]["nodes"][0]["kind"] = "forged_node"
    forged["graph_slice"]["edges"][0].update({"source": "target:1", "target": "finding:1", "relation": "forged_relation", "cross_layer": True})
    _rehash_handoff(forged)
    forged_contract = copy.deepcopy(contract)
    forged_contract["graph_binding"]["local_handoff_sha256"] = forged["handoff_sha256"]
    _rehash_contract(forged_contract)
    with pytest.raises(ValueError):
        validate_controller_local_role_handoff(research, forged, expected_handoff_sha256=forged["handoff_sha256"])
    with pytest.raises(ValueError, match="expected hash differs"):
        validate_local_role_handoff(forged, expected_packet_sha256=research.packet_sha256, expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])
    with pytest.raises(ValueError, match="expected contract hash differs"):
        validate_curated_coding_workspace_contract(forged_contract, expected_contract_sha256=contract["contract_sha256"], expected_packet_sha256=research.packet_sha256, expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])
    forged_payload = _input(forged_contract, forged)
    with pytest.raises(ValueError, match="expected contract hash differs"):
        validate_bounded_coding_input(forged_payload, forged_contract, expected_packet_sha256=research.packet_sha256, expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"], expected_role="coding_agent", expected_contract_sha256=contract["contract_sha256"])


def test_p1_local_and_contract_validators_require_external_digest_arguments() -> None:
    research, handoff = _handoff()
    contract, _ = _contract()
    with pytest.raises(TypeError):
        validate_local_role_handoff(handoff)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        validate_curated_coding_workspace_contract(contract)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        authorize_workspace_path(contract, path="coding_workspace/candidate/candidate_workspace.py", access="write", expected_contract_sha256=contract["contract_sha256"])  # type: ignore[call-arg]


def test_hash_payload_and_role_crossovers_fail_closed() -> None:
    contract, handoff = _contract()
    payload = _input(contract, handoff)
    payload["unexpected_graph"] = {"nodes": []}
    with pytest.raises(ValueError, match="schema or binding"):
        validate_bounded_coding_input(payload, contract, expected_packet_sha256=contract["graph_binding"]["packet_sha256"], expected_source_binding=SOURCE, expected_handoff_sha256=contract["graph_binding"]["local_handoff_sha256"], expected_role="coding_agent", expected_contract_sha256=contract["contract_sha256"])
    implementation_contract, _ = _contract("implementation_meta")
    _, coding_handoff = _handoff("coding_agent")
    crossover = build_curated_coding_workspace_contract(
        contract_id=implementation_contract["contract_id"], role="implementation_meta",
        task_id=implementation_contract["task"]["task_id"], task_ref=implementation_contract["task"]["task_ref"],
        measurement_plan_id=implementation_contract["measurement_plan"]["measurement_plan_id"],
        measurement_plan_ref=implementation_contract["measurement_plan"]["measurement_plan_ref"],
        packet_sha256=implementation_contract["graph_binding"]["packet_sha256"], source_binding=SOURCE,
        local_handoff_sha256=coding_handoff["handoff_sha256"],
        read_only_source_paths=implementation_contract["read_scope"]["source_documents"],
        read_only_test_paths=implementation_contract["read_scope"]["test_documents"],
        writable_implementation_paths=implementation_contract["write_scope"]["candidate_implementation"],
        writable_test_paths=implementation_contract["write_scope"]["candidate_tests"],
        writable_helper_paths=implementation_contract["write_scope"]["local_helpers"],
    )
    with pytest.raises(ValueError, match="roles differ"):
        build_bounded_coding_input(crossover, coding_handoff, expected_packet_sha256=crossover["graph_binding"]["packet_sha256"], expected_source_binding=SOURCE, expected_handoff_sha256=coding_handoff["handoff_sha256"], expected_role="implementation_meta", expected_contract_sha256=crossover["contract_sha256"])
