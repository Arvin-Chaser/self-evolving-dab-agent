#!/usr/bin/env python3
"""Replay the current candidate workspace diff against a fresh child baseline.

This is a Codex-native self-check tool. It does not decide how to repair; it
only answers whether the current working-tree patch can be applied to the same
kind of fresh parent-materialized workspace used by child eval.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_AGENT_CANONICAL_PROMPT = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(command: list[str], *, cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, input=input_text, text=True, capture_output=True, check=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ignore_workspace(_: str, names: list[str]) -> list[str]:
    ignored = {".git", ".venv", ".env", ".codex", "__pycache__", "logs", "candidates", "reports", "trajectories"}
    return [name for name in names if name in ignored]


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def collect_parent_patches(source_root: Path, parent_agent_id: str | None) -> list[Path]:
    patches: list[Path] = []
    seen: set[str] = set()

    def collect(agent_id: str | None) -> None:
        if not agent_id or agent_id in seen:
            return
        seen.add(agent_id)
        card = load_json(source_root / "archive" / "agents" / agent_id / "agent_card.json")
        if not card:
            return
        lineage = card.get("lineage") if isinstance(card.get("lineage"), dict) else {}
        collect(str(lineage.get("parent_agent_id") or ""))
        source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
        patch_ref = source_refs.get("candidate_patch")
        if not patch_ref:
            return
        patch_path = Path(str(patch_ref))
        if not patch_path.is_absolute():
            patch_path = source_root / patch_path
        if patch_path.exists() and patch_path not in patches:
            patches.append(patch_path)

    collect(parent_agent_id)
    return patches


def init_git_baseline(workspace: Path) -> None:
    for command in [
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "candidate-replay"],
        ["git", "config", "user.email", "candidate-replay@localhost"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "baseline"],
    ]:
        proc = run(command, cwd=workspace)
        if proc.returncode != 0:
            raise RuntimeError(f"command failed: {' '.join(command)}\n{proc.stderr}")


def amend_baseline(workspace: Path) -> None:
    proc = run(["git", "add", "."], cwd=workspace)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    proc = run(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=workspace)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def materialize_parent_source(child_ws: Path, source_root: Path, parent_agent_id: str | None) -> dict[str, Any]:
    patch_paths = collect_parent_patches(source_root, parent_agent_id)
    applied: list[str] = []
    for patch_path in patch_paths:
        if not patch_path.read_text(encoding="utf-8", errors="replace").strip():
            continue
        proc = run(["git", "apply", f"--exclude={DATA_AGENT_CANONICAL_PROMPT.as_posix()}", str(patch_path)], cwd=child_ws)
        if proc.returncode != 0:
            return {"status": "failed", "patch_path": str(patch_path), "applied_patches": applied, "stderr": proc.stderr}
        applied.append(str(patch_path))
    if applied:
        amend_baseline(child_ws)
    return {"status": "applied" if applied else "skipped", "patch_paths": applied, "excluded_prompt": DATA_AGENT_CANONICAL_PROMPT.as_posix()}


def materialize_parent_prompt(child_ws: Path, source_root: Path, parent_prompt: str | None) -> dict[str, Any]:
    if not parent_prompt:
        return {"status": "skipped", "reason": "parent_prompt not provided"}
    source = Path(parent_prompt)
    if not source.is_absolute():
        source = source_root / source
    if not source.exists():
        return {"status": "failed", "reason": f"parent prompt not found: {source}"}
    target = child_ws / DATA_AGENT_CANONICAL_PROMPT
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    proc = run(["git", "add", str(DATA_AGENT_CANONICAL_PROMPT)], cwd=child_ws)
    if proc.returncode != 0:
        return {"status": "failed", "stderr": proc.stderr}
    proc = run(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=child_ws)
    if proc.returncode != 0:
        return {"status": "failed", "stderr": proc.stderr}
    return {"status": "materialized_parent_prompt", "source_prompt": str(source), "canonical_target": DATA_AGENT_CANONICAL_PROMPT.as_posix()}


def current_patch(candidate_workspace: Path) -> tuple[str, str, str]:
    run(["git", "add", "-N", "."], cwd=candidate_workspace)
    diff = run(["git", "diff", "--binary"], cwd=candidate_workspace)
    status = run(["git", "status", "--short"], cwd=candidate_workspace)
    numstat = run(["git", "diff", "--numstat"], cwd=candidate_workspace)
    return diff.stdout or "", status.stdout or "", numstat.stdout or ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, help="Main project root used as child-eval source snapshot.")
    parser.add_argument("--candidate-workspace", default=".", help="Workspace containing current candidate edits and git HEAD baseline.")
    parser.add_argument("--parent-agent-id")
    parser.add_argument("--parent-prompt")
    parser.add_argument("--report", required=True)
    parser.add_argument("--patch-out")
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    candidate_workspace = Path(args.candidate_workspace).resolve()
    report_path = Path(args.report).resolve()
    patch_text, status_text, numstat_text = current_patch(candidate_workspace)
    patch_out = Path(args.patch_out).resolve() if args.patch_out else report_path.with_suffix(".patch")
    patch_out.parent.mkdir(parents=True, exist_ok=True)
    patch_out.write_text(patch_text, encoding="utf-8")

    child_root = Path(tempfile.mkdtemp(prefix="candidate_patch_replay."))
    child_ws = child_root / "workspace"
    shutil.copytree(source_root, child_ws, ignore=ignore_workspace, symlinks=True)
    init_git_baseline(child_ws)
    source_materialization = materialize_parent_source(child_ws, source_root, args.parent_agent_id)
    prompt_materialization = materialize_parent_prompt(child_ws, source_root, args.parent_prompt)

    check = run(["git", "apply", "--check", str(patch_out)], cwd=child_ws)
    applied = None
    if check.returncode == 0:
        applied = run(["git", "apply", str(patch_out)], cwd=child_ws)

    report = {
        "status": "replay_apply_passed" if check.returncode == 0 and applied and applied.returncode == 0 else "replay_apply_failed",
        "created_at": utc_now(),
        "source_root": str(source_root),
        "candidate_workspace": str(candidate_workspace),
        "child_workspace": str(child_ws),
        "parent_agent_id": args.parent_agent_id,
        "parent_prompt": args.parent_prompt,
        "patch_out": str(patch_out),
        "patch_empty": not bool(patch_text.strip()),
        "candidate_git_status": status_text.splitlines(),
        "candidate_numstat": numstat_text.splitlines(),
        "source_materialization": source_materialization,
        "prompt_materialization": prompt_materialization,
        "git_apply_check_returncode": check.returncode,
        "git_apply_check_stderr": check.stderr,
        "git_apply_returncode": applied.returncode if applied is not None else None,
        "git_apply_stderr": applied.stderr if applied is not None else None,
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "replay_apply_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
