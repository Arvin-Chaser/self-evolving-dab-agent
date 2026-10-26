#!/usr/bin/env python3
"""Read-only, answer-blind status snapshot for the unique G10 run."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G10 = BASE / "g010_revision001"
RUN_ID = "g010_verification_reconciliation_nohint_56_v1"
RUN = G10 / "evaluation" / RUN_ID
PID = 225760
TREE_SHA = "80f002ac7a2d90b3cfed0fda7fec03c64c0a442c69a0ae27c7506852b32d36b9"
PRE_EXEC = BASE / "graph/g010_pre_execution.json"
PREFLIGHT = BASE / "graph/g010_preflight.json"
CLAIM = BASE / "graph/g010_launch_claim.json"
MANIFEST = BASE / "graph/g010_launch_manifest.json"
SIDECARS = {
    "journal_files": "g004_paired_structural_journal.jsonl",
    "normalized_sidecar_files": "g004_postrun_normalized_structural.json",
    "provenance_files": "g005_provenance_sidecar.jsonl",
    "tool_class_files": "g006_tool_class_sidecar.jsonl",
    "last_pre_exec_files": "g007_last_pre_exec_sidecar.jsonl",
    "verification_audit_files": "g008_verification_audit_sidecar.jsonl",
    "verification_turn_gate_files": "g009_verification_turn_gate_sidecar.jsonl",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    pre = read(PRE_EXEC)
    preflight = read(PREFLIGHT)
    claim = read(CLAIM)
    launch = read(MANIFEST)
    binding = launch.get("binding", {})
    args = launch.get("command", [])
    if (
        launch.get("pid") != PID
        or binding.get("candidate_tree_sha256") != TREE_SHA
        or any(item.get("binding") != binding for item in (pre, preflight, claim))
        or preflight.get("status") != "passed"
        or preflight.get("model_probe", {}).get("http_status") != 200
        or claim.get("pre_execution_sha256") != digest(PRE_EXEC)
        or claim.get("preflight_sha256") != digest(PREFLIGHT)
        or launch.get("preflight_sha256") != digest(PREFLIGHT)
        or "--run-id" not in args
        or args[args.index("--run-id") + 1] != RUN_ID
    ):
        raise RuntimeError("G10 launch identity differs")
    cmdline = Path(f"/proc/{PID}/cmdline")
    command = (
        cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if cmdline.is_file() else ""
    )
    running = bool(command)
    if running and (
        RUN_ID not in command
        or str(G10 / "source/experiments/run_multi_query_baseline.py") not in command
    ):
        raise RuntimeError("G10 PID no longer belongs to the bound runner")

    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    strict_unknown = 0
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError("G10 result status differs")
        statuses[status] += 1
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            strict_unknown += row.get("strict_match_passed") is None
    if len(rows) > 56:
        raise RuntimeError("G10 progress exceeds frozen 56")
    run_dirs = list((RUN / "runs").glob("*")) if (RUN / "runs").is_dir() else []
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_unknown_completed": strict_unknown,
        **{name: sum((path / filename).is_file() for path in run_dirs)
           for name, filename in SIDECARS.items()},
        "summary_present": summary_path.is_file(), "free_bytes": free,
        "free_gib": round(free / 1024**3, 3), "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
