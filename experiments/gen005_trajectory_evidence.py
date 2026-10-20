"""Build a compact Meta card from Gen5's trace-backed terminal audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MECHANISM = "trajectory_information_gain_stall_bounding_with_fact_ledger"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def build_card(audit_path: Path, summary_path: Path, intent_path: Path,
               candidate_ref_path: Path, launch_manifest_path: Path) -> dict:
    audit, summary, intent = read(audit_path), read(summary_path), read(intent_path)
    candidate, launch = read(candidate_ref_path), read(launch_manifest_path)
    progress_path = summary_path.parent / "multi_query_progress.json"
    progress = read(progress_path)
    if (audit.get("schema_version") != "dab_gen005_terminal_audit_v1"
            or intent.get("mechanism_key") != MECHANISM or intent.get("generation") != 5
            or audit.get("summary_sha256") != sha(summary_path)
            or audit.get("batch_sha256") != launch.get("frozen_batch_sha256")):
        raise ValueError("Gen5 audit or frozen input binding differs")
    if (candidate.get("source_tree_sha256") != launch.get("candidate_source_tree_sha256")
            or summary["execution_context"].get("runner_sha256") != launch.get("candidate_agent_sha256")
            or summary["execution_context"].get("batch_runner_sha256") != launch.get("evaluation_runner_sha256")):
        raise ValueError("Gen5 candidate or runner binding differs")
    rows = summary.get("per_query_feedback", [])
    progress_rows = progress.get("queries", [])
    if (len(rows) != 56 or [row.get("query_id") for row in rows] !=
            [row.get("query_id") for row in progress_rows] or
            len({row.get("query_id") for row in rows}) != 56):
        raise ValueError("Gen5 summary/progress exact ID coverage differs")
    coverage = {
        "batch_rows": 56,
        "completed_rows": sum(row.get("status") == "completed" for row in rows),
        "timeout_rows": sum(row.get("status") == "timeout" for row in rows),
        "telemetry_rows": audit["telemetry_rows"],
        "strict_pass_rows": summary["strict_pass_count"],
        "strict_evaluated_rows": summary["strict_evaluated_count"],
        "final_answer_nonempty_rows": summary["final_answer_nonempty_count"],
    }
    if (coverage["completed_rows"] != audit["completed_rows"] or
            coverage["timeout_rows"] != audit["timeout_rows"] or
            coverage["telemetry_rows"] != coverage["completed_rows"] or
            coverage["strict_pass_rows"] != audit["strict_pass_rows"] or
            coverage["strict_evaluated_rows"] != audit["strict_evaluated_rows"] or
            coverage["final_answer_nonempty_rows"] != audit["nonempty_answer_rows"] or
            audit["missing_telemetry_query_ids"] or audit["over_budget_rows"]):
        raise ValueError("Gen5 coverage, telemetry, or render bound differs")
    failures = audit["provider_tool_protocol_failure_rows"]
    if (len(failures) != 11 or
            any(row["tool_protocol_violations"] < 1 for row in failures) or
            len(audit["tool_protocol_violation_rows"]) != len(failures)):
        raise ValueError("Gen5 tool-protocol failure trace binding differs")
    trajectory_interleavings = sum(row["first"]["intervening_trajectory_directive"] for row in failures)
    repair_interleavings = sum(row["first"]["intervening_gen3_repair_directive"] for row in failures)
    if trajectory_interleavings != 3 or repair_interleavings != 8:
        raise ValueError("Gen5 directive attribution differs")
    counters = audit["mechanism_counter_totals"]
    if (counters["stalls_detected"] != 6 or counters["directives_injected"] != 6 or
            counters["consolidations_forced"] != 0 or counters["readonly_scope_blocks"] != 0 or
            counters["first_use_blocks"] != 0 or counters["raw_passthrough_chars"] != 0 or
            audit["actual_max_tool_message_chars"] > 1200):
        raise ValueError("Gen5 mechanism counters or render bound differ")
    return {
        "schema": "dab_gen005_trajectory_mechanism_card_v1",
        "generation": 5,
        "mechanism_key": MECHANISM,
        "coverage": coverage,
        "mechanism_counters": counters,
        "max_actual_tool_message_chars": audit["actual_max_tool_message_chars"],
        "render_budget_chars": 1200,
        "directive_present_in_model_context_rows": audit["directive_present_in_model_context_rows"],
        "consolidation_present_in_model_context_rows": audit["consolidation_present_in_model_context_rows"],
        "candidate_protocol_failure_count": len(failures),
        "protocol_failure_attribution": {
            "gen3_repair_directive_interleavings": repair_interleavings,
            "gen5_trajectory_directive_interleavings": trajectory_interleavings,
            "all_failures_have_malformed_tool_response_sequence": True,
        },
        "measurement_status": {
            "execution_path": "trajectory_log_and_final_message_sequence_verified_on_51_completed_runs",
            "activation": "six_stalls_six_directives_no_second_stall_consolidations_or_scope_blocks",
            "render_bound": "actual_tool_role_messages_bounded_on_51_completed_runs",
            "task_effect": "no_gain_established; eleven_candidate_induced_tool_protocol_terminal_failures",
        },
        "evaluation_binding": {
            "result_type": "gen005_candidate_revision001_frozen_batch",
            "homogeneous_runtime": True,
            "human_accepted_mixed": False,
            "comparability": "candidate_batch_internal_only; no matched control; causal strict delta suppressed",
            "repair_policy": "max_iterations_0; runner wall timeout remains failure; 400 tool-protocol errors remain failed rows",
            "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
            "regimes": [{
                "name": "gen005_candidate_revision001", "row_count": 56,
                "source_sha256": candidate["source_tree_sha256"],
                "upstream_runtime_sha256": launch["evaluation_runner_sha256"],
                "input_policy": "frozen_internal_56_only", "workers": 4,
            }],
        },
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "summary_sha256": sha(summary_path),
            "progress_sha256": sha(progress_path),
            "intent_sha256": sha(intent_path),
            "candidate_ref_sha256": sha(candidate_ref_path),
            "launch_manifest_sha256": sha(launch_manifest_path),
            "candidate_source_tree_sha256": candidate["source_tree_sha256"],
            "evaluation_runner_sha256": launch["evaluation_runner_sha256"],
            "frozen_batch_sha256": launch["frozen_batch_sha256"],
        },
        "evidence_limits": [
            "Five runner-owned timeouts have no completed-run trajectory telemetry.",
            "The 1200-char tool-message bound held, but the ledger's intended second-stall consolidation and scope blocking never activated.",
            "Eleven 400 errors have exact malformed message-sequence evidence: eight inherited Gen3 repair directives and three Gen5 trajectory directives were inserted before all tool responses. These are candidate protocol failures, not proven provider infrastructure failures.",
            "No matched control supports a causal strict-accuracy comparison; do not reuse this source as a validated improvement.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--candidate-ref", type=Path, required=True)
    parser.add_argument("--launch-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    card = build_card(args.audit, args.summary, args.intent, args.candidate_ref, args.launch_manifest)
    if args.output.exists():
        raise SystemExit(f"Evidence card already exists: {args.output}")
    args.output.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "built", "card": str(args.output), "sha256": sha(args.output)}))


if __name__ == "__main__":
    main()
