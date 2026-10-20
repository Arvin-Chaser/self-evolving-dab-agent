"""Bind Gen8 divergence-governor evidence to the frozen evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


MECHANISM = "cost_normalized_divergence_commitment_trigger"


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
    counts = audit["counts"]
    rows = summary["per_query_feedback"]
    progress_rows = progress["queries"]
    context = summary["execution_context"]
    if (audit.get("schema_version") != "dab_gen008_divergence_terminal_audit_v001"
            or intent.get("generation") != 8 or intent.get("mechanism_key") != MECHANISM
            or audit.get("summary_sha256") != sha(summary_path)
            or audit.get("progress_sha256") != sha(progress_path)
            or audit.get("batch_sha256") != launch.get("frozen_batch_sha256")
            or candidate.get("source_tree_sha256") != launch.get("candidate_source_tree_sha256")
            or context.get("runner_sha256") != launch.get("candidate_agent_sha256")
            or context.get("batch_runner_sha256") != launch.get("evaluation_runner_sha256")):
        raise ValueError("Gen8 frozen audit, intent, candidate, or runtime binding differs")
    ids = [row.get("query_id") for row in rows]
    if (len(ids) != 56 or len(set(ids)) != 56 or not audit.get("exact_56_id_order")
            or ids != [row.get("query_id") for row in progress_rows]
            or ids != [row.get("query_id") for row in audit["per_query_metrics"]]
            or audit.get("missing_or_invalid") or audit.get("protocol_failures")
            or audit.get("provider_error_rows") or audit.get("oversize_tool_message_rows")):
        raise ValueError("Gen8 coverage or protocol audit differs")
    completed = sum(row.get("status") == "completed" for row in rows)
    timeouts = sum(row.get("status") == "timeout" for row in rows)
    scored = sum(isinstance(row.get("strict_match_passed"), bool) for row in rows)
    passed = sum(row.get("strict_match_passed") is True for row in rows)
    if (completed != 50 or timeouts != 6 or scored != 47 or passed != 27
            or counts["status_completed"] != completed or counts["status_timeout"] != timeouts
            or counts["strict_evaluated"] != scored or counts["strict_pass"] != passed
            or counts["nonempty"] != summary["final_answer_nonempty_count"]
            or counts["governor_telemetry_rows"] != 56
            or counts["recorded_requests"] != counts["preflight_sequences_checked"]
            or counts["protocol_preflight_failures"] or counts["preflight_pairing_violations"]
            or counts["standalone_directive_messages"] or counts["fail_closed_turns"]
            or counts["provider_rounds_added"] or counts["tool_calls_added"]
            or counts["commitment_block_attached"] != len(audit["commitment_rows"])
            or counts["commitment_unattachable"]
            or counts["exploratory_calls_blocked"] != sum(row["blocked"] for row in audit["commitment_rows"])
            or audit["completed_governor_opportunity_denominator"] != completed
            or len(audit["timeout_with_governor_telemetry"]) != timeouts
            or audit["max_actual_tool_message_chars"] > 1200):
        raise ValueError("Gen8 mechanism or metric invariants differ")
    return {
        "schema": "dab_gen008_divergence_mechanism_card_v1",
        "generation": 8,
        "mechanism_key": MECHANISM,
        "coverage": {
            "batch_rows": 56, "completed_rows": completed, "timeout_rows": timeouts,
            "strict_pass_rows": passed, "strict_evaluated_rows": scored,
            "non_timeout_strict_denominator": completed,
            "non_timeout_strict_pass_rate": passed / completed,
            "nonempty_answer_rows": counts["nonempty"],
            "unscored_non_timeout_rows": len(audit["unscored_non_timeout_query_ids"]),
        },
        "activation": {
            "completed_opportunity_rows": completed,
            "committed_rows": len(audit["commitment_rows"]),
            "exploratory_calls_blocked": counts["exploratory_calls_blocked"],
            "commitment_blocks_attached": counts["commitment_block_attached"],
            "timeout_rows_with_governor_telemetry": len(audit["timeout_with_governor_telemetry"]),
            "commitment_rows": audit["commitment_rows"],
        },
        "safety": {
            "recorded_requests": counts["recorded_requests"],
            "protocol_violation_rows": 0,
            "provider_error_rows": 0,
            "max_actual_tool_message_chars": audit["max_actual_tool_message_chars"],
            "max_tool_calls_per_row": audit["max_tool_calls_per_row"],
            "max_llm_calls_per_row": audit["max_llm_calls_per_row"],
        },
        "evaluation_binding": {
            "result_type": "gen008_divergence_revision002_frozen_batch",
            "homogeneous_runtime": True,
            "human_accepted_mixed": False,
            "comparability": "candidate_batch_internal_only; no matched control; causal strict delta suppressed",
            "repair_policy": "max_iterations_0; runner wall timeout remains failure; no heterogeneous reruns",
            "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
            "regimes": [{
                "name": "gen008_divergence_revision002", "row_count": 56,
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
            "Commitment was observed in 4/50 completed rows, so most completed trajectories did not test its behavioral effect.",
            "Six runner-owned 1200s timeouts have telemetry but no completed strict verdict.",
            "Three non-timeout rows lack strict verdicts; the stopping denominator is all 50 completed rows, not 47 scored rows.",
            "27/50 strict is descriptive only; no matched control or held-out evaluation establishes a causal gain.",
        ],
    }
