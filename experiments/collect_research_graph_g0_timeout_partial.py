#!/usr/bin/env python3
"""Summarize G0 timeout partial event logs without exposing event payloads."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
RUN = BASE / "evaluation/baseline_g000_nohint_56_v1"
SUMMARY = RUN / "multi_query_summary.json"
EXPECTED_SUMMARY_SHA = "17697240bc73641e18d691459a109f86f3d77c45279e6c8aa12c6682ae050542"
ALLOWED_TOOLS = {"list_db", "query_db", "execute_python", "return_answer", "get_schema"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def records(path: Path) -> tuple[list[dict], int]:
    result = []
    torn_tail = 0
    with path.open("rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                if stream.tell() != path.stat().st_size or torn_tail:
                    raise RuntimeError("Malformed nonterminal event row")
                torn_tail = len(raw)
                continue
            if not isinstance(row, dict):
                raise RuntimeError("Event row is not an object")
            result.append(row)
    return result, torn_tail


def number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def event_epoch(value: object) -> float | None:
    if isinstance(value, str) and len(value) == 15 and value[8] == "_":
        try:
            return datetime.strptime(value, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None
    epoch = number(value)
    return epoch if epoch is not None and 1_500_000_000 <= epoch <= 2_500_000_000 else None


def main() -> None:
    if digest(SUMMARY) != EXPECTED_SUMMARY_SHA:
        raise RuntimeError("G0 summary hash differs")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    dab_root = Path(summary["execution_context"]["dab_root"]).resolve()
    if not dab_root.is_dir():
        raise RuntimeError("Frozen DAB root unavailable")
    if float(summary["execution_context"]["query_timeout_sec"]) != 1200:
        raise RuntimeError("Timeout protocol differs")
    timeout_rows = [row for row in summary["per_query_feedback"] if row["status"] == "timeout"]
    if len(timeout_rows) != 6 or any(row.get("run_exit_code") != 124 for row in timeout_rows):
        raise RuntimeError("Frozen timeout cohort differs")
    cases = []
    for index, row in enumerate(timeout_rows, 1):
        domain, separator, name = row["query_id"].partition("/")
        if not separator or not domain or not name:
            raise RuntimeError("Malformed frozen task locator")
        upstream = (dab_root / ("query_" + domain) / name / "logs/data_agent" / row["run_id"]).resolve()
        if not upstream.is_relative_to(dab_root):
            raise RuntimeError("Upstream log locator escapes DAB root")
        llm_path, tool_path = upstream / "llm_calls.jsonl", upstream / "tool_calls.jsonl"
        if not llm_path.is_file() or not tool_path.is_file():
            raise RuntimeError("Timeout partial event logs absent")
        if (llm_path.stat().st_mtime > SUMMARY.stat().st_mtime + 5
                or tool_path.stat().st_mtime > SUMMARY.stat().st_mtime + 5):
            raise RuntimeError("Partial log changed after G0 summary")
        llm_rows, llm_torn = records(llm_path)
        tool_rows, tool_torn = records(tool_path)
        calls = Counter()
        failures = Counter()
        tool_durations = []
        all_starts, all_ends = [], []
        for event in llm_rows:
            start, end = event_epoch(event.get("start_time")), event_epoch(event.get("end_time"))
            if start is not None:
                all_starts.append(start)
            if end is not None:
                all_ends.append(end)
        for event in tool_rows:
            tool_name = event.get("tool_name")
            if tool_name not in ALLOWED_TOOLS:
                tool_name = "other_tool"
            calls[tool_name] += 1
            result = event.get("result")
            if not isinstance(result, dict) or result.get("success") is not True:
                failures[tool_name] += 1
            start, end = event_epoch(event.get("start")), event_epoch(event.get("end"))
            if start is not None:
                all_starts.append(start)
            if end is not None:
                all_ends.append(end)
            duration = number(event.get("time"))
            if duration is not None and duration >= 0:
                tool_durations.append(duration)
        llm_durations = [value for row in llm_rows
                         if (value := number(row.get("duration"))) is not None and value >= 0]
        cases.append({
            "anonymous_timeout_index": index,
            "llm_record_count": len(llm_rows),
            "llm_response_present_count": sum(row.get("response") is not None for row in llm_rows),
            "llm_error_present_count": sum(bool(row.get("last_error")) for row in llm_rows),
            "tool_record_count": len(tool_rows),
            "tool_calls_by_name": dict(sorted(calls.items())),
            "tool_failures_by_name": dict(sorted(failures.items())),
            "recorded_llm_duration_sec": round(sum(llm_durations), 3),
            "recorded_tool_duration_sec": round(sum(tool_durations), 3),
            "observed_event_span_sec": round(max(all_ends) - min(all_starts), 3) if all_starts and all_ends else None,
            "torn_tail_bytes": {"llm": llm_torn, "tool": tool_torn},
            "source_hashes": {"llm_calls_sha256": digest(llm_path),
                              "tool_calls_sha256": digest(tool_path)},
        })
    print(json.dumps({
        "schema_version": "dab_g0_timeout_partial_answer_blind_v1",
        "source_summary_sha256": EXPECTED_SUMMARY_SHA,
        "timeout_case_count": len(cases),
        "cases": cases,
        "scope": "Only event counts, timestamps/durations, tool names, success flags, and log hashes; no messages, arguments, results, or answer text exported.",
        "limitations": [
            "An abruptly stopped process may leave its last event unlogged.",
            "Recorded durations do not include an unfinished final call or all process overhead.",
            "Partial event logs are not normalized full traces and do not imply a final answer.",
        ],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
