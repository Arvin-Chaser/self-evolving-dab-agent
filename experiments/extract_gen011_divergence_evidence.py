"""Bind Gen11's answer-blind divergence telemetry to its frozen result."""

import argparse
import hashlib
import json
from pathlib import Path


MECHANISM = "executed_evidence_divergence_reconciliation_note"


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
    launch_path = intent_path.parent / "deployment_divergence_r1/launch_manifest.json"
    launch = read(launch_path)
    if (audit["schema_version"] != "gen011_divergence_terminal_audit_v1"
            or intent["mechanism_key"] != MECHANISM or intent["generation"] != 11
            or audit["summary_sha256"] != sha(summary_path)
            or audit["exact_ids"] != len(rows) or not audit["ids_match_order"]
            or len(rows) != 56 or audit["completed"] != len(completed)
            or audit["runner_timeout_1200s"] != len(timed_out)
            or audit["strict_pass"] != sum(row.get("strict_match_passed") is True for row in completed)
            or audit["mechanism_trace_coverage"].get("completed_present") != len(completed)
            or audit["mechanism_trace_coverage"].get("timeout_missing") != len(timed_out)
            or launch["source_tree_sha256"] != candidate["source_tree_sha256"]
            or launch["intent_sha256"] != intent["canonical_json_sha256"]):
        raise ValueError("Gen11 terminal evidence bindings or counts differ")
    counts = audit["mechanism_counts"]
    if counts["notes_emitted"] != sum(row["notes_emitted"] for row in audit["mechanism_activation_rows"]):
        raise ValueError("Gen11 note accounting differs")
    return {
        "schema": "gen011_divergence_mechanism_evidence_v1",
        "generation": 11,
        "mechanism_key": MECHANISM,
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "original_summary_sha256": sha(summary_path),
            "sealed_intent_file_sha256": sha(intent_path),
            "candidate_tree_sha256": candidate["source_tree_sha256"],
            "launch_manifest_sha256": sha(launch_path),
        },
        "coverage": {"frozen_tasks": 56,
                     "completed_tasks_with_mechanism_trace": len(completed),
                     "timeout_tasks_without_mechanism_trace": len(timed_out),
                     "scored_completed_tasks": audit["strict_scored"]},
        "mechanism_counters": counts,
        "fail_open_reasons": audit["mechanism_fail_open_reasons"],
        "tasks_with_intervention": len(audit["mechanism_activation_rows"]),
        "measurement_status": {
            "integration": "observed_on_completed_runs",
            "intervention": "observed" if counts["notes_emitted"] else "measured_zero_on_completed_runs",
            "timeout_mechanism_state": "unknown",
            "causal_accuracy_gain": "not_established",
        },
        "evidence_limits": audit["limitations"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(build_card(args.audit, args.summary, args.intent), indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    else:
        print(encoded, end="")
