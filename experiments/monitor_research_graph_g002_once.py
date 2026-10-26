#!/usr/bin/env python3
"""Read-only, answer-blind status snapshot for the uniquely bound G2 run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G2 = BASE / "g002_revision001"
RUN_ID = "baseline_g002_lifecycle_nohint_56_v1"
RUN = G2 / "evaluation" / RUN_ID
PID = 389396
TREE_SHA = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    launch = read(BASE / "graph/g002_launch_manifest.json")
    claim = read(BASE / "graph/g002_launch_claim.json")
    if (launch.get("pid") != PID or launch["binding"]["candidate_tree_sha256"] != TREE_SHA
            or claim["binding"] != launch["binding"] or
            "--run-id" not in launch["command"] or
            launch["command"][launch["command"].index("--run-id") + 1] != RUN_ID):
        raise RuntimeError("G2 launch identity differs")
    cmdline_path = Path(f"/proc/{PID}/cmdline")
    running = cmdline_path.is_file()
    if running:
        command = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if RUN_ID not in command or str(G2 / "source/experiments/run_multi_query_baseline.py") not in command:
            raise RuntimeError("G2 PID no longer belongs to the bound runner")
    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    unknown_completed = 0
    trigger_bound = 0
    reserve_records = 0
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError(f"Unexpected G2 progress status: {status}")
        statuses[status] += 1
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            unknown_completed += row.get("strict_match_passed") is None
        record = row.get("deadline_reserve_trigger")
        if isinstance(record, dict):
            reserve_records += 1
            trigger_bound += record.get("bound") is True
        elif status == "completed":
            raise RuntimeError("Completed G2 task lacks the reserve trigger record")
    if len(rows) > 56:
        raise RuntimeError("G2 progress exceeds the frozen 56")
    lifecycle_dir = RUN / "lifecycle"
    lifecycle_records = 0
    for path in lifecycle_dir.glob("q[0-9][0-9].json") if lifecycle_dir.is_dir() else ():
        record = read(path)
        if record.get("schema_version") != "g002_lifecycle_stages_v1" or record.get("answer_blind") is not True:
            raise RuntimeError("G2 lifecycle record protocol differs")
        lifecycle_records += 1
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_rate_all_so_far": round(strict_true / 56, 6),
        "strict_unknown_completed": unknown_completed,
        "reserve_trigger_bound": trigger_bound, "reserve_records": reserve_records,
        "lifecycle_records": lifecycle_records, "summary_present": summary_path.is_file(),
        "free_bytes": free, "free_gib": round(free / 1024**3, 3),
        "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
