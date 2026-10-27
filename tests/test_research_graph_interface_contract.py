"""Provider-free tests for the role-scoped Research Graph interface contract."""

from __future__ import annotations

import copy

import pytest

from experiments.research_graph_interface_contract import (
    RESEARCH_META_ROLE,
    ResearchGraphInterface,
    validate_graph_use_evidence,
    validate_local_view_contract,
)


SOURCE = {"source_type": "validated_packet", "source_id": "synthetic:opaque-v1"}
USE = {"output_id": "draft:17", "use": "implementation rationale"}


def packet(edges: list[dict] | None = None) -> dict:
    return {
        "nodes": [
            {"id": "n:alpha", "layer": "formal", "evidence_refs": [{"sha256": "b"}, {"sha256": "a"}]},
            {"id": "n:beta", "layer": "incubation"},
            {"id": "n:gamma", "layer": "incubation"},
            {"id": "n:delta", "layer": "formal"},
        ],
        "edges": edges if edges is not None else [
            {"id": "e:z", "source": "n:alpha", "target": "n:gamma", "relation": "supports"},
            {"id": "e:a", "source": "n:alpha", "target": "n:beta", "relation": "motivated_by"},
            {"id": "e:m", "source": "n:beta", "target": "n:delta", "relation": "revises"},
        ],
    }


def interface(edges: list[dict] | None = None) -> ResearchGraphInterface:
    return ResearchGraphInterface(packet(edges), source_binding=SOURCE)


def test_ordered_read_operations_and_receipt_bindings_are_json_serializable() -> None:
    graph = interface()
    response = graph.neighbors(
        role=RESEARCH_META_ROLE, node_id="n:alpha", direction="outgoing", relations=["supports", "motivated_by"], output_use_ref=USE
    )
    assert [row["edge_id"] for row in response["data"]] == ["e:a", "e:z"]
    assert response["receipt"] == {
        "schema_version": "research_graph_interface_receipt_v1",
        "role": "research_meta", "operation": "neighbors",
        "normalized_input": {"node_id": "n:alpha", "direction": "outgoing", "relations": ["motivated_by", "supports"]},
        "returned_node_ids": ["n:alpha", "n:beta", "n:gamma"], "returned_edge_ids": ["e:a", "e:z"],
        "packet_sha256": graph.packet_sha256, "source_binding": SOURCE, "output_use_ref": USE,
        "local_view_sha256": None,
    }
    assert graph.evidence_refs(role=RESEARCH_META_ROLE, node_id="n:alpha", output_use_ref=USE)["data"]["evidence_refs"] == [{"sha256": "a"}, {"sha256": "b"}]


def test_local_roles_have_no_whole_graph_fallback_and_cross_layer_scope_is_explicit() -> None:
    graph = interface()
    view = graph.build_local_view(seed_node_ids=["n:alpha"], depth=1, relation_allowlist=["motivated_by"])
    assert view["node_ids"] == ["n:alpha", "n:beta"]
    assert view["cross_layer_edge_ids"] == ["e:a"]
    with pytest.raises(ValueError, match="require a controller-supplied"):
        graph.get_node(role="coding_agent", node_id="n:delta", output_use_ref=USE)
    with pytest.raises(ValueError, match="outside the local view"):
        graph.get_node(role="implementation_meta", node_id="n:gamma", output_use_ref=USE, local_view=view)
    response = graph.neighbors(role="coding_agent", node_id="n:alpha", direction="outgoing", output_use_ref=USE, local_view=view)
    assert [row["edge_id"] for row in response["data"]] == ["e:a"]
    assert isinstance(response["receipt"]["local_view_sha256"], str)
    with pytest.raises(ValueError, match="outside the local view"):
        graph.neighbors(role="coding_agent", node_id="n:alpha", direction="outgoing", relations=["supports"], output_use_ref=USE, local_view=view)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"role": "unknown"}, "Unknown role"),
        ({"node_id": "n:missing"}, "Unknown node"),
        ({"direction": "sideways"}, "Invalid direction"),
        ({"relations": ["missing"]}, "Unknown relation"),
        ({"output_use_ref": {"output_id": "only"}}, "output_use_ref schema"),
    ],
)
def test_closed_failures_for_invalid_calls(kwargs: dict, message: str) -> None:
    graph = interface()
    call = {"role": RESEARCH_META_ROLE, "node_id": "n:alpha", "direction": "outgoing", "output_use_ref": USE}
    call.update(kwargs)
    with pytest.raises(ValueError, match=message):
        graph.neighbors(**call)


def test_subgraph_is_directional_and_receipt_required_for_graph_use_evidence() -> None:
    graph = interface()
    response = graph.subgraph(role=RESEARCH_META_ROLE, seed_node_ids=["n:alpha"], depth=2, direction="outgoing", output_use_ref=USE)
    assert response["data"] == {"node_ids": ["n:alpha", "n:beta", "n:delta", "n:gamma"], "edge_ids": ["e:a", "e:m", "e:z"], "cross_layer_edge_ids": ["e:a", "e:m", "e:z"]}
    with pytest.raises(ValueError, match="requires node_ids and a receipt"):
        validate_graph_use_evidence({"node_ids": ["n:alpha"]})
    evidence = validate_graph_use_evidence({"node_ids": ["n:alpha", "n:beta"], "receipt": response["receipt"]}, packet_sha256=graph.packet_sha256, source_binding=SOURCE)
    assert evidence["node_ids"] == ["n:alpha", "n:beta"]
    bad = copy.deepcopy(evidence)
    bad["node_ids"] = ["n:delta", "n:gamma", "n:alpha", "n:beta", "n:outside"]
    with pytest.raises(ValueError, match="not covered"):
        validate_graph_use_evidence(bad)


def test_predeclared_edge_permutation_changes_adjacency_not_ordering() -> None:
    original = packet()["edges"]
    reordered = list(reversed(original))
    changed = [
        {"id": "e:z", "source": "n:alpha", "target": "n:delta", "relation": "supports"},
        *original[1:],
    ]
    def edge_ids(edges: list[dict]) -> list[str]:
        return [row["neighbor_id"] for row in interface(edges).neighbors(role=RESEARCH_META_ROLE, node_id="n:alpha", direction="outgoing", output_use_ref=USE)["data"]]
    assert edge_ids(original) == edge_ids(reordered) == ["n:beta", "n:gamma"]
    assert edge_ids(changed) == ["n:beta", "n:delta"]


def test_local_view_v2_requires_a_budgeted_strict_subset_of_the_complete_graph() -> None:
    graph = interface()
    view = graph.build_local_view(
        seed_node_ids=["n:alpha"], depth=1, relation_allowlist=["motivated_by"]
    )
    assert view["scope_budget"] == {
        "max_depth": 4, "max_seed_nodes": 4, "max_nodes": 32,
        "max_edges": 64, "max_relations": 8,
    }
    assert view["full_graph_cardinality"] == {"nodes": 4, "edges": 3, "relations": 3}
    assert view["local_graph_cardinality"] == {"nodes": 2, "edges": 1, "relations": 1}
    with pytest.raises(ValueError, match="explicit relation allowlist"):
        graph.build_local_view(seed_node_ids=["n:alpha"], depth=1)
    with pytest.raises(ValueError, match="strictly smaller"):
        graph.build_local_view(
            seed_node_ids=["n:alpha"], depth=1,
            relation_allowlist=["motivated_by", "revises", "supports"],
        )
    with pytest.raises(ValueError, match="depth exceeds"):
        graph.build_local_view(seed_node_ids=["n:alpha"], depth=5, relation_allowlist=["motivated_by"])
    malformed = copy.deepcopy(view)
    malformed["full_graph_cardinality"] = malformed["local_graph_cardinality"]
    with pytest.raises(ValueError, match="strictly smaller"):
        validate_local_view_contract(malformed)
    malformed = copy.deepcopy(view)
    malformed["node_ids"] = []
    with pytest.raises(ValueError, match="seeds leave"):
        graph.get_node(role="coding_agent", node_id="n:alpha", output_use_ref=USE, local_view=malformed)
