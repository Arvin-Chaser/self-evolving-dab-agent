#!/usr/bin/env python3
"""Read-only, answer-blind terminal audit for the bound G4 run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G4 = BASE / "g004_revision001"
RUN_ID = "baseline_g004_paired_journal_nohint_56_v1"
RUN = G4 / "evaluation" / RUN_ID
GRAPH = BASE / "graph"
PID = 50136
TREE_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
JOURNAL = "g004_paired_structural_journal.jsonl"
SIDECAR = "g004_postrun_normalized_structural.json"
ALLOWED_JOURNAL_FIELDS = {
    "pre_exec": {"schema_version", "event", "anonymous_task_index", "step_ordinal", "signal_category"},
    "post_exec": {"schema_version", "event", "anonymous_task_index", "step_ordinal", "completed"},
    "task_summary": {
        "schema_version", "event", "anonymous_task_index", "pre_exec_count", "post_exec_count",
        "completed_count", "in_flight_count", "repeat_count", "nonrepeat_count", "unknown_count",
    },
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def main() -> None:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G4 runner still active")
    pre = read(GRAPH / "g004_pre_execution.json")
    preflight = read(GRAPH / "g004_preflight.json")
    claim = read(GRAPH / "g004_launch_claim.json")
    launch = read(GRAPH / "g004_launch_manifest.json")
    binding = pre["binding"]
    require(
        binding["candidate_tree_sha256"] == TREE_SHA
        and binding["query_count"] == 56
        and binding["query_timeout_sec"] == 1200
        and binding["description_mode"] == "full_db_description_no_hints"
        and preflight["binding"] == claim["binding"] == launch["binding"] == binding
        and preflight["status"] == "passed"
        and claim["pre_execution_sha256"] == digest(GRAPH / "g004_pre_execution.json")
        and claim["preflight_sha256"] == digest(GRAPH / "g004_preflight.json")
        and launch["pid"] == PID,
        "G4 frozen binding, protocol, or launch identity differs",
    )
    source = G4 / "source"
    module_path = source / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g4_manifest", module_path)
    require(spec is not None and spec.loader is not None, "G4 source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = module.source_manifest_hash(sorted(module.source_tree_manifest(source), key=lambda row: row["path"].lower()))
    require(tree == TREE_SHA, "G4 source tree changed during evaluation")

    summary = read(RUN / "multi_query_summary.json")
    progress = read(RUN / "multi_query_progress.json")
    rows = summary.get("per_query_feedback", [])
    progress_rows = progress.get("queries", [])
    context = summary.get("execution_context", {})
    require(
        summary.get("query_count") == 56 and len(rows) == len(progress_rows) == 56
        and context.get("db_description_mode") == "base"
        and context.get("query_timeout_sec") == 1200,
        "G4 terminal summary or fixed protocol differs",
    )
    require(
        all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
            for a, b in zip(rows, progress_rows)),
        "G4 summary and progress result partitions differ",
    )
    statuses = Counter(row.get("status") for row in rows)
    require(set(statuses) <= {"completed", "timeout", "failed"}, "G4 result status differs")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(
        statuses["completed"] + statuses["timeout"] + statuses["failed"] == 56
        and known_fail + strict_pass + strict_unknown == statuses["completed"]
        and summary.get("strict_pass_count") == strict_pass,
        "G4 strict or terminal partition differs",
    )
    run_root = RUN / "runs"
    run_ids = [row.get("run_id") for row in rows]
    require(len(set(run_ids)) == 56, "G4 run ids are not unique")
    journal_files = structural_files = journal_events = journal_partial = sidecar_violations = 0
    timeout_journal_files = completed_structural_files = 0
    for index, row in enumerate(rows, start=1):
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "G4 run directory binding is unsafe")
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(), "G4 result directory missing")
        journal = run_dir / JOURNAL
        sidecar = run_dir / SIDECAR
        if journal.is_file():
            journal_files += 1
            timeout_journal_files += row["status"] == "timeout"
            for line in journal.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    journal_partial += 1
                    continue
                require(isinstance(event, dict) and event.get("event") in ALLOWED_JOURNAL_FIELDS,
                        "G4 journal event schema differs")
                require(set(event) == ALLOWED_JOURNAL_FIELDS[event["event"]], "G4 journal contains forbidden fields")
                require(event.get("anonymous_task_index") == index, "G4 anonymous index binding differs")
                journal_events += 1
        if sidecar.is_file():
            structural_files += 1
            completed_structural_files += row["status"] == "completed"
            structural = read(sidecar)
            if (set(structural) != {"schema_version", "steps", "completeness_metadata"}
                    or any(set(step) != {"ordinal", "signal_category"} for step in structural.get("steps", []))):
                sidecar_violations += 1
    require(journal_files == 56 and completed_structural_files == statuses["completed"] and sidecar_violations == 0,
            "G4 structural source coverage or allowlist differs")
    require(statuses["failed"] == 0 and strict_pass > 0, "G4 infrastructure validity needs review")
    print(json.dumps({
        "status": "valid_terminal_run_pending_evidence",
        "ended": 56, "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_pass,
        "strict_denominator": 56, "strict_unknown_completed": strict_unknown,
        "known_strict_fail": known_fail, "journal_files": journal_files,
        "journal_events": journal_events, "journal_partial_lines": journal_partial,
        "timeout_journal_files": timeout_journal_files,
        "structural_files": structural_files, "completed_structural_files": completed_structural_files,
        "sidecar_schema_violations": sidecar_violations,
        "summary_sha256": digest(RUN / "multi_query_summary.json"),
        "progress_sha256": digest(RUN / "multi_query_progress.json"),
        "pre_execution_sha256": digest(GRAPH / "g004_pre_execution.json"),
        "launch_manifest_sha256": digest(GRAPH / "g004_launch_manifest.json"),
        "extractor_sha256": digest(source / "experiments/g004_evidence_extractor.py"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
