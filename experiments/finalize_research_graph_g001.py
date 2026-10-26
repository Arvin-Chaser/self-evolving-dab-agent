#!/usr/bin/env python3
"""Append G1 Evidence after natural termination using answer-blind run metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
RUN_ID = "baseline_g001_deadline_reserve_nohint_56_v1"
G1 = BASE / "g001_revision001"
RUN = G1 / "evaluation" / RUN_ID
GRAPH = BASE / "graph"
EXPECTED_PID = 257107
EXPECTED_BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
EXPECTED_TREE_SHA = "8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d"


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


def main(*, check_only: bool = False) -> None:
    if Path(f"/proc/{EXPECTED_PID}").exists():
        raise RuntimeError("G1 runner still exists")
    pre_path = GRAPH / "g001_pre_execution.json"
    claim_path = GRAPH / "g001_launch_claim.json"
    launch_path = GRAPH / "g001_launch_manifest.json"
    summary_path = RUN / "multi_query_summary.json"
    progress_path = RUN / "multi_query_progress.json"
    batch_path = G1 / "source/dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
    pre, claim, launch, summary, progress, batch = map(
        read, (pre_path, claim_path, launch_path, summary_path, progress_path, batch_path)
    )
    args = launch["command"]
    if (launch["pid"] != EXPECTED_PID or option(args, "--run-id") != RUN_ID
            or claim["binding"] != launch["binding"] or pre["binding"] != launch["binding"]
            or claim["pre_execution_sha256"] != sha(pre_path)
            or launch["pre_execution_sha256"] != sha(pre_path)):
        raise RuntimeError("G1 launch identity or frozen pre-execution binding differs")
    if any(flag in args for flag in ("--use-hints", "--use-hint-only-db-description")):
        raise RuntimeError("G1 run command is not no-hint")
    if "--skip-observer" not in args or float(option(args, "--query-timeout-sec")) != 1200:
        raise RuntimeError("G1 observer/timeout protocol differs")
    binding = pre["binding"]
    if (binding["query_count"] != 56 or binding["candidate_tree_sha256"] != EXPECTED_TREE_SHA
            or binding["batch_sha256"] != EXPECTED_BATCH_SHA or sha(batch_path) != EXPECTED_BATCH_SHA
            or binding["timeout_scoring"] != "timeout_failure_in_fixed_56_denominator"):
        raise RuntimeError("G1 candidate/task/timeout binding differs")
    expected_ids = batch["query_ids"]
    rows = summary["per_query_feedback"]
    progress_rows = progress["queries"]
    if (summary["query_count"] != 56 or len(expected_ids) != 56 or len(set(expected_ids)) != 56
            or len(rows) != 56 or [row["query_id"] for row in rows] != expected_ids
            or [row["query_id"] for row in progress_rows] != expected_ids):
        raise RuntimeError("G1 results do not cover the exact frozen batch")
    context = summary["execution_context"]
    if (float(context["query_timeout_sec"]) != 1200 or context["db_description_mode"] != "base"
            or context["runner_sha256"] != binding["agent_sha256"]
            or context["batch_runner_sha256"] != binding["runner_sha256"]):
        raise RuntimeError("Executed G1 source or no-hint protocol differs")
    statuses = Counter(row.get("status") for row in rows)
    if set(statuses) - {"completed", "timeout", "failed"}:
        raise RuntimeError(f"Unexpected G1 terminal status: {sorted(statuses)}")
    if statuses["completed"] + statuses["timeout"] + statuses["failed"] != 56:
        raise RuntimeError("G1 terminal count differs from fixed 56")
    exit_key_by_stage = {"run": "run_exit_code", "analyze": "analyze_exit_code",
                         "observer": "observer_exit_code"}
    for row in rows:
        if row["status"] == "timeout":
            exit_key = exit_key_by_stage.get(row.get("query_timeout_stage"))
            if exit_key is None or row.get(exit_key) != 124:
                raise RuntimeError("G1 timeout row lacks stage-specific runner exit 124")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_known = sum(isinstance(row.get("strict_match_passed"), bool) for row in rows)
    unknown_completed = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    if summary["strict_pass_count"] != strict_pass or summary["strict_evaluated_count"] != strict_known:
        raise RuntimeError("G1 summary strict counts differ from per-task verdicts")

    traces = []
    reserve_counts = Counter()
    for index, row in enumerate(rows):
        run_dir = Path(row["run_dir"])
        if not run_dir.is_relative_to(RUN):
            raise RuntimeError("G1 trace reference escapes the formal run")
        trace = run_dir / "full_execution_trace.jsonl"
        trigger = run_dir / "deadline_reserve_trigger.json"
        record = row.get("deadline_reserve_trigger")
        if trigger.is_file():
            if not isinstance(record, dict) or read(trigger) != record or record.get("answer_blind") is not True:
                raise RuntimeError("G1 reserve record differs between run and summary")
            reserve_counts["bound" if record.get("bound") is True else "unbound"] += 1
        elif record is not None:
            raise RuntimeError("G1 summary references missing reserve record")
        else:
            reserve_counts["record_missing"] += 1
            if row["status"] == "completed":
                raise RuntimeError("Normally completed G1 task lacks reserve instrumentation")
        traces.append({
            "batch_index": index,
            "trace_relative_path": str(trace.relative_to(RUN)) if trace.is_file() else None,
            "trace_sha256": sha(trace) if trace.is_file() else None,
            "reserve_record_relative_path": str(trigger.relative_to(RUN)) if trigger.is_file() else None,
            "reserve_record_sha256": sha(trigger) if trigger.is_file() else None,
            "terminal_status": row["status"],
        })
    trace_path = GRAPH / "g001_trace_manifest.json"
    evidence_path = GRAPH / "g001_evidence.json"
    graph_path = GRAPH / "g001_graph.json"
    if any(path.exists() for path in (trace_path, evidence_path, graph_path)):
        raise RuntimeError("G1 Evidence already exists; refusing overwrite")
    if check_only:
        print(json.dumps({
            "status": "terminal_audit_passed_no_writes", "ended": len(rows),
            "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
            "other_failures": statuses["failed"], "strict_pass": strict_pass,
            "strict_denominator": 56, "strict_unknown_completed": unknown_completed,
            "reserve_trigger_counts": dict(reserve_counts),
            "trace_files": sum(entry["trace_sha256"] is not None for entry in traces),
            "pre_execution_sha256": sha(pre_path), "summary_sha256": sha(summary_path),
            "progress_sha256": sha(progress_path),
        }, sort_keys=True))
        return
    write_new(trace_path, {
        "schema_version": "dab_research_graph_trace_manifest_v1",
        "generation": 1, "run_id": RUN_ID,
        "summary_sha256": sha(summary_path), "entries": traces,
    })
    evidence = {
        "schema_version": "dab_research_graph_evidence_v1",
        "generation": 1,
        "node": {
            "id": "evidence:g001", "kind": "evidence",
            "statement": "G1 deadline-reserve result on the unchanged no-hint frozen 56; 1200-second timeouts count as failures.",
            "frozen_task_count": 56, "ended_count": 56,
            "completed_count": statuses["completed"],
            "timeout_failure_count": statuses["timeout"],
            "other_terminal_failure_count": statuses["failed"],
            "strict_pass_count": strict_pass,
            "strict_pass_rate_all": round(strict_pass / 56, 6),
            "strict_verdict_missing_completed_count": unknown_completed,
            "strict_verdict_known_count": strict_known,
            "reserve_trigger_counts": dict(reserve_counts),
            "final_answer_nonempty_count": summary["final_answer_nonempty_count"],
            "query_wall_timeout_sec": 1200,
            "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
            "limits": [
                "A single unpaired run cannot establish a causal benefit over G0.",
                "A reserve trigger is a mechanism observation, not evidence of a correct answer.",
                "Missing strict verdicts remain unknown without shrinking the fixed denominator.",
            ],
            "artifact_refs": {
                "pre_execution_path": str(pre_path), "pre_execution_sha256": sha(pre_path),
                "launch_manifest_path": str(launch_path), "launch_manifest_sha256": sha(launch_path),
                "summary_path": str(summary_path), "summary_sha256": sha(summary_path),
                "progress_path": str(progress_path), "progress_sha256": sha(progress_path),
                "trace_manifest_path": str(trace_path), "trace_manifest_sha256": sha(trace_path),
            },
        },
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_new(evidence_path, evidence)
    graph = {
        "schema_version": "dab_research_graph_generation_v1", "generation": 1,
        "status": "four_nodes_complete", "pre_execution_sha256": sha(pre_path),
        "evidence_sha256": sha(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], evidence["node"]],
        "edges": [*pre["edges"],
                  {"source": "evidence:g001", "target": "experiment:g001", "relation": "observes"}],
    }
    write_new(graph_path, graph)
    print(json.dumps({
        "status": graph["status"], "graph_sha256": sha(graph_path),
        "evidence_sha256": sha(evidence_path), "trace_manifest_sha256": sha(trace_path),
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_pass,
        "strict_denominator": 56, "strict_unknown_completed": unknown_completed,
        "reserve_trigger_counts": dict(reserve_counts),
        "trace_files": sum(entry["trace_sha256"] is not None for entry in traces),
    }, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    main(check_only=parser.parse_args().check_only)
