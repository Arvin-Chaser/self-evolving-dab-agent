"""Prepare a small Coding Agent workspace from a Meta-selected file plan.

This is a workflow boundary, not an operating-system sandbox. The upstream
Meta Agent selects files and ties each selection to local Graph evidence. The
controller validates that selection against a frozen contract, copies it, and
writes reproducible receipts before the Coding Agent is started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from typing import Any, Mapping, Sequence

from experiments.curated_coding_workspace_contract import (
    authorize_workspace_path,
    build_bounded_coding_input,
    normalise_workspace_path,
    validate_curated_coding_workspace_contract,
)
from experiments.research_graph_role_scoped_wiring import validate_local_role_handoff


MATERIALIZER_SCHEMA_VERSION = "curated_coding_workspace_materializer_v5"
META_WORKSPACE_REQUEST_SCHEMA_VERSION = "curated_coding_workspace_request_v1"
MANIFEST_SCHEMA_VERSION = "curated_coding_workspace_manifest_v4"
MANIFEST_NAME = "coding_workspace_manifest.json"
CODING_INPUT_NAME = "coding_agent_input.json"
TASK_NAME = "TASK.md"
_MAX_SELECTIONS = 32
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_BYTES = 12 * 1024 * 1024
_REQUEST_KEYS = {"schema_version", "request_id", "contract_sha256", "coding_task", "graph_refs", "selection"}
_SELECTION_KEYS = {"source_relative_path", "target_path", "category", "reason", "graph_refs"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical(value))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _require_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a trimmed non-empty string")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _normalise_graph_refs(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 12:
        raise ValueError(f"{label} must be a non-empty bounded list")
    refs = [_require_text(item, label, maximum=128) for item in value]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{label} has duplicate references")
    return sorted(refs)


def _normalise_source_path(value: Any) -> str:
    return normalise_workspace_path(value)


def _normalise_source_roots(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not value:
        raise ValueError("controller source roots must be a non-empty sequence")
    roots = [_normalise_source_path(item.rstrip("/")) + "/" for item in value]
    if len(set(roots)) != len(roots):
        raise ValueError("controller source roots have duplicates")
    return tuple(sorted(roots))


def _source_path(source_root: Path, relative: str, roots: tuple[str, ...]) -> Path:
    if not any(relative.startswith(root) for root in roots):
        raise ValueError("Meta selection source is outside controller source roots")
    candidate = source_root.joinpath(*relative.split("/"))
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("Meta selection source must be an ordinary file")
    resolved_root = source_root.resolve()
    if resolved_root not in candidate.resolve().parents:
        raise ValueError("Meta selection source escapes repository")
    mode = candidate.stat(follow_symlinks=False).st_mode
    if not stat.S_ISREG(mode) or os.stat(candidate, follow_symlinks=False).st_nlink != 1:
        raise ValueError("Meta selection source is not an independent regular file")
    return candidate


def _contract_paths(contract: Mapping[str, Any]) -> set[str]:
    return {path for scope in ("read_scope", "write_scope") for paths in contract[scope].values() for path in paths}


def _normalise_request(
    request: Mapping[str, Any], contract: Mapping[str, Any], *, expected_contract_sha256: str,
    expected_packet_sha256: str, expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _copy_json(request)
    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise ValueError("Meta workspace request schema differs")
    checked_contract = validate_curated_coding_workspace_contract(
        contract, expected_contract_sha256=expected_contract_sha256,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
    )
    if value["schema_version"] != META_WORKSPACE_REQUEST_SCHEMA_VERSION:
        raise ValueError("Meta workspace request schema version differs")
    if _require_sha256(value["contract_sha256"], "request contract_sha256") != checked_contract["contract_sha256"]:
        raise ValueError("Meta workspace request contract binding differs")
    selection = value["selection"]
    if not isinstance(selection, list) or not selection or len(selection) > _MAX_SELECTIONS:
        raise ValueError("Meta workspace request selection is invalid")
    entries: list[dict[str, Any]] = []
    for item in selection:
        if not isinstance(item, Mapping) or set(item) != _SELECTION_KEYS:
            raise ValueError("Meta workspace selection item schema differs")
        target = normalise_workspace_path(item["target_path"])
        authorization = authorize_workspace_path(
            checked_contract, path=target, access="read",
            expected_contract_sha256=checked_contract["contract_sha256"],
            expected_packet_sha256=expected_packet_sha256,
            expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
        )
        if item["category"] != authorization["category"]:
            raise ValueError("Meta workspace selection category differs from contract")
        entries.append({
            "source_relative_path": _normalise_source_path(item["source_relative_path"]),
            "target_path": target, "category": authorization["category"],
            "reason": _require_text(item["reason"], "selection reason", maximum=600),
            "graph_refs": _normalise_graph_refs(item["graph_refs"], "selection graph_refs"),
        })
    # One source file can intentionally seed both readonly context and an
    # editable candidate; only destination paths must be unique.
    if len({entry["target_path"] for entry in entries}) != len(entries):
        raise ValueError("Meta workspace selection has duplicate target paths")
    if {entry["target_path"] for entry in entries} != _contract_paths(checked_contract):
        raise ValueError("Meta workspace selection must exactly cover the frozen contract")
    entries.sort(key=lambda entry: entry["target_path"])
    return ({
        "schema_version": META_WORKSPACE_REQUEST_SCHEMA_VERSION,
        "request_id": _require_text(value["request_id"], "request_id", maximum=128),
        "contract_sha256": checked_contract["contract_sha256"],
        "coding_task": _require_text(value["coding_task"], "coding_task", maximum=8000),
        "graph_refs": _normalise_graph_refs(value["graph_refs"], "request graph_refs"),
        "selection": entries,
    }, checked_contract)


def _new_workspace(source_root: Path, target_root: Path) -> None:
    if target_root.exists() or source_root == target_root or source_root in target_root.parents:
        raise ValueError("Controller workspace target must be a new separate directory")
    target_root.mkdir(mode=0o700, parents=False)


def _workspace_path(root: Path, relative: str) -> Path:
    path = root.joinpath(*relative.split("/"))
    if root.resolve() not in path.resolve().parents:
        raise ValueError("Workspace destination escapes root")
    return path


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(_canonical(value) + "\n", encoding="ascii", newline="\n")


def _validate_request_graph_refs(
    request: Mapping[str, Any], local_handoff: Mapping[str, Any], *, expected_packet_sha256: str,
    expected_source_binding: Mapping[str, Any], expected_handoff_sha256: str,
) -> dict[str, Any]:
    """Require every Meta selection citation to exist in the passed local view."""
    handoff = validate_local_role_handoff(
        local_handoff, expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
    )
    view = handoff["local_view"]
    allowed = set(view["node_ids"]) | set(view["edge_ids"])
    references = [*request["graph_refs"], *(ref for item in request["selection"] for ref in item["graph_refs"])]
    if not set(references) <= allowed:
        raise ValueError("Meta workspace request cites Graph references outside the local handoff")
    return handoff


def prepare_curated_coding_workspace(
    *, source_repository: str | Path, target_workspace: str | Path,
    contract: Mapping[str, Any], meta_workspace_request: Mapping[str, Any],
    local_handoff: Mapping[str, Any], expected_contract_sha256: str,
    expected_packet_sha256: str, expected_source_binding: Mapping[str, Any],
    expected_handoff_sha256: str, controller_source_roots: Sequence[str],
) -> dict[str, Any]:
    """Materialize exactly the file plan selected by the upstream Meta Agent."""
    source_root = Path(source_repository).resolve()
    if not source_root.is_dir():
        raise ValueError("Controller source repository must be a directory")
    target_root = Path(target_workspace).resolve()
    request_sha256 = _sha256(_copy_json(meta_workspace_request))
    checked_request, checked_contract = _normalise_request(
        meta_workspace_request, contract, expected_contract_sha256=expected_contract_sha256,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
    )
    checked_handoff = _validate_request_graph_refs(
        checked_request, local_handoff, expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
    )
    bounded_input = build_bounded_coding_input(
        checked_contract, checked_handoff, expected_contract_sha256=expected_contract_sha256,
        expected_packet_sha256=expected_packet_sha256,
        expected_source_binding=expected_source_binding, expected_handoff_sha256=expected_handoff_sha256,
        expected_role=checked_contract["role"],
    )
    roots = _normalise_source_roots(controller_source_roots)
    sources: list[tuple[dict[str, Any], Path, str, int]] = []
    total_bytes = 0
    for entry in checked_request["selection"]:
        source = _source_path(source_root, entry["source_relative_path"], roots)
        digest, size = _file_digest(source)
        if size > _MAX_FILE_BYTES or total_bytes + size > _MAX_TOTAL_BYTES:
            raise ValueError("Meta workspace selection exceeds controller byte budget")
        total_bytes += size
        sources.append((entry, source, digest, size))
    _new_workspace(source_root, target_root)
    try:
        for entry, source, digest, size in sources:
            destination = _workspace_path(target_root, entry["target_path"])
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            before, before_size = _file_digest(source)
            if (before, before_size) != (digest, size):
                raise ValueError("Source file changed before copy")
            shutil.copyfile(source, destination, follow_symlinks=False)
            after, after_size = _file_digest(destination)
            if (after, after_size) != (digest, size):
                raise ValueError("Workspace copy hash or size differs")
        _write_json(target_root / CODING_INPUT_NAME, bounded_input)
        task_text = checked_request["coding_task"] + "\n"
        (target_root / TASK_NAME).write_text(task_text, encoding="utf-8", newline="\n")
        body = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
            "request_id": checked_request["request_id"], "request_sha256": request_sha256,
            "contract_sha256": checked_contract["contract_sha256"],
            "packet_sha256": expected_packet_sha256, "local_handoff_sha256": expected_handoff_sha256,
            "source_binding": _copy_json(expected_source_binding),
            "controller_source_roots": list(roots),
            "files": [{**entry, "sha256": digest, "bytes": size} for entry, _source, digest, size in sources],
            "coding_input_sha256": _sha256(bounded_input),
            "task_sha256": hashlib.sha256(task_text.encode("utf-8")).hexdigest(),
        }
        manifest = {**body, "manifest_sha256": _sha256(body)}
        _write_json(target_root / MANIFEST_NAME, manifest)
        return {"workspace": str(target_root), "manifest_sha256": manifest["manifest_sha256"], "file_count": len(sources)}
    except Exception:
        # Do not leave a partial workspace that could be launched later.
        shutil.rmtree(target_root)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controller-owned curated workspace prepare-only gate")
    parser.add_argument("--prepare-request", required=True, type=Path)
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    raise ValueError("The evolution controller must invoke preparation; direct CLI preparation is not wired yet")


if __name__ == "__main__":
    raise SystemExit(main())
