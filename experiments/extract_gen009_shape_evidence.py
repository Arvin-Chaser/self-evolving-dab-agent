"""Bind Gen9's answer-blind mechanism audit to the immutable formal result."""

import argparse
import hashlib
import json
from pathlib import Path


MECHANISM = "bounded_preflight_source_shape_card"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_card(audit_path, summary_path, intent_path):
    audit, summary, intent = (read(path) for path in
                              (audit_path, summary_path, intent_path))
    rows = summary["per_query_feedback"]
    completed = [row for row in rows if row["status"] == "completed"]
    if (audit["schema_version"] != "gen009_shape_terminal_audit_v1"
            or intent["mechanism_key"] != MECHANISM or intent["generation"] != 9
            or audit["summary_sha256"] != sha(summary_path)
            or audit["intent_sha256"] != intent["canonical_json_sha256"]
            or audit["source_tree_sha256"] !=
                read(intent_path.parent / "candidate_ref.json")["source_tree_sha256"]
            or audit["exact_ids"] != len(rows) or len(rows) != 56
            or not audit["ids_match_order"]
            or audit["completed"] != len(completed)
            or audit["runner_timeout_1200s"] != len(rows) - len(completed)
            or audit["strict_pass"] != sum(row.get("strict_match_passed") is True for row in completed)
            or audit["mechanism_trace_coverage"].get("completed_present") != len(completed)):
        raise ValueError("Gen9 terminal evidence bindings or counts differ")
    counts = audit["mechanism_counts"]
    if (counts["dispatches_short_circuited"] != counts["corrections_issued"]
            or counts["dispatches_short_circuited"] !=
                sum(row["short_circuited"] for row in audit["mechanism_activation_rows"])):
        raise ValueError("Mechanism activation accounting differs")
    return {
        "schema": "gen009_shape_mechanism_evidence_v1",
        "generation": 9,
        "mechanism_key": MECHANISM,
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "original_summary_sha256": sha(summary_path),
            "sealed_intent_file_sha256": sha(intent_path),
        },
        "coverage": {
            "frozen_tasks": 56,
            "completed_tasks_with_mechanism_trace": len(completed),
            "timeout_tasks_without_mechanism_trace": audit["runner_timeout_1200s"],
            "scored_completed_tasks": audit["strict_scored"],
        },
        "mechanism_counters": counts,
        "classification_counts": audit["mechanism_classifications"],
        "tasks_with_intervention": len(audit["mechanism_activation_rows"]),
        "measurement_status": {
            "integration": "observed_on_completed_runs",
            "intervention": "observed_once",
            "timeout_mechanism_state": "unknown",
            "causal_accuracy_gain": "not_established",
        },
        "evidence_limits": audit["limitations"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(build_card(args.audit, args.summary, args.intent),
                         sort_keys=True, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
