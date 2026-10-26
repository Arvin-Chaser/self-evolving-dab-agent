"""Build a compact Gen7 mechanism card from frozen trace-backed evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


MECHANISM = "wallclock_budget_governor_with_forced_evidence_commitment"


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
    if (audit.get("schema_version") != "dab_gen007_terminal_audit_v1"
            or intent.get("mechanism_key") != MECHANISM or intent.get("generation") != 7
            or audit.get("summary_sha256") != sha(summary_path)
            or audit.get("progress_sha256") != sha(progress_path)
            or audit.get("batch_sha256") != launch.get("frozen_batch_sha256")):
        raise ValueError("Gen7 audit or frozen input binding differs")
    context = summary.get("execution_context", {})
    if (candidate.get("source_tree_sha256") != launch.get("candidate_source_tree_sha256")
            or context.get("runner_sha256") != launch.get("candidate_agent_sha256")
            or context.get("batch_runner_sha256") != launch.get("evaluation_runner_sha256")):
        raise ValueError("Gen7 candidate or runner binding differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    if (len(rows) != 56 or len(progress_rows) != 56
            or [row.get("query_id") for row in rows] != [row.get("query_id") for row in progress_rows]
            or len({row.get("query_id") for row in rows}) != 56):
        raise ValueError("Gen7 summary/progress exact ID coverage differs")
    coverage = {
        "batch_rows": 56,
        "completed_rows": sum(row.get("status") == "completed" for row in rows),
        "timeout_rows": sum(row.get("status") == "timeout" for row in rows),
        "telemetry_rows": audit["telemetry_rows"],
        "strict_pass_rows": summary["strict_pass_count"],
        "strict_evaluated_rows": summary["strict_evaluated_count"],
        "final_answer_nonempty_rows": summary["final_answer_nonempty_count"],
    }
    if (coverage["completed_rows"] != audit["completed_rows"]
            or coverage["timeout_rows"] != audit["timeout_rows"]
            or coverage["telemetry_rows"] != coverage["completed_rows"]
            or coverage["strict_pass_rows"] != audit["strict_pass_rows"]
            or coverage["strict_evaluated_rows"] != audit["strict_evaluated_rows"]
            or coverage["final_answer_nonempty_rows"] != audit["nonempty_answer_rows"]
            or audit["missing_or_mismatched_query_ids"] or audit["over_budget_rows"]):
        raise ValueError("Gen7 coverage, telemetry, or render bound differs")
    channel, trajectory = audit["channel_counter_totals"], audit["trajectory_counter_totals"]
    governor = audit["governor_counter_totals"]
    if (audit["request_rows"] != coverage["completed_rows"]
            or channel["preflight_sequences_checked"] != audit["request_sequences_verified"]
            or channel["directives_attached_to_observation"]
               + governor["commitment_block_attached_count"] != audit["directive_blocks_in_final_context"]
            or audit["governor_committed_rows"] != governor["commitment_entered_count"]
            or audit["governor_attached_rows"] != governor["commitment_block_attached_count"]
            or audit["governor_completed_row_denominator"] != coverage["completed_rows"]
            or audit["governor_event_mismatch_rows"] or audit["governor_invariant_failure_rows"]
            or audit["request_protocol_violation_rows"] or audit["final_protocol_violation_rows"]
            or audit["provider_400_rows"] or channel["standalone_directive_messages"]
            or channel["protocol_preflight_failures"] or channel["preflight_pairing_violations"]
            or audit["max_actual_tool_message_chars"] > 1200 or trajectory["raw_passthrough_chars"]):
        raise ValueError("Gen7 governor, protocol, or render invariant differs")
    if (audit["rows_exceeding_gen5_call_maxima"] != ["krama/query3"]
            or audit["max_tool_calls_per_row"] != 174 or audit["max_llm_calls_per_row"] != 139):
        raise ValueError("Gen7 resource regression evidence differs")
    evaluation_binding = {
        "result_type": "gen007_candidate_revision001_frozen_batch",
        "homogeneous_runtime": True,
        "human_accepted_mixed": False,
        "comparability": "candidate_batch_internal_only; no matched control; causal strict delta suppressed",
        "repair_policy": "max_iterations_0; runner wall timeout remains failure; no heterogeneous reruns",
        "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
        "regimes": [{
            "name": "gen007_candidate_revision001", "row_count": 56,
            "source_sha256": candidate["source_tree_sha256"],
            "upstream_runtime_sha256": launch["evaluation_runner_sha256"],
            "input_policy": "frozen_internal_56_only", "workers": 4,
        }],
    }
    return {
        "schema": "dab_gen007_budget_governor_mechanism_card_v1",
        "generation": 7,
        "mechanism_key": MECHANISM,
        "coverage": coverage,
        "channel_counters": channel,
        "trajectory_counters": trajectory,
        "governor_counters": governor,
        "governor_committed_rows": audit["governor_committed_rows"],
        "governor_completed_row_denominator": audit["governor_completed_row_denominator"],
        "governor_attached_rows": audit["governor_attached_rows"],
        "governor_block_budget_exhausted_rows": audit["governor_block_budget_exhausted_rows"],
        "governor_event_mismatch_rows": 0,
        "governor_invariant_failure_rows": 0,
        "directive_blocks_in_final_context": audit["directive_blocks_in_final_context"],
        "max_actual_tool_message_chars": audit["max_actual_tool_message_chars"],
        "render_budget_chars": 1200,
        "request_sequences_verified": audit["request_sequences_verified"],
        "request_protocol_violation_rows": 0,
        "provider_bad_request_400_rows": 0,
        "max_tool_calls_per_row": audit["max_tool_calls_per_row"],
        "max_llm_calls_per_row": audit["max_llm_calls_per_row"],
        "rows_exceeding_gen5_call_maxima": audit["rows_exceeding_gen5_call_maxima"],
        "timeout_query_ids": audit["timeout_query_ids"],
        "measurement_status": {
            "execution_path": "actual_upstream_probe_and_52_completed_run_traces_verified",
            "activation": "7_of_52_completed_rows_committed;_17_exploratory_calls_blocked;_1_block_budget_exhausted",
            "protocol": "2039_recorded_requests_structurally_valid;_zero_provider_400_rows",
            "render_bound": "actual_tool_role_messages_bounded_on_52_completed_runs",
            "task_effect": "descriptive_32_of_50_strict_and_52_nonempty;_no_matched_control_or_causal_claim",
        },
        "evaluation_binding": evaluation_binding,
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
            "Four runner-owned 1200s timeouts have no terminal governor telemetry; their activation is unknown, not zero.",
            "The governor committed on 7/52 completed rows and blocked 17 exploratory calls, but its six-block budget was exhausted on one row.",
            "krama/query3 reached 174 tool and 139 LLM calls: tool calls exceed Gen5's 139 and Gen6's 162 maxima, while LLM calls exceed Gen5's 115 but not Gen6's 151; the resource invariant did not hold.",
            "The governor triggered on krama/query3 only after 722s and 173 dispatched calls; the final strict result was false.",
            "Zero protocol violations and a 1197-character maximum establish structural safety only on this completed batch, not a general guarantee.",
            "Descriptive 32/50 strict and 52/56 nonempty outcomes cannot establish a causal gain without a matched control; F1 and 48 held-out queries were not supplied to Meta.",
        ],
    }
