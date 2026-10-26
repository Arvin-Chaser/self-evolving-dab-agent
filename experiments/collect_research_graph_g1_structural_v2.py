#!/usr/bin/env python3
"""Extract hash-bound, answer-blind G1 task structure from frozen artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016"
TARGET = OUT / "g001_structural_v2.json"
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]
EXPECTED_G0 = "256570b3813f79bced5332994c5e3506765cd88ebdbaf6371115e9e3290bc86e"
EXPECTED_G1 = "c8d35afeb677d018c76711737df8c30b468e1574c18d7450702188a857196b9b"

REMOTE_CODE = r'''
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

base = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
g0_run = base / "evaluation/baseline_g000_nohint_56_v1"
g1_run = base / "g001_revision001/evaluation/baseline_g001_deadline_reserve_nohint_56_v1"
g0_graph_path = base / "graph/g000_graph.json"
g1_graph_path = base / "graph/g001_graph.json"
g0_summary_path = g0_run / "multi_query_summary.json"
g1_summary_path = g1_run / "multi_query_summary.json"
g1_progress_path = g1_run / "multi_query_progress.json"
g1_manifest_path = base / "graph/g001_trace_manifest.json"

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def grade(row):
    if row.get("status") != "completed":
        return "not_completed"
    value = row.get("strict_match_passed")
    return "true" if value is True else "false" if value is False else "unknown"

def event_time(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) and 1500000000 <= value <= 2500000000 else None

def error_signature(row):
    if row.get("status") != "failed":
        return None
    message = row.get("run_error")
    if not isinstance(message, str):
        return {"outer_class": "missing", "pattern": "unclassified"}
    prefix = message.split(":", 1)[0]
    outer = prefix if prefix in {"FatalError", "RuntimeError", "TimeoutError"} else "other_or_unsafe"
    patterns = {
        "rate_limit": r"(?i)(?:rate.?limit|\b429\b)",
        "auth": r"(?i)(?:authentication|unauthorized|\b401\b|\b403\b)",
        "connectivity": r"(?i)(?:connection|connecterror|network|dns)",
        "remote_service": r"(?i)(?:\b50[0234]\b|gateway|service unavailable)",
        "context_limit": r"(?i)(?:context length|token limit|maximum context)",
        "docker": r"(?i)(?:docker|container daemon)",
    }
    matched = [name for name, pattern in patterns.items() if re.search(pattern, message)]
    return {"outer_class": outer,
            "pattern": matched[0] if len(matched) == 1 else "ambiguous" if matched else "unclassified"}

g0_graph, g1_graph = read(g0_graph_path), read(g1_graph_path)
g0_evidence, g1_evidence = g0_graph["nodes"][-1], g1_graph["nodes"][-1]
if (digest(g0_graph_path) != "256570b3813f79bced5332994c5e3506765cd88ebdbaf6371115e9e3290bc86e"
        or digest(g1_graph_path) != "c8d35afeb677d018c76711737df8c30b468e1574c18d7450702188a857196b9b"
        or digest(g0_summary_path) != g0_evidence["artifact_refs"]["summary_sha256"]
        or digest(g1_summary_path) != g1_evidence["artifact_refs"]["summary_sha256"]
        or digest(g1_progress_path) != g1_evidence["artifact_refs"]["progress_sha256"]
        or digest(g1_manifest_path) != g1_evidence["artifact_refs"]["trace_manifest_sha256"]):
    raise RuntimeError("Frozen source hashes differ")
g0_rows = read(g0_summary_path)["per_query_feedback"]
g1_rows = read(g1_summary_path)["per_query_feedback"]
progress_rows = read(g1_progress_path)["queries"]
manifest = read(g1_manifest_path)["entries"]
if (not all(len(rows) == 56 for rows in (g0_rows, g1_rows, progress_rows, manifest))
        or [row["query_id"] for row in g0_rows] != [row["query_id"] for row in g1_rows]
        or [row["query_id"] for row in progress_rows] != [row["query_id"] for row in g1_rows]):
    raise RuntimeError("Frozen task order differs")

cases = []
for index, (g0, g1, progress, entry) in enumerate(zip(g0_rows, g1_rows, progress_rows, manifest)):
    if (entry["batch_index"] != index or entry["terminal_status"] != g1["status"]
            or progress["status"] != g1["status"]):
        raise RuntimeError("Frozen trace/status binding differs")
    relative = entry.get("trace_relative_path")
    if not isinstance(relative, str):
        raise RuntimeError("G1 trace missing")
    trace = (g1_run / relative).resolve()
    if not trace.is_relative_to(g1_run.resolve()) or digest(trace) != entry["trace_sha256"]:
        raise RuntimeError("G1 trace hash differs")
    counts = Counter()
    starts, completed_ends = [], []
    return_answer_end = 0
    with trace.open(encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            kind = event.get("event_type")
            if kind not in {"llm_request", "llm_response", "tool_call_start", "tool_call_end", "agent_termination"}:
                raise RuntimeError("Unexpected event kind")
            counts[kind] += 1
            timestamp = event_time(event.get("event_time"))
            if timestamp is not None and kind in {"llm_request", "tool_call_start"}:
                starts.append(timestamp)
            if timestamp is not None and kind in {"llm_response", "tool_call_end"}:
                completed_ends.append(timestamp)
            if kind == "tool_call_end" and event.get("tool_name") == "return_answer":
                return_answer_end += 1
            # Never inspect messages, arguments, tool results, final_result, or raw responses.
    if (counts["tool_call_start"] != counts["tool_call_end"]
            or counts["agent_termination"] != 1):
        raise RuntimeError("Frozen full trace lacks structural closure")
    trigger = g1.get("deadline_reserve_trigger")
    if not isinstance(trigger, dict) or trigger.get("answer_blind") is not True:
        raise RuntimeError("Frozen reserve record missing")
    if progress.get("deadline_reserve_trigger") != trigger:
        raise RuntimeError("Summary/progress reserve record differs")
    cases.append({
        "anonymous_batch_index": index,
        "g0_terminal_status": g0["status"],
        "g0_strict_verdict": grade(g0),
        "g1_terminal_status": g1["status"],
        "g1_strict_verdict": grade(g1),
        "reserve_bound": trigger.get("bound") is True,
        "llm_request_count": counts["llm_request"],
        "llm_response_count": counts["llm_response"],
        "tool_call_count": counts["tool_call_end"],
        "return_answer_end_count": return_answer_end,
        "completed_event_span_sec": round(max(completed_ends) - min(starts), 3)
            if starts and completed_ends else None,
        "error_signature": error_signature(g1),
        "trace_sha256": entry["trace_sha256"],
    })

if (sum(case["g1_terminal_status"] == "completed" for case in cases) != 54
        or sum(case["g1_terminal_status"] == "failed" for case in cases) != 2
        or sum(case["g1_strict_verdict"] == "true" for case in cases) != 30
        or sum(case["reserve_bound"] for case in cases) != 5):
    raise RuntimeError("Structural counts differ from frozen Evidence")
print(json.dumps({
    "schema_version": "g001_answer_blind_structural_v2",
    "source_hashes": {"g0_graph_sha256": digest(g0_graph_path),
                      "g1_graph_sha256": digest(g1_graph_path),
                      "g0_summary_sha256": digest(g0_summary_path),
                      "g1_summary_sha256": digest(g1_summary_path),
                      "g1_progress_sha256": digest(g1_progress_path),
                      "g1_trace_manifest_sha256": digest(g1_manifest_path)},
    "cases": cases,
    "limitations": [
        "Anonymous batch indices are for deterministic joining only and are not task identifiers in the Meta packet.",
        "A message-pattern error signature is not a verified root cause.",
        "Recorded event span excludes unlogged work and any in-flight final call.",
        "G0/G1 cross-run outcome transitions are descriptive, not causal treatment effects.",
    ],
    "answer_blind": True,
}, sort_keys=True))
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_output(result: dict) -> None:
    if (result.get("schema_version") != "g001_answer_blind_structural_v2"
            or result.get("answer_blind") is not True
            or result["source_hashes"]["g0_graph_sha256"] != EXPECTED_G0
            or result["source_hashes"]["g1_graph_sha256"] != EXPECTED_G1
            or len(result["cases"]) != 56
            or [case["anonymous_batch_index"] for case in result["cases"]] != list(range(56))):
        raise RuntimeError("G1 structural collection contract differs")
    allowed_fields = {"anonymous_batch_index", "g0_terminal_status", "g0_strict_verdict",
                      "g1_terminal_status", "g1_strict_verdict", "reserve_bound",
                      "llm_request_count", "llm_response_count", "tool_call_count",
                      "return_answer_end_count", "completed_event_span_sec",
                      "error_signature", "trace_sha256"}
    if any(set(case) != allowed_fields for case in result["cases"]):
        raise RuntimeError("G1 structural output contains an unapproved field")
    if any(case["g0_terminal_status"] not in {"completed", "timeout", "failed"}
           or case["g1_terminal_status"] not in {"completed", "timeout", "failed"}
           or case["g0_strict_verdict"] not in {"true", "false", "unknown", "not_completed"}
           or case["g1_strict_verdict"] not in {"true", "false", "unknown", "not_completed"}
           or type(case["reserve_bound"]) is not bool
           or not re.fullmatch(r"[0-9a-f]{64}", case["trace_sha256"])
           or any(type(case[field]) is not int or case[field] < 0 or case[field] > 10000
                  for field in ("llm_request_count", "llm_response_count",
                                "tool_call_count", "return_answer_end_count"))
           or (case["completed_event_span_sec"] is not None and
               (type(case["completed_event_span_sec"]) not in {int, float} or
                not 0 <= case["completed_event_span_sec"] <= 86400))
           for case in result["cases"]):
        raise RuntimeError("G1 structural output contains an unsafe value")
    if any(case["error_signature"] is not None and
           (set(case["error_signature"]) != {"outer_class", "pattern"} or
            case["error_signature"]["outer_class"] not in
            {"FatalError", "RuntimeError", "TimeoutError", "missing", "other_or_unsafe"} or
            case["error_signature"]["pattern"] not in
            {"rate_limit", "auth", "connectivity", "remote_service", "context_limit",
             "docker", "ambiguous", "unclassified"}) for case in result["cases"]):
        raise RuntimeError("G1 structural error category is not allowlisted")


def main() -> None:
    if TARGET.exists():
        raise RuntimeError("G1 structural sidecar already exists")
    g0 = json.loads((OUT / "g000_graph.json").read_text(encoding="utf-8"))
    g1 = json.loads((OUT / "g001_graph.json").read_text(encoding="utf-8"))
    if (digest(OUT / "g000_graph.json") != EXPECTED_G0
            or digest(OUT / "g001_graph.json") != EXPECTED_G1
            or g0.get("status") != "four_nodes_complete"
            or g1.get("status") != "four_nodes_complete"):
        raise RuntimeError("Local frozen graphs differ")
    proc = subprocess.run(SSH, input=REMOTE_CODE, text=True, encoding="utf-8",
                          capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"Remote structural collection failed: exit {proc.returncode}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("SSH did not begin with disk check")
    result = json.loads(lines[-1])
    validate_output(result)
    with TARGET.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "collected", "sidecar_sha256": digest(TARGET),
                      "disk_header": lines[1] if len(lines) > 1 else None,
                      "case_count": len(result["cases"])}, sort_keys=True))


if __name__ == "__main__":
    main()
