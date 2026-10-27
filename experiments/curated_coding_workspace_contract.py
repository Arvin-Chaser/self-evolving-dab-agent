"""Provider-free contract for a future curated coding workspace.

This declares a positive-root, hash-bound interface for a later workspace
materializer/launcher. It does not copy or read workspace files, enforce an
operating-system sandbox, or prove that a real provider or Coding Agent has
been connected. Its structural bounds constrain an honest controller; they
are not a steganography defence against a malicious controller.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from experiments.research_graph_interface_contract import LOCAL_ROLES
from experiments.research_graph_role_scoped_wiring import validate_local_role_handoff


CONTRACT_SCHEMA_VERSION = "curated_coding_workspace_contract_v2"
BOUNDED_INPUT_SCHEMA_VERSION = "curated_coding_workspace_input_v2"
_CONTRACT_KEYS = {"schema_version", "contract_id", "role", "task", "measurement_plan", "graph_binding", "read_scope", "write_scope", "default_access", "contract_sha256"}
_TASK_KEYS = {"task_id", "task_ref", "frozen"}
_MEASUREMENT_KEYS = {"measurement_plan_id", "measurement_plan_ref", "frozen"}
_GRAPH_BINDING_KEYS = {"packet_sha256", "source_binding", "local_handoff_sha256"}
_READ_SCOPE_KEYS = {"source_documents", "test_documents"}
_WRITE_SCOPE_KEYS = {"candidate_implementation", "candidate_tests", "local_helpers"}
_SOURCE_BINDING_KEYS = {"source_type", "source_id"}
_PATH_CATEGORIES = (*sorted(_READ_SCOPE_KEYS), *sorted(_WRITE_SCOPE_KEYS))

_CATEGORY_ROOTS = {
    "source_documents": "coding_workspace/readonly/",
    "test_documents": "coding_workspace/readonly/",
    "candidate_implementation": "coding_workspace/candidate/",
    "candidate_tests": "coding_workspace/candidate/",
    "local_helpers": "coding_workspace/helpers/",
}
_MAX_PATHS_PER_CATEGORY = 12
_MAX_PATHS_TOTAL = 32
_MAX_PATH_BYTES_PER_CATEGORY = 2048
_MAX_PATH_BYTES_TOTAL = 4096
_MAX_PATH_LENGTH = 256
_MAX_BOUNDED_INPUT_BYTES = 73728
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_REF = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,127}$")
_CANONICAL_PATH = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,255}$")
_ABSOLUTE_WINDOWS_PATH = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED_NAMES = frozenset({"aux", "con", "nul", "prn", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))})
_DEFENSIVE_DENY_COMPONENTS = frozenset({".git", ".ssh", ".env", "credentials", "secrets", "logs", "traces", "provider_payloads"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical(value))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _serialized_bytes(value: Any) -> int:
    return len(_canonical(value).encode("ascii"))


def _require_string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a trimmed non-empty string")
    return value


def _require_opaque_ref(value: Any, label: str) -> str:
    reference = _require_string(value, label, maximum=128)
    if _OPAQUE_REF.fullmatch(reference) is None:
        raise ValueError(f"{label} must be a small lowercase opaque reference")
    return reference


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _normalise_source_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _SOURCE_BINDING_KEYS:
        raise ValueError("source_binding schema differs")
    return {"source_type": _require_string(value["source_type"], "source_type", maximum=128), "source_id": _require_string(value["source_id"], "source_id", maximum=256)}


def normalise_workspace_path(value: Any) -> str:
    """Accept only an exact, lowercase-ASCII, portable relative file path."""
    raw = _require_string(value, "workspace path", maximum=_MAX_PATH_LENGTH)
    if raw != raw.replace("\\", "/") or _ABSOLUTE_WINDOWS_PATH.match(raw) or raw.startswith("/"):
        raise ValueError("Workspace paths must be canonical relative slash paths")
    if _CANONICAL_PATH.fullmatch(raw) is None:
        raise ValueError("Workspace paths must be lowercase ASCII canonical paths")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Workspace path is not normalized or traverses the workspace")
    if any(part.endswith(".") or part.split(".", 1)[0] in _WINDOWS_RESERVED_NAMES for part in parts):
        raise ValueError("Workspace path uses a non-portable component")
    # Positive roots provide the isolation basis; this is only defense in depth.
    if any(part in _DEFENSIVE_DENY_COMPONENTS or part.startswith(".env.") for part in parts):
        raise ValueError("Workspace path is defensively rejected")
    return raw


def _normalise_path_list(value: Any, label: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a path list")
    paths = [normalise_workspace_path(item) for item in value]
    if len(paths) > _MAX_PATHS_PER_CATEGORY:
        raise ValueError(f"{label} exceeds the path-count budget")
    if len(set(paths)) != len(paths):
        raise ValueError(f"{label} has duplicate or colliding canonical paths")
    if sum(len(path.encode("ascii")) for path in paths) > _MAX_PATH_BYTES_PER_CATEGORY:
        raise ValueError(f"{label} exceeds the path-byte budget")
    root = _CATEGORY_ROOTS[label]
    if any(not path.startswith(root) or path == root for path in paths):
        raise ValueError(f"{label} paths must stay under {root}")
    return sorted(paths)


def _normalise_scopes(read_scope: Any, write_scope: Any) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    if not isinstance(read_scope, Mapping) or set(read_scope) != _READ_SCOPE_KEYS:
        raise ValueError("read_scope schema differs")
    if not isinstance(write_scope, Mapping) or set(write_scope) != _WRITE_SCOPE_KEYS:
        raise ValueError("write_scope schema differs")
    reads = {key: _normalise_path_list(read_scope[key], key) for key in sorted(_READ_SCOPE_KEYS)}
    writes = {key: _normalise_path_list(write_scope[key], key) for key in sorted(_WRITE_SCOPE_KEYS)}
    all_paths = [path for category in _PATH_CATEGORIES for path in (reads | writes)[category]]
    if len(all_paths) > _MAX_PATHS_TOTAL or sum(len(path.encode("ascii")) for path in all_paths) > _MAX_PATH_BYTES_TOTAL:
        raise ValueError("Workspace scope exceeds the total path budget")
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("A workspace path may appear in exactly one permission category")
    if not any(writes.values()):
        raise ValueError("At least one writable candidate path is required")
    return reads, writes


def _normalise_task(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TASK_KEYS or value.get("frozen") is not True:
        raise ValueError("Frozen task schema differs")
    return {"task_id": _require_opaque_ref(value["task_id"], "task_id"), "task_ref": _require_opaque_ref(value["task_ref"], "task_ref"), "frozen": True}


def _normalise_measurement(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MEASUREMENT_KEYS or value.get("frozen") is not True:
        raise ValueError("Frozen measurement plan schema differs")
    return {"measurement_plan_id": _require_opaque_ref(value["measurement_plan_id"], "measurement_plan_id"), "measurement_plan_ref": _require_opaque_ref(value["measurement_plan_ref"], "measurement_plan_ref"), "frozen": True}


def _normalise_graph_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _GRAPH_BINDING_KEYS:
        raise ValueError("graph_binding schema differs")
    return {"packet_sha256": _require_sha256(value["packet_sha256"], "packet_sha256"), "source_binding": _normalise_source_binding(value["source_binding"]), "local_handoff_sha256": _require_sha256(value["local_handoff_sha256"], "local_handoff_sha256")}


def _normalise_contract_body(value: Mapping[str, Any]) -> dict[str, Any]:
    required = _CONTRACT_KEYS - {"contract_sha256"}
    if set(value) != required or value.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ValueError("Workspace contract schema differs")
    role = value.get("role")
    if role not in LOCAL_ROLES:
        raise ValueError("Workspace contract role must be local")
    if value.get("default_access") != "deny":
        raise ValueError("Workspace contract must default deny")
    reads, writes = _normalise_scopes(value.get("read_scope"), value.get("write_scope"))
    return {"schema_version": CONTRACT_SCHEMA_VERSION, "contract_id": _require_opaque_ref(value.get("contract_id"), "contract_id"), "role": role, "task": _normalise_task(value.get("task")), "measurement_plan": _normalise_measurement(value.get("measurement_plan")), "graph_binding": _normalise_graph_binding(value.get("graph_binding")), "read_scope": reads, "write_scope": writes, "default_access": "deny"}


def build_curated_coding_workspace_contract(*, contract_id: str, role: str, task_id: str, task_ref: str, measurement_plan_id: str, measurement_plan_ref: str, packet_sha256: str, source_binding: Mapping[str, Any], local_handoff_sha256: str, read_only_source_paths: Sequence[str], read_only_test_paths: Sequence[str], writable_implementation_paths: Sequence[str], writable_test_paths: Sequence[str], writable_helper_paths: Sequence[str]) -> dict[str, Any]:
    """Build a deterministic default-deny contract without reading any path."""
    body = {"schema_version": CONTRACT_SCHEMA_VERSION, "contract_id": contract_id, "role": role, "task": {"task_id": task_id, "task_ref": task_ref, "frozen": True}, "measurement_plan": {"measurement_plan_id": measurement_plan_id, "measurement_plan_ref": measurement_plan_ref, "frozen": True}, "graph_binding": {"packet_sha256": packet_sha256, "source_binding": source_binding, "local_handoff_sha256": local_handoff_sha256}, "read_scope": {"source_documents": list(read_only_source_paths), "test_documents": list(read_only_test_paths)}, "write_scope": {"candidate_implementation": list(writable_implementation_paths), "candidate_tests": list(writable_test_paths), "local_helpers": list(writable_helper_paths)}, "default_access": "deny"}
    normalised = _normalise_contract_body(body)
    contract = {**normalised, "contract_sha256": _sha256(normalised)}
    return validate_curated_coding_workspace_contract(
        contract,
        expected_contract_sha256=contract["contract_sha256"],
        expected_packet_sha256=normalised["graph_binding"]["packet_sha256"],
        expected_source_binding=normalised["graph_binding"]["source_binding"],
        expected_handoff_sha256=normalised["graph_binding"]["local_handoff_sha256"],
    )


def validate_curated_coding_workspace_contract(contract: Mapping[str, Any], *, expected_contract_id: str | None = None, expected_contract_sha256: str, expected_task_id: str | None = None, expected_role: str | None = None, expected_packet_sha256: str, expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str) -> dict[str, Any]:
    """Validate exact schema using controller-retained contract and graph anchors.

    Expected digests come from outside the candidate contract/payload.  This
    detects a non-controller rewrite even when its internal hashes are
    recomputed; a malicious issuer that controls both sides is out of scope.
    """
    value = _copy_json(contract)
    if not isinstance(value, dict) or set(value) != _CONTRACT_KEYS:
        raise ValueError("Workspace contract schema differs")
    body = {key: value[key] for key in value if key != "contract_sha256"}
    normalised = _normalise_contract_body(body)
    if body != normalised:
        raise ValueError("Workspace contract is not canonical")
    if _sha256(normalised) != value.get("contract_sha256"):
        raise ValueError("Workspace contract hash differs")
    binding = normalised["graph_binding"]
    if expected_contract_id is not None and normalised["contract_id"] != _require_opaque_ref(expected_contract_id, "expected_contract_id"):
        raise ValueError("Workspace contract ID differs")
    if value["contract_sha256"] != _require_sha256(expected_contract_sha256, "expected_contract_sha256"):
        raise ValueError("Workspace expected contract hash differs")
    if expected_task_id is not None and normalised["task"]["task_id"] != _require_opaque_ref(expected_task_id, "expected_task_id"):
        raise ValueError("Workspace task ID differs")
    if expected_role is not None and normalised["role"] != expected_role:
        raise ValueError("Workspace role differs")
    if binding["packet_sha256"] != _require_sha256(expected_packet_sha256, "expected_packet_sha256"):
        raise ValueError("Workspace packet binding differs")
    if binding["source_binding"] != _normalise_source_binding(expected_source_binding):
        raise ValueError("Workspace source binding differs")
    if binding["local_handoff_sha256"] != _require_sha256(expected_handoff_sha256, "expected_handoff_sha256"):
        raise ValueError("Workspace local handoff binding differs")
    return {**normalised, "contract_sha256": value["contract_sha256"]}


def authorize_workspace_path(contract: Mapping[str, Any], *, path: str, access: str, expected_contract_sha256: str, expected_packet_sha256: str, expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str) -> dict[str, str]:
    """Authorize one exact canonical path; root membership is positive-policy only."""
    checked = validate_curated_coding_workspace_contract(
        contract,
        expected_contract_sha256=expected_contract_sha256,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding,
        expected_handoff_sha256=expected_handoff_sha256,
    )
    requested = normalise_workspace_path(path)
    if access not in {"read", "write"}:
        raise ValueError("Workspace access must be read or write")
    scopes = []
    if access == "read":
        scopes.extend(("read_scope", category) for category in sorted(_READ_SCOPE_KEYS))
        scopes.extend(("write_scope", category) for category in sorted(_WRITE_SCOPE_KEYS))
    else:
        scopes.extend(("write_scope", category) for category in sorted(_WRITE_SCOPE_KEYS))
    for scope, category in scopes:
        if requested in checked[scope][category]:
            return {"path": requested, "access": access, "category": category}
    raise ValueError("Workspace path is not allowlisted for requested access")


def _bounded_input_body(contract: Mapping[str, Any], handoff: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": BOUNDED_INPUT_SCHEMA_VERSION, "role": contract["role"], "contract_id": contract["contract_id"], "contract_sha256": contract["contract_sha256"], "task": _copy_json(contract["task"]), "measurement_plan": _copy_json(contract["measurement_plan"]), "workspace_scope": {"default_access": "deny", "read_only": _copy_json(contract["read_scope"]), "writable": _copy_json(contract["write_scope"])}, "local_graph": {"packet_sha256": contract["graph_binding"]["packet_sha256"], "source_binding": _copy_json(contract["graph_binding"]["source_binding"]), "local_handoff_sha256": contract["graph_binding"]["local_handoff_sha256"], "handoff": _copy_json(handoff)}}


def build_bounded_coding_input(contract: Mapping[str, Any], local_handoff: Mapping[str, Any], *, expected_packet_sha256: str, expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str, expected_role: str, expected_contract_sha256: str) -> dict[str, Any]:
    """Build the only bounded payload for a future local implementation role."""
    checked_contract = validate_curated_coding_workspace_contract(contract, expected_role=expected_role, expected_contract_sha256=expected_contract_sha256, expected_packet_sha256=expected_packet_sha256, expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256)
    checked_handoff = validate_local_role_handoff(local_handoff, expected_packet_sha256=expected_packet_sha256, expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256)
    if checked_handoff["role"] != checked_contract["role"]:
        raise ValueError("Workspace contract and local handoff roles differ")
    payload = _bounded_input_body(checked_contract, checked_handoff)
    if _serialized_bytes(payload) > _MAX_BOUNDED_INPUT_BYTES:
        raise ValueError("Bounded coding input exceeds the serialized-byte budget")
    return payload


def validate_bounded_coding_input(payload: Mapping[str, Any], contract: Mapping[str, Any], *, expected_packet_sha256: str, expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str, expected_role: str, expected_contract_sha256: str) -> dict[str, Any]:
    """Fail closed on additions, tampering, role crossover, or stale bindings."""
    value = _copy_json(payload)
    if not isinstance(value, dict):
        raise ValueError("Bounded coding input must be an object")
    if _serialized_bytes(value) > _MAX_BOUNDED_INPUT_BYTES:
        raise ValueError("Bounded coding input exceeds the serialized-byte budget")
    checked_contract = validate_curated_coding_workspace_contract(contract, expected_role=expected_role, expected_contract_sha256=expected_contract_sha256, expected_packet_sha256=expected_packet_sha256, expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256)
    local_graph = value.get("local_graph")
    if not isinstance(local_graph, dict) or "handoff" not in local_graph:
        raise ValueError("Bounded coding input local handoff is missing")
    checked_handoff = validate_local_role_handoff(local_graph["handoff"], expected_packet_sha256=expected_packet_sha256, expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256)
    if checked_handoff["role"] != checked_contract["role"]:
        raise ValueError("Workspace contract and local handoff roles differ")
    expected = _bounded_input_body(checked_contract, checked_handoff)
    if value != expected:
        raise ValueError("Bounded coding input schema or binding differs")
    return expected
