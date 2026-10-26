#!/usr/bin/env python3
"""Read-only, answer-blind status snapshot for the uniquely bound G3 run."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G3 = BASE / "g003_revision001"
RUN_ID = "baseline_g003_proposed_calls_nohint_56_v1"
RUN = G3 / "evaluation" / RUN_ID
PID = 436296
TREE_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    launch = read(BASE / "graph/g003_launch_manifest.json")
    claim = read(BASE / "graph/g003_launch_claim.json")
    if (launch.get("pid") != PID or launch["binding"]["candidate_tree_sha256"] != TREE_SHA
            or claim["binding"] != launch["binding"] or
            "--run-id" not in launch["command"] or
            launch["command"][launch["command"].index("--run-id") + 1] != RUN_ID):
        raise RuntimeError("G3 launch identity differs")
    cmdline_path = Path(f"/proc/{PID}/cmdline")
    running = cmdline_path.is_file()
    if running:
        command = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if RUN_ID not in command or str(G3 / "source/experiments/run_multi_query_baseline.py") not in command:
            raise RuntimeError("G3 PID no longer belongs to the bound runner")
    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    unknown_completed = 0
    reserve_records = 0
    run_exit_nonzero = 0
    analysis_exit_nonzero = 0
    answer_nonempty = 0
    llm_calls = 0
    tool_calls = 0
    run_error_count = 0
    attribute_error_count = 0
    tool_log_path_error_count = 0
    llm_response_failures = 0
    llm_error_types: dict[str, int] = {}
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError(f"Unexpected G3 progress status: {status}")
        statuses[status] += 1
        run_exit_nonzero += row.get("run_exit_code") not in (0, None)
        analysis_exit_nonzero += row.get("analyze_exit_code") not in (0, None)
        answer_nonempty += row.get("final_answer_nonempty") is True
        llm_calls += row.get("llm_call_count") or 0
        tool_calls += row.get("tool_call_count") or 0
        error = row.get("run_error") or ""
        run_error_count += bool(error)
        attribute_error_count += "AttributeError" in error
        tool_log_path_error_count += "tool_log_path" in error
        reason = row.get("terminate_reason") or ""
        if reason.startswith("llm_response_failed"):
            llm_response_failures += 1
            match = re.match(r"llm_response_failed attempt \d+/\d+ \(([A-Za-z_]+)\):", reason)
            error_type = match.group(1) if match else "unknown"
            llm_error_types[error_type] = llm_error_types.get(error_type, 0) + 1
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            unknown_completed += row.get("strict_match_passed") is None
            reserve_records += isinstance(row.get("deadline_reserve_trigger"), dict)
            if not isinstance(row.get("deadline_reserve_trigger"), dict):
                raise RuntimeError("Completed G3 task lacks the reserve trigger record")
    if len(rows) > 56:
        raise RuntimeError("G3 progress exceeds the frozen 56")
    lifecycle_dir = RUN / "lifecycle"
    lifecycle_records = 0
    for path in lifecycle_dir.glob("q[0-9][0-9].json") if lifecycle_dir.is_dir() else ():
        record = read(path)
        if record.get("schema_version") != "g002_lifecycle_stages_v1" or record.get("answer_blind") is not True:
            raise RuntimeError("G3 lifecycle record protocol differs")
        lifecycle_records += 1
    proposed_call_files = sum(1 for _ in RUN.rglob("g003_proposed_calls.jsonl")) if RUN.is_dir() else 0
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_rate_all_so_far": round(strict_true / 56, 6),
        "strict_unknown_completed": unknown_completed,
        "reserve_records": reserve_records, "lifecycle_records": lifecycle_records,
        "proposed_call_files": proposed_call_files,
        "run_exit_nonzero": run_exit_nonzero,
        "analysis_exit_nonzero": analysis_exit_nonzero,
        "answer_nonempty": answer_nonempty,
        "llm_calls": llm_calls, "tool_calls": tool_calls,
        "run_error_count": run_error_count,
        "attribute_error_count": attribute_error_count,
        "tool_log_path_error_count": tool_log_path_error_count,
        "llm_response_failures": llm_response_failures,
        "llm_error_types": llm_error_types,
        "summary_present": summary_path.is_file(),
        "free_bytes": free, "free_gib": round(free / 1024**3, 3),
        "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
