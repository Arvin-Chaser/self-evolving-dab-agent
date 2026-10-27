"""Focused provider-free tests for role-scoped Graph wiring."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.research_graph_role_scoped_wiring import (
    build_local_role_handoff,
    build_research_meta_session,
    graph_use_sidecar,
    load_research_meta_session,
    reissue_implementation_handoff_for_coding_agent,
    validate_controller_local_role_handoff,
    validate_graph_use_sidecar,
    validate_local_role_handoff,
)
from experiments.research_graph_solution_loop_meta_packet import (
    LENS_IDS,
    validate_solution_loop_result,
)


SOURCE = {"source_type": "validated_packet_file", "source_id": "sha256:" + "a" * 64}
ROOT = Path(__file__).resolve().parents[1]
G14_PACKET = ROOT / "experiments/research_graph_baseline_20261016/research_graph_solution_loop_meta_packet_g014_post_interface_v1.json"
G14_PACKET_SHA256 = "d492489c4fdea1a96dde961aaf056e46082c3ac2023200d333ac7f141eeea19b"


def current_packet_shape() -> dict:
    """Minimal shape used by the current G14 solution-loop packet."""
    return {
        "schema_version": "research_graph_solution_loop_meta_packet_v2",
        "formal_evolution_layer": {
            "generations": [0],
            "fact_suffixes_per_generation": ["outcome"],
            "facts": {"g000_outcome": {"strict_pass_count": 1}},
            "graphs": [
                {
                    "generation": 0,
                    "nodes": [
                        {"id": "problem:g000", "kind": "problem"},
                        {"id": "evidence:g000", "kind": "evidence"},
                    ],
                    "edges": [
                        {
                            "source": "evidence:g000",
                            "target": "problem:g000",
                            "relation": "observes",
                        }
                    ],
                }
            ],
        },
        "research_incubation_layer": {
            "nodes": [
                {"id": "research_target:g001:001", "kind": "research_target"},
                {"id": "interface_finding:g001:001", "kind": "interface_finding"},
            ],
            "edges": [
                {
                    "source": "interface_finding:g001:001",
                    "target": "research_target:g001:001",
                    "relation": "investigates",
                }
            ],
        },
        "cross_layer_edges": [
            {
                "source": "research_target:g001:001",
                "target": "evidence:g000",
                "relation": "motivated_by",
            }
        ],
    }


def validate_packet(packet: dict) -> None:
    assert packet["schema_version"] == "research_graph_solution_loop_meta_packet_v2"
    assert packet["formal_evolution_layer"]["generations"] == [0]


def session():
    return build_research_meta_session(
        current_packet_shape(),
        source_binding=SOURCE,
        packet_validator=validate_packet,
    )


def test_research_meta_gets_complete_current_packet_graph_scope() -> None:
    research = session()
    descriptor = research.input_descriptor()
    assert descriptor["scope"] == "complete_validated_packet"
    assert descriptor["local_view_sha256"] is None
    response = research.query(
        "subgraph",
        seed_node_ids=["interface_finding:g001:001"],
        depth=3,
        direction="both",
        output_use_ref={"output_id": "research:1", "use": "mechanism selection"},
    )
    assert response["data"]["node_ids"] == [
        "evidence:g000",
        "interface_finding:g001:001",
        "problem:g000",
        "research_target:g001:001",
    ]


def test_frozen_latest_g14_packet_loads_through_the_provider_free_adapter() -> None:
    def validate_g14(packet: dict) -> None:
        assert packet["schema_version"] == "research_graph_solution_loop_meta_packet_v2"
        assert packet["formal_evolution_layer"]["generations"] == list(range(14))
        nodes = packet["research_incubation_layer"]["nodes"]
        assert len(nodes) == 30
        assert {
            "research_target:g014:001",
            "interface_investigation:g014:001",
            "interface_finding:g014:001",
        } <= {row["id"] for row in nodes}

    research = load_research_meta_session(
        G14_PACKET,
        expected_file_sha256=G14_PACKET_SHA256,
        packet_validator=validate_g14,
    )
    response = research.query(
        "get_node",
        node_id="g013_outcome_partition",
        output_use_ref={"output_id": "g014:adapter-smoke", "use": "packet scope check"},
    )
    assert response["data"]["id"] == "g013_outcome_partition"
    assert response["data"]["kind"] == "formal_fact"
    assert response["receipt"]["packet_sha256"] == research.packet_sha256
    assert research.source_binding["source_id"] == f"sha256:{G14_PACKET_SHA256}"


@pytest.mark.parametrize("role", ["implementation_meta", "coding_agent"])
def test_controller_handoff_contains_only_the_selected_local_scope(role: str) -> None:
    research = session()
    handoff = build_local_role_handoff(
        research,
        role=role,
        handoff_id=f"{role}:output:1",
        seed_node_ids=["research_target:g001:001"],
        depth=1,
        relation_allowlist=["motivated_by"],
    )
    checked = validate_local_role_handoff(
        handoff,
        expected_packet_sha256=research.packet_sha256,
        expected_source_binding=SOURCE,
        expected_handoff_sha256=handoff["handoff_sha256"],
    )
    assert checked["local_view"]["node_ids"] == [
        "evidence:g000",
        "research_target:g001:001",
    ]
    assert [row["id"] for row in checked["graph_slice"]["nodes"]] == checked["local_view"]["node_ids"]
    assert "problem:g000" not in str(checked)
    assert "formal_evolution_layer" not in checked
    assert "research_incubation_layer" not in checked


def test_controller_can_reissue_a_verified_implementation_view_to_coding_agent() -> None:
    research = session()
    implementation = build_local_role_handoff(
        research,
        role="implementation_meta",
        handoff_id="implementation:transfer:1",
        seed_node_ids=["research_target:g001:001"],
        depth=1,
        relation_allowlist=["motivated_by"],
    )
    coding = reissue_implementation_handoff_for_coding_agent(
        implementation,
        handoff_id="coding:transfer:1",
        expected_packet_sha256=research.packet_sha256,
        expected_source_binding=SOURCE,
        expected_implementation_handoff_sha256=implementation["handoff_sha256"],
    )
    assert coding["role"] == "coding_agent"
    assert coding["handoff_id"] == "coding:transfer:1"
    assert coding["local_view"] == implementation["local_view"]
    assert coding["graph_slice"] == implementation["graph_slice"]
    assert {receipt["role"] for receipt in coding["receipts"]} == {"coding_agent"}
    with pytest.raises(ValueError, match="expected hash differs"):
        reissue_implementation_handoff_for_coding_agent(
            implementation,
            handoff_id="coding:transfer:1",
            expected_packet_sha256=research.packet_sha256,
            expected_source_binding=SOURCE,
            expected_implementation_handoff_sha256="0" * 64,
        )


@pytest.mark.parametrize("field", ["packet_sha256", "source_binding", "local_view", "graph_slice"])
def test_handoff_hash_and_source_bindings_fail_closed(field: str) -> None:
    research = session()
    handoff = build_local_role_handoff(
        research,
        role="implementation_meta",
        handoff_id="implementation:1",
        seed_node_ids=["research_target:g001:001"],
        depth=1,
        relation_allowlist=["motivated_by"],
    )
    broken = copy.deepcopy(handoff)
    if field == "packet_sha256":
        broken[field] = "0" * 64
    elif field == "source_binding":
        broken[field]["source_id"] = "sha256:" + "b" * 64
    elif field == "local_view":
        broken[field]["depth"] = 9
    else:
        broken[field]["nodes"][0]["kind"] = "tampered"
    with pytest.raises(ValueError):
        validate_local_role_handoff(broken, expected_packet_sha256=research.packet_sha256, expected_source_binding=SOURCE, expected_handoff_sha256=handoff["handoff_sha256"])


def test_controller_rejects_rehashed_graph_slice_and_receipt_forgery() -> None:
    research = session()
    handoff = build_local_role_handoff(
        research, role="implementation_meta", handoff_id="implementation:forgery:1",
        seed_node_ids=["research_target:g001:001"], depth=1,
        relation_allowlist=["motivated_by"],
    )
    forged = copy.deepcopy(handoff)
    original_coverage = copy.deepcopy(forged["coverage_receipt"])
    forged["coverage_receipt"]["output_use_ref"]["use"] = "forged coverage receipt"
    for receipt in forged["receipts"]:
        if receipt == original_coverage:
            receipt["output_use_ref"]["use"] = "forged coverage receipt"
            break
    body = {key: value for key, value in forged.items() if key != "handoff_sha256"}
    forged["handoff_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    with pytest.raises(ValueError, match="coverage receipt differs from the complete graph"):
        validate_controller_local_role_handoff(research, forged, expected_handoff_sha256=forged["handoff_sha256"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda handoff: handoff["graph_slice"]["nodes"][0].__setitem__("kind", "forged"),
        lambda handoff: handoff["graph_slice"]["edges"][0].__setitem__("relation", "forged_relation"),
        lambda handoff: handoff["graph_slice"]["edges"][0].__setitem__("source", "evidence:g000"),
        lambda handoff: handoff["graph_slice"]["edges"][0].__setitem__("target", "research_target:g001:001"),
    ],
)
def test_controller_rejects_rehashed_node_edge_relation_and_endpoint_forgery(mutation) -> None:
    research = session()
    handoff = build_local_role_handoff(
        research, role="coding_agent", handoff_id="coding:content-forgery:1",
        seed_node_ids=["research_target:g001:001"], depth=1,
        relation_allowlist=["motivated_by"],
    )
    forged = copy.deepcopy(handoff)
    mutation(forged)
    body = {key: value for key, value in forged.items() if key != "handoff_sha256"}
    forged["handoff_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    with pytest.raises(ValueError, match="content differs"):
        validate_controller_local_role_handoff(research, forged, expected_handoff_sha256=forged["handoff_sha256"])


def test_graph_citation_without_an_issued_covering_receipt_fails_closed() -> None:
    research = session()
    response = research.query(
        "get_node",
        node_id="evidence:g000",
        output_use_ref={"output_id": "research:2", "use": "research claim"},
    )
    valid = graph_use_sidecar(
        research,
        output_id="research:2",
        citations=[{"node_ids": ["evidence:g000"], "receipt": response["receipt"]}],
        graph_use_required=True,
    )
    assert valid["citations"][0]["node_ids"] == ["evidence:g000"]
    missing = copy.deepcopy(valid)
    missing["citations"] = [{"node_ids": ["evidence:g000"]}]
    with pytest.raises(ValueError, match="requires node_ids and a receipt"):
        validate_graph_use_sidecar(
            missing,
            graph_use_required=True,
            allowed_receipts=research.issued_receipts,
        )
    with pytest.raises(ValueError, match="no receipt-backed citation"):
        validate_graph_use_sidecar(
            {**valid, "citations": []},
            graph_use_required=True,
            allowed_receipts=research.issued_receipts,
        )


def legacy_result(packet: dict) -> dict:
    fact = "g000_outcome"
    node = "research_target:g001:001"
    mechanisms = [
        {
            "mechanism_id": f"mechanism:{index}",
            "name": "Synthetic",
            "problem_focus": "Synthetic problem",
            "proposed_mechanism": "Synthetic mechanism",
            "primary_lens": LENS_IDS[0],
            "related_lenses": [],
            "behavioral_change": "Synthetic change",
            "key_unknown": "Synthetic unknown",
            "minimum_no_task_check": "Synthetic check",
            "runtime_content_use": "No task content",
            "interface_status": "Unknown",
            "fact_ids": [fact],
            "incubation_refs": [],
            "counterevidence": "Synthetic counterevidence",
        }
        for index in range(3)
    ]
    return {
        "observations": [{"statement": "Observation", "fact_ids": [fact], "incubation_refs": [node, "interface_finding:g001:001"]}],
        "counterexamples": [{"statement": "Counterexample", "fact_ids": [fact], "incubation_refs": []}],
        "unknowns": [{"statement": "Unknown", "fact_ids": [fact], "incubation_refs": []}],
        "lens_review": [
            {"lens_id": lens, "fact_ids": [fact], "incubation_refs": [], "observed_gap": "Gap", "relevant_unknowns": ["Unknown"]}
            for lens in LENS_IDS
        ],
        "mechanism_candidates": mechanisms,
        "mechanism_ranking": [
            {
                "rank": index + 1,
                "mechanism_id": mechanism["mechanism_id"],
                "behavioral_leverage": "Leverage",
                "research_value": "Value",
                "information_gain": "Information",
                "formal_case": "Case",
                "counterevidence": "Counterevidence",
                "implementation_blind_reason": "Implementation blind",
            }
            for index, mechanism in enumerate(mechanisms)
        ],
        "few_mechanisms_reason": None,
        "research_target": {
            "mechanism_id": "mechanism:0",
            "state": "interface_investigation",
            "primary_lens": LENS_IDS[0],
            "related_lenses": [],
            "problem": "Problem",
            "hypothesis": "Hypothesis",
            "why_now": "Now",
            "de_risk_questions": ["Question"],
            "no_task_checks": ["Check"],
            "interface_gaps": ["Gap"],
        },
        "feasibility_after_selection": {
            "mechanism_id": "mechanism:0",
            "interface_state": "interface_investigation",
            "interface_gaps": ["Gap"],
            "minimum_de_risking": ["Check"],
            "path_dependence_assessment": "Assessment",
        },
        "no_selection_reason": None,
    }


def test_wiring_does_not_change_the_existing_packet_result_validator() -> None:
    packet = current_packet_shape()
    result = legacy_result(packet)
    validate_solution_loop_result(packet, result)
    before = copy.deepcopy(packet)
    build_research_meta_session(packet, source_binding=SOURCE, packet_validator=validate_packet)
    assert packet == before
    validate_solution_loop_result(packet, result)


def test_local_handoff_rejects_graph_payloads_over_the_serialized_byte_budget() -> None:
    packet = current_packet_shape()
    packet["research_incubation_layer"]["nodes"][0]["detail"] = "x" * 70000
    research = build_research_meta_session(
        packet, source_binding=SOURCE, packet_validator=validate_packet
    )
    with pytest.raises(ValueError, match="serialized-byte budget"):
        build_local_role_handoff(
            research, role="coding_agent", handoff_id="coding:large:1",
            seed_node_ids=["research_target:g001:001"], depth=1,
            relation_allowlist=["motivated_by"],
        )
