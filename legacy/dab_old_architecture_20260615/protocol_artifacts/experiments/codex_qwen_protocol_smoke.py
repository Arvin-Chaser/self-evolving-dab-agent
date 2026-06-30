"""Smoke-test Codex CLI running against the Qwen/DashScope profile.

This verifies the exact boundary needed for using Codex CLI as a Qwen-backed
meta agent:

1. plain model response works;
2. Codex can emit and execute a real shell tool action;
3. the tool action can modify a file and produce a git diff;
4. Codex can, or cannot, complete the post-tool continuation cleanly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "logs" / "meta_agent" / "codex_qwen_protocol_smoke"


def load_dashscope_key_from_bashrc(env: dict[str, str]) -> None:
    if env.get("DASHSCOPE_API_KEY"):
        return
    bashrc = Path.home() / ".bashrc"
    if not bashrc.exists():
        return
    for line in bashrc.read_text(errors="ignore").splitlines():
        match = re.match(r"^\s*export\s+DASHSCOPE_API_KEY=(.*)\s*$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if value:
            env["DASHSCOPE_API_KEY"] = value
        return


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
        stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")
        return {
            "returncode": proc.returncode,
            "elapsed_sec": round(time.time() - started, 3),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8", errors="replace")
        return {
            "returncode": None,
            "timeout": True,
            "elapsed_sec": round(time.time() - started, 3),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def init_fixture(workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "smoke@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "smoke"], cwd=workspace, check=True)
    (workspace / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workspace, check=True)


def git_diff(workspace: Path) -> str:
    proc = subprocess.run(
        ["git", "diff", "--", "sample.py"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout


def smoke_for_model(args: argparse.Namespace, model: str, output_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    load_dashscope_key_from_bashrc(env)
    env.setdefault("NO_COLOR", "1")

    model_dir = output_root / model.replace("/", "_")
    model_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "model": model,
        "profile": args.profile,
        "dashscope_api_key_present": bool(env.get("DASHSCOPE_API_KEY")),
    }
    if not env.get("DASHSCOPE_API_KEY"):
        report["status"] = "failed_missing_dashscope_api_key"
        return report

    plain_out = model_dir / "plain_last_message.txt"
    plain = run_command(
        [
            "codex",
            "--profile",
            args.profile,
            "--model",
            model,
            "--sandbox",
            "workspace-write",
            "-a",
            "never",
            "exec",
            "--skip-git-repo-check",
            "--output-last-message",
            str(plain_out),
            "Say exactly: codex qwen ok",
        ],
        cwd=Path("/tmp"),
        env=env,
        timeout=args.timeout,
        stdout_path=model_dir / "plain.stdout",
        stderr_path=model_dir / "plain.stderr",
    )
    plain_message = read_text(plain_out)
    plain.update(
        {
            "last_message_path": str(plain_out),
            "last_message": plain_message.strip(),
            "passed": plain.get("returncode") == 0 and plain_message.strip() == "codex qwen ok",
        }
    )
    report["plain_response"] = plain

    workspace = Path("/tmp") / f"codex_qwen_protocol_smoke_{model.replace('/', '_')}"
    init_fixture(workspace)
    tool_out = model_dir / "tool_last_message.txt"
    exact_command = "perl -0pi -e 's/VALUE = 1/VALUE = 2/' sample.py && git diff -- sample.py"
    tool = run_command(
        [
            "codex",
            "--profile",
            args.profile,
            "--model",
            model,
            "--sandbox",
            "workspace-write",
            "-a",
            "never",
            "exec",
            "-C",
            str(workspace),
            "--output-last-message",
            str(tool_out),
            (
                "Your first and only tool action must run this exact shell command: "
                f"{exact_command}. Do not run cat or inspect files first."
            ),
        ],
        cwd=workspace,
        env=env,
        timeout=args.timeout,
        stdout_path=model_dir / "tool.stdout",
        stderr_path=model_dir / "tool.stderr",
    )
    sample_text = read_text(workspace / "sample.py")
    diff_text = git_diff(workspace)
    (model_dir / "sample.py").write_text(sample_text, encoding="utf-8")
    (model_dir / "tool.diff").write_text(diff_text, encoding="utf-8")

    tool_stdout = read_text(model_dir / "tool.stdout")
    tool_stderr = read_text(model_dir / "tool.stderr")
    tool_log = tool_stdout + "\n" + tool_stderr
    stream_disconnected = "stream disconnected before completion" in tool_log
    tool.update(
        {
            "workspace": str(workspace),
            "last_message_path": str(tool_out),
            "sample_path": str(model_dir / "sample.py"),
            "diff_path": str(model_dir / "tool.diff"),
            "tool_call_emitted": exact_command in tool_log or "exec" in tool_log,
            "tool_command_succeeded": "VALUE = 2" in sample_text and bool(diff_text.strip()),
            "file_modified": "VALUE = 2" in sample_text,
            "diff_nonempty": bool(diff_text.strip()),
            "codex_completed_after_tool": tool.get("returncode") == 0 and tool_out.exists(),
            "stream_disconnected_before_completion": stream_disconnected,
        }
    )
    report["tool_edit"] = tool

    if plain["passed"] and tool["codex_completed_after_tool"]:
        report["status"] = "protocol_smoke_passed"
    elif plain["passed"] and tool["file_modified"] and tool["stream_disconnected_before_completion"]:
        report["status"] = "tool_executed_but_post_tool_stream_failed"
    elif plain["passed"] and tool["file_modified"]:
        report["status"] = "tool_executed_but_codex_did_not_complete"
    else:
        report["status"] = "protocol_smoke_failed"
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen")
    parser.add_argument("--model", action="append", default=None)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()

    models = args.model or ["qwen-plus"]
    output_root = Path(args.output_root).resolve()
    run_dir = output_root / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    results = [smoke_for_model(args, model, run_dir) for model in models]
    report = {
        "run_dir": str(run_dir),
        "results": results,
        "summary": {
            "protocol_smoke_passed": [r["model"] for r in results if r["status"] == "protocol_smoke_passed"],
            "post_tool_stream_failed": [
                r["model"] for r in results if r["status"] == "tool_executed_but_post_tool_stream_failed"
            ],
            "failed": [
                r["model"]
                for r in results
                if r["status"]
                not in {"protocol_smoke_passed", "tool_executed_but_post_tool_stream_failed"}
            ],
        },
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "summary": report["summary"]}, ensure_ascii=False))

    if not report["summary"]["protocol_smoke_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
