#!/usr/bin/env python3
"""Read-only, answer-blind snapshot for the bound G3 attempt 2 run."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G3 = BASE / "g003_revision001"
RUN_ID = "baseline_g003_proposed_calls_nohint_56_v2"
RUN = G3 / "evaluation" / RUN_ID
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
PID = 6654
TREE_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    launch = read(BASE / "graph/g003_launch_manifest_attempt002.json")
    claim = read(BASE / "graph/g003_launch_claim_attempt002.json")
    preflight = read(BASE / "graph/g003_preflight_attempt002.json")
    if (launch.get("pid") != PID or launch.get("attempt") != 2 or
            launch["binding"]["candidate_tree_sha256"] != TREE_SHA or
            claim["binding"] != launch["binding"] or
            launch.get("preflight_sha256") != claim.get("preflight_sha256") or
            preflight.get("status") != "passed" or
            preflight.get("model_probe", {}).get("http_status") != 200 or
            "--run-id" not in launch["command"] or
            launch["command"][launch["command"].index("--run-id") + 1] != RUN_ID):
        raise RuntimeError("G3 attempt 2 launch identity differs")
    cmdline_path = Path(f"/proc/{PID}/cmdline")
    running = cmdline_path.is_file()
    if running:
        command = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if RUN_ID not in command or str(G3 / "source/experiments/run_multi_query_baseline.py") not in command:
            raise RuntimeError("G3 attempt 2 PID no longer belongs to the bound runner")
    progress_path = RUN / "multi_query_progress.json"
    summary_path = RUN / "multi_query_summary.json"
    rows = read(progress_path).get("queries", []) if progress_path.is_file() else []
    statuses = {"completed": 0, "timeout": 0, "failed": 0}
    strict_true = 0
    unknown_completed = 0
    answer_nonempty = 0
    llm_calls = 0
    tool_calls = 0
    run_exit_nonzero = 0
    analysis_exit_nonzero = 0
    llm_response_failures = 0
    llm_error_types: dict[str, int] = {}
    reserve_records = 0
    for row in rows:
        status = row.get("status")
        if status not in statuses:
            raise RuntimeError(f"Unexpected G3 attempt 2 status: {status}")
        statuses[status] += 1
        run_exit_nonzero += row.get("run_exit_code") not in (0, None)
        analysis_exit_nonzero += row.get("analyze_exit_code") not in (0, None)
        answer_nonempty += row.get("final_answer_nonempty") is True
        llm_calls += row.get("llm_call_count") or 0
        tool_calls += row.get("tool_call_count") or 0
        if status == "completed":
            strict_true += row.get("strict_match_passed") is True
            unknown_completed += row.get("strict_match_passed") is None
            reserve_records += isinstance(row.get("deadline_reserve_trigger"), dict)
            if not isinstance(row.get("deadline_reserve_trigger"), dict):
                raise RuntimeError("Completed G3 attempt 2 task lacks reserve record")
        reason = row.get("terminate_reason") or ""
        if reason.startswith("llm_response_failed"):
            llm_response_failures += 1
            match = re.match(r"llm_response_failed attempt \d+/\d+ \(([A-Za-z_]+)\):", reason)
            error_type = match.group(1) if match else "unknown"
            llm_error_types[error_type] = llm_error_types.get(error_type, 0) + 1
    if len(rows) > 56:
        raise RuntimeError("G3 attempt 2 progress exceeds frozen 56")
    lifecycle_dir = RUN / "lifecycle"
    lifecycle_records = sum(1 for _ in lifecycle_dir.glob("q[0-9][0-9].json")) if lifecycle_dir.is_dir() else 0
    sidecars = list(UPSTREAM.glob(
        f"query_*/query*/logs/data_agent/{RUN_ID}_q*/g003_proposed_calls.jsonl"))
    proposed_call_files = len(sidecars)
    proposed_call_records = 0
    proposed_call_categories = {"repeat": 0, "nonrepeat": 0, "unknown": 0}
    for path in sidecars:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            category = record.get("signal_category")
            if category not in proposed_call_categories:
                raise RuntimeError("G3 attempt 2 sidecar category differs")
            proposed_call_categories[category] += 1
            proposed_call_records += 1
    free = shutil.disk_usage(BASE).free
    print(json.dumps({
        "run_id": RUN_ID, "attempt": 2, "pid": PID, "runner_running": running,
        "ended": len(rows), "frozen_tasks": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_true,
        "strict_denominator": 56, "strict_rate_all_so_far": round(strict_true / 56, 6),
        "strict_unknown_completed": unknown_completed,
        "answer_nonempty": answer_nonempty, "llm_calls": llm_calls,
        "tool_calls": tool_calls, "llm_response_failures": llm_response_failures,
        "llm_error_types": llm_error_types,
        "run_exit_nonzero": run_exit_nonzero,
        "analysis_exit_nonzero": analysis_exit_nonzero,
        "reserve_records": reserve_records, "lifecycle_records": lifecycle_records,
        "proposed_call_files": proposed_call_files,
        "proposed_call_records": proposed_call_records,
        "proposed_call_categories": proposed_call_categories,
        "summary_present": summary_path.is_file(),
        "free_bytes": free, "free_gib": round(free / 1024**3, 3),
        "below_5_gib": free < 5 * 1024**3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
