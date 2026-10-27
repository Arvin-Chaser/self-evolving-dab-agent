"""Provider-free preflight for a prepared Coding Agent workspace.

This module intentionally returns a launch specification. It never starts
Codex, a provider, a shell, or a test command.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from experiments.curated_coding_workspace_materializer import (
    CODING_INPUT_NAME,
    MANIFEST_NAME,
    TASK_NAME,
)


LAUNCH_SPEC_SCHEMA_VERSION = "curated_coding_workspace_launch_spec_v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _read_manifest(workspace: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    path = workspace / MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Prepared workspace manifest is unreadable") from exc
    if not isinstance(value, dict) or "manifest_sha256" not in value:
        raise ValueError("Prepared workspace manifest schema differs")
    body = {key: item for key, item in value.items() if key != "manifest_sha256"}
    if _canonical(body) == "{}" or value["manifest_sha256"] != hashlib.sha256(_canonical(body).encode("ascii")).hexdigest():
        raise ValueError("Prepared workspace manifest hash differs")
    if value["manifest_sha256"] != _require_sha256(expected_manifest_sha256, "expected_manifest_sha256"):
        raise ValueError("Prepared workspace expected manifest hash differs")
    if not isinstance(value.get("files"), list) or not value["files"]:
        raise ValueError("Prepared workspace manifest files differ")
    return value


def _validate_commands(value: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes)) or len(value) > 8:
        raise ValueError("Controller test commands must be a bounded sequence")
    commands = []
    for command in value:
        if not isinstance(command, str) or not command.strip() or command != command.strip() or "\n" in command or "\r" in command:
            raise ValueError("Controller test command is invalid")
        commands.append(command)
    return commands


def build_coding_agent_launch_spec(
    *, workspace: str | Path, expected_manifest_sha256: str,
    controller_test_commands: Sequence[str],
) -> dict[str, Any]:
    """Verify immutable prepared inputs and return a non-executing launch spec."""
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ValueError("Prepared workspace is not a directory")
    manifest = _read_manifest(root, expected_manifest_sha256)
    expected_files = {CODING_INPUT_NAME, TASK_NAME, MANIFEST_NAME}
    for entry in manifest["files"]:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("target_path"), str):
            raise ValueError("Prepared workspace manifest file entry differs")
        relative = entry["target_path"]
        path = root.joinpath(*relative.split("/"))
        if not path.is_file() or path.is_symlink():
            raise ValueError("Prepared workspace file is missing or linked")
        digest, size = _sha256_file(path)
        if digest != _require_sha256(entry.get("sha256"), "prepared file hash") or size != entry.get("bytes"):
            raise ValueError("Prepared workspace file hash or size differs")
        expected_files.add(relative)
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise ValueError("Prepared workspace file inventory differs")
    input_path = root / CODING_INPUT_NAME
    try:
        input_value = json.loads(input_path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Prepared Coding Agent input is unreadable") from exc
    if not isinstance(input_value, dict) or hashlib.sha256(_canonical(input_value).encode("ascii")).hexdigest() != manifest.get("coding_input_sha256"):
        raise ValueError("Prepared Coding Agent input hash differs")
    if _sha256_file(root / TASK_NAME)[0] != manifest.get("task_sha256"):
        raise ValueError("Prepared Coding Agent task hash differs")
    return {
        "schema_version": LAUNCH_SPEC_SCHEMA_VERSION,
        "mode": "dry-run",
        "cwd": str(root),
        "task_path": str(root / TASK_NAME),
        "coding_input_path": str(input_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "controller_test_commands": _validate_commands(controller_test_commands),
    }
