#!/usr/bin/env python3
"""Read-only compare staged G3 source manifest with local admission."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_manifest, source_tree_hash


LOCAL = Path(__file__).resolve().parent / "research_graph_baseline_20261016/g003_candidate_001/repo"
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o",
       "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]
REMOTE = r'''
import hashlib,importlib.util,json
from pathlib import Path
root=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g003_revision001/source")
paths=[]
for name in ("AGENTS.md","llm_client.py"):
    path=root/name
    if path.is_file() and not path.is_symlink(): paths.append(path)
for path in (root/"experiments").glob("*.py"):
    if path.is_file() and not path.is_symlink() and not path.name.startswith("."): paths.append(path)
for dirname in ("adapters","prompts/dab","meta_agent","tests"):
    base=root/dirname
    if not base.is_dir(): continue
    for path in base.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in {".py",".txt",".md"}:
            if not any(part.startswith(".") or part=="__pycache__" for part in path.relative_to(root).parts):
                paths.append(path)
manifest=[{"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
          for path in sorted(set(paths),key=lambda path:path.relative_to(root).as_posix().lower())
          if path.relative_to(root).as_posix()!="AGENTS.md"]
spec=importlib.util.spec_from_file_location("g3_manifest",root/"experiments/intent_candidate_workspace.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({"manual_manifest":manifest,
                  "module_manifest":module.source_tree_manifest(root),
                  "module_tree":module.source_tree_hash(root),
                  "canonical_tree":module.source_manifest_hash(sorted(
                      module.source_tree_manifest(root),key=lambda row:row["path"].lower()))},sort_keys=True))
'''


def main() -> None:
    proc = subprocess.run(SSH, input=REMOTE, text=True, encoding="utf-8",
                          capture_output=True, timeout=30, check=False)
    if proc.returncode:
        raise RuntimeError(f"G3 staging inspection failed: {proc.returncode}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("SSH did not start with disk check")
    expected = {item["path"]: item["sha256"] for item in source_tree_manifest(LOCAL)}
    remote = json.loads(lines[-1])
    actual = {item["path"]: item["sha256"] for item in remote["module_manifest"]}
    first_order_difference = next((index for index, (a, b) in enumerate(
        zip(remote["manual_manifest"], remote["module_manifest"])) if a != b), None)
    print(json.dumps({"local_tree": source_tree_hash(LOCAL),
                      "local_count": len(expected), "remote_count": len(actual),
                      "remote_tree": remote["module_tree"],
                      "remote_canonical_tree": remote["canonical_tree"],
                      "manual_vs_module": remote["manual_manifest"] == remote["module_manifest"],
                      "first_order_difference": first_order_difference,
                      "first_manual_path": (remote["manual_manifest"][first_order_difference]["path"]
                                            if first_order_difference is not None else None),
                      "first_module_path": (remote["module_manifest"][first_order_difference]["path"]
                                            if first_order_difference is not None else None),
                      "different_paths": sorted(path for path in set(expected) | set(actual)
                                                if expected.get(path) != actual.get(path))}, sort_keys=True))


if __name__ == "__main__":
    main()
