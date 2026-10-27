"""Turn an Implementation Meta file-selection plan into controller inputs.

The Meta Agent chooses files and explains each choice with local Graph IDs.
The controller owns task identity, Graph anchors, and the final contract.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from experiments.curated_coding_workspace_contract import (
    build_curated_coding_workspace_contract,
    normalise_workspace_path,
)
from experiments.curated_coding_workspace_materializer import META_WORKSPACE_REQUEST_SCHEMA_VERSION
from experiments.research_graph_role_scoped_wiring import validate_local_role_handoff


IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION = "implementation_meta_workspace_plan_v1"
_PLAN_KEYS = {"schema_version", "plan_id", "coding_task", "graph_refs", "files"}
_FILE_KEYS = {"source_relative_path", "category", "target_relative_path", "reason", "graph_refs"}
_ROOTS = {
    "source_documents": "coding_workspace/readonly/",
    "test_documents": "coding_workspace/readonly/",
    "candidate_implementation": "coding_workspace/candidate/",
    "candidate_tests": "coding_workspace/candidate/",
    "local_helpers": "coding_workspace/helpers/",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a trimmed non-empty string")
    return value


def _refs(value: Any, label: str, allowed: set[str]) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 12:
        raise ValueError(f"{label} must be a non-empty bounded list")
    refs = [_text(item, label, 128) for item in value]
    if len(set(refs)) != len(refs) or not set(refs) <= allowed:
        raise ValueError(f"{label} must cite only the local Graph handoff")
    return sorted(refs)


def build_workspace_inputs_from_meta_plan(
    plan: Mapping[str, Any], *, local_handoff: Mapping[str, Any], contract_id: str,
    task_id: str, task_ref: str, measurement_plan_id: str, measurement_plan_ref: str,
    expected_packet_sha256: str, expected_source_binding: Mapping[str, Any],
    expected_handoff_sha256: str, protected_writable_target_paths: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a bounded Meta plan and return `(contract, workspace_request)`.

    The controller may retain regression paths as read-only references. A Meta
    plan can still use one as a seed for a differently named synthetic test,
    but cannot turn the retained path itself into a candidate output.
    """
    handoff = validate_local_role_handoff(
        local_handoff, expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
    )
    value = _copy(plan)
    if not isinstance(value, dict) or set(value) != _PLAN_KEYS or value["schema_version"] != IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION:
        raise ValueError("Implementation Meta workspace plan schema differs")
    allowed_refs = set(handoff["local_view"]["node_ids"]) | set(handoff["local_view"]["edge_ids"])
    protected = {normalise_workspace_path(path) for path in protected_writable_target_paths}
    files = value["files"]
    if not isinstance(files, list) or not files or len(files) > 32:
        raise ValueError("Implementation Meta workspace plan files differ")
    selections = []
    scopes = {category: [] for category in _ROOTS}
    for item in files:
        if not isinstance(item, Mapping) or set(item) != _FILE_KEYS or item.get("category") not in _ROOTS:
            raise ValueError("Implementation Meta workspace file schema differs")
        source = normalise_workspace_path(item["source_relative_path"])
        target_tail = normalise_workspace_path(item["target_relative_path"])
        if target_tail in protected and item["category"] in {"candidate_implementation", "candidate_tests", "local_helpers"}:
            raise ValueError("Implementation Meta plan makes a protected target writable")
        target = _ROOTS[item["category"]] + target_tail
        selections.append({
            "source_relative_path": source, "target_path": target, "category": item["category"],
            "reason": _text(item["reason"], "file reason", 600),
            "graph_refs": _refs(item["graph_refs"], "file graph_refs", allowed_refs),
        })
        scopes[item["category"]].append(target)
    if len({item["target_path"] for item in selections}) != len(selections):
        raise ValueError("Implementation Meta workspace plan has duplicate targets")
    contract = build_curated_coding_workspace_contract(
        contract_id=contract_id, role="coding_agent", task_id=task_id, task_ref=task_ref,
        measurement_plan_id=measurement_plan_id, measurement_plan_ref=measurement_plan_ref,
        packet_sha256=expected_packet_sha256, source_binding=expected_source_binding,
        local_handoff_sha256=expected_handoff_sha256,
        read_only_source_paths=scopes["source_documents"],
        read_only_test_paths=scopes["test_documents"],
        writable_implementation_paths=scopes["candidate_implementation"],
        writable_test_paths=scopes["candidate_tests"], writable_helper_paths=scopes["local_helpers"],
    )
    request = {
        "schema_version": META_WORKSPACE_REQUEST_SCHEMA_VERSION,
        "request_id": _text(value["plan_id"], "plan_id", 128),
        "contract_sha256": contract["contract_sha256"],
        "coding_task": _text(value["coding_task"], "coding_task", 8000),
        "graph_refs": _refs(value["graph_refs"], "plan graph_refs", allowed_refs),
        "selection": sorted(selections, key=lambda item: item["target_path"]),
    }
    return contract, request
