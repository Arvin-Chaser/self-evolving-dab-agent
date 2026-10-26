#!/usr/bin/env python3
"""Audit G2 without answers, then append Evidence and its four-node Graph."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G2 = BASE / "g002_revision001"
GRAPH = BASE / "graph"
RUN_ID = "baseline_g002_lifecycle_nohint_56_v1"
RUN = G2 / "evaluation" / RUN_ID
PID = 389396
TREE_SHA = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"
BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
ALLOWED_STAGES = {
    "task_claimed", "child_spawn_requested", "child_entered", "inputs_validated",
    "dependencies_ready", "agent_constructed", "agent_run_started",
    "first_llm_call_entered", "first_llm_call_returned", "agent_run_ended",
    "startup_failed", "agent_failed", "normalized", "child_process_exited",
    "wall_timeout", "task_summary_written",
}
STAGE_KEYS = {"schema_version", "stages", "last_stage", "last_progress_stage",
              "failure_origin_stage", "answer_blind"}


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


def main(*, check_only: bool) -> None:
    if Path(f"/proc/{PID}").exists():
        raise RuntimeError("G2 runner still exists")
    pre_path = GRAPH / "g002_pre_execution.json"
    claim_path = GRAPH / "g002_launch_claim.json"
    launch_path = GRAPH / "g002_launch_manifest.json"
    summary_path = RUN / "multi_query_summary.json"
    progress_path = RUN / "multi_query_progress.json"
    batch_path = G2 / "source/dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
    pre, claim, launch, summary, progress, batch = map(
        read, (pre_path, claim_path, launch_path, summary_path, progress_path, batch_path)
    )
    args = launch["command"]
    if (launch["pid"] != PID or option(args, "--run-id") != RUN_ID or
            claim["binding"] != launch["binding"] or pre["binding"] != launch["binding"] or
            claim["pre_execution_sha256"] != sha(pre_path) or
            launch["pre_execution_sha256"] != sha(pre_path)):
        raise RuntimeError("G2 launch identity or pre-execution binding differs")
    if any(flag in args for flag in ("--use-hints", "--use-hint-only-db-description")):
        raise RuntimeError("G2 run command is not no-hint")
    if ("--skip-observer" not in args or float(option(args, "--query-timeout-sec")) != 1200 or
            option(args, "--source-root") != str(G2 / "source")):
        raise RuntimeError("G2 observer, timeout, or source protocol differs")
    binding = pre["binding"]
    if (binding["query_count"] != 56 or binding["candidate_tree_sha256"] != TREE_SHA or
            binding["batch_sha256"] != BATCH_SHA or sha(batch_path) != BATCH_SHA or
            binding["timeout_scoring"] != "timeout_failure_in_fixed_56_denominator"):
        raise RuntimeError("G2 candidate, task, or timeout binding differs")
    source = G2 / "source"
    spec = importlib.util.spec_from_file_location("g2_manifest", source / "experiments/intent_candidate_workspace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = sorted(module.source_tree_manifest(source), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(manifest) != TREE_SHA:
        raise RuntimeError("G2 source tree changed during evaluation")
    expected_ids = batch["query_ids"]
    rows = summary["per_query_feedback"]
    progress_rows = progress["queries"]
    if (summary["query_count"] != 56 or len(expected_ids) != 56 or len(set(expected_ids)) != 56 or
            len(rows) != 56 or [row["query_id"] for row in rows] != expected_ids or
            [row["query_id"] for row in progress_rows] != expected_ids):
        raise RuntimeError("G2 results do not cover the exact frozen batch")
    context = summary["execution_context"]
    if (float(context["query_timeout_sec"]) != 1200 or context["db_description_mode"] != "base" or
            context["runner_sha256"] != binding["agent_sha256"] or
            context["batch_runner_sha256"] != binding["runner_sha256"]):
        raise RuntimeError("Executed G2 source or no-hint protocol differs")
    statuses = Counter(row.get("status") for row in rows)
    if set(statuses) - {"completed", "timeout", "failed"} or sum(statuses.values()) != 56:
        raise RuntimeError("G2 terminal partition differs from fixed 56")
    exit_key_by_stage = {"run": "run_exit_code", "analyze": "analyze_exit_code",
                         "observer": "observer_exit_code"}
    for row in rows:
        if row["status"] == "timeout":
            exit_key = exit_key_by_stage.get(row.get("query_timeout_stage"))
            if exit_key is None or row.get(exit_key) != 124:
                raise RuntimeError("G2 timeout lacks stage-specific runner exit 124")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_known = sum(isinstance(row.get("strict_match_passed"), bool) for row in rows)
    unknown_completed = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    if summary["strict_pass_count"] != strict_pass or summary["strict_evaluated_count"] != strict_known:
        raise RuntimeError("G2 strict summary differs from task verdicts")

    artifacts = []
    reserve_counts = Counter()
    stage_counts = Counter()
    last_progress_by_status = Counter()
    for index, row in enumerate(rows):
        run_dir = Path(row["run_dir"])
        if not run_dir.is_relative_to(RUN):
            raise RuntimeError("G2 trace reference escapes the formal run")
        trace = run_dir / "full_execution_trace.jsonl"
        trigger = run_dir / "deadline_reserve_trigger.json"
        lifecycle = RUN / "lifecycle" / f"q{index + 1:02d}.json"
        record = row.get("deadline_reserve_trigger")
        if trigger.is_file():
            if not isinstance(record, dict) or read(trigger) != record or record.get("answer_blind") is not True:
                raise RuntimeError("G2 reserve record differs between run and summary")
            reserve_counts["bound" if record.get("bound") is True else "unbound"] += 1
        elif record is not None or row["status"] == "completed":
            raise RuntimeError("G2 normally completed task lacks valid reserve record")
        else:
            reserve_counts["record_missing"] += 1
        if not lifecycle.is_file():
            raise RuntimeError("G2 task lacks lifecycle record")
        stages = read(lifecycle)
        values = stages.get("stages")
        if (set(stages) != STAGE_KEYS or stages.get("schema_version") != "g002_lifecycle_stages_v1" or
                stages.get("answer_blind") is not True or not isinstance(values, list) or
                not values or len(values) != len(set(values)) or set(values) - ALLOWED_STAGES or
                values[0] != "task_claimed" or values[-1] != "task_summary_written" or
                stages.get("last_stage") != values[-1]):
            raise RuntimeError("G2 lifecycle record protocol differs")
        if "first_llm_call_returned" in values and "first_llm_call_entered" not in values:
            raise RuntimeError("G2 lifecycle first-call order differs")
        for stage in values:
            stage_counts[stage] += 1
        last_progress_by_status[f"{row['status']}:{stages.get('last_progress_stage')}"] += 1
        artifacts.append({
            "batch_index": index, "terminal_status": row["status"],
            "trace_sha256": sha(trace) if trace.is_file() else None,
            "reserve_record_sha256": sha(trigger) if trigger.is_file() else None,
            "lifecycle_record_sha256": sha(lifecycle),
            "last_progress_stage": stages.get("last_progress_stage"),
            "failure_origin_stage": stages.get("failure_origin_stage"),
        })
    paths = [GRAPH / name for name in ("g002_trace_manifest.json", "g002_evidence.json", "g002_graph.json")]
    if any(path.exists() for path in paths):
        raise RuntimeError("G2 Evidence already exists; refusing overwrite")
    facts = {
        "ended": 56, "completed": statuses["completed"],
        "timeout_failures": statuses["timeout"], "other_failures": statuses["failed"],
        "strict_pass": strict_pass, "strict_denominator": 56,
        "strict_unknown_completed": unknown_completed,
        "reserve_trigger_counts": dict(reserve_counts),
        "lifecycle_record_count": len(artifacts),
        "lifecycle_stage_counts": dict(stage_counts),
        "last_progress_by_status": dict(last_progress_by_status),
        "trace_files": sum(item["trace_sha256"] is not None for item in artifacts),
        "pre_execution_sha256": sha(pre_path), "summary_sha256": sha(summary_path),
        "progress_sha256": sha(progress_path),
    }
    if check_only:
        print(json.dumps({"status": "terminal_audit_passed_no_writes", **facts}, sort_keys=True))
        return
    trace_path, evidence_path, graph_path = paths
    write_new(trace_path, {
        "schema_version": "dab_research_graph_trace_manifest_v2", "generation": 2,
        "run_id": RUN_ID, "summary_sha256": sha(summary_path), "entries": artifacts,
    })
    evidence = {
        "schema_version": "dab_research_graph_evidence_v1", "generation": 2,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "node": {
            "id": "evidence:g002", "kind": "evidence",
            "statement": "G2 lifecycle-stage instrumentation on the frozen no-hint 56; 1200-second timeouts count as failures.",
            "frozen_task_count": 56, "ended_count": 56,
            "completed_count": statuses["completed"],
            "timeout_failure_count": statuses["timeout"],
            "other_terminal_failure_count": statuses["failed"],
            "strict_pass_count": strict_pass,
            "strict_pass_rate_all": round(strict_pass / 56, 6),
            "strict_verdict_missing_completed_count": unknown_completed,
            "strict_verdict_known_count": strict_known,
            "reserve_trigger_counts": dict(reserve_counts),
            "lifecycle_record_count": len(artifacts),
            "lifecycle_stage_counts": dict(stage_counts),
            "last_progress_by_status": dict(last_progress_by_status),
            "final_answer_nonempty_count": summary["final_answer_nonempty_count"],
            "query_wall_timeout_sec": 1200,
            "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
            "limits": [
                "A single unpaired run cannot establish a causal benefit over G1.",
                "No pre-event terminal failure means the localization hypothesis is untested in this run.",
                "Lifecycle stage coverage does not prove instrumentation inertness or answer quality.",
                "Missing strict verdicts remain unknown without shrinking the fixed denominator.",
            ],
            "artifact_refs": {
                "pre_execution_sha256": sha(pre_path),
                "launch_manifest_sha256": sha(launch_path),
                "summary_sha256": sha(summary_path),
                "progress_sha256": sha(progress_path),
                "trace_manifest_sha256": sha(trace_path),
            },
        },
    }
    write_new(evidence_path, evidence)
    graph = {
        "schema_version": "dab_research_graph_generation_v1", "generation": 2,
        "status": "four_nodes_complete", "pre_execution_sha256": sha(pre_path),
        "evidence_sha256": sha(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], evidence["node"]],
        "edges": [*pre["edges"],
                  {"source": "evidence:g002", "target": "experiment:g002", "relation": "observes"}],
    }
    write_new(graph_path, graph)
    print(json.dumps({"status": graph["status"], "graph_sha256": sha(graph_path),
                      "evidence_sha256": sha(evidence_path),
                      "trace_manifest_sha256": sha(trace_path), **facts}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    main(check_only=parser.parse_args().check_only)
