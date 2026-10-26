#!/usr/bin/env python3
"""Count exact G2 tool-call repetition without exporting task content or IDs."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g002_exact_repetition_v1.json"
REMOTE_BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH_SHA = "38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54"
SUMMARY_SHA = "d18d1650670d5ed362c3a0920053e60f9243adbb3cafb4e3375ad11cf50ddd02"
MANIFEST_SHA = "bd8083f263254fff2e4e8cfa68bc577220928fecd0809ed88c1a781df02003f1"
INTERFACE_SHA = "f9a05ed3c9dcc171b3db4c1cef69d61ecd9625a646abbf90f95baddd56e37025"
COHORT_SIZES = {"strict_pass": 30, "strict_fail": 21, "strict_unknown": 3,
                "timeout_failure": 2}
MIN_COMPLETE_COVERAGE = 0.8
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes",
       "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python - --remote"]


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def canonical_signature(event: dict) -> str | None:
    name = event.get("tool_name")
    index = event.get("tool_call_index")
    args = event.get("validated_args")
    if (not isinstance(name, str) or not name or
            type(index) is not int or index < 1 or args is None):
        return None
    try:
        return json.dumps([name, args], sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return None


def count_task(starts: list[dict]) -> dict[str, int | str]:
    indices = [event.get("tool_call_index") for event in starts]
    if indices != list(range(1, len(starts) + 1)):
        raise RuntimeError("G2 tool-call-start order or index differs")
    seen: set[str] = set()
    repeat = eligible = unknown = 0
    for event in starts:
        signature = canonical_signature(event)
        if signature is None:
            unknown += 1
            continue
        eligible += 1
        if signature in seen:
            repeat += 1
        seen.add(signature)
    coverage = "complete" if eligible and not unknown else "partial" if eligible else "no_eligible"
    return {"starts": len(starts), "eligible": eligible, "repeat": repeat,
            "unknown": unknown, "coverage": coverage}


def summarize(rows: list[dict[str, int | str]], expected: int) -> dict:
    unmeasured = expected - len(rows)
    if unmeasured < 0 or (unmeasured and expected != COHORT_SIZES["timeout_failure"]):
        raise RuntimeError("G2 cohort task count differs")
    complete = [row for row in rows if row["coverage"] == "complete"]
    rates = [row["repeat"] / row["eligible"] for row in complete]
    return {
        "tasks": expected,
        "unmeasured_tasks": unmeasured,
        "complete_tasks": len(complete),
        "partial_tasks": sum(row["coverage"] == "partial" for row in rows),
        "no_eligible_tasks": sum(row["coverage"] == "no_eligible" for row in rows),
        "tool_call_starts": sum(row["starts"] for row in rows),
        "eligible_starts": sum(row["eligible"] for row in rows),
        "unknown_starts": sum(row["unknown"] for row in rows),
        "exact_repeats": sum(row["repeat"] for row in rows),
        "complete_tasks_with_repeat": sum(row["repeat"] > 0 for row in complete),
        "mean_complete_task_rate": round(statistics.mean(rates), 6) if rates else None,
        "median_complete_task_rate": round(statistics.median(rates), 6) if rates else None,
    }


def remote_main() -> None:
    run = REMOTE_BASE / "g002_revision001/evaluation/baseline_g002_lifecycle_nohint_56_v1"
    graph = REMOTE_BASE / "graph/g002_graph.json"
    summary = run / "multi_query_summary.json"
    manifest = REMOTE_BASE / "graph/g002_trace_manifest.json"
    expected = {graph: GRAPH_SHA, summary: SUMMARY_SHA, manifest: MANIFEST_SHA}
    if any(digest(path) != value for path, value in expected.items()):
        raise RuntimeError("Frozen G2 source hash differs")
    graph_data = json.loads(graph.read_text(encoding="utf-8"))
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    feedback = summary_data["per_query_feedback"]
    entries = manifest_data["entries"]
    evidence = graph_data["nodes"][-1]
    if (graph_data.get("status") != "four_nodes_complete" or
            evidence.get("kind") != "evidence" or
            evidence.get("strict_pass_count") != 30 or
            len(feedback) != 56 or len(entries) != 56):
        raise RuntimeError("G2 Graph or frozen task coverage differs")
    cohorts: dict[str, list[dict[str, int | str]]] = {name: [] for name in COHORT_SIZES}
    for position, (row, entry) in enumerate(zip(feedback, entries)):
        status = row["status"]
        if status == "timeout":
            cohort = "timeout_failure"
        elif status == "completed":
            verdict = row.get("strict_match_passed")
            cohort = "strict_pass" if verdict is True else "strict_fail" if verdict is False else "strict_unknown"
        else:
            raise RuntimeError("Unexpected G2 terminal status")
        if entry["batch_index"] != position or entry["terminal_status"] != status:
            raise RuntimeError("G2 trace manifest order or status differs")
        run_dir = Path(row["run_dir"]).resolve()
        if not run_dir.is_relative_to(run.resolve()):
            raise RuntimeError("G2 task run path escapes frozen run")
        trace = run_dir / "full_execution_trace.jsonl"
        if status == "timeout":
            if trace.is_file() or entry.get("trace_sha256") is not None:
                raise RuntimeError("Unexpected timeout full trace")
            continue
        if not trace.is_file() or digest(trace) != entry["trace_sha256"]:
            raise RuntimeError("Completed trace hash differs")
        starts: list[dict] = []
        with trace.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("event_type") == "tool_call_start":
                    starts.append({key: event.get(key) for key in
                                   ("tool_name", "tool_call_index", "validated_args")})
        cohorts[cohort].append(count_task(starts))
    result = {
        "schema_version": "g002_exact_repetition_answer_blind_v1",
        "source_hashes": {"g2_graph_sha256": GRAPH_SHA,
                          "g2_summary_sha256": SUMMARY_SHA,
                          "g2_trace_manifest_sha256": MANIFEST_SHA,
                          "g2_runtime_interface_card_sha256": INTERFACE_SHA},
        "frozen_task_count": 56,
        "rule": "Within each completed task, compare exact tool_name plus canonical validated_args; sorted JSON object keys, preserved array order and scalar types. Missing fields are unknown. All tools including return_answer count. Only fully covered tasks enter equal-weighted cohort rates.",
        "minimum_complete_coverage": MIN_COMPLETE_COVERAGE,
        "cohorts": {name: summarize(rows, COHORT_SIZES[name]) for name, rows in cohorts.items()},
        "limitations": [
            "Exact repetition is not no-progress, task relevance, or correctness.",
            "Validated arguments are post-execution log fields and may include changing execution state.",
            "Timeout tasks have no complete normalized trace and remain unmeasured.",
            "Strict-verdict-unknown completed tasks are reported separately.",
            "This is a within-G2 association, not evidence that suppressing repeats improves score.",
        ],
    }
    failed = result["cohorts"]["strict_fail"]
    passed = result["cohorts"]["strict_pass"]
    enough = all(row["complete_tasks"] >= math.ceil(row["tasks"] * MIN_COMPLETE_COVERAGE)
                 for row in (failed, passed))
    result["hypothesis_check"] = {
        "coverage_sufficient": enough,
        "strict_fail_mean_exceeds_pass": (
            failed["mean_complete_task_rate"] > passed["mean_complete_task_rate"]
            if enough else None),
        "interpretation": "association_only" if enough else "untested_coverage_insufficient",
    }
    print(json.dumps(result, sort_keys=True))


def validate_output(value: dict) -> None:
    if (value.get("schema_version") != "g002_exact_repetition_answer_blind_v1" or
            value.get("frozen_task_count") != 56 or
            set(value.get("cohorts", {})) != set(COHORT_SIZES) or
            value.get("source_hashes") != {
                "g2_graph_sha256": GRAPH_SHA, "g2_summary_sha256": SUMMARY_SHA,
                "g2_trace_manifest_sha256": MANIFEST_SHA,
                "g2_runtime_interface_card_sha256": INTERFACE_SHA,
            }):
        raise RuntimeError("Exact-repeat sidecar binding or cohort schema differs")
    for name, count in COHORT_SIZES.items():
        row = value["cohorts"][name]
        if (row["tasks"] != count or
                row["complete_tasks"] + row["partial_tasks"] + row["no_eligible_tasks"]
                + row["unmeasured_tasks"] != count or
                row["eligible_starts"] + row["unknown_starts"] != row["tool_call_starts"] or
                row["exact_repeats"] > row["eligible_starts"]):
            raise RuntimeError("Exact-repeat cohort arithmetic differs")
    if value["cohorts"]["timeout_failure"]["tool_call_starts"] != 0:
        raise RuntimeError("Timeout traces were treated as completed")


def local_main() -> None:
    if OUT.exists():
        raise RuntimeError("Exact-repeat sidecar already exists")
    source = Path(__file__).read_text(encoding="utf-8")
    proc = subprocess.run(SSH, input=source, text=True, encoding="utf-8",
                          capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"G2 read-only extraction failed: exit {proc.returncode}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("SSH did not start with disk check")
    value = json.loads(lines[-1])
    validate_output(value)
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps({"status": "collected", "sidecar_sha256": digest(OUT),
                      "coverage_sufficient": value["hypothesis_check"]["coverage_sufficient"]},
                     sort_keys=True))


if __name__ == "__main__":
    remote_main() if sys.argv[1:] == ["--remote"] else local_main()
