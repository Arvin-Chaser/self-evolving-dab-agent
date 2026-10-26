#!/usr/bin/env python3
"""Count G2 proposed-call coverage without emitting task content or identifiers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
LOCAL_OUT = (Path(__file__).resolve().parent /
             "research_graph_baseline_20261016/g002_proposed_call_coverage_v2.json")
RUN = BASE / "g002_revision001/evaluation/baseline_g002_lifecycle_nohint_56_v1"
GRAPH = BASE / "graph/g002_graph.json"
SUMMARY = RUN / "multi_query_summary.json"
MANIFEST = BASE / "graph/g002_trace_manifest.json"
EXPECTED = {
    GRAPH: "38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54",
    SUMMARY: "d18d1650670d5ed362c3a0920053e60f9243adbb3cafb4e3375ad11cf50ddd02",
    MANIFEST: "bd8083f263254fff2e4e8cfa68bc577220928fecd0809ed88c1a781df02003f1",
}
COHORT_SIZES = {"strict_pass": 30, "strict_fail": 21,
                "strict_unknown": 3, "timeout_failure": 2}
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o",
       "IdentitiesOnly=yes", "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python - --remote"]


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def remote_main() -> None:
    if any(digest(path) != expected for path, expected in EXPECTED.items()):
        raise RuntimeError("Frozen G2 source hash differs")
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    feedback = summary["per_query_feedback"]
    entries = manifest["entries"]
    if (graph.get("status") != "four_nodes_complete" or
            graph["nodes"][-1]["strict_pass_count"] != 30 or
            len(feedback) != 56 or len(entries) != 56):
        raise RuntimeError("Frozen G2 coverage differs")
    cohorts = {name: {"tasks": 0, "tasks_with_all_proposals_parseable": 0,
                      "tasks_with_proposal_count_equal_logged_starts": 0,
                      "proposed_calls": 0, "parseable_proposals": 0,
                      "logged_tool_starts": 0, "unknown_proposals": 0,
                      "exact_proposed_repeats": 0,
                      "complete_tasks_with_repeat": 0}
               for name in COHORT_SIZES}
    for position, (row, entry) in enumerate(zip(feedback, entries)):
        status = row["status"]
        if status == "timeout":
            cohort = "timeout_failure"
        elif status == "completed":
            verdict = row.get("strict_match_passed")
            cohort = ("strict_pass" if verdict is True else
                      "strict_fail" if verdict is False else "strict_unknown")
        else:
            raise RuntimeError("Unexpected G2 terminal status")
        if entry["batch_index"] != position or entry["terminal_status"] != status:
            raise RuntimeError("G2 manifest order differs")
        aggregate = cohorts[cohort]
        aggregate["tasks"] += 1
        if status == "timeout":
            if entry.get("trace_sha256") is not None:
                raise RuntimeError("Unexpected timeout full trace")
            continue
        run_dir = Path(row["run_dir"]).resolve()
        if not run_dir.is_relative_to(RUN.resolve()):
            raise RuntimeError("G2 task path escapes frozen run")
        trace = run_dir / "full_execution_trace.jsonl"
        if digest(trace) != entry["trace_sha256"]:
            raise RuntimeError("G2 trace hash differs")
        proposed = parseable = starts = repeats = 0
        seen: set[str] = set()
        with trace.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("event_type") == "tool_call_start":
                    starts += 1
                if event.get("event_type") != "llm_response":
                    continue
                calls = event.get("tool_calls")
                if calls is None:
                    continue
                if not isinstance(calls, list):
                    raise RuntimeError("G2 response tool-call schema differs")
                for call in calls:
                    proposed += 1
                    function = call.get("function") if isinstance(call, dict) else None
                    name = function.get("name") if isinstance(function, dict) else None
                    arguments = function.get("arguments") if isinstance(function, dict) else None
                    if not isinstance(name, str) or not name or not isinstance(arguments, str):
                        continue
                    try:
                        parsed = json.loads(arguments)
                        if not isinstance(parsed, dict):
                            continue
                        signature = json.dumps([name, parsed], sort_keys=True,
                                               separators=(",", ":"), allow_nan=False)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    parseable += 1
                    if signature in seen:
                        repeats += 1
                    seen.add(signature)
        aggregate["proposed_calls"] += proposed
        aggregate["parseable_proposals"] += parseable
        aggregate["unknown_proposals"] += proposed - parseable
        aggregate["logged_tool_starts"] += starts
        aggregate["exact_proposed_repeats"] += repeats
        aggregate["tasks_with_all_proposals_parseable"] += proposed == parseable
        aggregate["tasks_with_proposal_count_equal_logged_starts"] += proposed == starts
        aggregate["complete_tasks_with_repeat"] += proposed == parseable and repeats > 0
    if any(cohorts[name]["tasks"] != size for name, size in COHORT_SIZES.items()):
        raise RuntimeError("G2 outcome partition differs")
    print(json.dumps({"schema_version": "g002_proposed_call_coverage_read_only_v2",
                      "source_sha256": {path.name: expected for path, expected in EXPECTED.items()},
                      "cohorts": cohorts}, sort_keys=True))


def local_main() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    proc = subprocess.run(SSH, input=source, text=True, encoding="utf-8",
                          capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"G2 read-only coverage audit failed: exit {proc.returncode}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("SSH did not start with disk check")
    result = json.loads(lines[-1])
    if (result.get("schema_version") != "g002_proposed_call_coverage_read_only_v2" or
            {name: row["tasks"] for name, row in result["cohorts"].items()}
            != COHORT_SIZES):
        raise RuntimeError("G2 proposed-call coverage output differs")
    result["audit_script_sha256"] = digest(Path(__file__))
    with LOCAL_OUT.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps({"audit_sha256": digest(LOCAL_OUT),
                      "cohorts": result["cohorts"]}, sort_keys=True))


if __name__ == "__main__":
    remote_main() if sys.argv[1:] == ["--remote"] else local_main()
