"""Provider-free wiring for role-scoped Research Graph evidence.

This module is an adapter for future Research Meta and Implementation/Coding
callers.  It does not invoke a provider, read or materialize workspace files,
enforce an operating-system sandbox, or prove that a real provider/Coding
Agent is connected.  It does not change historical output schemas.  Controllers
retain the validated packet and hand local roles only a hash-bound, budgeted
materialized local graph slice for later materializer/launcher wiring.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from experiments.research_graph_interface_contract import (
    LOCAL_ROLES,
    RESEARCH_META_ROLE,
    ResearchGraphInterface,
    validate_local_view_contract,
    validate_graph_use_evidence,
)


_ROLE_INPUT_SCHEMA = "research_graph_role_input_v1"
_HANDOFF_SCHEMA = "research_graph_local_handoff_v2"
_OUTPUT_EVIDENCE_SCHEMA = "research_graph_output_evidence_v1"
_OPERATIONS = frozenset({"get_node", "neighbors", "evidence_refs", "subgraph"})
_LOCAL_HANDOFF_MAX_SERIALIZED_BYTES = 65536


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical(value))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _serialized_bytes(value: Any) -> int:
    return len(_canonical(value).encode("ascii"))


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _normalise_source_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"source_type", "source_id"}:
        raise ValueError("source_binding schema differs")
    return {
        "source_type": _require_string(value["source_type"], "source_type"),
        "source_id": _require_string(value["source_id"], "source_id"),
    }


def _receipt_key(receipt: Mapping[str, Any]) -> str:
    return _sha256(_copy_json(receipt))


@dataclass
class RoleScopedGraphSession:
    """Controller-owned query session that records exactly issued receipts."""

    graph: ResearchGraphInterface
    role: str
    local_view: dict[str, Any] | None = None
    _issued_receipts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role == RESEARCH_META_ROLE:
            if self.local_view is not None:
                raise ValueError("Research Meta cannot receive a local view")
        elif self.role in LOCAL_ROLES:
            if self.local_view is None:
                raise ValueError("Local roles require a controller-supplied local view")
        else:
            raise ValueError("Unknown role")

    @property
    def packet_sha256(self) -> str:
        return self.graph.packet_sha256

    @property
    def source_binding(self) -> dict[str, str]:
        return self.graph.source_binding

    @property
    def issued_receipts(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy_json(self._issued_receipts[key]) for key in sorted(self._issued_receipts))

    def query(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Execute one allowed graph query inside this session's fixed role scope."""
        if operation not in _OPERATIONS:
            raise ValueError("Unknown graph operation")
        if "role" in kwargs or "local_view" in kwargs:
            raise ValueError("Role scope is controller-owned")
        method = getattr(self.graph, operation)
        response = method(role=self.role, local_view=self.local_view, **kwargs)
        receipt = _copy_json(response["receipt"])
        self._issued_receipts[_receipt_key(receipt)] = receipt
        return _copy_json(response)

    def input_descriptor(self) -> dict[str, Any]:
        """Return the serializable adapter contract, never the complete packet."""
        local_view_sha256 = _sha256(self.local_view) if self.local_view is not None else None
        return {
            "schema_version": _ROLE_INPUT_SCHEMA,
            "role": self.role,
            "scope": "complete_validated_packet" if self.role == RESEARCH_META_ROLE else "controller_local_view",
            "packet_sha256": self.packet_sha256,
            "source_binding": self.source_binding,
            "local_view_sha256": local_view_sha256,
            "available_operations": sorted(_OPERATIONS),
            "citation_contract": _OUTPUT_EVIDENCE_SCHEMA,
        }


def build_research_meta_session(
    packet: Mapping[str, Any],
    *,
    source_binding: Mapping[str, Any],
    packet_validator: Callable[[Mapping[str, Any]], None],
) -> RoleScopedGraphSession:
    """Validate a packet before exposing its complete graph to Research Meta."""
    if not callable(packet_validator):
        raise ValueError("packet_validator must be callable")
    isolated = _copy_json(packet)
    packet_validator(copy.deepcopy(isolated))
    graph = ResearchGraphInterface(isolated, source_binding=source_binding)
    return RoleScopedGraphSession(graph=graph, role=RESEARCH_META_ROLE)


def load_research_meta_session(
    packet_path: Path,
    *,
    expected_file_sha256: str,
    packet_validator: Callable[[Mapping[str, Any]], None],
) -> RoleScopedGraphSession:
    """Hash-check and validate a JSON packet before constructing the full session."""
    raw = packet_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_file_sha256:
        raise ValueError("Packet file SHA256 differs")
    packet = json.loads(raw.decode("utf-8"))
    return build_research_meta_session(
        packet,
        source_binding={"source_type": "validated_packet_file", "source_id": f"sha256:{actual}"},
        packet_validator=packet_validator,
    )


def build_local_role_handoff(
    research_session: RoleScopedGraphSession,
    *,
    role: str,
    handoff_id: str,
    seed_node_ids: Sequence[str],
    depth: int,
    relation_allowlist: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Materialize a controller-selected slice without handing over the packet."""
    if research_session.role != RESEARCH_META_ROLE or research_session.local_view is not None:
        raise ValueError("Local handoffs require a full Research Meta controller session")
    if role not in LOCAL_ROLES:
        raise ValueError("Handoff role must be local")
    handoff_id = _require_string(handoff_id, "handoff_id")
    view = research_session.graph.build_local_view(
        seed_node_ids=seed_node_ids,
        depth=depth,
        relation_allowlist=relation_allowlist,
    )
    local = RoleScopedGraphSession(graph=research_session.graph, role=role, local_view=view)
    use_ref = {"output_id": handoff_id, "use": "controller local graph handoff"}
    coverage = local.query(
        "subgraph",
        seed_node_ids=view["node_ids"],
        depth=0,
        direction="both",
        output_use_ref=use_ref,
    )
    nodes = [
        local.query("get_node", node_id=node_id, output_use_ref=use_ref)["data"]
        for node_id in view["node_ids"]
    ]
    edges_by_id: dict[str, dict[str, Any]] = {}
    for node_id in view["node_ids"]:
        response = local.query(
            "neighbors",
            node_id=node_id,
            direction="both",
            output_use_ref=use_ref,
        )
        for edge in response["data"]:
            edges_by_id[edge["edge_id"]] = {
                key: edge[key]
                for key in ("edge_id", "source", "target", "relation", "cross_layer")
            }
    local_view_sha256 = _sha256(view)
    body = {
        "schema_version": _HANDOFF_SCHEMA,
        "role": role,
        "handoff_id": handoff_id,
        "packet_sha256": research_session.packet_sha256,
        "source_binding": research_session.source_binding,
        "local_view_sha256": local_view_sha256,
        "local_view": view,
        "graph_slice": {
            "nodes": sorted(nodes, key=lambda row: row["id"]),
            "edges": [edges_by_id[key] for key in sorted(edges_by_id)],
        },
        "coverage_receipt": coverage["receipt"],
        "receipts": list(local.issued_receipts),
    }
    if _serialized_bytes(body) > _LOCAL_HANDOFF_MAX_SERIALIZED_BYTES:
        raise ValueError("Local handoff exceeds the serialized-byte budget")
    handoff = {**body, "handoff_sha256": _sha256(body)}
    # Check the serialized product against the controller's complete graph
    # before it crosses into a local role.
    return validate_controller_local_role_handoff(
        research_session,
        handoff,
        expected_handoff_sha256=handoff["handoff_sha256"],
    )


def validate_local_role_handoff(
    handoff: Mapping[str, Any],
    *,
    expected_packet_sha256: str,
    expected_source_binding: Mapping[str, Any],
    expected_handoff_sha256: str,
) -> dict[str, Any]:
    """Validate a local payload against controller-supplied external digests.

    The expected values must be retained and passed by the controller or its
    trusted launcher; this function intentionally does not treat a payload's
    own recomputed hash as authority.  It cannot defend against a malicious
    controller that replaces both a payload and every expected digest.
    """
    value = _copy_json(handoff)
    required = {
        "schema_version", "role", "handoff_id", "packet_sha256", "source_binding",
        "local_view_sha256", "local_view", "graph_slice", "coverage_receipt",
        "receipts", "handoff_sha256",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != _HANDOFF_SCHEMA:
        raise ValueError("Local handoff schema differs")
    if _serialized_bytes(value) > _LOCAL_HANDOFF_MAX_SERIALIZED_BYTES:
        raise ValueError("Local handoff exceeds the serialized-byte budget")
    if value["role"] not in LOCAL_ROLES:
        raise ValueError("Local handoff role differs")
    _require_string(value["handoff_id"], "handoff_id")
    packet_sha256 = value.get("packet_sha256")
    if not isinstance(packet_sha256, str) or len(packet_sha256) != 64:
        raise ValueError("Local handoff packet binding is invalid")
    if packet_sha256 != _require_sha256(expected_packet_sha256, "expected_packet_sha256"):
        raise ValueError("Local handoff packet binding differs")
    source_binding = _normalise_source_binding(value.get("source_binding"))
    if source_binding != _normalise_source_binding(expected_source_binding):
        raise ValueError("Local handoff source binding differs")
    view = value.get("local_view")
    if not isinstance(view, dict) or _sha256(view) != value.get("local_view_sha256"):
        raise ValueError("Local handoff view hash differs")
    view = validate_local_view_contract(view)
    if view.get("packet_sha256") != packet_sha256 or view.get("source_binding") != source_binding:
        raise ValueError("Local handoff view binding differs")
    graph_slice = value.get("graph_slice")
    if not isinstance(graph_slice, dict) or set(graph_slice) != {"nodes", "edges"}:
        raise ValueError("Local handoff graph slice differs")
    nodes = graph_slice.get("nodes")
    edges = graph_slice.get("edges")
    if (
        not isinstance(nodes, list)
        or any(not isinstance(row, dict) for row in nodes)
        or [row.get("id") for row in nodes] != view.get("node_ids")
    ):
        raise ValueError("Local handoff node scope differs")
    if (
        not isinstance(edges, list)
        or any(not isinstance(row, dict) for row in edges)
        or [row.get("edge_id") for row in edges] != view.get("edge_ids")
    ):
        raise ValueError("Local handoff edge scope differs")
    receipts = value.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("Local handoff receipts are missing")
    for receipt in receipts:
        returned = receipt.get("returned_node_ids") if isinstance(receipt, dict) else None
        validate_graph_use_evidence(
            {"node_ids": returned, "receipt": receipt},
            packet_sha256=packet_sha256,
            source_binding=source_binding,
        )
        if receipt.get("role") != value["role"] or receipt.get("local_view_sha256") != value["local_view_sha256"]:
            raise ValueError("Local handoff receipt scope differs")
    coverage = value.get("coverage_receipt")
    if not isinstance(coverage, dict) or _receipt_key(coverage) not in {_receipt_key(row) for row in receipts}:
        raise ValueError("Local handoff coverage receipt differs")
    if coverage.get("returned_node_ids") != view.get("node_ids") or coverage.get("returned_edge_ids") != view.get("edge_ids"):
        raise ValueError("Local handoff coverage is incomplete")
    body = {key: value[key] for key in value if key != "handoff_sha256"}
    if _sha256(body) != value.get("handoff_sha256"):
        raise ValueError("Local handoff hash differs")
    if value["handoff_sha256"] != _require_sha256(expected_handoff_sha256, "expected_handoff_sha256"):
        raise ValueError("Local handoff expected hash differs")
    return value


def reissue_implementation_handoff_for_coding_agent(
    implementation_handoff: Mapping[str, Any],
    *,
    handoff_id: str,
    expected_packet_sha256: str,
    expected_source_binding: Mapping[str, Any],
    expected_implementation_handoff_sha256: str,
) -> dict[str, Any]:
    """Reissue one already validated local view to the Coding Agent role.

    This is a controller-only role transfer, not a new Graph query. It keeps
    the exact bounded view, Graph slice, and returned IDs from the validated
    Implementation Meta handoff, while making the downstream role explicit.
    """
    checked = validate_local_role_handoff(
        implementation_handoff,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding,
        expected_handoff_sha256=expected_implementation_handoff_sha256,
    )
    if checked["role"] != "implementation_meta":
        raise ValueError("Only an Implementation Meta handoff can be reissued to Coding Agent")
    body = {key: _copy_json(value) for key, value in checked.items() if key != "handoff_sha256"}
    body["role"] = "coding_agent"
    body["handoff_id"] = _require_string(handoff_id, "handoff_id")
    body["coverage_receipt"]["role"] = "coding_agent"
    for receipt in body["receipts"]:
        receipt["role"] = "coding_agent"
    if _serialized_bytes(body) > _LOCAL_HANDOFF_MAX_SERIALIZED_BYTES:
        raise ValueError("Reissued Coding Agent handoff exceeds the serialized-byte budget")
    handoff = {**body, "handoff_sha256": _sha256(body)}
    return validate_local_role_handoff(
        handoff,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding,
        expected_handoff_sha256=handoff["handoff_sha256"],
    )


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def validate_controller_local_role_handoff(
    research_session: RoleScopedGraphSession,
    handoff: Mapping[str, Any],
    *,
    expected_handoff_sha256: str,
) -> dict[str, Any]:
    """Controller gate: verify a handoff against the retained complete graph."""
    if research_session.role != RESEARCH_META_ROLE or research_session.local_view is not None:
        raise ValueError("Controller validation requires a full Research Meta controller session")
    checked = validate_local_role_handoff(
        handoff,
        expected_packet_sha256=research_session.packet_sha256,
        expected_source_binding=research_session.source_binding,
        expected_handoff_sha256=expected_handoff_sha256,
    )
    research_session.graph.validate_local_handoff_materialization(
        role=checked["role"],
        local_view=checked["local_view"],
        graph_slice=checked["graph_slice"],
        coverage_receipt=checked["coverage_receipt"],
        receipts=checked["receipts"],
        output_use_ref={"output_id": checked["handoff_id"], "use": "controller local graph handoff"},
    )
    return checked


def validate_graph_use_sidecar(
    sidecar: Mapping[str, Any],
    *,
    graph_use_required: bool,
    allowed_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate optional output evidence without changing the role's output schema."""
    value = _copy_json(sidecar)
    required = {
        "schema_version", "role", "output_id", "packet_sha256", "source_binding",
        "local_view_sha256", "citations",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != _OUTPUT_EVIDENCE_SCHEMA:
        raise ValueError("Graph-use sidecar schema differs")
    role = value.get("role")
    if role not in {RESEARCH_META_ROLE, *LOCAL_ROLES}:
        raise ValueError("Graph-use sidecar role differs")
    output_id = _require_string(value.get("output_id"), "output_id")
    packet_sha256 = value.get("packet_sha256")
    if not isinstance(packet_sha256, str) or len(packet_sha256) != 64:
        raise ValueError("Graph-use sidecar packet binding is invalid")
    source_binding = _normalise_source_binding(value.get("source_binding"))
    citations = value.get("citations")
    if not isinstance(citations, list) or (graph_use_required and not citations):
        raise ValueError("Required graph use has no receipt-backed citation")
    allowed = {_receipt_key(receipt) for receipt in allowed_receipts}
    for citation in citations:
        checked = validate_graph_use_evidence(
            citation,
            packet_sha256=packet_sha256,
            source_binding=source_binding,
        )
        receipt = checked["receipt"]
        if _receipt_key(receipt) not in allowed:
            raise ValueError("Graph-use citation receipt was not issued")
        if receipt.get("role") != role or receipt.get("output_use_ref", {}).get("output_id") != output_id:
            raise ValueError("Graph-use citation output binding differs")
        if receipt.get("local_view_sha256") != value.get("local_view_sha256"):
            raise ValueError("Graph-use citation local-view binding differs")
    return value


def graph_use_sidecar(
    session: RoleScopedGraphSession,
    *,
    output_id: str,
    citations: Sequence[Mapping[str, Any]],
    graph_use_required: bool,
) -> dict[str, Any]:
    """Build and immediately validate a new-schema graph-use evidence sidecar."""
    value = {
        "schema_version": _OUTPUT_EVIDENCE_SCHEMA,
        "role": session.role,
        "output_id": _require_string(output_id, "output_id"),
        "packet_sha256": session.packet_sha256,
        "source_binding": session.source_binding,
        "local_view_sha256": _sha256(session.local_view) if session.local_view is not None else None,
        "citations": [_copy_json(row) for row in citations],
    }
    return validate_graph_use_sidecar(
        value,
        graph_use_required=graph_use_required,
        allowed_receipts=session.issued_receipts,
    )


# ---------------------------------------------------------------------------
# Bounded competing-hypothesis register
# ---------------------------------------------------------------------------
#
# The prototype below is deliberately independent of providers, tasks, graph
# packets, and filesystem state.  Its inputs are synthetic opaque structural
# tokens.  A register can select at most one declared discriminating
# observation per bounded action, retire only branches contradicted by a
# well-formed observation, and retain an explicit unknown result for every
# observation fault.  The aggregate export contains counts and fixed status
# enums only; opaque IDs and structural values never cross that boundary.

_COMPETING_HYPOTHESIS_EXPORT_SCHEMA = "research_graph_competing_hypothesis_aggregate_v1"
_COMPETING_HYPOTHESIS_MAX_HYPOTHESES = 8
_COMPETING_HYPOTHESIS_MAX_EXPECTATIONS = 32
_COMPETING_HYPOTHESIS_MAX_TOKEN_LENGTH = 64
_COMPETING_HYPOTHESIS_MAX_REGISTER_BYTES = 32768
_COMPETING_HYPOTHESIS_FAULT_REASONS = (
    "missing",
    "stale",
    "conflicting",
    "non_discriminating",
    "instrumentation_loss",
)
_COMPETING_HYPOTHESIS_GUARD_REASONS = (
    "action_budget_exhausted",
    "observation_budget_exhausted",
    "deadline_exceeded",
    "stale_tick",
    "no_issued_observation",
    "observation_mismatch",
)
_COMPETING_HYPOTHESIS_UNKNOWN_REASONS = frozenset(
    {*_COMPETING_HYPOTHESIS_FAULT_REASONS, *_COMPETING_HYPOTHESIS_GUARD_REASONS}
)
_COMPETING_HYPOTHESIS_STATUSES = frozenset({"open", "single_viable", "disabled", "unknown"})
_COMPETING_HYPOTHESIS_OBSERVATION_STATUSES = frozenset(
    {"observed", *_COMPETING_HYPOTHESIS_FAULT_REASONS}
)
_STRUCTURAL_TOKEN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-."
)


def _require_structural_token(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _COMPETING_HYPOTHESIS_MAX_TOKEN_LENGTH
        or any(char not in _STRUCTURAL_TOKEN_CHARS for char in value)
    ):
        raise ValueError(f"{label} must be an opaque structural token")
    return value


def _require_bounded_integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"{label} is outside its bound")
    return value


def _normalise_competing_hypotheses(
    hypotheses: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    if (
        isinstance(hypotheses, (str, bytes, bytearray))
        or not isinstance(hypotheses, Sequence)
        or not 2 <= len(hypotheses) <= _COMPETING_HYPOTHESIS_MAX_HYPOTHESES
    ):
        raise ValueError("Competing hypothesis count is outside its bound")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in hypotheses:
        if not isinstance(row, Mapping) or set(row) != {"hypothesis_id", "expectations"}:
            raise ValueError("Competing hypothesis schema differs")
        hypothesis_id = _require_structural_token(row["hypothesis_id"], "hypothesis_id")
        if hypothesis_id in seen:
            raise ValueError("Competing hypothesis IDs must be unique")
        seen.add(hypothesis_id)
        expectations = row["expectations"]
        if (
            not isinstance(expectations, Mapping)
            or not expectations
            or len(expectations) > _COMPETING_HYPOTHESIS_MAX_EXPECTATIONS
        ):
            raise ValueError("Structural observation expectations are outside their bound")
        normalised: dict[str, str] = {}
        for observation_id, value in expectations.items():
            observation_id = _require_structural_token(observation_id, "observation_id")
            normalised[observation_id] = _require_structural_token(value, "observation value")
        rows.append({"hypothesis_id": hypothesis_id, "expectations": normalised})
    if _serialized_bytes(rows) > _COMPETING_HYPOTHESIS_MAX_REGISTER_BYTES:
        raise ValueError("Competing hypothesis register exceeds its serialized-byte budget")
    return tuple(rows)


class CompetingHypothesisRegister:
    """A bounded state machine over synthetic structural hypotheses.

    Every hypothesis begins viable.  An observed value can retire mismatching
    viable hypotheses, while faults never change viability.  The class exposes
    only opaque structural IDs and aggregate counts; it has no provider, task,
    network, database, filesystem, or clock dependency.
    """

    def __init__(
        self,
        hypotheses: Sequence[Mapping[str, Any]],
        *,
        enabled: bool = True,
        max_actions: int = 4,
        max_observations: int = 8,
        deadline_tick: int = 64,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self._enabled = enabled
        self._max_actions = _require_bounded_integer(
            max_actions, "max_actions", minimum=1, maximum=8
        )
        self._max_observations = _require_bounded_integer(
            max_observations, "max_observations", minimum=1, maximum=32
        )
        self._deadline_tick = _require_bounded_integer(
            deadline_tick, "deadline_tick", minimum=1, maximum=1_000_000
        )
        self._hypotheses = _normalise_competing_hypotheses(hypotheses)
        self._hypotheses_by_id = {
            row["hypothesis_id"]: row for row in self._hypotheses
        }
        self._states = {row["hypothesis_id"]: "viable" for row in self._hypotheses}
        self._retirement_reasons: dict[str, str] = {}
        self._observed_observation_ids: set[str] = set()
        self._pending_observation_id: str | None = None
        self._actions_issued = 0
        self._observation_attempts = 0
        self._contradicted_retirements = 0
        self._unknown_events = 0
        self._last_tick = -1
        self._last_status = "disabled" if not enabled else "open"
        self._last_unknown_reason: str | None = None
        self._fault_counts = {reason: 0 for reason in _COMPETING_HYPOTHESIS_FAULT_REASONS}
        self._guard_counts = {reason: 0 for reason in _COMPETING_HYPOTHESIS_GUARD_REASONS}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def viable_hypothesis_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                hypothesis_id
                for hypothesis_id, state in self._states.items()
                if state == "viable"
            )
        )

    @property
    def pending_observation_id(self) -> str | None:
        return self._pending_observation_id

    def structural_state_fingerprint(self) -> str:
        """Hash structural state without exposing IDs, values, or raw observations."""
        return _sha256(
            {
                "hypotheses": self._hypotheses,
                "states": self._states,
                "observed_observation_ids": sorted(self._observed_observation_ids),
            }
        )

    def _viable_count(self) -> int:
        return sum(state == "viable" for state in self._states.values())

    def _record_unknown(
        self, reason: str, *, observation_id: str | None = None
    ) -> dict[str, Any]:
        if reason not in _COMPETING_HYPOTHESIS_UNKNOWN_REASONS:
            raise ValueError("Unknown competing-hypothesis reason")
        self._unknown_events += 1
        if reason in self._fault_counts:
            self._fault_counts[reason] += 1
        else:
            self._guard_counts[reason] += 1
        self._last_status = "unknown"
        self._last_unknown_reason = reason
        return {
            "mode": "register_observation",
            "action": "observe",
            "status": "unknown",
            "reason": reason,
            "observation_id": observation_id,
            "retired_count": 0,
            "viable_count": self._viable_count(),
        }

    def _check_tick(self, at_tick: Any) -> str | None:
        if not isinstance(at_tick, int) or isinstance(at_tick, bool) or at_tick < 0:
            raise ValueError("at_tick must be a non-negative integer")
        if at_tick < self._last_tick:
            return "stale_tick"
        self._last_tick = at_tick
        if at_tick >= self._deadline_tick:
            return "deadline_exceeded"
        return None

    def _discriminating_candidates(self) -> list[tuple[int, int, int, str]]:
        viable = self.viable_hypothesis_ids
        if len(viable) < 2:
            return []
        common_observations: set[str] | None = None
        for hypothesis_id in viable:
            observation_ids = set(
                self._hypotheses_by_id[hypothesis_id]["expectations"]
            )
            common_observations = (
                observation_ids
                if common_observations is None
                else common_observations & observation_ids
            )
        candidates: list[tuple[int, int, int, str]] = []
        for observation_id in sorted(common_observations or ()):
            if observation_id in self._observed_observation_ids:
                continue
            groups: dict[str, int] = {}
            for hypothesis_id in viable:
                value = self._hypotheses_by_id[hypothesis_id]["expectations"][
                    observation_id
                ]
                groups[value] = groups.get(value, 0) + 1
            if len(groups) < 2:
                continue
            # Prefer the most distinct branches, then the best-balanced split.
            # The observation ID is the final deterministic tie-breaker.
            candidates.append(
                (-len(groups), max(groups.values()), len(viable), observation_id)
            )
        return candidates

    def select_discriminating_observation(self, *, at_tick: int = 0) -> dict[str, Any]:
        """Issue one bounded structural observation action, if available."""
        if not self._enabled:
            return {
                "mode": "disabled",
                "action": None,
                "status": "disabled",
                "reason": "disabled",
                "observation_id": None,
                "retired_count": 0,
                "viable_count": self._viable_count(),
            }
        tick_reason = self._check_tick(at_tick)
        if tick_reason is not None:
            return self._record_unknown(tick_reason)
        if self._pending_observation_id is not None:
            return {
                "mode": "register_action",
                "action": "observe",
                "status": "open",
                "reason": None,
                "observation_id": self._pending_observation_id,
                "new_action": False,
                "retired_count": 0,
                "viable_count": self._viable_count(),
            }
        if self._viable_count() < 2:
            self._last_status = "single_viable"
            self._last_unknown_reason = None
            return {
                "mode": "register_action",
                "action": None,
                "status": "single_viable",
                "reason": None,
                "observation_id": None,
                "new_action": False,
                "retired_count": 0,
                "viable_count": self._viable_count(),
            }
        if self._actions_issued >= self._max_actions:
            return self._record_unknown("action_budget_exhausted")
        if self._observation_attempts >= self._max_observations:
            return self._record_unknown("observation_budget_exhausted")
        candidates = self._discriminating_candidates()
        if not candidates:
            return self._record_unknown("non_discriminating")
        observation_id = min(candidates)[-1]
        self._actions_issued += 1
        self._pending_observation_id = observation_id
        self._last_status = "open"
        self._last_unknown_reason = None
        return {
            "mode": "register_action",
            "action": "observe",
            "status": "open",
            "reason": None,
            "observation_id": observation_id,
            "new_action": True,
            "retired_count": 0,
            "viable_count": self._viable_count(),
        }

    def record_observation(
        self, observation: Mapping[str, Any], *, at_tick: int = 0
    ) -> dict[str, Any]:
        """Consume one issued observation and update viability fail-closed."""
        if not self._enabled:
            return {
                "mode": "disabled",
                "action": None,
                "status": "disabled",
                "reason": "disabled",
                "observation_id": None,
                "retired_count": 0,
                "viable_count": self._viable_count(),
            }
        tick_reason = self._check_tick(at_tick)
        if tick_reason is not None:
            return self._record_unknown(tick_reason)
        if self._pending_observation_id is None:
            return self._record_unknown("no_issued_observation")
        if not isinstance(observation, Mapping):
            return self._record_unknown("instrumentation_loss")
        observation_id = observation.get("observation_id")
        if observation_id != self._pending_observation_id:
            return self._record_unknown("observation_mismatch")
        status = observation.get("status")
        if status not in _COMPETING_HYPOTHESIS_OBSERVATION_STATUSES:
            self._observation_attempts += 1
            self._pending_observation_id = None
            return self._record_unknown("instrumentation_loss", observation_id=observation_id)
        if self._observation_attempts >= self._max_observations:
            return self._record_unknown(
                "observation_budget_exhausted", observation_id=observation_id
            )
        if status != "observed":
            self._observation_attempts += 1
            self._pending_observation_id = None
            return self._record_unknown(status, observation_id=observation_id)

        value = observation.get("value")
        declared_values = {
            row["expectations"].get(observation_id) for row in self._hypotheses
        }
        declared_values.discard(None)
        if not isinstance(value, str) or value not in declared_values:
            self._observation_attempts += 1
            self._pending_observation_id = None
            return self._record_unknown(
                "instrumentation_loss", observation_id=observation_id
            )
        viable = self.viable_hypothesis_ids
        grouped_values = {
            self._hypotheses_by_id[hypothesis_id]["expectations"][observation_id]
            for hypothesis_id in viable
        }
        if len(grouped_values) < 2:
            self._observation_attempts += 1
            self._pending_observation_id = None
            return self._record_unknown(
                "non_discriminating", observation_id=observation_id
            )

        contradicted = [
            hypothesis_id
            for hypothesis_id in viable
            if self._hypotheses_by_id[hypothesis_id]["expectations"][observation_id]
            != value
        ]
        for hypothesis_id in contradicted:
            self._states[hypothesis_id] = "retired"
            self._retirement_reasons[hypothesis_id] = "contradicted_by_structural_observation"
        self._contradicted_retirements += len(contradicted)
        self._observed_observation_ids.add(observation_id)
        self._observation_attempts += 1
        self._pending_observation_id = None
        self._last_status = "single_viable" if self._viable_count() == 1 else "open"
        self._last_unknown_reason = None
        return {
            "mode": "register_observation",
            "action": "observe",
            "status": "observed",
            "reason": None,
            "observation_id": observation_id,
            "retired_count": len(contradicted),
            "viable_count": self._viable_count(),
        }

    def generic_message_control(self) -> dict[str, Any]:
        """Return the fixed same-state control message without changing state."""
        return {
            "mode": "generic_control",
            "action": "observe",
            "status": "generic",
            "reason": None,
            "message": "Continue with the next bounded structural observation.",
            "observation_id": None,
            "state_fingerprint": self.structural_state_fingerprint(),
        }

    def aggregate_export(self) -> dict[str, Any]:
        """Export fixed structural aggregates only; no IDs or values cross over."""
        return {
            "schema_version": _COMPETING_HYPOTHESIS_EXPORT_SCHEMA,
            "enabled": self._enabled,
            "hypothesis_count": len(self._hypotheses),
            "viable_count": self._viable_count(),
            "retired_count": len(self._retirement_reasons),
            "actions_issued": self._actions_issued,
            "observation_attempts": self._observation_attempts,
            "observation_faults": sum(self._fault_counts.values()),
            "unknown_events": self._unknown_events,
            "contradicted_retirements": self._contradicted_retirements,
            "last_status": self._last_status,
            "last_unknown_reason": self._last_unknown_reason,
            "fault_status_counts": dict(self._fault_counts),
            "guard_counts": dict(self._guard_counts),
        }


def validate_competing_hypothesis_aggregate_export(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the fixed aggregate-only export boundary."""
    checked = _copy_json(value)
    required = {
        "schema_version",
        "enabled",
        "hypothesis_count",
        "viable_count",
        "retired_count",
        "actions_issued",
        "observation_attempts",
        "observation_faults",
        "unknown_events",
        "contradicted_retirements",
        "last_status",
        "last_unknown_reason",
        "fault_status_counts",
        "guard_counts",
    }
    if (
        not isinstance(checked, dict)
        or set(checked) != required
        or checked.get("schema_version") != _COMPETING_HYPOTHESIS_EXPORT_SCHEMA
        or not isinstance(checked.get("enabled"), bool)
        or checked.get("last_status") not in _COMPETING_HYPOTHESIS_STATUSES
    ):
        raise ValueError("Competing-hypothesis aggregate export schema differs")
    for key in required - {
        "schema_version",
        "enabled",
        "last_status",
        "last_unknown_reason",
        "fault_status_counts",
        "guard_counts",
    }:
        if (
            not isinstance(checked.get(key), int)
            or isinstance(checked[key], bool)
            or checked[key] < 0
        ):
            raise ValueError("Competing-hypothesis aggregate count differs")
    reason = checked.get("last_unknown_reason")
    if reason is not None and reason not in _COMPETING_HYPOTHESIS_UNKNOWN_REASONS:
        raise ValueError("Competing-hypothesis aggregate reason differs")
    faults = checked.get("fault_status_counts")
    guards = checked.get("guard_counts")
    if (
        not isinstance(faults, dict)
        or set(faults) != set(_COMPETING_HYPOTHESIS_FAULT_REASONS)
        or not isinstance(guards, dict)
        or set(guards) != set(_COMPETING_HYPOTHESIS_GUARD_REASONS)
    ):
        raise ValueError("Competing-hypothesis aggregate counts differ")
    for counts in (faults, guards):
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts.values()
        ):
            raise ValueError("Competing-hypothesis aggregate counts differ")
    if checked["hypothesis_count"] != checked["viable_count"] + checked["retired_count"]:
        raise ValueError("Competing-hypothesis aggregate viability differs")
    if checked["observation_faults"] != sum(faults.values()):
        raise ValueError("Competing-hypothesis aggregate faults differ")
    return checked


def synthetic_competing_hypothesis_register(
    *,
    enabled: bool = True,
    max_actions: int = 4,
    max_observations: int = 8,
    deadline_tick: int = 64,
) -> CompetingHypothesisRegister:
    """Build a deterministic, task-free three-hypothesis synthetic fixture.

    ``obs:0`` initially splits the first viable branch.  If its value selects
    the pair, the next call selects ``obs:1`` to split that surviving pair.
    """
    return CompetingHypothesisRegister(
        (
            {
                "hypothesis_id": "hyp:0",
                "expectations": {"obs:0": "value:0", "obs:1": "value:0"},
            },
            {
                "hypothesis_id": "hyp:1",
                "expectations": {"obs:0": "value:0", "obs:1": "value:1"},
            },
            {
                "hypothesis_id": "hyp:2",
                "expectations": {"obs:0": "value:1", "obs:1": "value:0"},
            },
        ),
        enabled=enabled,
        max_actions=max_actions,
        max_observations=max_observations,
        deadline_tick=deadline_tick,
    )
