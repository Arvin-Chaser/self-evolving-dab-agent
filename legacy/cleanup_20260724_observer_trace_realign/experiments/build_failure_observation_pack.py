#!/usr/bin/env python3
"""Build an evidence-grounded failure observation pack for a candidate.

This script does not repair anything.  It mechanically aligns candidate patch
changes, child-eval metrics, per-query feedback, tool-call failures, and answer
artifacts so a downstream Failure Observer can describe what actually happened
without relying only on pre-baked stage/signal labels.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"_read_error": type(exc).__name__, "path": str(path), "error": str(exc)}


def read_text(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if limit is None else text[:limit]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def extract_patch_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            files.append(line.split(" b/", 1)[1].strip())
    return sorted(set(files))


def extract_registry_targets(patch_text: str) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    pending_name: str | None = None
    for line_no, line in enumerate(patch_text.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        text = line[1:].strip()
        name_match = re.search(r"""["']name["']\s*:\s*["']([^"']+)["']""", text)
        if name_match:
            pending_name = name_match.group(1)
        function_match = re.search(r"""["']function["']\s*:\s*["']([^"']+:[^"']+)["']""", text)
        if function_match:
            value = function_match.group(1)
            module, func = value.split(":", 1)
            targets.append(
                {
                    "name": pending_name,
                    "target": value,
                    "module": module,
                    "function": func,
                    "patch_line": line_no,
                    "source": "patch.diff.added_registry_function",
                }
            )
            pending_name = None
    return targets


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                row["_line"] = line_no
                rows.append(row)
        except json.JSONDecodeError:
            rows.append({"_line": line_no, "_raw": line[:500], "_parse_error": "JSONDecodeError"})
    return rows


def compact_failure_text(value: Any, limit: int = 700) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def extract_tool_failures(run_dir: Path) -> list[dict[str, Any]]:
    rows = iter_jsonl(run_dir / "tool_calls.jsonl")
    failures: list[dict[str, Any]] = []
    for row in rows:
        success = row.get("success")
        result = row.get("result")
        error = row.get("error") or row.get("exception")
        if success is False or error:
            failures.append(
                {
                    "line": row.get("_line"),
                    "tool_name": row.get("tool_name") or row.get("name"),
                    "success": success,
                    "error": compact_failure_text(error or result),
                    "raw_preview": compact_failure_text(row),
                }
            )
    return failures[:20]


def summarize_query_feedback(row: dict[str, Any], registry_targets: list[dict[str, Any]]) -> dict[str, Any]:
    aq = row.get("answer_quality") if isinstance(row.get("answer_quality"), dict) else {}
    helper = row.get("helper_usage_summary") if isinstance(row.get("helper_usage_summary"), dict) else {}
    run_dir = Path(str(row.get("run_dir") or ""))
    final_answer = read_text(run_dir / "final_answer.txt", limit=1200) if row.get("run_dir") else ""
    raw_answer = read_text(run_dir / "raw_final_answer.txt", limit=1200) if row.get("run_dir") else ""
    helper_samples = helper.get("helper_call_samples") if isinstance(helper.get("helper_call_samples"), list) else []
    helper_failure_previews = [
        compact_failure_text(sample.get("result_preview"))
        for sample in helper_samples
        if isinstance(sample, dict) and ("success': False" in str(sample.get("result_preview")) or '"success": false' in str(sample.get("result_preview")).lower())
    ]
    matched_registry_errors: list[dict[str, Any]] = []
    joined_error_text = "\n".join(helper_failure_previews)
    for target in registry_targets:
        if target["module"] in joined_error_text and target["function"] in joined_error_text:
            matched_registry_errors.append(
                {
                    "target": target["target"],
                    "name": target.get("name"),
                    "matched_error_preview": compact_failure_text(joined_error_text),
                    "inferred_pattern": "registered_helper_target_failed_at_runtime",
                }
            )
    return {
        "query_id": row.get("query_id"),
        "domain": row.get("domain"),
        "status": row.get("status"),
        "terminate_reason": row.get("terminate_reason"),
        "final_answer_nonempty": row.get("final_answer_nonempty"),
        "run_exit_code": row.get("run_exit_code"),
        "analyze_exit_code": row.get("analyze_exit_code"),
        "selected_stage": row.get("selected_stage"),
        "selected_signal": row.get("selected_signal"),
        "selected_problem_type": row.get("selected_problem_type"),
        "answer_quality": {
            "metric_type": aq.get("metric_type"),
            "strict_match_passed": aq.get("strict_match_passed"),
            "strict_match_reason": aq.get("strict_match_reason"),
            "missing_count": aq.get("missing_count"),
            "extra_count": aq.get("extra_count"),
            "precision": aq.get("precision"),
            "recall": aq.get("recall"),
            "f1": aq.get("f1"),
            "missing_codes_sample": aq.get("missing_codes_sample"),
            "extra_codes_sample": aq.get("extra_codes_sample"),
        },
        "helper_usage": {
            "status": helper.get("status"),
            "registered_helper_names": helper.get("registered_helper_names"),
            "helper_call_count": helper.get("helper_call_count"),
            "helper_failure_previews": helper_failure_previews[:5],
            "matched_registry_errors": matched_registry_errors,
        },
        "tool_failures": extract_tool_failures(run_dir) if row.get("run_dir") else [],
        "final_answer_preview": compact_failure_text(final_answer or raw_answer),
        "artifact_paths": {
            "run_dir": str(run_dir) if row.get("run_dir") else None,
            "feedback_summary": str(run_dir / "feedback_summary.json") if row.get("run_dir") else None,
            "tool_calls": str(run_dir / "tool_calls.jsonl") if row.get("run_dir") else None,
            "final_answer": str(run_dir / "final_answer.txt") if row.get("run_dir") else None,
        },
    }


def infer_candidate_patterns(pack: dict[str, Any]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    query_summaries = pack.get("query_summaries") if isinstance(pack.get("query_summaries"), list) else []
    if pack.get("registry_targets_added"):
        any_match = any(
            qs.get("helper_usage", {}).get("matched_registry_errors")
            for qs in query_summaries
            if isinstance(qs, dict)
        )
        if any_match:
            patterns.append(
                {
                    "pattern": "helper_registry_callable_mismatch",
                    "confidence": 0.96,
                    "evidence": [
                        "patch.diff added helper registry target(s)",
                        "runtime helper call failed with matching module/function error",
                    ],
                }
            )
    delta = pack.get("parent_child_delta") if isinstance(pack.get("parent_child_delta"), dict) else {}
    if delta.get("delta_tool_failure_count", 0) and delta.get("delta_tool_failure_count", 0) > 0:
        patterns.append(
            {
                "pattern": "introduced_tool_failure_regression",
                "confidence": 0.9,
                "evidence": [f"delta_tool_failure_count={delta.get('delta_tool_failure_count')}"],
            }
        )
    if delta.get("delta_final_answer_nonempty_count", 0) and delta.get("delta_final_answer_nonempty_count", 0) < 0:
        patterns.append(
            {
                "pattern": "lost_final_answer_after_patch",
                "confidence": 0.88,
                "evidence": [f"delta_final_answer_nonempty_count={delta.get('delta_final_answer_nonempty_count')}"],
            }
        )
    for qs in query_summaries:
        aq = qs.get("answer_quality") if isinstance(qs.get("answer_quality"), dict) else {}
        if isinstance(aq.get("f1"), (int, float)) and float(aq.get("f1")) <= 0 and aq.get("missing_count"):
            patterns.append(
                {
                    "pattern": "answer_set_overlap_collapsed",
                    "confidence": 0.86,
                    "query_id": qs.get("query_id"),
                    "evidence": [
                        f"f1={aq.get('f1')}",
                        f"missing_count={aq.get('missing_count')}",
                        f"extra_count={aq.get('extra_count')}",
                    ],
                }
            )
    return patterns


def build_pack(candidate_dir: Path) -> dict[str, Any]:
    candidate_dir = candidate_dir.resolve()
    patch_text = read_text(candidate_dir / "patch.diff")
    manifest = read_json(candidate_dir / "manifest.json", {})
    state = read_json(candidate_dir / "candidate_state.json", {})
    child_eval = read_json(candidate_dir / "child_eval/child_eval_report.json", {})
    summary = child_eval.get("child_multi_query_summary") if isinstance(child_eval.get("child_multi_query_summary"), dict) else {}
    registry_targets = extract_registry_targets(patch_text)
    per_query = summary.get("per_query_feedback") if isinstance(summary.get("per_query_feedback"), list) else []
    pack = {
        "schema_version": "failure_observation_pack_v001",
        "created_at": utc_now(),
        "candidate_id": candidate_dir.name,
        "candidate_dir": str(candidate_dir),
        "status": state.get("status") or child_eval.get("final_status") or manifest.get("status"),
        "changed_files": manifest.get("project_changed_files") or extract_patch_files(patch_text),
        "patch_files": extract_patch_files(patch_text),
        "registry_targets_added": registry_targets,
        "child_eval_status": child_eval.get("final_status"),
        "child_failure_gates": child_eval.get("child_failure_gates") or [],
        "parent_child_delta": child_eval.get("parent_child_delta") or {},
        "multi_query_summary": {
            "query_count": summary.get("query_count"),
            "successful_run_count": summary.get("successful_run_count"),
            "final_answer_nonempty_count": summary.get("final_answer_nonempty_count"),
            "average_f1": summary.get("average_f1"),
            "selected_problem_type_counts": summary.get("selected_problem_type_counts"),
            "selected_stage_counts": summary.get("selected_stage_counts"),
            "helper_usage_status_counts": summary.get("helper_usage_status_counts"),
        },
        "query_summaries": [summarize_query_feedback(row, registry_targets) for row in per_query if isinstance(row, dict)],
        "artifact_paths": {
            "patch": str(candidate_dir / "patch.diff"),
            "manifest": str(candidate_dir / "manifest.json"),
            "candidate_state": str(candidate_dir / "candidate_state.json"),
            "child_eval_report": str(candidate_dir / "child_eval/child_eval_report.json"),
        },
    }
    pack["candidate_failure_patterns"] = infer_candidate_patterns(pack)
    return pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output", help="Defaults to <candidate-dir>/failure_observation_pack.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidate_dir = Path(args.candidate_dir)
    output = Path(args.output) if args.output else candidate_dir / "failure_observation_pack.json"
    pack = build_pack(candidate_dir)
    write_json(output, pack)
    print(json.dumps({"status": "ok", "output": str(output), "patterns": pack.get("candidate_failure_patterns")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
