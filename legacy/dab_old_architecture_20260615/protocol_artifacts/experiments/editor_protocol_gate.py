#!/usr/bin/env python3
"""Hard protocol gates shared by editor launchers and negative controls."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


TOOL_MARKERS = ('"type":"command_execution"', '"type":"file_change"')


def write_result(path: Path, status: str, **details: object) -> None:
    payload = {"status": status, **details}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def first_action(args: argparse.Namespace) -> int:
    transcript = Path(args.transcript)
    result = Path(args.result)
    while True:
        try:
            os.kill(args.pid, 0)
        except ProcessLookupError:
            write_result(result, "protocol_failed_no_completed_tool_action")
            return 42

        text = transcript.read_text(encoding="utf-8") if transcript.exists() else ""
        completed = [
            line
            for line in text.splitlines()
            if '"type":"item.completed"' in line and any(marker in line for marker in TOOL_MARKERS)
        ]
        if completed:
            diff = subprocess.run(
                ["git", "-C", args.workspace, "diff", "--quiet", "--", *args.allowed],
                check=False,
            )
            if diff.returncode == 0:
                try:
                    os.kill(args.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                write_result(
                    result,
                    "protocol_failed_first_action_no_diff",
                    first_tool_evidence=completed[0],
                    first_action_gate_passed=False,
                )
                return 41
            write_result(
                result,
                "first_action_gate_passed",
                first_tool_evidence=completed[0],
                first_action_gate_passed=True,
            )
            return 0
        time.sleep(0.05)


def prevalidation(args: argparse.Namespace) -> int:
    result = Path(args.result)
    patch = Path(args.patch)
    status_path = Path(args.git_status)
    patch_nonempty = patch.exists() and bool(patch.read_text(encoding="utf-8").strip())
    lines = status_path.read_text(encoding="utf-8").splitlines() if status_path.exists() else []
    changed = [line[3:].split(" -> ")[-1] for line in lines if len(line) >= 4]
    allowed = set(args.allowed)
    project_changed = [path for path in changed if path in allowed]
    unexpected = [path for path in changed if path not in allowed]

    details = {
        "patch_nonempty": patch_nonempty,
        "project_changed_files": project_changed,
        "unexpected_changed_files": unexpected,
        "validation_allowed": False,
    }
    if not patch_nonempty:
        write_result(result, "protocol_failed_empty_patch", **details)
        return 51
    if not project_changed:
        write_result(result, "protocol_failed_no_project_changed_files", **details)
        return 52
    if unexpected:
        write_result(result, "protocol_failed_unexpected_changed_files", **details)
        return 53
    write_result(result, "prevalidation_gate_passed", **{**details, "validation_allowed": True})
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    first = commands.add_parser("first-action")
    first.add_argument("--pid", type=int, required=True)
    first.add_argument("--transcript", required=True)
    first.add_argument("--workspace", required=True)
    first.add_argument("--result", required=True)
    first.add_argument("--allowed", nargs="+", required=True)
    first.set_defaults(func=first_action)
    pre = commands.add_parser("prevalidation")
    pre.add_argument("--patch", required=True)
    pre.add_argument("--git-status", required=True)
    pre.add_argument("--result", required=True)
    pre.add_argument("--allowed", nargs="+", required=True)
    pre.set_defaults(func=prevalidation)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.func(arguments))
