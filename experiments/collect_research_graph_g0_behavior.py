#!/usr/bin/env python3
"""Read frozen G0 metadata and traces, emitting only answer-blind counts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
RUN = BASE / "evaluation/baseline_g000_nohint_56_v1"
GRAPH = BASE / "graph"
EXPECTED_GRAPH_SHA = "256570b3813f79bced5332994c5e3506765cd88ebdbaf6371115e9e3290bc86e"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cohort(row: dict) -> str:
    if row["status"] == "timeout":
        return "timeout_failure"
    if row["status"] != "completed":
        return "other_failure"
    value = row.get("strict_match_passed")
    return "strict_pass" if value is True else "strict_fail" if value is False else "strict_unknown"


def main() -> None:
    graph_path = GRAPH / "g000_graph.json"
    summary_path = RUN / "multi_query_summary.json"
    manifest_path = GRAPH / "g000_trace_manifest.json"
    if digest(graph_path) != EXPECTED_GRAPH_SHA:
        raise RuntimeError("Frozen G0 Graph hash differs")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = next(node for node in graph["nodes"] if node["kind"] == "evidence")
    rows = summary["per_query_feedback"]
    if len(rows) != 56 or len(manifest["entries"]) != 56:
        raise RuntimeError("G0 result coverage differs")
    counts: Counter[str] = Counter()
    traces: Counter[str] = Counter()
    by_cohort: dict[str, Counter[str]] = defaultdict(Counter)
    tool_calls: Counter[str] = Counter()
    tool_failure: Counter[str] = Counter()
    trace_hashes_verified = 0
    for index, (row, entry) in enumerate(zip(rows, manifest["entries"])):
        if entry["batch_index"] != index or entry["terminal_status"] != row["status"]:
            raise RuntimeError("Trace manifest order/status differs")
        group = cohort(row)
        counts[group] += 1
        path_text = entry["trace_relative_path"]
        if path_text is None:
            if entry["trace_sha256"] is not None or group != "timeout_failure":
                raise RuntimeError("Unexpected missing trace")
            continue
        trace_path = (RUN / path_text).resolve()
        if not trace_path.is_relative_to(RUN.resolve()) or digest(trace_path) != entry["trace_sha256"]:
            raise RuntimeError("Trace path/hash differs")
        trace_hashes_verified += 1
        traces[group] += 1
        events: Counter[str] = Counter()
        failures = 0
        for line in trace_path.open(encoding="utf-8"):
            event = json.loads(line)
            kind = event.get("event_type")
            if kind not in {"llm_request", "llm_response", "tool_call_start", "tool_call_end", "agent_termination"}:
                raise RuntimeError("Unexpected trace event type")
            events[kind] += 1
            if kind == "tool_call_end":
                tool_name = event.get("tool_name")
                if tool_name not in {"list_db", "query_db", "return_answer", "execute_python", "get_schema"}:
                    tool_name = "other_tool"
                tool_calls[tool_name] += 1
                if event.get("success") is not True:
                    tool_failure[tool_name] += 1
                    failures += 1
            # Do not inspect request messages, tool arguments/results, or final answers.
        if events["agent_termination"] != 1 or events["tool_call_start"] != events["tool_call_end"]:
            raise RuntimeError("Incomplete completed-task trace")
        by_cohort[group]["llm_requests"] += events["llm_request"]
        by_cohort[group]["tool_calls"] += events["tool_call_end"]
        by_cohort[group]["tool_failures"] += failures
        by_cohort[group]["tasks_with_tool_failure"] += int(failures > 0)
        by_cohort[group]["tasks_with_no_tool_call"] += int(events["tool_call_end"] == 0)
    if (sum(counts.values()) != 56 or counts["strict_pass"] != evidence["strict_pass_count"]
            or counts["timeout_failure"] != evidence["timeout_failure_count"]
            or counts["strict_unknown"] != evidence["strict_verdict_missing_completed_count"]
            or sum(traces.values()) != trace_hashes_verified):
        raise RuntimeError("G0 Evidence and behavioral counts differ")
    result = {
        "schema_version": "dab_g0_answer_blind_behavior_v1",
        "source_graph_sha256": digest(graph_path),
        "source_summary_sha256": digest(summary_path),
        "source_trace_manifest_sha256": digest(manifest_path),
        "frozen_task_count": 56,
        "task_cohorts": dict(sorted(counts.items())),
        "trace_count_by_cohort": dict(sorted(traces.items())),
        "trace_hashes_verified": trace_hashes_verified,
        "trace_behavior_by_cohort": {key: dict(sorted(value.items())) for key, value in sorted(by_cohort.items())},
        "tool_calls_by_name": dict(sorted(tool_calls.items())),
        "tool_failures_by_name": dict(sorted(tool_failure.items())),
        "limitations": [
            "Timeout tasks lack full traces; their in-task behavior is unknown.",
            "Tool success flags do not establish answer correctness.",
            "Strict verdict missing is unknown, not a known failure verdict.",
            "No task identifiers, prompts, tool arguments/results, final answers, hints, or validators were read into this output.",
        ],
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
