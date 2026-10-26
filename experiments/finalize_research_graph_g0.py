#!/usr/bin/env python3
"""Append G0 evidence using only bound result metadata and artifact hashes."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
RUN_ID = "baseline_g000_nohint_56_v1"
RUN = BASE / "evaluation" / RUN_ID
GRAPH = BASE / "graph"
EXPECTED_PID = 174606
EXPECTED_BATCH_SHA256 = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
EXPECTED_SOURCE_SHA256 = "93e4d9ebf9d8e8b0f4d6b8b356926b7ab7a66a125dc9652d30aac86e930d4eb9"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def option(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def main() -> None:
    if Path(f"/proc/{EXPECTED_PID}").exists():
        raise RuntimeError("G0 runner is still present")
    pre_path = GRAPH / "g000_pre_execution.json"
    launch_path = GRAPH / "g000_launch_manifest.json"
    summary_path = RUN / "multi_query_summary.json"
    progress_path = RUN / "multi_query_progress.json"
    batch_path = BASE / "source/dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
    pre, launch, summary, progress, batch = map(
        read, (pre_path, launch_path, summary_path, progress_path, batch_path)
    )
    args = launch["command"]
    if launch["pid"] != EXPECTED_PID or option(args, "--run-id") != RUN_ID:
        raise RuntimeError("G0 launch identity differs")
    if any(flag in args for flag in ("--use-hints", "--use-hint-only-db-description")):
        raise RuntimeError("G0 command is not no-hint")
    if "--skip-observer" not in args or float(option(args, "--query-timeout-sec")) != 1200:
        raise RuntimeError("G0 observer/timeout protocol differs")
    binding = pre["binding"]
    if (binding != launch["binding"] or binding["query_count"] != 56
            or binding["source_tree_sha256"] != EXPECTED_SOURCE_SHA256
            or binding["batch_sha256"] != EXPECTED_BATCH_SHA256
            or sha(batch_path) != EXPECTED_BATCH_SHA256):
        raise RuntimeError("Frozen G0 binding differs")
    expected_ids = batch["query_ids"]
    rows = summary["per_query_feedback"]
    progress_rows = progress["queries"]
    if (summary["query_count"] != 56 or len(expected_ids) != 56
            or len(set(expected_ids)) != 56 or len(rows) != 56
            or [row["query_id"] for row in rows] != expected_ids
            or [row["query_id"] for row in progress_rows] != expected_ids):
        raise RuntimeError("G0 results do not cover the exact frozen batch")
    context = summary["execution_context"]
    if (float(context["query_timeout_sec"]) != 1200
            or context["db_description_mode"] != "base"
            or context["runner_sha256"] != binding["agent_sha256"]
            or context["batch_runner_sha256"] != binding["runner_sha256"]):
        raise RuntimeError("Executed G0 protocol differs")
    statuses = Counter(row.get("status") for row in rows)
    if set(statuses) - {"completed", "timeout"}:
        raise RuntimeError("Unexpected G0 terminal status")
    timeout_rows = [row for row in rows if row["status"] == "timeout"]
    if any(row.get("run_exit_code") != 124 for row in timeout_rows):
        raise RuntimeError("Timeout row lacks runner timeout exit")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_known = sum(isinstance(row.get("strict_match_passed"), bool) for row in rows)
    unknown_completed = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    if (summary["strict_pass_count"] != strict_pass
            or summary["strict_evaluated_count"] != strict_known
            or statuses["completed"] + statuses["timeout"] != 56):
        raise RuntimeError("G0 result counts differ")

    traces = []
    for index, row in enumerate(rows):
        run_dir = Path(row["run_dir"])
        if not run_dir.is_relative_to(RUN):
            raise RuntimeError("Trace reference escapes the G0 run")
        trace = run_dir / "full_execution_trace.jsonl"
        traces.append({
            "batch_index": index,
            "trace_relative_path": str(trace.relative_to(RUN)) if trace.is_file() else None,
            "trace_sha256": sha(trace) if trace.is_file() else None,
            "terminal_status": row["status"],
        })
    trace_path = GRAPH / "g000_trace_manifest.json"
    evidence_path = GRAPH / "g000_evidence.json"
    graph_path = GRAPH / "g000_graph.json"
    if any(path.exists() for path in (trace_path, evidence_path, graph_path)):
        raise RuntimeError("G0 evidence already exists; refusing overwrite")
    write_new(trace_path, {
        "schema_version": "dab_research_graph_trace_manifest_v1",
        "generation": 0,
        "run_id": RUN_ID,
        "summary_sha256": sha(summary_path),
        "entries": traces,
    })
    evidence = {
        "schema_version": "dab_research_graph_evidence_v1",
        "generation": 0,
        "node": {
            "id": "evidence:g000",
            "kind": "evidence",
            "statement": "Frozen no-hint root baseline result; timeouts count as failures in the full-batch denominator.",
            "frozen_task_count": 56,
            "ended_count": 56,
            "completed_count": statuses["completed"],
            "timeout_failure_count": statuses["timeout"],
            "other_terminal_failure_count": 0,
            "strict_pass_count": strict_pass,
            "strict_pass_rate_all": round(strict_pass / 56, 6),
            "strict_verdict_missing_completed_count": unknown_completed,
            "strict_verdict_known_count": strict_known,
            "final_answer_nonempty_count": summary["final_answer_nonempty_count"],
            "query_wall_timeout_sec": 1200,
            "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
            "score_policy_clarified_during_run": True,
            "limits": [
                "G0 is a control rerun, not a blind discovery result.",
                "Missing strict verdicts remain unknown, but do not shrink the main denominator.",
                "Unpaired generation comparisons cannot establish causal improvement.",
            ],
            "artifact_refs": {
                "pre_execution_path": str(pre_path),
                "pre_execution_sha256": sha(pre_path),
                "launch_manifest_path": str(launch_path),
                "launch_manifest_sha256": sha(launch_path),
                "summary_path": str(summary_path),
                "summary_sha256": sha(summary_path),
                "progress_path": str(progress_path),
                "progress_sha256": sha(progress_path),
                "trace_manifest_path": str(trace_path),
                "trace_manifest_sha256": sha(trace_path),
            },
        },
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_new(evidence_path, evidence)
    graph = {
        "schema_version": "dab_research_graph_generation_v1",
        "generation": 0,
        "status": "four_nodes_complete",
        "pre_execution_sha256": sha(pre_path),
        "evidence_sha256": sha(evidence_path),
        "binding": binding,
        "nodes": [*pre["nodes"], evidence["node"]],
        "edges": [*pre["edges"], {
            "source": "evidence:g000", "target": "experiment:g000", "relation": "observes"
        }],
    }
    write_new(graph_path, graph)
    print(json.dumps({
        "status": graph["status"], "graph_sha256": sha(graph_path),
        "evidence_sha256": sha(evidence_path), "trace_manifest_sha256": sha(trace_path),
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "strict_pass": strict_pass, "strict_denominator": 56,
        "strict_unknown_completed": unknown_completed,
        "trace_files": sum(entry["trace_sha256"] is not None for entry in traces),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
