#!/usr/bin/env python3
"""Fail-closed protocol gates for Codex editor launchers."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


TOOL_MARKERS = ('"type":"command_execution"', '"type":"file_change"')


def emit(path: Path, status: str, **details: object) -> None:
    path.write_text(json.dumps({"status": status, **details}, indent=2), encoding="utf-8")


def completed_tool_line(transcript: Path) -> str | None:
    if not transcript.exists():
        return None
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if '"type":"item.completed"' in line and any(marker in line for marker in TOOL_MARKERS):
            return line
    return None


def first_action(args: argparse.Namespace) -> int:
    transcript = Path(args.transcript)
    result = Path(args.result)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        evidence = completed_tool_line(transcript)
        if evidence:
            diff = subprocess.run(
                ["git", "-C", args.workspace, "diff", "--quiet", "--", *args.allowed],
                check=False,
            )
            if diff.returncode == 0:
                try:
                    os.kill(args.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                emit(
                    result,
                    "protocol_failed_first_action_no_diff",
                    first_action_gate_passed=False,
                    first_tool_evidence=evidence,
                    validation_allowed=False,
                )
                return 41
            emit(
                result,
                "first_action_gate_passed",
                first_action_gate_passed=True,
                first_tool_evidence=evidence,
                validation_allowed=False,
            )
            return 0
        try:
            os.kill(args.pid, 0)
        except ProcessLookupError:
            emit(result, "protocol_failed_no_completed_tool_action", validation_allowed=False)
            return 42
        time.sleep(0.05)
    try:
        os.kill(args.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    emit(result, "protocol_failed_first_action_timeout", validation_allowed=False)
    return 43


def prevalidation(args: argparse.Namespace) -> int:
    patch = Path(args.patch)
    result = Path(args.result)
    patch_nonempty = patch.exists() and bool(patch.read_text(encoding="utf-8").strip())
    status_lines = Path(args.git_status).read_text(encoding="utf-8").splitlines()
    changed = [line[3:].split(" -> ")[-1] for line in status_lines if len(line) >= 4]
    allowed = set(args.allowed)
    project_changed = [path for path in changed if path in allowed]
    unexpected = [path for path in changed if path not in allowed]
    total_changed = 0
    numstat_path = Path(args.numstat)
    if numstat_path.exists():
        for line in numstat_path.read_text(encoding="utf-8").splitlines():
            added, deleted, _ = line.split("\t", 2)
            total_changed += int(added) + int(deleted)
    details = {
        "patch_nonempty": patch_nonempty,
        "project_changed_files": project_changed,
        "unexpected_changed_files": unexpected,
        "total_changed_lines": total_changed,
        "validation_allowed": False,
    }
    if not patch_nonempty:
        emit(result, "protocol_failed_empty_patch", **details)
        return 51
    if not project_changed:
        emit(result, "protocol_failed_no_project_changed_files", **details)
        return 52
    if unexpected:
        emit(result, "protocol_failed_unexpected_changed_files", **details)
        return 53
    if total_changed > args.max_changed_lines:
        emit(result, "protocol_failed_diff_too_large", **details)
        return 54
    emit(result, "prevalidation_gate_passed", **{**details, "validation_allowed": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    first = commands.add_parser("first-action")
    first.add_argument("--pid", type=int, required=True)
    first.add_argument("--transcript", required=True)
    first.add_argument("--workspace", required=True)
    first.add_argument("--result", required=True)
    first.add_argument("--timeout", type=float, default=120.0)
    first.add_argument("--allowed", nargs="+", required=True)
    first.set_defaults(func=first_action)
    pre = commands.add_parser("prevalidation")
    pre.add_argument("--patch", required=True)
    pre.add_argument("--git-status", required=True)
    pre.add_argument("--numstat", required=True)
    pre.add_argument("--result", required=True)
    pre.add_argument("--max-changed-lines", type=int, required=True)
    pre.add_argument("--allowed", nargs="+", required=True)
    pre.set_defaults(func=prevalidation)
    return root


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.func(parsed))
