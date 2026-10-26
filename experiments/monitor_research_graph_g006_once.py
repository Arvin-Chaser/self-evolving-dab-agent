#!/usr/bin/env python3
"""Read-only, answer-blind status snapshot for the unique G6 run."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G6 = BASE / "g006_revision001"
RUN_ID = "baseline_g006_tool_class_nohint_56_v1"
RUN = G6 / "evaluation" / RUN_ID
PID = 42155
TREE_SHA = "845e0f89f3df104d1fcb0ca564256fe8ca0f92c8880127dc4b3c2d4cfb0244c6"
PRE_EXEC = BASE / "graph/g006_pre_execution.json"
PREFLIGHT = BASE / "graph/g006_preflight.json"
CLAIM = BASE / "graph/g006_launch_claim.json"
MANIFEST = BASE / "graph/g006_launch_manifest.json"
JOURNAL = "g004_paired_structural_journal.jsonl"
STRUCTURAL = "g004_postrun_normalized_structural.json"
PROVENANCE = "g005_provenance_sidecar.jsonl"
TOOL_CLASS = "g006_tool_class_sidecar.jsonl"


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
    if (
        launch.get("pid") != PID
        or binding.get("candidate_tree_sha256") != TREE_SHA
        or pre.get("binding") != binding
        or preflight.get("binding") != binding
        or claim.get("binding") != binding
        or preflight.get("status") != "passed"
        or preflight.get("model_probe", {}).get("http_status") != 200
        or claim.get("pre_execution_sha256") != digest(PRE_EXEC)
        or claim.get("preflight_sha256") != digest(PREFLIGHT)
        or launch.get("preflight_sha256") != digest(PREFLIGHT)
        or "--run-id" not in launch.get("command", [])
        or launch["command"][launch["command"].index("--run-id") + 1] != RUN_ID
    ):
        raise RuntimeError("G6 launch identity differs")
    cmdline = Path(f"/proc/{PID}/cmdline")
    command = (
        cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if cmdline.is_file() else ""
    )
    running = bool(command)
    if running and (
        RUN_ID not in command
        or str(G6 / "source/experiments/run_multi_query_baseline.py") not in command
    ):
        raise RuntimeError("G6 PID no longer belongs to the bound runner")

    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    strict_unknown = 0
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError("G6 result status differs")
        statuses[status] += 1
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            strict_unknown += row.get("strict_match_passed") is None
    if len(rows) > 56:
        raise RuntimeError("G6 progress exceeds frozen 56")
    run_dirs = list((RUN / "runs").glob("*")) if (RUN / "runs").is_dir() else []
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_unknown_completed": strict_unknown,
        "journal_files": sum((path / JOURNAL).is_file() for path in run_dirs),
        "normalized_sidecar_files": sum((path / STRUCTURAL).is_file() for path in run_dirs),
        "provenance_files": sum((path / PROVENANCE).is_file() for path in run_dirs),
        "tool_class_files": sum((path / TOOL_CLASS).is_file() for path in run_dirs),
        "summary_present": summary_path.is_file(), "free_bytes": free,
        "free_gib": round(free / 1024**3, 3), "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
