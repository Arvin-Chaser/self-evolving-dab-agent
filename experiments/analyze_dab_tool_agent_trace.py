#!/usr/bin/env python3
"""Analyze DAB tool-agent workflow artifacts into generic feedback observations.

This analyzer is the first zero-start bridge from DAB workflow logs to the
meta-agent evidence layer.  It intentionally avoids PATENTS/CPC-specific rules.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "path": str(path)}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            value = {"_parse_error": str(exc), "line_no": line_no, "raw": line}
        rows.append(value if isinstance(value, dict) else {"value": value})
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def observation(
    problem_id: str,
    *,
    stage: str,
    problem_type: str,
    severity: str,
    evidence: dict[str, Any],
    confidence: float,
    uncertainty: str,
    suggested_targets: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "problem_id": problem_id,
        "stage": stage,
        "problem_type": problem_type,
        "severity": severity,
        "evidence": evidence,
        "confidence": confidence,
        "uncertainty": uncertainty,
        "suggested_targets": suggested_targets,
        "rationale": rationale,
    }


def result_is_empty(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, dict):
        if result.get("success") is False:
            return False
        values = [result[key] for key in ("result", "preview") if key in result]
        if not values:
            return False
        return all(value in (None, "", [], {}, "[]") for value in values)
    if result in ("", [], {}, "[]"):
        return True
    return False


def analyze_run(run_dir: Path) -> dict[str, Any]:
    summary = read_json(run_dir / "summary.json", {})
    workflow_trace = read_jsonl(run_dir / "workflow_trace.jsonl")
    llm_calls = read_jsonl(run_dir / "llm_calls.jsonl")
    tool_calls = read_jsonl(run_dir / "tool_calls.jsonl")
    final_agent = read_json(run_dir / "final_agent.json", {})
    validation_rows = read_jsonl(run_dir / "validation.jsonl")
    final_answer = read_text(run_dir / "final_answer.txt")

    observations: list[dict[str, Any]] = []
    tool_names = [row.get("tool_name") for row in tool_calls if row.get("tool_name")]
    tool_counter = Counter(tool_names)
    failed_tool_calls = []
    empty_tool_calls = []

    for idx, row in enumerate(tool_calls, start=1):
        result = row.get("result")
        success = result.get("success") if isinstance(result, dict) else row.get("success")
        if success is False:
            failed_tool_calls.append({"index": idx, "tool_name": row.get("tool_name"), "result": result})
        elif result_is_empty(result):
            empty_tool_calls.append({"index": idx, "tool_name": row.get("tool_name"), "result": result})

    if summary.get("run_error"):
        observations.append(observation(
            "run_error",
            stage="run_execution",
            problem_type="run_error",
            severity="error",
            evidence={"run_error": summary.get("run_error")},
            confidence=0.95,
            uncertainty="The wrapper captured an exception, but downstream cause may require log inspection.",
            suggested_targets=["runner", "tool_environment", "data_agent_wrapper"],
            rationale="The run terminated with an explicit wrapper-level error.",
        ))

    if not str(final_answer).strip():
        observations.append(observation(
            "no_final_answer",
            stage="answer_submission",
            problem_type="missing_final_answer",
            severity="warning",
            evidence={"final_answer_path": str(run_dir / "final_answer.txt"), "terminate_reason": summary.get("terminate_reason")},
            confidence=0.9,
            uncertainty="A short smoke run may intentionally stop before answer generation.",
            suggested_targets=["prompt", "tool_policy", "iteration_budget"],
            rationale="The normalized final answer is empty.",
        ))

    if summary.get("terminate_reason") == "max_iterations" or "max_iterations" in str(summary.get("terminate_reason")):
        observations.append(observation(
            "max_iterations_reached",
            stage="workflow_control",
            problem_type="budget_exhausted",
            severity="info",
            evidence={"llm_call_count": summary.get("llm_call_count"), "terminate_reason": summary.get("terminate_reason")},
            confidence=0.9,
            uncertainty="May be expected for smoke tests with intentionally low max_iterations.",
            suggested_targets=["iteration_budget", "prompt", "tool_policy"],
            rationale="The agent stopped because the iteration limit was reached.",
        ))

    if not llm_calls and not workflow_trace:
        observations.append(observation(
            "no_llm_activity",
            stage="llm_call",
            problem_type="no_llm_call_recorded",
            severity="error" if not summary.get("run_error") else "warning",
            evidence={"llm_calls_path": str(run_dir / "llm_calls.jsonl"), "workflow_trace_count": len(workflow_trace)},
            confidence=0.85,
            uncertainty="The run may have failed before DataAgent startup or logs may be missing.",
            suggested_targets=["runner", "model_client", "logging"],
            rationale="No LLM activity was recorded.",
        ))

    llm_without_tool = []
    for idx, row in enumerate(workflow_trace, start=1):
        if row.get("event") == "llm_call" and int(row.get("tool_call_count") or 0) == 0:
            llm_without_tool.append({"index": row.get("index", idx), "has_content": row.get("has_content")})
    if llm_without_tool:
        observations.append(observation(
            "llm_no_tool_call",
            stage="tool_selection",
            problem_type="llm_did_not_call_tool",
            severity="warning",
            evidence={"llm_without_tool": llm_without_tool[:5], "count": len(llm_without_tool)},
            confidence=0.8,
            uncertainty="Some providers may encode tool calls differently; inspect raw llm_calls if needed.",
            suggested_targets=["prompt", "model_tool_protocol", "tool_schema"],
            rationale="At least one LLM turn did not produce a tool call in the normalized workflow trace.",
        ))

    if not tool_calls:
        observations.append(observation(
            "no_tool_calls",
            stage="tool_execution",
            problem_type="no_tool_call_recorded",
            severity="warning",
            evidence={"tool_calls_path": str(run_dir / "tool_calls.jsonl")},
            confidence=0.85,
            uncertainty="May be expected if the run failed before the first tool execution.",
            suggested_targets=["prompt", "model_tool_protocol", "runner"],
            rationale="No tool calls were recorded.",
        ))

    if tool_counter and set(tool_counter) <= {"list_db"}:
        observations.append(observation(
            "only_list_db_no_query_db",
            stage="tool_selection",
            problem_type="insufficient_data_retrieval",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.75,
            uncertainty="A short exploratory run may only inspect schema; longer runs may query later.",
            suggested_targets=["prompt", "tool_policy", "iteration_budget"],
            rationale="The agent inspected databases but did not retrieve data rows.",
        ))

    if tool_counter.get("query_db", 0) == 0:
        observations.append(observation(
            "query_db_never_called",
            stage="tool_selection",
            problem_type="missing_data_query",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.7,
            uncertainty="Some tasks may be answerable without query_db, but DAB data tasks usually need evidence retrieval.",
            suggested_targets=["prompt", "tool_policy"],
            rationale="No query_db call was observed.",
        ))

    if tool_counter.get("execute_python", 0) == 0:
        observations.append(observation(
            "execute_python_never_called",
            stage="tool_selection",
            problem_type="missing_local_computation",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.65,
            uncertainty="Some simple tasks may not need Python, but complex benchmark queries often do.",
            suggested_targets=["prompt", "tool_policy", "helper_tools"],
            rationale="No execute_python call was observed.",
        ))

    if failed_tool_calls:
        observations.append(observation(
            "tool_call_failed",
            stage="tool_execution",
            problem_type="tool_failure",
            severity="error",
            evidence={"failed_tool_calls": failed_tool_calls[:5], "count": len(failed_tool_calls)},
            confidence=0.95,
            uncertainty="Failure may be caused by tool args, environment, database, or generated code.",
            suggested_targets=["tool_args", "tool_environment", "prompt", "helper_tools"],
            rationale="One or more tool calls returned success=false.",
        ))

    if empty_tool_calls:
        observations.append(observation(
            "empty_tool_result",
            stage="tool_execution",
            problem_type="empty_result",
            severity="warning",
            evidence={"empty_tool_calls": empty_tool_calls[:5], "count": len(empty_tool_calls)},
            confidence=0.75,
            uncertainty="An empty result can be correct for some queries; compare with query intent and later tool usage.",
            suggested_targets=["query_logic", "schema_grounding", "prompt"],
            rationale="One or more successful tool calls produced an empty-looking result.",
        ))

    if validation_rows:
        failed_validation = [row for row in validation_rows if row.get("success") is False or row.get("status") in {"failed", "error"}]
        if failed_validation:
            observations.append(observation(
                "validation_failed",
                stage="validation",
                problem_type="answer_validation_failed",
                severity="error",
                evidence={"failed_validation": failed_validation[:3], "count": len(failed_validation)},
                confidence=0.9,
                uncertainty="Validator output should be inspected for answer-level details.",
                suggested_targets=["answer_logic", "prompt", "helper_tools"],
                rationale="Validation artifacts indicate failure.",
            ))

    feedback_summary = {
        "schema_version": "dab_tool_agent_feedback_summary_v001",
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "status": summary.get("status"),
        "terminate_reason": summary.get("terminate_reason"),
        "final_answer_nonempty": bool(str(final_answer).strip()),
        "llm_call_count": summary.get("llm_call_count") or len(llm_calls),
        "tool_call_count": summary.get("tool_call_count") or len(tool_calls),
        "tool_counts": dict(tool_counter),
        "observation_count": len(observations),
        "problem_types": dict(Counter(row["problem_type"] for row in observations)),
        "severities": dict(Counter(row["severity"] for row in observations)),
    }

    meta_agent_seed = {
        "schema_version": "dab_tool_agent_meta_agent_seed_v001",
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "zero_start_profile": "meta_agent/zero_start_data_agent_profile.md",
        "allowed_initial_tools": ["list_db", "query_db", "execute_python", "return_answer"],
        "forbidden_initial_domain_helpers": ["cpc_level_helper", "ema_helper", "patents_schema_helper", "metadata_parser_helper"],
        "feedback_summary": feedback_summary,
        "top_observations": observations[:8],
        "instruction": (
            "Use these observations as evidence for DataAgent evolution. Do not treat them as fixed repair decisions. "
            "Prefer generic prompt/tool/logging/analyzer improvements unless repeated evidence justifies a domain helper."
        ),
    }

    return {
        "summary": summary,
        "final_agent": final_agent,
        "feedback_summary": feedback_summary,
        "observations": observations,
        "meta_agent_seed": meta_agent_seed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Path to logs/dab_tool_agent/<run_id>.")
    parser.add_argument("--output-dir", help="Defaults to --run-dir.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_dir
    result = analyze_run(run_dir)
    write_json(output_dir / "observations.json", result["observations"])
    write_json(output_dir / "feedback_summary.json", result["feedback_summary"])
    write_json(output_dir / "meta_agent_seed.json", result["meta_agent_seed"])
    print(json.dumps(result["feedback_summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
