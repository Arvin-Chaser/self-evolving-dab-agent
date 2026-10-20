"""Build a bounded, model-free mechanism evidence card from a terminal audit.

This tool reads immutable local evidence and writes only a JSON card to stdout.
It does not invoke a model, database, review, result recorder, or graph writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "dab_mechanism_evidence_card_v1"
COUNTERS = (
    "obligation_created",
    "advancing_results",
    "completion",
    "continuation_requested",
    "bound_reached",
    "pass_through",
)
REQUIRED_CHECKS = (
    "actual_execution_paths",
    "progress_contract_schema_counters",
    "final_generic_state_exact",
    "final_durable_counters",
    "source_intent_parent_input_model_binding",
)


def _read_json(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value, raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_card(audit_path: Path, summary_path: Path, intent_path: Path) -> dict:
    audit, audit_raw = _read_json(audit_path)
    summary, summary_raw = _read_json(summary_path)
    intent, intent_raw = _read_json(intent_path)
    remote = audit.get("remote")
    if not isinstance(remote, dict):
        raise ValueError("Terminal audit has no remote evidence object")
    summary_sha = _sha(summary_raw)
    if audit.get("summary_sha256") != summary_sha or remote.get("summary_sha256") != summary_sha:
        raise ValueError("Original summary SHA256 does not match both audit bindings")
    if audit.get("summary_bytes") != len(summary_raw):
        raise ValueError("Original summary byte length does not match audit")
    if not (audit.get("formal_result_eligible") is True
            and remote.get("complete") is True
            and remote.get("healthy_full17_eligible") is True
            and remote.get("global_full_narrow_admitted_upstream_frozen17_bindings_valid") is True):
        raise ValueError("Terminal audit does not establish a complete, healthy bound batch")
    if audit.get("Graph_or_Meta_launched") is not False:
        raise ValueError("Unexpected review/Graph state in pre-review evidence")
    if intent.get("mechanism_key") != "observable_tool_progress_contract":
        raise ValueError("This extractor only understands the observable progress contract")
    if not isinstance(intent.get("generation"), int):
        raise ValueError("Missing generation binding")
    rows = remote.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing audited rows")
    indices = [row.get("task_index") for row in rows if isinstance(row, dict)]
    if indices != list(range(1, len(rows) + 1)):
        raise ValueError("Audited rows are missing, duplicated, or out of order")
    health = audit.get("local_health")
    if not isinstance(health, dict) or health.get("normal") != len(rows):
        raise ValueError("Normal row count does not cover the audited batch")
    if health.get("strict") != sum(row.get("strict") is True for row in rows):
        raise ValueError("Strict row count does not match audited rows")
    if any(health.get(name) != 0 for name in ("run_errors", "analysis_errors", "provider_termination")):
        raise ValueError("Terminal health contains errors")
    if not isinstance(summary.get("per_query_feedback"), list) or len(summary["per_query_feedback"]) != len(rows):
        raise ValueError("Original summary row count differs from the terminal audit")

    totals = {name: 0 for name in COUNTERS}
    positive_tasks = {name: 0 for name in COUNTERS}
    for row in rows:
        checks = row.get("checks")
        if not isinstance(checks, dict) or any(checks.get(name) is not True for name in REQUIRED_CHECKS):
            raise ValueError("An audited row lacks a required mechanism/binding check")
        if row.get("audit_errors") != [] or row.get("normal") is not True:
            raise ValueError("An audited row is unhealthy or has audit errors")
        counters = row.get("progress_counters")
        if not isinstance(counters, dict):
            raise ValueError("An audited row lacks progress counters")
        for name in COUNTERS:
            value = counters.get(name)
            if type(value) is not int or value < 0:
                raise ValueError(f"Invalid progress counter: {name}")
            totals[name] += value
            positive_tasks[name] += int(value > 0)

    n = len(rows)
    return {
        "schema": SCHEMA,
        "generation": intent["generation"],
        "mechanism_key": intent["mechanism_key"],
        "run_id": audit.get("run_id"),
        "evidence_binding": {
            "terminal_audit_sha256": _sha(audit_raw),
            "original_summary_sha256": summary_sha,
            "sealed_intent_file_sha256": _sha(intent_raw),
        },
        "coverage": {
            "audited_tasks": n,
            "mechanism_state_verified_tasks": n,
            "normal_tasks": health["normal"],
            "strict_pass_tasks": health["strict"],
            "terminal_error_tasks": 0,
        },
        "mechanism_counters": totals,
        "tasks_with_positive_counter": positive_tasks,
        "measurement_status": {
            "state_bookkeeping": "observed" if totals["obligation_created"] else "measured_zero",
            "continuation_intervention": (
                "observed" if totals["continuation_requested"] else "measured_zero"
            ),
            "eligible_content_opportunity_denominator": "not_instrumented",
            "behavior_after_intervention": (
                "requires_independent_review" if totals["continuation_requested"] else "not_observable_without_intervention"
            ),
            "causal_accuracy_gain": "not_established",
        },
        "evidence_limits": [
            "Obligation creation is not the denominator for content-ending opportunities.",
            "A zero continuation counter is measured non-activation, not missing activation data.",
            "Aggregate strict-pass results do not identify a causal mechanism effect.",
        ],
        "review_or_graph_started_by_extractor": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_card(args.audit, args.summary, args.intent), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
