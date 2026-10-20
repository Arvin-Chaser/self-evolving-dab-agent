#!/usr/bin/env python3
"""Deterministically replace invalid DAB rows with infrastructure-only retries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.dab_result_health import provider_failure


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--retry", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--retry-batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    original = read_json(args.original)
    retry = read_json(args.retry)
    batch = read_json(args.batch)
    retry_batch = read_json(args.retry_batch)
    expected_ids = batch.get("query_ids")
    retry_ids = retry_batch.get("query_ids")
    if not isinstance(expected_ids, list) or not isinstance(retry_ids, list):
        raise ValueError("both batch files must provide query_ids lists")

    original_rows = original.get("per_query_feedback")
    retry_rows = retry.get("per_query_feedback")
    if not isinstance(original_rows, list) or not isinstance(retry_rows, list):
        raise ValueError("both summaries must provide per_query_feedback lists")
    original_by_id = {row.get("query_id"): row for row in original_rows}
    retry_by_id = {row.get("query_id"): row for row in retry_rows}
    if list(retry_by_id) != retry_ids:
        raise ValueError(f"retry row order/content mismatch: {list(retry_by_id)!r}")
    if any(query_id not in original_by_id for query_id in expected_ids):
        raise ValueError("original summary does not cover the frozen batch")
    if any(query_id not in retry_by_id for query_id in retry_ids):
        raise ValueError("retry summary does not cover the frozen retry batch")
    if any(retry_by_id[query_id].get("run_exit_code") != 0 for query_id in retry_ids):
        raise ValueError("at least one retry row has a nonzero run_exit_code")
    if any(retry_by_id[query_id].get("run_error") for query_id in retry_ids):
        raise ValueError("at least one retry row still has run_error")
    if any(provider_failure(retry_by_id[query_id]) for query_id in retry_ids):
        raise ValueError("at least one retry row still has a provider/transport failure")

    rows = [retry_by_id.get(query_id, original_by_id[query_id]) for query_id in expected_ids]
    if [row.get("query_id") for row in rows] != expected_ids:
        raise ValueError("merged result order differs from frozen batch order")
    if any(row.get("run_exit_code") != 0 or row.get("run_error") for row in rows):
        raise ValueError("merged result contains an unsuccessful run")
    if any(provider_failure(row) for row in rows):
        raise ValueError("merged result contains a provider/transport failure")

    f1s = [float(row["answer_f1"]) for row in rows if isinstance(row.get("answer_f1"), (int, float))]
    problem_counts = Counter(str(row.get("selected_problem_type") or "unknown") for row in rows)
    stage_counts = Counter(str(row.get("selected_stage") or "unknown") for row in rows)
    helper_counts = Counter(
        str((row.get("helper_usage_summary") or {}).get("status") or "unknown")
        if isinstance(row.get("helper_usage_summary"), dict)
        else "unknown"
        for row in rows
    )

    merged = dict(original)
    merged.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "batch": batch,
            "batch_id": batch.get("batch_id"),
            "query_count": len(rows),
            "audit_only": False,
            "formal_result_eligible": True,
            "provider_failure_count": 0,
            "successful_run_count": len(rows),
            "final_answer_nonempty_count": sum(bool(row.get("final_answer_nonempty")) for row in rows),
            "strict_pass_count": sum(row.get("strict_match_passed") is True for row in rows),
            "average_f1": round(sum(f1s) / len(f1s), 6) if f1s else None,
            "selected_problem_type_counts": dict(problem_counts),
            "selected_stage_counts": dict(stage_counts),
            "helper_usage_status_counts": dict(helper_counts),
            "helper_registered_but_not_called_count": helper_counts.get(
                "helper_tool_registered_but_not_called", 0
            ),
            "per_query_feedback": rows,
            "execution_context": {
                **(original.get("execution_context") or {}),
                "result_merge": {
                    "type": "infrastructure_retry_row_replacement_v001",
                    "original_summary": str(args.original.resolve()),
                    "retry_summary": str(args.retry.resolve()),
                    "retry_batch": str(args.retry_batch.resolve()),
                    "replaced_query_ids": retry_ids,
                },
            },
            "artifact_paths": {
                **(original.get("artifact_paths") or {}),
                "merged_multi_query_summary": str(args.output.resolve()),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "query_count": merged["query_count"],
                "successful_run_count": merged["successful_run_count"],
                "final_answer_nonempty_count": merged["final_answer_nonempty_count"],
                "strict_pass_count": merged["strict_pass_count"],
                "average_f1": merged["average_f1"],
                "replaced_query_ids": retry_ids,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
