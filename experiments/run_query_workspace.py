#!/usr/bin/env python3
"""Validate or run an isolated DAB query workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_workspace(path: Path) -> dict[str, Any]:
    config_path = path / "workspace.json"
    if not config_path.exists():
        raise SystemExit(f"workspace.json not found: {config_path}")
    value = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"workspace.json must contain an object: {config_path}")
    return value


def local_path(workspace: Path, value: str | None, default: str) -> Path:
    path = Path(value or default)
    return path if path.is_absolute() else workspace / path


def validate_workspace(workspace: Path, config: dict[str, Any]) -> dict[str, Any]:
    agent = config.get("agent") if isinstance(config.get("agent"), dict) else {}
    required = {
        "workspace": workspace,
        "query_dir": Path(str(config.get("query_dir") or "")),
        "query_json": Path(str(config.get("query_dir") or "")) / "query.json",
        "policy": local_path(workspace, agent.get("policy"), "agent/policy.txt"),
        "helper_registry": local_path(workspace, agent.get("helper_registry"), "agent/helpers/registry.py"),
        "helper_module_root": local_path(workspace, agent.get("helper_module_root"), "agent"),
        "current_parent_state": workspace / "state/current_parent.json",
    }
    missing = {name: str(path) for name, path in required.items() if not path.exists()}
    patch_results: list[dict[str, Any]] = []
    patch_chain_path = workspace / "lineage/patch_chain.json"
    if patch_chain_path.exists():
        chain = json.loads(patch_chain_path.read_text(encoding="utf-8"))
        for item in chain.get("patches") or []:
            patch_path = workspace / "lineage" / str(item.get("file"))
            actual = hashlib.sha256(patch_path.read_bytes()).hexdigest() if patch_path.exists() else None
            expected = item.get("sha256")
            patch_results.append(
                {
                    "file": str(patch_path),
                    "exists": patch_path.exists(),
                    "sha256_matches": bool(actual and actual == expected),
                    "actual_sha256": actual,
                    "expected_sha256": expected,
                }
            )
    status = "passed" if not missing and all(item["sha256_matches"] for item in patch_results) else "failed"
    return {
        "status": status,
        "workspace_id": config.get("workspace_id"),
        "workspace": str(workspace),
        "query_dir": str(required["query_dir"]),
        "initial_parent_agent_id": config.get("initial_parent_agent_id"),
        "source_lineage_family": config.get("source_lineage_family"),
        "helper_registry": str(required["helper_registry"]),
        "patch_chain": patch_results,
        "missing": missing,
    }


def run_command(command: list[str], env: dict[str, str]) -> int:
    print(json.dumps({"command": command, "cwd": str(ROOT)}, indent=2))
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--action", choices=["validate", "prepare", "run-data-agent", "run-parent", "evolve"], default="validate")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--mode", choices=["dry-run", "run"], default="run")
    parser.add_argument("--candidate-launcher", default="experiments/run_codex_native_repair_launcher.py")
    parser.add_argument("--repair-profile", default="data_agent_project_repair")
    parser.add_argument(
        "--parent-mode",
        choices=["best-archive", "initial"],
        default="best-archive",
        help="For evolve, choose the first parent from this query lineage archive or force the workspace initial parent.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config = load_workspace(workspace)
    validation = validate_workspace(workspace, config)
    if args.action == "validate":
        print(json.dumps(validation, indent=2, ensure_ascii=False))
        return 0 if validation["status"] == "passed" else 1
    if validation["status"] != "passed":
        print(json.dumps(validation, indent=2, ensure_ascii=False))
        return 1

    workspace_rel = workspace.relative_to(ROOT).as_posix()
    env = os.environ.copy()
    env["DAB_QUERY_WORKSPACE"] = workspace_rel
    env["DAB_TOOL_AGENT_MAX_ITERATIONS"] = str(args.max_iterations)
    env["DAB_TOOL_AGENT_PARENT_MAX_ITERATIONS"] = str(args.max_iterations)
    env["DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS"] = str(args.max_iterations)
    env["CODEX_NATIVE_DATA_AGENT_MAX_ITERATIONS"] = str(args.max_iterations)

    if args.action in {"prepare", "run-data-agent"}:
        command = [
            str(ROOT / ".venv/bin/python"),
            "experiments/run_dab_tool_agent.py",
            "--query-workspace",
            workspace_rel,
            "--run-id",
            f"{config.get('workspace_id')}_{args.action.replace('-', '_')}",
            "--max-iterations",
            str(args.max_iterations),
        ]
        if args.action == "prepare":
            command.append("--prepare-only")
        return run_command(command, env)

    command = [
        str(ROOT / ".venv/bin/python"),
        "experiments/run_meta_agent_evolution_loop.py",
        "--query-workspace",
        workspace_rel,
        "--mode",
        args.mode,
        "--iterations",
        str(args.iterations),
        "--archive-max-parent-age-hours",
        "0",
        "--repair-profile",
        args.repair_profile,
        "--query-parent-mode",
        args.parent_mode,
    ]
    if args.action == "evolve":
        command.extend(["--candidate-launcher", args.candidate_launcher, "--run-generic-child-eval"])
    return run_command(command, env)


if __name__ == "__main__":
    raise SystemExit(main())
