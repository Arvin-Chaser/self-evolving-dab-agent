#!/usr/bin/env python3
"""Isolated, provenance-bound recovery for G10's pre-model PostgreSQL failures."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G10 = BASE / "g010_revision001"
SOURCE = G10 / "source"
ORIGINAL_ID = "g010_verification_reconciliation_nohint_56_v1"
ORIGINAL = G10 / "evaluation" / ORIGINAL_ID
ORIGINAL_SUMMARY_SHA = "158a46757001991281f4feedf8bc20aba72bd7771e4f2b77bd2658b484b62abe"
ORIGINAL_PROGRESS_SHA = "cc3022f8c1d4209c48abe603172720b5825a8b95e755439cc242cdb08c2581a9"
SOURCE_SHA = "80f002ac7a2d90b3cfed0fda7fec03c64c0a442c69a0ae27c7506852b32d36b9"
RECOVERY = G10 / "recovery/g010_pgload_subset_v1"
BATCH = RECOVERY / "target_batch.json"
PREPARE_ID = "g010_pgload_subset_prepare_v1"
RUN_ID = "g010_pgload_subset_recovery_v1"
EVALUATION = RECOVERY / "evaluation" / RUN_ID
PYTHON = Path("/srv/text2sql/.venv/bin/python")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def source_tree_hash() -> str:
    spec = importlib.util.spec_from_file_location(
        "g010_manifest", SOURCE / "experiments/intent_candidate_workspace.py"
    )
    require(spec is not None and spec.loader is not None, "source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    return module.source_manifest_hash(rows)


def original_and_targets() -> tuple[dict, list[dict]]:
    require(digest(ORIGINAL / "multi_query_summary.json") == ORIGINAL_SUMMARY_SHA,
            "original summary changed")
    require(digest(ORIGINAL / "multi_query_progress.json") == ORIGINAL_PROGRESS_SHA,
            "original progress changed")
    require(source_tree_hash() == SOURCE_SHA, "frozen source changed")
    formal = read(BASE / "graph/g010_launch_manifest.json")
    require(formal["pid"] == 225760 and formal["binding"]["candidate_tree_sha256"] == SOURCE_SHA,
            "formal launch binding changed")
    require(not Path("/proc/225760/cmdline").is_file(), "formal runner still active")
    summary = read(ORIGINAL / "multi_query_summary.json")
    rows = summary["per_query_feedback"]
    frozen_batch = read(ORIGINAL / "batch.json")["query_ids"]
    require(len(rows) == len(frozen_batch) == 56, "original frozen task count differs")
    require(all(row["query_id"] == query_id for row, query_id in zip(rows, frozen_batch)),
            "original batch order differs")
    failures = [row for row in rows if row["status"] == "failed"]
    require(len(failures) == 5, "unexpected failure count")
    for row in failures:
        error = str(row.get("run_error") or "")
        require(
            all(marker in error for marker in ("FatalError", "CalledProcessError", "psql", "exit status 2"))
            and row.get("llm_call_count") in (None, 0)
            and row.get("tool_call_count") in (None, 0)
            and row.get("run_exit_code") == 1,
            "failed task is not a corroborated pre-model PostgreSQL load failure",
        )
    domains = {row["domain"] for row in failures}
    require(len(domains) == 1, "unexpected failure-domain scope")
    domain = next(iter(domains))
    require(sum(row["status"] == "completed" and row["domain"] == domain for row in rows) >= 2,
            "no later same-domain recovery evidence")
    return formal, failures


def command(formal: dict, output_root: Path, run_id: str, *, prepare_only: bool) -> list[str]:
    args = list(formal["command"])
    for flag, value in (("--batch", BATCH), ("--output-root", output_root), ("--run-id", run_id)):
        require(flag in args and args.index(flag) + 1 < len(args), f"formal command missing {flag}")
        args[args.index(flag) + 1] = str(value)
    require("--use-hints" not in args and "--use-hint-only-db-description" not in args,
            "formal no-hint protocol differs")
    require(args[args.index("--query-timeout-sec") + 1] == "1200",
            "formal wall-time protocol differs")
    if prepare_only:
        args.append("--prepare-only")
    return args


def prepare() -> None:
    formal, failures = original_and_targets()
    require(not RECOVERY.exists(), "recovery path already exists")
    require(shutil.disk_usage(G10).free >= 5 * 1024**3, "below 5 GiB")
    incident = BASE / "graph/g010_execution_incident.json"
    require(not incident.exists(), "G10 incident already recorded")
    write_new(incident, {
        "schema_version": "g010_execution_incident_v1",
        "status": "invalid_infrastructure_hypothesis_not_tested",
        "original_run_id": ORIGINAL_ID,
        "original_summary_sha256": ORIGINAL_SUMMARY_SHA,
        "original_progress_sha256": ORIGINAL_PROGRESS_SHA,
        "source_tree_sha256": SOURCE_SHA,
        "affected_task_count": len(failures),
        "observed_signature": "pre_model_postgresql_dump_load_psql_exit_2",
        "scope": "one_anonymous_domain_five_failures_then_two_completions",
        "root_cause": "unconfirmed_transient_database_connection_or_load_environment",
        "official_results_rewritten": False,
        "candidate_quality_inferred_from_affected_run": False,
    })
    RECOVERY.mkdir(parents=True)
    write_new(BATCH, {
        "schema_version": "dab_query_batch_v001",
        "batch_id": "g010_pgload_subset_v1",
        "query_ids": [row["query_id"] for row in failures],
    })
    write_new(RECOVERY / "selection.json", {
        "schema_version": "g010_pgload_subset_selection_v1",
        "original_run_id": ORIGINAL_ID,
        "original_summary_sha256": ORIGINAL_SUMMARY_SHA,
        "original_progress_sha256": ORIGINAL_PROGRESS_SHA,
        "source_tree_sha256": SOURCE_SHA,
        "target_batch_sha256": digest(BATCH),
        "target_positions_in_frozen_56": [i + 1 for i, row in enumerate(read(ORIGINAL / "multi_query_summary.json")["per_query_feedback"])
                                           if row["status"] == "failed"],
        "classification": "pre_model_postgresql_dump_load_psql_exit_2_same_domain_then_later_success",
        "official_score_substitution": False,
    })
    args = command(formal, RECOVERY / "preflight", PREPARE_ID, prepare_only=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (RECOVERY / "prepare.log").open("x", encoding="utf-8") as log:
        process = subprocess.run(args, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    require(process.returncode == 0, "targeted prepare-only failed; log preserved")
    summary = read(RECOVERY / "preflight" / PREPARE_ID / "multi_query_summary.json")
    context = summary["execution_context"]
    require(
        summary["query_count"] == 5
        and all(row["status"] == "prepared" and row["run_exit_code"] == 0
                for row in summary["per_query_feedback"])
        and context["db_description_mode"] == "base"
        and context["query_timeout_sec"] == 1200,
        "targeted prepare-only protocol differs",
    )
    print(json.dumps({"status": "prepared", "target_count": 5,
                      "target_batch_sha256": digest(BATCH)}, sort_keys=True))


def launch() -> None:
    formal, failures = original_and_targets()
    selection = read(RECOVERY / "selection.json")
    require(len(failures) == 5 and selection["target_batch_sha256"] == digest(BATCH),
            "target selection changed")
    require(read(RECOVERY / "preflight" / PREPARE_ID / "multi_query_summary.json")["query_count"] == 5,
            "targeted prepare missing")
    require(not (RECOVERY / "launch_claim.json").exists() and not EVALUATION.exists(),
            "recovery already claimed")
    free = shutil.disk_usage(G10).free
    require(free >= 5 * 1024**3, "below 5 GiB")
    error = str(failures[0].get("run_error") or "")
    match = re.search(r"'(-h[^']+)'", error)
    require(match is not None and match.group(1).startswith("-h"), "frozen PostgreSQL host unavailable")
    checks = (
        ["docker", "exec", "dab-postgres", "pg_isready"],
        ["pg_isready", match.group(1)],
    )
    require(all(subprocess.run(item, capture_output=True, timeout=15).returncode == 0 for item in checks),
            "PostgreSQL preflight failed")
    key = sys.stdin.readline().strip()
    require(bool(key) and not any(char.isspace() for char in key), "credential unavailable")
    probe = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps({"model": "deepseek-flash", "messages": [{"role": "user", "content": "Reply with OK."}],
                         "max_tokens": 8, "stream": False}).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(probe, timeout=45) as response:
        payload = json.load(response)
        require(response.status == 200 and isinstance(payload.get("choices", [{}])[0].get("message", {}).get("content"), str),
                "model response protocol preflight failed")
    write_new(RECOVERY / "preflight.json", {
        "status": "passed", "task_content_sent": False,
        "source_tree_sha256": SOURCE_SHA,
        "original_summary_sha256": ORIGINAL_SUMMARY_SHA,
        "target_batch_sha256": digest(BATCH), "free_bytes": free,
    })
    args = command(formal, RECOVERY / "evaluation", RUN_ID, prepare_only=False)
    write_new(RECOVERY / "launch_claim.json", {
        "status": "claimed_exclusive_recovery",
        "preflight_sha256": digest(RECOVERY / "preflight.json"),
        "selection_sha256": digest(RECOVERY / "selection.json"),
        "command": args,
    })
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    (RECOVERY / "evaluation").mkdir(exist_ok=True)
    with (RECOVERY / "launcher.log").open("x", encoding="utf-8") as log:
        process = subprocess.Popen(args, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write_new(RECOVERY / "launch_manifest.json", {
        "status": "launched_separate_recovery", "pid": process.pid,
        "run_id": RUN_ID, "source_tree_sha256": SOURCE_SHA,
        "preflight_sha256": digest(RECOVERY / "preflight.json"),
        "claim_sha256": digest(RECOVERY / "launch_claim.json"),
        "target_batch_sha256": digest(BATCH),
        "credential_env_name": "DEEPSEEK_API_KEY",
        "original_score_unchanged": True,
    })
    print(json.dumps({"status": "launched_separate_recovery", "pid": process.pid,
                      "target_count": 5, "free_bytes": free}, sort_keys=True))


def status() -> None:
    manifest = read(RECOVERY / "launch_manifest.json")
    pid = manifest["pid"]
    cmdline = Path(f"/proc/{pid}/cmdline")
    command_line = cmdline.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace") if cmdline.is_file() else ""
    require(not command_line or RUN_ID in command_line, "recovery PID reused")
    path = EVALUATION / "multi_query_progress.json"
    rows = read(path)["queries"] if path.is_file() else []
    require(len(rows) <= 5, "recovery exceeds five selected tasks")
    counts = Counter(row["status"] for row in rows)
    print(json.dumps({"status": "running" if command_line else "exited", "ended": len(rows),
                      "completed": counts["completed"], "failed": counts["failed"],
                      "timeout": counts["timeout"], "free_bytes": shutil.disk_usage(G10).free}, sort_keys=True))


def reconcile() -> None:
    manifest = read(RECOVERY / "launch_manifest.json")
    pid = manifest["pid"]
    cmdline = Path(f"/proc/{pid}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "recovery still active")
    require(digest(BATCH) == manifest["target_batch_sha256"]
            and digest(RECOVERY / "preflight.json") == manifest["preflight_sha256"]
            and digest(RECOVERY / "launch_claim.json") == manifest["claim_sha256"]
            and source_tree_hash() == SOURCE_SHA, "recovery binding differs")
    original = read(ORIGINAL / "multi_query_summary.json")["per_query_feedback"]
    recovered = read(EVALUATION / "multi_query_summary.json")
    progress = read(EVALUATION / "multi_query_progress.json")
    rows = recovered["per_query_feedback"]
    targets = read(BATCH)["query_ids"]
    require(recovered["query_count"] == len(rows) == len(progress["queries"]) == len(targets) == 5,
            "recovery result partition differs")
    require([row["query_id"] for row in rows] == targets and len(set(targets)) == 5,
            "recovery task selection differs")
    require(recovered["execution_context"]["db_description_mode"] == "base"
            and recovered["execution_context"]["query_timeout_sec"] == 1200,
            "recovery protocol differs")
    by_id = {row["query_id"]: row for row in original}
    mapping = []
    recovered_strict = 0
    for position, row in enumerate(rows):
        before = by_id[row["query_id"]]
        require(before["status"] == "failed", "non-target was recovered")
        strict = row["status"] == "completed" and row.get("strict_match_passed") is True
        recovered_strict += strict
        mapping.append({
            "frozen_position": read(ORIGINAL / "batch.json")["query_ids"].index(row["query_id"]) + 1,
            "query_id_sha256": hashlib.sha256(row["query_id"].encode()).hexdigest(),
            "original_run_id_sha256": hashlib.sha256(before["run_id"].encode()).hexdigest(),
            "recovery_run_id_sha256": hashlib.sha256(row["run_id"].encode()).hexdigest(),
            "original_status": before["status"], "recovery_status": row["status"],
            "recovery_strict_match_passed": row.get("strict_match_passed") if row["status"] == "completed" else None,
        })
    official_strict = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in original)
    write_new(RECOVERY / "reconciled_report.json", {
        "schema_version": "g010_pgload_subset_reconciled_v1",
        "status": "supplementary_not_official_full_run",
        "original_run_id": ORIGINAL_ID, "recovery_run_id": RUN_ID,
        "original_summary_sha256": ORIGINAL_SUMMARY_SHA,
        "recovery_summary_sha256": digest(EVALUATION / "multi_query_summary.json"),
        "source_tree_sha256": SOURCE_SHA, "target_batch_sha256": digest(BATCH),
        "original_strict_pass_over_56": official_strict,
        "supplementary_recovered_strict_pass_over_56": official_strict + recovered_strict,
        "supplementary_new_strict_passes": recovered_strict,
        "recovery_status_counts": dict(Counter(row["status"] for row in rows)),
        "original_result_mutated": False,
        "task_mapping": mapping,
    })
    print(json.dumps({"status": "reconciled_supplementary", "target_count": 5,
                      "original_strict_pass_over_56": official_strict,
                      "supplementary_recovered_strict_pass_over_56": official_strict + recovered_strict,
                      "recovery_status_counts": dict(Counter(row["status"] for row in rows)),
                      "report_sha256": digest(RECOVERY / "reconciled_report.json")}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch", "status", "reconcile"))
    action = parser.parse_args().action
    {"prepare": prepare, "launch": launch, "status": status, "reconcile": reconcile}[action]()
