"""Read-only, role-scoped access to an already validated Research Graph packet.

``research_meta`` can read the complete loaded graph. ``implementation_meta``
and ``coding_agent`` require an explicit controller-built local view. Every
read returns a bound receipt. This never reads or materializes workspace files,
is not an operating-system sandbox, and does not prove a real provider/Coding
Agent is connected; it only supplies a later materializer/launcher contract.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


RESEARCH_META_ROLE = "research_meta"
LOCAL_ROLES = frozenset({"implementation_meta", "coding_agent"})
ALL_ROLES = frozenset({RESEARCH_META_ROLE, *LOCAL_ROLES})
_DIRECTIONS = frozenset({"outgoing", "incoming", "both"})
_RECEIPT_SCHEMA = "research_graph_interface_receipt_v1"
_VIEW_SCHEMA = "research_graph_local_view_v2"

# These caps bound future controller-selected handoffs.  They are an
# auditable structural boundary for an honest controller, not a defence
# against an adversarial controller hiding data in otherwise valid fields.
LOCAL_VIEW_SCOPE_BUDGET = {
    "max_depth": 4,
    "max_seed_nodes": 4,
    "max_nodes": 32,
    "max_edges": 64,
    "max_relations": 8,
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy_json(value: Any) -> Any:
    """Reject non-JSON values while returning an isolated JSON-compatible copy."""
    return json.loads(_canonical(value))


def _packet_sha256(packet: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(packet).encode("ascii")).hexdigest()


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _normalise_source_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("source_binding must be an object")
    if set(value) != {"source_type", "source_id"}:
        raise ValueError("source_binding schema differs")
    return {
        "source_type": _require_nonempty_string(value["source_type"], "source_type"),
        "source_id": _require_nonempty_string(value["source_id"], "source_id"),
    }


def _normalise_output_use_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"output_id", "use"}:
        raise ValueError("output_use_ref schema differs")
    return {
        "output_id": _require_nonempty_string(value["output_id"], "output_id"),
        "use": _require_nonempty_string(value["use"], "use"),
    }


def _normalise_relations(
    relations: Sequence[str] | None, *, known: frozenset[str]
) -> tuple[str, ...]:
    if relations is None:
        return tuple(sorted(known))
    if isinstance(relations, (str, bytes)) or not isinstance(relations, Sequence):
        raise ValueError("relations must be a sequence of relation names")
    normalised = tuple(sorted(set(relations)))
    if not normalised or any(not isinstance(value, str) or value not in known for value in normalised):
        raise ValueError("Unknown relation")
    return normalised


def _normalise_direction(direction: str) -> str:
    if direction not in _DIRECTIONS:
        raise ValueError("Invalid direction")
    return direction


def _full_graph_cardinality(
    nodes: Mapping[str, Any], edges: Mapping[str, Any], relations: Iterable[str]
) -> dict[str, int]:
    return {"nodes": len(nodes), "edges": len(edges), "relations": len(set(relations))}


def validate_local_view_contract(local_view: Mapping[str, Any]) -> dict[str, Any]:
    """Validate portable local-view bounds before graph-specific membership checks.

    This intentionally validates declarations only.  ``ResearchGraphInterface``
    additionally verifies every declared ID and endpoint against its complete
    in-memory graph; handoff consumers bind this metadata to the packet hash.
    """
    view = _copy_json(local_view)
    required = {
        "schema_version", "packet_sha256", "source_binding", "seed_node_ids", "depth",
        "relation_allowlist", "node_ids", "edge_ids", "cross_layer_edge_ids",
        "scope_budget", "full_graph_cardinality", "local_graph_cardinality",
    }
    if not isinstance(view, dict) or set(view) != required or view.get("schema_version") != _VIEW_SCHEMA:
        raise ValueError("Local view schema differs")
    if not isinstance(view.get("packet_sha256"), str) or len(view["packet_sha256"]) != 64:
        raise ValueError("Local view packet binding differs")
    _normalise_source_binding(view.get("source_binding"))
    if view.get("scope_budget") != LOCAL_VIEW_SCOPE_BUDGET:
        raise ValueError("Local view scope budget differs")
    for key in ("seed_node_ids", "node_ids", "edge_ids", "relation_allowlist", "cross_layer_edge_ids"):
        values = view.get(key)
        if not isinstance(values, list) or values != sorted(set(values)) or any(
            not isinstance(item, str) or not item for item in values
        ):
            raise ValueError("Local view IDs must be sorted, unique strings")
    if not isinstance(view.get("depth"), int) or isinstance(view["depth"], bool) or view["depth"] < 0:
        raise ValueError("Local view depth differs")
    if view["depth"] > LOCAL_VIEW_SCOPE_BUDGET["max_depth"]:
        raise ValueError("Local view depth exceeds scope budget")
    if not view["seed_node_ids"] or len(view["seed_node_ids"]) > LOCAL_VIEW_SCOPE_BUDGET["max_seed_nodes"]:
        raise ValueError("Local view seed scope exceeds scope budget")
    if not set(view["seed_node_ids"]).issubset(view["node_ids"]):
        raise ValueError("Local view seeds leave local nodes")
    if not view["relation_allowlist"] or len(view["relation_allowlist"]) > LOCAL_VIEW_SCOPE_BUDGET["max_relations"]:
        raise ValueError("Local view relation scope exceeds scope budget")
    if not view["node_ids"] or not view["edge_ids"]:
        raise ValueError("Empty local graph handoff is forbidden")
    if len(view["node_ids"]) > LOCAL_VIEW_SCOPE_BUDGET["max_nodes"] or len(view["edge_ids"]) > LOCAL_VIEW_SCOPE_BUDGET["max_edges"]:
        raise ValueError("Local view graph scope exceeds scope budget")
    if not set(view["cross_layer_edge_ids"]).issubset(view["edge_ids"]):
        raise ValueError("Local view cross-layer scope differs")
    cardinality = view.get("full_graph_cardinality")
    local = view.get("local_graph_cardinality")
    if not isinstance(cardinality, dict) or set(cardinality) != {"nodes", "edges", "relations"}:
        raise ValueError("Local view full graph cardinality differs")
    if not isinstance(local, dict) or set(local) != {"nodes", "edges", "relations"}:
        raise ValueError("Local view graph cardinality differs")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in cardinality.values()):
        raise ValueError("Local view full graph cardinality is invalid")
    expected_local = {
        "nodes": len(view["node_ids"]),
        "edges": len(view["edge_ids"]),
        "relations": len(view["relation_allowlist"]),
    }
    if local != expected_local:
        raise ValueError("Local view graph cardinality differs")
    if any(local[key] >= cardinality[key] for key in ("nodes", "edges", "relations")):
        raise ValueError("Local graph scope must be strictly smaller than the complete graph")
    return view


@dataclass(frozen=True)
class _Edge:
    edge_id: str
    source: str
    target: str
    relation: str
    payload: dict[str, Any]
    cross_layer: bool


class ResearchGraphInterface:
    """Immutable in-memory graph interface; it never reads the filesystem."""

    def __init__(self, packet: Mapping[str, Any], *, source_binding: Mapping[str, Any]) -> None:
        if not isinstance(packet, Mapping):
            raise ValueError("packet must be an object")
        packet_copy = _copy_json(packet)
        self._packet_sha256 = _packet_sha256(packet_copy)
        self._source_binding = _normalise_source_binding(source_binding)
        nodes = self._collect_nodes(packet_copy)
        edges = self._collect_edges(packet_copy, nodes)
        self._nodes = nodes
        self._edges = edges
        self._relations = frozenset(edge.relation for edge in edges.values())
        self._outgoing = self._index_edges(edges.values(), endpoint="source")
        self._incoming = self._index_edges(edges.values(), endpoint="target")

    @property
    def packet_sha256(self) -> str:
        return self._packet_sha256

    @property
    def source_binding(self) -> dict[str, str]:
        return dict(self._source_binding)

    @staticmethod
    def _collect_nodes(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
        candidates: list[tuple[str, Any]] = [("packet", packet.get("nodes", []))]
        formal = packet.get("formal_evolution_layer")
        if isinstance(formal, Mapping):
            candidates.append(("formal", formal.get("nodes", [])))
            graphs = formal.get("graphs", [])
            if not isinstance(graphs, list):
                raise ValueError("Formal graphs must be a list")
            for graph in graphs:
                if not isinstance(graph, Mapping):
                    raise ValueError("Formal graph must be an object")
                candidates.append(("formal", graph.get("nodes", [])))
            code_parents = formal.get("verified_code_parents", [])
            if not isinstance(code_parents, list):
                raise ValueError("Verified code parents must be a list")
            for parent in code_parents:
                if not isinstance(parent, Mapping) or not isinstance(parent.get("generation"), int):
                    raise ValueError("Verified code parent must bind a generation")
                candidates.append(("formal", [{
                    "id": f"g{parent['generation']:03d}",
                    "kind": "verified_code_parent",
                    **_copy_json(parent),
                }]))
            facts = formal.get("facts", [])
            if isinstance(facts, list):
                candidates.append(("formal", facts))
            elif isinstance(facts, Mapping):
                candidates.append(("formal", [
                    {
                        "id": fact_id,
                        "kind": "formal_fact",
                        "value": _copy_json(value),
                    }
                    for fact_id, value in facts.items()
                ]))
            else:
                raise ValueError("Formal facts must be a list or object")
            for ref in formal.get("generation_refs", []) if isinstance(formal.get("generation_refs", []), list) else []:
                if isinstance(ref, Mapping):
                    candidates.append(("formal", ref.get("node_ids", [])))
        incubation = packet.get("research_incubation_layer")
        if isinstance(incubation, Mapping):
            candidates.append(("incubation", incubation.get("nodes", [])))

        nodes: dict[str, dict[str, Any]] = {}
        for default_layer, rows in candidates:
            if not isinstance(rows, list):
                raise ValueError("Graph nodes must be a list")
            for row in rows:
                node = {"id": row} if isinstance(row, str) else row
                if not isinstance(node, Mapping):
                    raise ValueError("Graph node must be an object or ID")
                node_copy = _copy_json(node)
                node_id = _require_nonempty_string(node_copy.get("id"), "node id")
                node_copy.setdefault("layer", default_layer)
                if node_id in nodes and nodes[node_id] != node_copy:
                    raise ValueError("Duplicate graph node ID")
                nodes[node_id] = node_copy
        if not nodes:
            raise ValueError("Graph packet has no nodes")
        return dict(sorted(nodes.items()))

    @staticmethod
    def _edge_id(row: Mapping[str, Any]) -> str:
        value = row.get("id")
        if value is not None:
            return _require_nonempty_string(value, "edge id")
        fingerprint = _canonical({key: row[key] for key in ("source", "target", "relation")})
        return "edge:" + hashlib.sha256(fingerprint.encode("ascii")).hexdigest()[:20]

    @classmethod
    def _collect_edges(
        cls, packet: dict[str, Any], nodes: Mapping[str, dict[str, Any]]
    ) -> dict[str, _Edge]:
        candidates: list[Any] = [packet.get("edges", []), packet.get("cross_layer_edges", [])]
        formal = packet.get("formal_evolution_layer")
        if isinstance(formal, Mapping):
            graphs = formal.get("graphs", [])
            if not isinstance(graphs, list):
                raise ValueError("Formal graphs must be a list")
            for graph in graphs:
                if not isinstance(graph, Mapping):
                    raise ValueError("Formal graph must be an object")
                candidates.append(graph.get("edges", []))
        incubation = packet.get("research_incubation_layer")
        if isinstance(incubation, Mapping):
            candidates.append(incubation.get("edges", []))
        edges: dict[str, _Edge] = {}
        for rows in candidates:
            if not isinstance(rows, list):
                raise ValueError("Graph edges must be a list")
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("Graph edge must be an object")
                payload = _copy_json(row)
                edge_id = cls._edge_id(payload)
                source = _require_nonempty_string(payload.get("source"), "edge source")
                target = _require_nonempty_string(payload.get("target"), "edge target")
                relation = _require_nonempty_string(payload.get("relation"), "edge relation")
                if source not in nodes or target not in nodes:
                    raise ValueError("Graph edge references an unknown node")
                edge = _Edge(
                    edge_id=edge_id,
                    source=source,
                    target=target,
                    relation=relation,
                    payload=payload,
                    cross_layer=nodes[source]["layer"] != nodes[target]["layer"],
                )
                if edge_id in edges:
                    raise ValueError("Duplicate graph edge ID")
                edges[edge_id] = edge
        return dict(sorted(edges.items()))

    @staticmethod
    def _index_edges(edges: Iterable[_Edge], *, endpoint: str) -> dict[str, tuple[_Edge, ...]]:
        grouped: dict[str, list[_Edge]] = {}
        for edge in edges:
            grouped.setdefault(getattr(edge, endpoint), []).append(edge)
        return {
            node_id: tuple(sorted(rows, key=lambda edge: (edge.relation, edge.edge_id)))
            for node_id, rows in sorted(grouped.items())
        }

    def _scope(self, role: str, local_view: Mapping[str, Any] | None) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        if role not in ALL_ROLES:
            raise ValueError("Unknown role")
        if role == RESEARCH_META_ROLE:
            if local_view is not None:
                raise ValueError("research_meta does not accept a local view")
            return frozenset(self._nodes), frozenset(self._edges), self._relations
        if local_view is None:
            raise ValueError("Local roles require a controller-supplied local view")
        view = self._validate_view(local_view)
        return (
            frozenset(view["node_ids"]),
            frozenset(view["edge_ids"]),
            frozenset(view["relation_allowlist"]),
        )

    def _validate_view(self, local_view: Mapping[str, Any]) -> dict[str, Any]:
        view = validate_local_view_contract(local_view)
        if view.get("packet_sha256") != self._packet_sha256:
            raise ValueError("Local view packet binding differs")
        if view.get("source_binding") != self._source_binding:
            raise ValueError("Local view source binding differs")
        if not set(view["node_ids"]).issubset(self._nodes) or not set(view["edge_ids"]).issubset(self._edges):
            raise ValueError("Local view contains unknown graph IDs")
        if not set(view["relation_allowlist"]).issubset(self._relations):
            raise ValueError("Local view contains an unknown relation")
        complete = _full_graph_cardinality(self._nodes, self._edges, self._relations)
        if view["full_graph_cardinality"] != complete:
            raise ValueError("Local view complete graph cardinality differs")
        for edge_id in view["edge_ids"]:
            edge = self._edges[edge_id]
            if edge.source not in view["node_ids"] or edge.target not in view["node_ids"]:
                raise ValueError("Local view edge leaves local nodes")
        return view

    def validate_local_handoff_materialization(
        self,
        *,
        role: str,
        local_view: Mapping[str, Any],
        graph_slice: Mapping[str, Any],
        coverage_receipt: Mapping[str, Any],
        receipts: Sequence[Mapping[str, Any]],
        output_use_ref: Mapping[str, Any],
    ) -> None:
        """Compare a local handoff to this controller's complete in-memory graph.

        This is deliberately a controller-only check: callers that receive a
        local handoff must not receive the complete graph merely to validate
        it.  The expected handoff digest is therefore a separately supplied
        trust anchor at the local-consumer boundary.  Hashes do not defend
        against a malicious controller that issues both the handoff and its
        expected digest.
        """
        if role not in LOCAL_ROLES:
            raise ValueError("Local handoff role differs")
        view = self._validate_view(local_view)
        use_ref = _normalise_output_use_ref(output_use_ref)
        if not isinstance(graph_slice, Mapping) or set(graph_slice) != {"nodes", "edges"}:
            raise ValueError("Local handoff graph slice differs")
        expected_nodes = [self._nodes[node_id] for node_id in view["node_ids"]]
        expected_edges = [
            {
                "edge_id": edge_id,
                "source": self._edges[edge_id].source,
                "target": self._edges[edge_id].target,
                "relation": self._edges[edge_id].relation,
                "cross_layer": self._edges[edge_id].cross_layer,
            }
            for edge_id in view["edge_ids"]
        ]
        if graph_slice.get("nodes") != expected_nodes:
            raise ValueError("Local handoff node content differs from the complete graph")
        if graph_slice.get("edges") != expected_edges:
            raise ValueError("Local handoff edge content differs from the complete graph")

        # Reconstruct the exact controller query plan used to materialize a
        # handoff, so receipt fields cannot be forged independently.
        expected_coverage = self.subgraph(
            role=role,
            local_view=view,
            seed_node_ids=view["node_ids"],
            depth=0,
            direction="both",
            output_use_ref=use_ref,
        )["receipt"]
        expected_receipts = [expected_coverage]
        for node_id in view["node_ids"]:
            expected_receipts.append(
                self.get_node(
                    role=role,
                    local_view=view,
                    node_id=node_id,
                    output_use_ref=use_ref,
                )["receipt"]
            )
        for node_id in view["node_ids"]:
            expected_receipts.append(
                self.neighbors(
                    role=role,
                    local_view=view,
                    node_id=node_id,
                    direction="both",
                    output_use_ref=use_ref,
                )["receipt"]
            )
        expected_receipts = sorted(
            expected_receipts,
            key=lambda receipt: hashlib.sha256(_canonical(receipt).encode("ascii")).hexdigest(),
        )
        if coverage_receipt != expected_coverage:
            raise ValueError("Local handoff coverage receipt differs from the complete graph")
        if list(receipts) != expected_receipts:
            raise ValueError("Local handoff receipts differ from the complete graph")

    def build_local_view(
        self,
        *,
        seed_node_ids: Sequence[str],
        depth: int,
        relation_allowlist: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Build an explicit, controller-passable local view for local roles."""
        if isinstance(seed_node_ids, (str, bytes)) or not isinstance(seed_node_ids, Sequence):
            raise ValueError("seed_node_ids must be a sequence")
        seeds = tuple(sorted(set(seed_node_ids)))
        if not seeds or any(node_id not in self._nodes for node_id in seeds):
            raise ValueError("Unknown seed node")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValueError("depth must be a non-negative integer")
        if depth > LOCAL_VIEW_SCOPE_BUDGET["max_depth"]:
            raise ValueError("Local view depth exceeds scope budget")
        if len(seeds) > LOCAL_VIEW_SCOPE_BUDGET["max_seed_nodes"]:
            raise ValueError("Local view seed scope exceeds scope budget")
        if relation_allowlist is None:
            raise ValueError("Local views require an explicit relation allowlist")
        relations = frozenset(_normalise_relations(relation_allowlist, known=self._relations))
        if len(relations) > LOCAL_VIEW_SCOPE_BUDGET["max_relations"] or len(relations) >= len(self._relations):
            raise ValueError("Local view relation scope must be strictly smaller than the complete graph")
        node_ids = set(seeds)
        queue: deque[tuple[str, int]] = deque((node_id, 0) for node_id in seeds)
        while queue:
            node_id, distance = queue.popleft()
            if distance == depth:
                continue
            incident = (*self._outgoing.get(node_id, ()), *self._incoming.get(node_id, ()))
            for edge in sorted(incident, key=lambda item: item.edge_id):
                if edge.relation not in relations:
                    continue
                neighbor = edge.target if edge.source == node_id else edge.source
                if neighbor not in node_ids:
                    node_ids.add(neighbor)
                    queue.append((neighbor, distance + 1))
        edge_ids = sorted(
            edge_id for edge_id, edge in self._edges.items()
            if edge.relation in relations and edge.source in node_ids and edge.target in node_ids
        )
        if not edge_ids:
            raise ValueError("Empty local graph handoff is forbidden")
        if len(node_ids) > LOCAL_VIEW_SCOPE_BUDGET["max_nodes"] or len(edge_ids) > LOCAL_VIEW_SCOPE_BUDGET["max_edges"]:
            raise ValueError("Local view graph scope exceeds scope budget")
        complete = _full_graph_cardinality(self._nodes, self._edges, self._relations)
        local = {"nodes": len(node_ids), "edges": len(edge_ids), "relations": len(relations)}
        if any(local[key] >= complete[key] for key in ("nodes", "edges", "relations")):
            raise ValueError("Local graph scope must be strictly smaller than the complete graph")
        cross_layer_edge_ids = [edge_id for edge_id in edge_ids if self._edges[edge_id].cross_layer]
        view = {
            "schema_version": _VIEW_SCHEMA,
            "packet_sha256": self._packet_sha256,
            "source_binding": dict(self._source_binding),
            "seed_node_ids": list(seeds),
            "depth": depth,
            "relation_allowlist": sorted(relations),
            "node_ids": sorted(node_ids),
            "edge_ids": edge_ids,
            "cross_layer_edge_ids": cross_layer_edge_ids,
            "scope_budget": dict(LOCAL_VIEW_SCOPE_BUDGET),
            "full_graph_cardinality": complete,
            "local_graph_cardinality": local,
        }
        return self._validate_view(view)

    def _receipt(
        self,
        *,
        role: str,
        operation: str,
        normalised_input: dict[str, Any],
        node_ids: Iterable[str],
        edge_ids: Iterable[str],
        output_use_ref: Mapping[str, Any],
        local_view: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        local_view_sha256 = None
        if role in LOCAL_ROLES:
            if local_view is None:
                raise ValueError("Local roles require a controller-supplied local view")
            local_view_sha256 = hashlib.sha256(_canonical(_copy_json(local_view)).encode("ascii")).hexdigest()
        return {
            "schema_version": _RECEIPT_SCHEMA,
            "role": role,
            "operation": operation,
            "normalized_input": _copy_json(normalised_input),
            "returned_node_ids": sorted(set(node_ids)),
            "returned_edge_ids": sorted(set(edge_ids)),
            "packet_sha256": self._packet_sha256,
            "source_binding": dict(self._source_binding),
            "output_use_ref": _normalise_output_use_ref(output_use_ref),
            "local_view_sha256": local_view_sha256,
        }

    @staticmethod
    def _response(data: Any, receipt: dict[str, Any]) -> dict[str, Any]:
        return {"data": _copy_json(data), "receipt": receipt}

    def get_node(
        self, *, role: str, node_id: str, output_use_ref: Mapping[str, Any], local_view: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        scope_nodes, _, _ = self._scope(role, local_view)
        if node_id not in self._nodes:
            raise ValueError("Unknown node")
        if node_id not in scope_nodes:
            raise ValueError("Node is outside the local view")
        return self._response(
            self._nodes[node_id],
            self._receipt(role=role, operation="get_node", normalised_input={"node_id": node_id}, node_ids=[node_id], edge_ids=[], output_use_ref=output_use_ref, local_view=local_view),
        )

    def neighbors(
        self,
        *,
        role: str,
        node_id: str,
        direction: str,
        output_use_ref: Mapping[str, Any],
        relations: Sequence[str] | None = None,
        local_view: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope_nodes, scope_edges, scope_relations = self._scope(role, local_view)
        if node_id not in self._nodes:
            raise ValueError("Unknown node")
        if node_id not in scope_nodes:
            raise ValueError("Node is outside the local view")
        direction = _normalise_direction(direction)
        # An omitted filter means the caller accepts this scope's allowlist,
        # never the complete graph's relation set.
        requested = tuple(sorted(scope_relations)) if relations is None else _normalise_relations(relations, known=self._relations)
        if not set(requested).issubset(scope_relations):
            raise ValueError("Relation is outside the local view")
        candidates: tuple[_Edge, ...] = ()
        if direction in ("outgoing", "both"):
            candidates += self._outgoing.get(node_id, ())
        if direction in ("incoming", "both"):
            candidates += self._incoming.get(node_id, ())
        rows = []
        for edge in candidates:
            if edge.edge_id not in scope_edges or edge.relation not in requested:
                continue
            neighbor_id = edge.target if edge.source == node_id else edge.source
            if neighbor_id in scope_nodes:
                rows.append({
                    "edge_id": edge.edge_id, "source": edge.source, "target": edge.target,
                    "relation": edge.relation, "neighbor_id": neighbor_id,
                    "cross_layer": edge.cross_layer,
                })
        rows.sort(key=lambda row: (row["neighbor_id"], row["relation"], row["edge_id"]))
        return self._response(
            rows,
            self._receipt(role=role, operation="neighbors", normalised_input={"node_id": node_id, "direction": direction, "relations": list(requested)}, node_ids=[node_id, *(row["neighbor_id"] for row in rows)], edge_ids=[row["edge_id"] for row in rows], output_use_ref=output_use_ref, local_view=local_view),
        )

    def evidence_refs(
        self, *, role: str, node_id: str, output_use_ref: Mapping[str, Any], local_view: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        scope_nodes, _, _ = self._scope(role, local_view)
        if node_id not in self._nodes:
            raise ValueError("Unknown node")
        if node_id not in scope_nodes:
            raise ValueError("Node is outside the local view")
        node = self._nodes[node_id]
        refs = node.get("evidence_refs", node.get("artifacts", []))
        if not isinstance(refs, list):
            raise ValueError("Node evidence_refs must be a list")
        ordered = sorted((_copy_json(ref) for ref in refs), key=_canonical)
        data = {"node_id": node_id, "evidence_refs": ordered}
        return self._response(
            data,
            self._receipt(role=role, operation="evidence_refs", normalised_input={"node_id": node_id}, node_ids=[node_id], edge_ids=[], output_use_ref=output_use_ref, local_view=local_view),
        )

    def subgraph(
        self,
        *,
        role: str,
        seed_node_ids: Sequence[str],
        depth: int,
        direction: str,
        output_use_ref: Mapping[str, Any],
        relations: Sequence[str] | None = None,
        local_view: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope_nodes, scope_edges, scope_relations = self._scope(role, local_view)
        if isinstance(seed_node_ids, (str, bytes)) or not isinstance(seed_node_ids, Sequence):
            raise ValueError("seed_node_ids must be a sequence")
        seeds = tuple(sorted(set(seed_node_ids)))
        if not seeds or any(node_id not in self._nodes for node_id in seeds):
            raise ValueError("Unknown node")
        if any(node_id not in scope_nodes for node_id in seeds):
            raise ValueError("Node is outside the local view")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValueError("depth must be a non-negative integer")
        direction = _normalise_direction(direction)
        # Keep an omitted relation filter bounded by a local role's view.
        requested = tuple(sorted(scope_relations)) if relations is None else _normalise_relations(relations, known=self._relations)
        if not set(requested).issubset(scope_relations):
            raise ValueError("Relation is outside the local view")
        found = set(seeds)
        queue: deque[tuple[str, int]] = deque((node_id, 0) for node_id in seeds)
        while queue:
            node_id, distance = queue.popleft()
            if distance == depth:
                continue
            candidates: tuple[_Edge, ...] = ()
            if direction in ("outgoing", "both"):
                candidates += self._outgoing.get(node_id, ())
            if direction in ("incoming", "both"):
                candidates += self._incoming.get(node_id, ())
            for edge in sorted(candidates, key=lambda item: item.edge_id):
                if edge.edge_id not in scope_edges or edge.relation not in requested:
                    continue
                neighbor = edge.target if edge.source == node_id else edge.source
                if neighbor not in found:
                    found.add(neighbor)
                    queue.append((neighbor, distance + 1))
        edge_ids = sorted(edge_id for edge_id in scope_edges if self._edges[edge_id].source in found and self._edges[edge_id].target in found and self._edges[edge_id].relation in requested)
        data = {
            "node_ids": sorted(found),
            "edge_ids": edge_ids,
            "cross_layer_edge_ids": [edge_id for edge_id in edge_ids if self._edges[edge_id].cross_layer],
        }
        return self._response(
            data,
            self._receipt(role=role, operation="subgraph", normalised_input={"seed_node_ids": list(seeds), "depth": depth, "direction": direction, "relations": list(requested)}, node_ids=found, edge_ids=edge_ids, output_use_ref=output_use_ref, local_view=local_view),
        )


def validate_graph_use_evidence(
    evidence: Mapping[str, Any], *, packet_sha256: str | None = None, source_binding: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Fail closed unless a node citation is backed by a valid graph-use receipt."""
    if not isinstance(evidence, Mapping) or set(evidence) != {"node_ids", "receipt"}:
        raise ValueError("Graph-use evidence requires node_ids and a receipt")
    node_ids = evidence.get("node_ids")
    if not isinstance(node_ids, list) or not node_ids or any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
        raise ValueError("Graph-use evidence has invalid node IDs")
    receipt = evidence.get("receipt")
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != _RECEIPT_SCHEMA:
        raise ValueError("Graph-use evidence requires a receipt")
    role = receipt.get("role")
    if role not in ALL_ROLES or receipt.get("operation") not in {"get_node", "neighbors", "evidence_refs", "subgraph"}:
        raise ValueError("Graph-use receipt has an invalid role or operation")
    if not isinstance(receipt.get("normalized_input"), Mapping):
        raise ValueError("Graph-use receipt input is invalid")
    local_view_sha256 = receipt.get("local_view_sha256")
    if role == RESEARCH_META_ROLE and local_view_sha256 is not None:
        raise ValueError("Research Meta receipts cannot bind a local view")
    if role in LOCAL_ROLES and (
        not isinstance(local_view_sha256, str) or len(local_view_sha256) != 64
    ):
        raise ValueError("Local graph-use receipts require a local-view binding")
    returned = receipt.get("returned_node_ids")
    if not isinstance(returned, list) or returned != sorted(set(returned)) or not set(node_ids).issubset(returned):
        raise ValueError("Graph-use citation is not covered by its receipt")
    edges = receipt.get("returned_edge_ids")
    if not isinstance(edges, list) or edges != sorted(set(edges)):
        raise ValueError("Graph-use receipt edge IDs are invalid")
    _normalise_output_use_ref(receipt.get("output_use_ref"))
    binding = _normalise_source_binding(receipt.get("source_binding"))
    if not isinstance(receipt.get("packet_sha256"), str) or len(receipt["packet_sha256"]) != 64:
        raise ValueError("Graph-use receipt packet binding is invalid")
    if packet_sha256 is not None and receipt["packet_sha256"] != packet_sha256:
        raise ValueError("Graph-use receipt packet binding differs")
    if source_binding is not None and binding != _normalise_source_binding(source_binding):
        raise ValueError("Graph-use receipt source binding differs")
    return _copy_json({"node_ids": sorted(set(node_ids)), "receipt": receipt})
