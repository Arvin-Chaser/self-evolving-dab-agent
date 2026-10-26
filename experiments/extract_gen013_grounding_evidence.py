"""Bind answer-blind Gen13 grounding telemetry to its frozen result."""

import argparse
import hashlib
import json
from pathlib import Path


MECHANISM = "bounded_runtime_referent_grounding_prefetch"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_card(audit_path, summary_path, intent_path):
    audit, summary, intent = (read(path) for path in (audit_path, summary_path, intent_path))
    rows = summary["per_query_feedback"]
    completed = [row for row in rows if row["status"] == "completed"]
    timed_out = [row for row in rows if row["status"] == "timeout"]
    candidate = read(intent_path.parent / "candidate_ref_revision_001.json")
    launch_path = intent_path.parent / "deployment_grounding_r3/launch_manifest.json"
    launch = read(launch_path)
    coverage = audit["mechanism_trace_coverage"]
    if (audit["schema_version"] != "gen013_grounding_terminal_audit_v1"
            or intent["mechanism_key"] != MECHANISM or intent["generation"] != 13
            or audit["summary_sha256"] != sha(summary_path)
            or audit["exact_ids"] != len(rows) or not audit["ids_match_order"]
            or len(rows) != 56 or audit["completed"] != len(completed)
            or audit["runner_timeout_1200s"] != len(timed_out)
            or audit["strict_pass"] != sum(row.get("strict_match_passed") is True for row in completed)
            or coverage.get("completed_present") != len(completed)
            or coverage.get("timeout_present") != len(timed_out)
            or launch["source_tree_sha256"] != candidate["source_tree_sha256"]
            or launch["intent_sha256"] != intent["canonical_json_sha256"]):
        raise ValueError("Gen13 terminal evidence bindings or counts differ")
    completed_counts = audit["completed_mechanism_counts"]
    timeout_counts = audit["partial_timeout_mechanism_counts"]
    for key, total in audit["mechanism_counts"].items():
        if completed_counts.get(key, 0) + timeout_counts.get(key, 0) != total:
            raise ValueError("Gen13 mechanism accounting differs: " + key)
    assert completed_counts["grounding_injected_rows"] <= len(completed)
    assert completed_counts["dispatches_refused_by_this_mechanism"] == 0
    assert completed_counts["forced_commitments"] == 0
    return {
        "schema": "gen013_grounding_mechanism_evidence_v1",
        "generation": 13,
        "mechanism_key": MECHANISM,
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "original_summary_sha256": sha(summary_path),
            "sealed_intent_file_sha256": sha(intent_path),
            "candidate_tree_sha256": candidate["source_tree_sha256"],
            "launch_manifest_sha256": sha(launch_path),
        },
        "coverage": {
            "frozen_tasks": 56,
            "completed_tasks_with_mechanism_trace": len(completed),
            "timeout_tasks_with_partial_mechanism_trace": len(timed_out),
            "scored_completed_tasks": audit["strict_scored"],
        },
        "mechanism_counters": completed_counts,
        "partial_timeout_mechanism_counters": timeout_counts,
        "skip_reasons": audit["mechanism_skip_reasons"],
        "completed_tasks_with_injection": completed_counts["grounding_injected_rows"],
        "measurement_status": {
            "integration": "observed_on_completed_runs",
            "intervention": "observed_initial_context_injection",
            "timeout_mechanism_state": "partial_trace_present_terminal_state_unknown",
            "causal_accuracy_gain": "not_established",
        },
        "evidence_limits": audit["limitations"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(build_card(args.audit, args.summary, args.intent), indent=2,
                                sort_keys=True) + "\n")
