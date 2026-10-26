#!/usr/bin/env python3
"""Read-only, answer-blind status snapshot for the bound G5 run."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G5 = BASE / "g005_revision001"
RUN_ID = "baseline_g005_provenance_nohint_56_v1"
RUN = G5 / "evaluation" / RUN_ID
PID = 1266
TREE_SHA = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
PRE_EXEC = BASE / "graph/g005_pre_execution.json"
PREFLIGHT = BASE / "graph/g005_preflight.json"
CLAIM = BASE / "graph/g005_launch_claim.json"
MANIFEST = BASE / "graph/g005_launch_manifest.json"
JOURNAL = "g004_paired_structural_journal.jsonl"
SIDECAR = "g004_postrun_normalized_structural.json"
PROVENANCE = "g005_provenance_sidecar.jsonl"


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
        raise RuntimeError("G5 launch identity differs")
    cmdline_path = Path(f"/proc/{PID}/cmdline")
    command = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace") if cmdline_path.is_file() else ""
    running = bool(command)
    if running and (RUN_ID not in command or str(G5 / "source/experiments/run_multi_query_baseline.py") not in command):
        raise RuntimeError("G5 PID no longer belongs to the bound runner")

    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    strict_unknown = 0
    reserve_records = 0
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError("G5 result status differs")
        statuses[status] += 1
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            strict_unknown += row.get("strict_match_passed") is None
            reserve_records += isinstance(row.get("deadline_reserve_trigger"), dict)
    if len(rows) > 56:
        raise RuntimeError("G5 progress exceeds frozen 56")
    run_dirs = list((RUN / "runs").glob("*")) if (RUN / "runs").is_dir() else []
    journal_files = sum((path / JOURNAL).is_file() for path in run_dirs)
    structural_files = sum((path / SIDECAR).is_file() for path in run_dirs)
    provenance_files = sum((path / PROVENANCE).is_file() for path in run_dirs)
    lifecycle_dir = RUN / "lifecycle"
    lifecycle_records = sum(1 for _ in lifecycle_dir.glob("q[0-9][0-9].json")) if lifecycle_dir.is_dir() else 0
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_unknown_completed": strict_unknown,
        "reserve_records": reserve_records, "lifecycle_records": lifecycle_records,
        "journal_files": journal_files, "normalized_sidecar_files": structural_files,
        "provenance_files": provenance_files,
        "summary_present": summary_path.is_file(), "free_bytes": free,
        "free_gib": round(free / 1024**3, 3), "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
