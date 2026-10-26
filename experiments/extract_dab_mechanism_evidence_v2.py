"""Bounded Gen10 failure-triggered steering evidence from a terminal audit.

Reads only already-audited compact local metadata. No model, database, trace,
review, Graph, or benchmark execution is performed by this extractor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "dab_mechanism_evidence_card_v2"
MECHANISM = "failure_triggered_obligation_steering"
COUNTERS = (
    "obligation_created", "advancing_results", "completion",
    "continuation_requested", "pass_through", "bound_reached",
    "eligible_intervention_opportunity", "intervention_raised",
    "intervention_bound_reached", "bookkeeping_degraded",
)
REQUIRED_CHECKS = (
    "actual_execution_paths", "progress_contract_schema_counters",
    "final_generic_state_exact", "final_durable_counters",
    "source_intent_parent_input_model_binding",
)


def _load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Bound evidence is not a JSON object")
    return value, raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_card(audit_path: Path, summary_path: Path, intent_path: Path) -> dict:
    audit, audit_raw = _load(audit_path)
    summary, summary_raw = _load(summary_path)
    intent, intent_raw = _load(intent_path)
    remote = audit.get("remote")
    if not isinstance(remote, dict) or intent.get("generation") != 10 or (
        intent.get("mechanism_key") != MECHANISM
    ):
        raise ValueError("Gen10 intent or remote evidence binding differs")
    summary_sha = _sha(summary_raw)
    if audit.get("summary_sha256") != summary_sha or remote.get("summary_sha256") != summary_sha or (
        audit.get("summary_bytes") != len(summary_raw)
    ):
        raise ValueError("Original summary byte binding differs")
    if audit.get("formal_result_eligible") is not True or (
        remote.get("complete") is not True or remote.get("healthy_full17_eligible") is not True
    ) or remote.get("global_full_narrow_admitted_upstream_frozen17_bindings_valid") is not True or (
        audit.get("Graph_or_Meta_launched") is not False
    ):
        raise ValueError("Terminal audit is not a healthy bound pre-review batch")
    if remote.get("forced_injection_synthetic_test_passed") is not True:
        raise ValueError("Bound synthetic forced-injection preflight is not verified")
    health = audit.get("local_health")
    rows = remote.get("rows")
    feedback = summary.get("per_query_feedback")
    if not isinstance(health, dict) or not isinstance(rows, list) or len(rows) != 17 or (
        not isinstance(feedback, list) or len(feedback) != 17
    ) or [row.get("task_index") for row in rows] != list(range(1, 18)) or (
        health.get("normal") != 17
    ) or any(health.get(name) != 0 for name in ("run_errors", "analysis_errors", "provider_termination")) or (
        health.get("strict") != sum(row.get("strict") is True for row in rows)
    ):
        raise ValueError("Terminal row coverage/health differs")
    totals = dict.fromkeys(COUNTERS, 0)
    positive = dict.fromkeys(COUNTERS, 0)
    for row in rows:
        checks = row.get("checks")
        if row.get("normal") is not True or row.get("audit_errors") != [] or (
            not isinstance(checks, dict) or any(checks.get(name) is not True for name in REQUIRED_CHECKS)
        ):
            raise ValueError("A terminal row lacks required checked Gen10 mechanism evidence")
        counters = row.get("progress_counters")
        if not isinstance(counters, dict) or set(counters) != set(COUNTERS):
            raise ValueError("Gen10 progress counter set is incomplete or contains extra fields")
        for name in COUNTERS:
            value = counters[name]
            if type(value) is not int or value < 0:
                raise ValueError("Gen10 progress counter invalid: " + name)
            totals[name] += value
            positive[name] += int(value > 0)
    if totals["continuation_requested"] > totals["intervention_raised"] or (
        totals["intervention_raised"] > totals["eligible_intervention_opportunity"]
    ):
        raise ValueError("Gen10 intervention counters exceed measured opportunities")
    return {
        "schema": SCHEMA,
        "generation": 10,
        "mechanism_key": MECHANISM,
        "run_id": audit.get("run_id"),
        "evidence_binding": {
            "terminal_audit_sha256": _sha(audit_raw),
            "original_summary_sha256": summary_sha,
            "sealed_intent_file_sha256": _sha(intent_raw),
        },
        "coverage": {
            "audited_tasks": 17,
            "mechanism_state_verified_tasks": 17,
            "normal_tasks": 17,
            "strict_pass_tasks": health["strict"],
            "terminal_error_tasks": 0,
        },
        "mechanism_counters": totals,
        "tasks_with_positive_counter": positive,
        "measurement_status": {
            "state_bookkeeping": "observed" if totals["obligation_created"] else "measured_zero",
            "eligible_tool_failure_opportunity_denominator": (
                "observed" if totals["eligible_intervention_opportunity"] else "measured_zero"
            ),
            "continuation_intervention": (
                "observed" if totals["continuation_requested"] else "measured_zero"
            ),
            "forced_injection_reachability": "verified_synthetic_not_real_activation",
            "behavior_after_intervention": (
                "requires_independent_review" if totals["continuation_requested"]
                else "no_continuation_observed_despite_raised_obligations"
            ),
            "causal_accuracy_gain": "not_established",
        },
        "evidence_limits": [
            "The eligible-opportunity denominator is measured from the candidate's own classified tool results, not an independent observer of all potential failures.",
            "A forced-injection self-test proves a synthetic path is reachable, not that the intervention activated in real tasks.",
            "The intervention-to-opportunity ratio is descriptive; aggregate strict accuracy cannot establish a causal effect without a controlled same-runtime comparison.",
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
