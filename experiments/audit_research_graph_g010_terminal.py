#!/usr/bin/env python3
"""Answer-blind terminal audit of the frozen G10 run; never scores recovery."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
SOURCE = BASE / "g010_revision001/source"
RUN_ID = "g010_verification_reconciliation_nohint_56_v1"
RUN = BASE / "g010_revision001/evaluation" / RUN_ID
PID = 225760
TREE_SHA = "80f002ac7a2d90b3cfed0fda7fec03c64c0a442c69a0ae27c7506852b32d36b9"
PARENT_GRAPH_SHA = "e49a7c765eef8aea4dd4bc295dfc907f7cf0fa743df41efff94fb4b9e31d0abd"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G10 runner still active")
    require(digest(GRAPH / "g009_graph.json") == PARENT_GRAPH_SHA, "parent Graph changed")
    pre_path = GRAPH / "g010_pre_execution.json"
    preflight_path = GRAPH / "g010_preflight.json"
    claim_path = GRAPH / "g010_launch_claim.json"
    launch_path = GRAPH / "g010_launch_manifest.json"
    pre, preflight, claim, launch = map(read, (pre_path, preflight_path, claim_path, launch_path))
    binding = pre["binding"]
    args = launch.get("command", [])
    require(
        binding["candidate_tree_sha256"] == TREE_SHA
        and binding["parent_graph_sha256"] == PARENT_GRAPH_SHA
        and binding["query_count"] == 56
        and binding["query_timeout_sec"] == 1200
        and binding["description_mode"] == "full_db_description_no_hints"
        and binding == preflight["binding"] == claim["binding"] == launch["binding"]
        and preflight["status"] == "passed"
        and preflight.get("model_probe", {}).get("http_status") == 200
        and claim["pre_execution_sha256"] == digest(pre_path)
        and claim["preflight_sha256"] == digest(preflight_path)
        and launch["preflight_sha256"] == digest(preflight_path)
        and launch["pid"] == PID
        and "--run-id" in args and args[args.index("--run-id") + 1] == RUN_ID,
        "frozen protocol, preflight, claim, or launch differs",
    )
    spec = importlib.util.spec_from_file_location(
        "g10_manifest", SOURCE / "experiments/intent_candidate_workspace.py"
    )
    require(spec is not None and spec.loader is not None, "source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = module.source_manifest_hash(
        sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    )
    require(tree == TREE_SHA, "source tree changed")

    summary_path = RUN / "multi_query_summary.json"
    progress_path = RUN / "multi_query_progress.json"
    summary, progress = read(summary_path), read(progress_path)
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    context = summary.get("execution_context", {})
    require(
        summary.get("query_count") == len(rows) == len(progress_rows) == 56
        and context.get("db_description_mode") == "base"
        and context.get("query_timeout_sec") == 1200
        and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                for a, b in zip(rows, progress_rows)),
        "summary, progress, or fixed protocol differs",
    )
    statuses = Counter(row.get("status") for row in rows)
    require(set(statuses) <= {"completed", "timeout", "failed"}, "status partition differs")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(
        strict_pass + strict_unknown + known_fail == statuses["completed"]
        and summary.get("strict_pass_count") == strict_pass,
        "strict partition differs",
    )
    names = (
        "g004_paired_structural_journal.jsonl",
        "g005_provenance_sidecar.jsonl",
        "g006_tool_class_sidecar.jsonl",
        "g007_last_pre_exec_sidecar.jsonl",
        "g008_verification_audit_sidecar.jsonl",
        "g009_verification_turn_gate_sidecar.jsonl",
        "g004_postrun_normalized_structural.json",
    )
    counts = Counter()
    seen = set()
    run_root = RUN / "runs"
    failure_signatures = Counter()
    failure_domains = Counter()
    for row in rows:
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id and run_id not in seen
                and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "task run id invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(), "task run dir missing")
        for name in names:
            counts[name] += (run_dir / name).is_file()
        if row["status"] == "completed":
            require(all((run_dir / name).is_file() for name in names), "completed sidecar gap")
        if row["status"] == "failed":
            error = str(row.get("run_error") or "")
            failure_signatures[("FatalError" in error, "CalledProcessError" in error,
                                "psql" in error, "exit status 2" in error,
                                row.get("llm_call_count"), row.get("tool_call_count"))] += 1
            failure_domains[hashlib.sha256(str(row.get("domain")).encode()).hexdigest()[:12]] += 1
    print(json.dumps({
        "status": "terminal_audit_requires_infrastructure_adjudication" if statuses["failed"] else "valid_terminal_run_pending_evidence",
        "ended": len(rows), "completed": statuses["completed"],
        "timeout_failures": statuses["timeout"], "other_failures": statuses["failed"],
        "strict_pass": strict_pass, "strict_denominator": 56,
        "strict_unknown_completed": strict_unknown, "known_strict_fail": known_fail,
        "sidecar_files": dict(counts),
        "failure_signatures": [{"fatal_error": key[0], "called_process_error": key[1],
                                "psql": key[2], "exit_2": key[3], "llm_calls": key[4],
                                "tool_calls": key[5], "count": count}
                               for key, count in failure_signatures.items()],
        "anonymous_failure_domains": dict(failure_domains),
        "summary_sha256": digest(summary_path), "progress_sha256": digest(progress_path),
        "pre_execution_sha256": digest(pre_path), "preflight_sha256": digest(preflight_path),
        "claim_sha256": digest(claim_path), "launch_manifest_sha256": digest(launch_path),
        "extractor_sha256": digest(SOURCE / "experiments/g010_evidence_extractor.py"),
        "parent_graph_sha256": PARENT_GRAPH_SHA,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
