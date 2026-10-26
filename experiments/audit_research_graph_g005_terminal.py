#!/usr/bin/env python3
"""Read-only, answer-blind terminal audit of the frozen G5 run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G5 = BASE / "g005_revision001"
SOURCE = G5 / "source"
RUN_ID = "baseline_g005_provenance_nohint_56_v1"
RUN = G5 / "evaluation" / RUN_ID
PID = 1266
TREE_SHA = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
PARENT_SHA = "fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def main() -> None:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G5 runner still active")
    require(digest(GRAPH / "g004_graph.json") == PARENT_SHA, "G5 parent Graph changed")
    pre_path = GRAPH / "g005_pre_execution.json"
    preflight_path = GRAPH / "g005_preflight.json"
    claim_path = GRAPH / "g005_launch_claim.json"
    launch_path = GRAPH / "g005_launch_manifest.json"
    pre, preflight, claim, launch = map(read, (pre_path, preflight_path, claim_path, launch_path))
    binding = pre["binding"]
    require(
        binding["candidate_tree_sha256"] == TREE_SHA
        and binding["query_count"] == 56
        and binding["query_timeout_sec"] == 1200
        and binding["description_mode"] == "full_db_description_no_hints"
        and binding == preflight["binding"] == claim["binding"] == launch["binding"]
        and preflight["status"] == "passed"
        and preflight.get("model_probe", {}).get("http_status") == 200
        and claim["pre_execution_sha256"] == digest(pre_path)
        and claim["preflight_sha256"] == digest(preflight_path)
        and launch["preflight_sha256"] == digest(preflight_path)
        and launch["pid"] == PID,
        "G5 frozen protocol, preflight, claim, or launch differs",
    )
    module_path = SOURCE / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g5_manifest", module_path)
    require(spec is not None and spec.loader is not None, "G5 source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = module.source_manifest_hash(sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower()))
    require(tree == TREE_SHA, "G5 source tree changed")

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
        "G5 summary, progress, or fixed protocol differs",
    )
    statuses = Counter(row.get("status") for row in rows)
    require(set(statuses) <= {"completed", "timeout", "failed"}, "G5 status partition differs")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(
        statuses["completed"] + statuses["timeout"] + statuses["failed"] == 56
        and strict_pass + strict_unknown + known_fail == statuses["completed"]
        and summary.get("strict_pass_count") == strict_pass,
        "G5 strict partition differs",
    )

    sys.path.insert(0, str(SOURCE))
    from experiments.g005_provenance_sidecar import SIDECAR_FILENAME, read_sidecar
    from experiments.g004_postrun_structural_sidecar import SIDECAR_FILENAME as NORMALIZED, read_structural_sidecar
    from experiments.g004_paired_structural_journal import JOURNAL_FILENAME

    seen: set[str] = set()
    run_root = RUN / "runs"
    provenance_count = journal_count = normalized_completed = forbidden = parse_errors = 0
    for row in rows:
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id and run_id not in seen
                and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "G5 task run id invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(), "G5 task run dir missing")
        journal_count += (run_dir / JOURNAL_FILENAME).is_file()
        provenance = read_sidecar(run_dir / SIDECAR_FILENAME)
        provenance_count += provenance["exists"]
        forbidden += provenance["forbidden_field_count"] + int(provenance["schema_violation"])
        parse_errors += provenance["parse_errors"] + provenance["invalid_record_count"]
        if row["status"] == "completed":
            normalized = read_structural_sidecar(run_dir / NORMALIZED)
            normalized_completed += normalized.exists
            forbidden += int(normalized.schema_violation) + normalized.forbidden_field_count
    require(journal_count == provenance_count == 56 and normalized_completed == statuses["completed"]
            and forbidden == 0, "G5 pre-registered sidecar coverage or allowlist differs")
    require(statuses["failed"] == 0 and strict_pass > 0, "G5 infrastructure validity needs review")
    print(json.dumps({
        "status": "valid_terminal_run_pending_evidence", "ended": 56,
        "completed": statuses["completed"], "timeout_failures": statuses["timeout"],
        "other_failures": statuses["failed"], "strict_pass": strict_pass,
        "strict_denominator": 56, "strict_unknown_completed": strict_unknown,
        "known_strict_fail": known_fail, "journal_files": journal_count,
        "normalized_completed_files": normalized_completed, "provenance_files": provenance_count,
        "provenance_parse_or_invalid_records": parse_errors,
        "summary_sha256": digest(summary_path), "progress_sha256": digest(progress_path),
        "pre_execution_sha256": digest(pre_path), "preflight_sha256": digest(preflight_path),
        "launch_manifest_sha256": digest(launch_path), "extractor_sha256": digest(SOURCE / "experiments/g005_evidence_extractor.py"),
        "parent_graph_sha256": PARENT_SHA,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
