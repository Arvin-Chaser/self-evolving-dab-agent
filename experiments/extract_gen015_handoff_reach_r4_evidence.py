"""Project bound Gen15 r4 handoff facts without query IDs or answers."""

import argparse
import hashlib
import json
from pathlib import Path


MECHANISM = "two_phase_frozen_evidence_handoff"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_card(audit_path, summary_path, ref_path, intent_path):
    audit, summary, ref, intent = (read(path) for path in (audit_path, summary_path, ref_path, intent_path))
    launch_path = ref_path.parent / "deployment_revision_001/launch_manifest.json"
    launch = read(launch_path)
    rows = summary["per_query_feedback"]
    completed = [row for row in rows if row["status"] == "completed"]
    timeouts = [row for row in rows if row["status"] == "timeout"]
    coverage = audit["mechanism_coverage"]
    states = [row["state"] for row in audit["mechanism_rows"]]
    if (audit.get("schema") != "gen015_handoff_reach_r4_terminal_audit_v1"
            or not all(audit.get(key) is True for key in (
                "complete", "natural_end", "hashes_verified", "ids_match_order", "transmitted_protocol_verified"))
            or ref.get("schema") != "dab_engineering_repair_ref_v1"
            or ref["branch_id"] != audit["branch_id"] != launch["branch_id"]
            or intent.get("generation") != 15 or intent.get("mechanism_key") != MECHANISM
            or intent["canonical_json_sha256"] != audit["intent_sha256"]
            or ref["sealed_intent_sha256"] != audit["intent_sha256"]
            or ref["code_parent_branch_node_id"] != "repair_gen015_handoff_reach_r2"
            or ref["source_tree_sha256"] != audit["source_tree_sha256"] != launch["source_tree_sha256"]
            or ref["parent_source_tree_sha256"] != audit["parent_source_tree_sha256"]
            or ref["repair_delta_sha256"] != audit["repair_delta_sha256"]
            or audit["summary_sha256"] != sha(summary_path)
            or audit["launch_manifest_sha256"] != sha(launch_path)
            or len(rows) != 56 or len({row["query_id"] for row in rows}) != 56
            or len(completed) + len(timeouts) != 56
            or audit["completed"] != len(completed) or audit["runner_timeout"] != len(timeouts)
            or audit["strict_pass"] != sum(row.get("strict_match_passed") is True for row in completed)
            or coverage.get("completed_present") != len(completed)
            or len(states) != len(completed)):
        raise ValueError("Gen15 repair terminal evidence binding differs")
    if any(not all(state[key] is True for key in (
            "bundle_render_bounded_invariant_ok", "composition_context_bounded_invariant_ok",
            "no_raw_passthrough_invariant_ok",
            "no_standalone_gate_message_invariant_ok")) for state in states):
        raise ValueError("Gen15 repair mechanism invariant failed")
    transient = sum(state["phase_b_fallback_restored_transcript_invariant_ok"] is not True for state in states)
    if coverage.get("fallback_restore_transient_false_rows") != transient:
        raise ValueError("Fallback snapshot coverage differs from audited rows")
    return {
        "schema": "gen015_handoff_reach_r4_mechanism_evidence_v1",
        "branch_id": ref["branch_id"], "generation_reference": 15, "mechanism_key": MECHANISM,
        "evidence_binding": {"terminal_audit_sha256": sha(audit_path),
            "original_summary_sha256": sha(summary_path), "repair_ref_sha256": sha(ref_path),
            "sealed_intent_file_sha256": sha(intent_path),
            "launch_manifest_sha256": sha(launch_path),
            "candidate_tree_sha256": ref["source_tree_sha256"],
            "parent_tree_sha256": ref["parent_source_tree_sha256"]},
        "coverage": coverage, "mechanism_counters": audit["completed_mechanism_counts"],
        "phase_a_refusal_rows": coverage.get("phase_a_refusal_rows", 0),
        "early_finalization_deferred_rows": coverage.get("early_finalization_deferred_rows", 0),
        "compaction_rows": coverage.get("compaction_rows", 0),
        "compaction_delivered_rows": coverage.get("compaction_delivered_rows", 0),
        "bounded_composition_observation_rows": coverage.get("bounded_composition_observation_rows", 0),
        "composition_observation_suppression_rows": coverage.get("composition_observation_suppression_rows", 0),
        "fallback_reasons": audit["fallback_reasons"],
        "termination_reasons": audit["termination_reasons"],
        "static_dynamic_total_chars": {
            "first_request_static": audit["first_request_context_chars"],
            "max_composition_static": max((s["composition_static_context_chars"] for s in states), default=0),
            "max_composition_dynamic": max((s["max_composition_dynamic_chars"] for s in states), default=0),
            "max_composition_total": max((s["max_composition_context_chars"] for s in states), default=0),
            "dynamic_cap": 12000, "absolute_total_cap": 48000},
        "measurement_status": {
            "integration": "observed_on_completed_runs",
            "activation": "positive" if coverage.get("context_rebuild_rows") else "measured_zero",
            "request_delivery": "positive" if coverage.get("composition_request_rows") else "measured_zero",
            "verification_compaction": "positive" if coverage.get("compaction_rows") else "measured_zero",
            "compacted_request_delivery": "positive" if coverage.get("compaction_delivered_rows") else "measured_zero",
            "bounded_verification_delivery": "positive" if coverage.get("bounded_composition_observation_rows") else "measured_zero",
            "fallback_restore_snapshot": "confounded" if transient else "positive",
            "semantic_model_uptake": "unknown_not_measured",
            "timeout_mechanism_state": "partial_or_unknown_not_zero",
            "causal_accuracy_gain": "not_established"},
        "evaluation_binding": {"homogeneous_runtime": True, "input_policy": "base_only_no_hint",
            "comparability": "single frozen run; unmatched strict outcomes cannot isolate stochastic effects"},
        "evidence_limits": audit["limitations"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("audit", "summary", "ref", "intent", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(build_card(args.audit, args.summary, args.ref, args.intent), stream, indent=2, sort_keys=True)
