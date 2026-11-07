"""Isolated source snapshots and lightweight admission checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


SOURCE_SUFFIXES = {".py", ".js", ".ts", ".java", ".go", ".rs", ".md", ".txt", ".toml", ".yaml", ".yml"}


def source_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES and ".git" not in path.parts:
            yield path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest(root: Path) -> list[dict[str, str]]:
    return [{"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(path)} for path in source_files(root)]


def source_tree_hash(root: Path) -> str:
    raw = json.dumps(source_manifest(root), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def prepare_workspace(parent_root: Path, output_root: Path) -> dict[str, object]:
    if output_root.exists():
        raise FileExistsError(output_root)
    shutil.copytree(parent_root, output_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "logs"))
    manifest = source_manifest(output_root)
    payload = {"parent_tree_sha256": source_tree_hash(parent_root), "candidate_tree_sha256": source_tree_hash(output_root), "files": manifest}
    (output_root / "workspace_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
