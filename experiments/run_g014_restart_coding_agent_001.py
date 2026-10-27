"""Run one isolated DeepSeek Coding Agent attempt for the accepted G14 plan."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.curated_coding_workspace_launcher import build_coding_agent_launch_spec
from experiments.dab_meta_runtime import meta_environment, run_logged_command
from experiments.dab_meta_standalone_runtime_v1 import CODEX

OUT = ROOT / "experiments/g014_restart_interface_candidate_001"
PREPARED = OUT / "workspace_repair003_receipt.json"
LAUNCH = OUT / "workspace_repair003_launch_spec.json"
RUN_RECEIPT = OUT / "coding_agent_run_001_receipt.json"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    if RUN_RECEIPT.exists():
        raise RuntimeError("G14 Coding Agent attempt already exists")
    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    if prepared.get("status") != "prepared_provider_free":
        raise ValueError("G14 workspace is not prepared")
    saved_launch = json.loads(LAUNCH.read_text(encoding="utf-8"))
    launch = build_coding_agent_launch_spec(
        workspace=prepared["workspace"],
        expected_manifest_sha256=prepared["manifest_sha256"],
        controller_test_commands=saved_launch["controller_test_commands"],
    )
    if launch != saved_launch:
        raise ValueError("G14 prepared launch specification differs")
    prompt = "\n".join([
        "You are the isolated Coding Agent for a provider-free, no-task G14 interface prototype.",
        "Read TASK.md and coding_agent_input.json.",
        "Modify only coding_workspace/candidate/experiments/research_graph_role_scoped_wiring.py",
        "and coding_workspace/candidate/tests/test_g014_restart_competing_hypothesis.py.",
        "coding_workspace/readonly is reference-only. Do not edit the manifest, bounded input,",
        "parent repository, Git metadata, logs, or outputs.",
        "Implement a small deterministic structural prototype and replace only the new synthetic test copy.",
        "Never weaken, rename, delete, or copy changes to the real G14 regression test.",
        "Do not call a provider, network, database, server, benchmark, task data, answer data, or formal evaluation.",
        "Run only: $env:PYTHONPATH='coding_workspace/candidate;coding_workspace/readonly'; python -m pytest -q coding_workspace/candidate/tests/test_g014_restart_competing_hypothesis.py",
        "Report changed candidate files and exact test outcome. Do not claim benchmark benefit, Graph causality, or production readiness.",
    ])
    command = [
        str(CODEX), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash",
        "--sandbox", "workspace-write", "-a", "never", "exec", "--skip-git-repo-check",
        "--output-last-message", str(OUT / "coding_agent_001_final.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=Path(prepared["workspace"]), prompt=prompt,
        stdout_path=OUT / "coding_agent_001.stdout", stderr_path=OUT / "coding_agent_001.stderr",
        env=meta_environment("deepseek-standalone-dab"), timeout=600,
    )
    write_json(RUN_RECEIPT, {
        "status": "completed" if result.returncode == 0 else "provider_or_coding_agent_failed",
        "provider_called": True, "exit_code": result.returncode,
        "workspace": prepared["workspace"], "manifest_sha256": prepared["manifest_sha256"],
        "coding_agent_final_path": str(OUT / "coding_agent_001_final.txt"),
        "controller_tests_started": False, "benchmark_started": False,
        "formal_evaluation_started": False,
    })
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
