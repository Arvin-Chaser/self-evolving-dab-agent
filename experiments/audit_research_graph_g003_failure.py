#!/usr/bin/env python3
"""Audit the frozen G3 terminal metadata without emitting task content."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G3 = BASE / "g003_revision001"
RUN_ID = "baseline_g003_proposed_calls_nohint_56_v1"
RUN = G3 / "evaluation" / RUN_ID
TREE_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    paths = {
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "claim": BASE / "graph/g003_launch_claim.json",
        "launch": BASE / "graph/g003_launch_manifest.json",
        "pre_execution": BASE / "graph/g003_pre_execution.json",
    }
    if any(not path.is_file() for path in paths.values()):
        raise RuntimeError("G3 terminal artifact missing")
    summary, progress = read(paths["summary"]), read(paths["progress"])
    claim, launch = read(paths["claim"]), read(paths["launch"])
    pre = read(paths["pre_execution"])
    rows = progress.get("queries", [])
    final_rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (summary.get("query_count") != 56 or len(rows) != 56 or len(final_rows) != 56 or
            {row.get("run_id") for row in rows} != {row.get("run_id") for row in final_rows} or
            len({row.get("run_id") for row in rows}) != 56 or
            context.get("db_description_mode") != "base" or
            context.get("query_timeout_sec") != 1200 or
            context.get("source_root") != str(G3 / "source") or
            context.get("runner_sha256") != launch["binding"]["agent_sha256"] or
            context.get("batch_runner_sha256") != launch["binding"]["runner_sha256"] or
            claim["binding"] != launch["binding"] or
            launch["binding"]["candidate_tree_sha256"] != TREE_SHA or
            launch.get("pre_execution_sha256") != digest(paths["pre_execution"]) or
            pre.get("binding") != launch["binding"] or
            len(pre.get("nodes", [])) != 3 or
            {node.get("kind") for node in pre["nodes"]} !=
            {"problem", "hypothesis", "experiment"}):
        raise RuntimeError("G3 terminal binding or protocol differs")
    if any(row.get("status") != "completed" or row.get("run_exit_code") != 0 or
           row.get("final_answer_nonempty") is not False or
           row.get("tool_call_count") != 0 or
           row.get("llm_call_count") != 1 or
           not (row.get("terminate_reason") or "").startswith("llm_response_failed") or
           "(APIConnectionError):" not in (row.get("terminate_reason") or "")
           for row in rows):
        raise RuntimeError("G3 failure pattern is not uniform; inspect without content exposure")
    if any(row.get("strict_match_passed") is True for row in rows):
        raise RuntimeError("G3 unexpected strict pass")
    if any(RUN.rglob("g003_proposed_calls.jsonl")):
        raise RuntimeError("G3 unexpected live diagnostic sidecar")
    print(json.dumps({
        "status": "evaluation_invalid_model_connection",
        "ended": 56, "runner_completed": 56, "runner_timeout": 0,
        "model_connection_failures": 56, "tool_calls": 0,
        "nonempty_answers": 0, "sidecar_files": 0,
        "strict_true": 0,
        "strict_unknown_completed": sum(row.get("strict_match_passed") is None for row in rows),
        "fixed_denominator": 56,
        "protocol": "exact56_base_nohint_1200s",
        "source_tree_sha256": TREE_SHA,
        "artifact_sha256": {name: digest(path) for name, path in paths.items()},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
