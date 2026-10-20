"""Audit Gen3's tool-error repair from frozen runs and build a compact Meta card."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


MECHANISM = "tool_error_observation_triggered_class_scoped_repair"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit(summary_path: Path, progress_path: Path, batch_path: Path) -> dict:
    summary, progress, batch = read(summary_path), read(progress_path), read(batch_path)
    expected = batch["query_ids"]
    summary_rows, progress_rows = summary["per_query_feedback"], progress["queries"]
    if (len(expected) != 56 or len(set(expected)) != 56
            or [row["query_id"] for row in summary_rows] != expected
            or [row["query_id"] for row in progress_rows] != expected):
        raise ValueError("Frozen 56 IDs are missing, duplicated, or reordered")
    if summary["query_count"] != 56:
        raise ValueError("Summary query count differs")

    counts, classes, decision_reasons = Counter(), Counter(), Counter()
    rows = []
    for result, progress_row in zip(summary_rows, progress_rows, strict=True):
        if result["status"] != progress_row["status"]:
            raise ValueError(f"Summary/progress status differs: {result['query_id']}")
        row = {"query_id": result["query_id"], "status": result["status"],
               "strict_match_passed": result["strict_match_passed"],
               "final_answer_nonempty": result["final_answer_nonempty"]}
        if result["status"] == "timeout":
            if (result["run_exit_code"] != 124 or result["run_error"] != "query_wall_timeout_1200s"
                    or result["terminate_reason"] != "query_wall_timeout_1200s"):
                raise ValueError(f"Unexpected timeout: {result['query_id']}")
            counts["timeout_rows"] += 1
            row["telemetry_available"] = False
        elif result["status"] == "completed":
            if result["run_exit_code"] != 0 or result["run_error"] is not None:
                raise ValueError(f"Unexpected completed-row error: {result['query_id']}")
            run = Path(result["run_dir"])
            if not run.is_dir() or run.parent != summary_path.parent / "runs":
                raise ValueError(f"Run directory outside frozen batch: {result['query_id']}")
            state_path = run / "tool_error_repair_summary.json"
            events_path = run / "tool_error_repair_events.jsonl"
            trace_path = run / "full_execution_trace.jsonl"
            state, events, trace = read(state_path), jsonl(events_path), jsonl(trace_path)
            if not events or not state.get("budget_invariant_ok"):
                raise ValueError(f"Missing decisions or failed budget invariant: {result['query_id']}")
            response_ids = [call.get("id") for item in trace if item.get("event_type") == "llm_response"
                            for call in (item.get("message", {}).get("tool_calls") or [])]
            if [item.get("tool_call_id") for item in events] != response_ids:
                raise ValueError(f"Repair decisions do not align with trace calls: {result['query_id']}")
            requests = [item for item in trace if item.get("event_type") == "llm_request"]
            per_class = Counter(item.get("failure_class") for item in events)
            if per_class != Counter(state.get("observation_class_counts", {})):
                raise ValueError(f"Observation class totals differ: {result['query_id']}")
            injected = [item for item in events if item.get("directive_applied")]
            if len(injected) != state.get("repair_injections"):
                raise ValueError(f"Injection count differs: {result['query_id']}")
            for item in injected:
                directive, index = item.get("directive_text"), item.get("llm_call_index")
                if (not directive or not isinstance(index, int)
                        or not any(directive in str(message.get("content"))
                                   for request in requests if request.get("llm_call_index", 0) > index
                                   for message in request.get("messages", []))):
                    raise ValueError(f"Directive not delivered in trace: {result['query_id']}")
            if (len(injected) > 3 or any(item.get("one_shot") is not True for item in injected)
                    or any(value > 1 for value in state.get("per_signature_directive_counts", {}).values())):
                raise ValueError(f"Repair bound violated: {result['query_id']}")
            counts.update({"completed_rows": 1, "decision_count": len(events),
                           "repair_injections": len(injected),
                           "activated_rows": int(bool(injected)),
                           "recurrence_rows": int(bool(state.get("repair_disabled_after_recurrence"))),
                           "passthrough_after_repair": state.get("passthrough_after_repair", 0),
                           "classified_error_observations": state.get("classified_error_observations", 0),
                           "ambiguous_observations": state.get("ambiguous_observations", 0)})
            classes.update(per_class)
            decision_reasons.update(item.get("decision_reason") for item in events)
            row.update({"telemetry_available": True, "event_count": len(events),
                        "repair_injections": len(injected), "repair_disabled_after_recurrence":
                        state.get("repair_disabled_after_recurrence"),
                        "event_log_sha256": sha(events_path), "state_sha256": sha(state_path),
                        "trace_sha256": sha(trace_path)})
        else:
            raise ValueError(f"Unexpected status: {result['query_id']}")
        rows.append(row)
    if (counts["completed_rows"] != summary["successful_run_count"]
            or sum(row["strict_match_passed"] is True for row in rows) != summary["strict_pass_count"]
            or sum(row["strict_match_passed"] is not None for row in rows) != summary["strict_evaluated_count"]
            or sum(row["final_answer_nonempty"] is True for row in rows) != summary["final_answer_nonempty_count"]):
        raise ValueError("Summary aggregates differ from audited rows")
    return {"schema": "dab_gen003_tool_error_terminal_audit_v1", "generation": 3,
            "mechanism_key": MECHANISM, "summary_sha256": sha(summary_path),
            "progress_sha256": sha(progress_path), "batch_sha256": sha(batch_path),
            "coverage": {"batch_rows": 56, "completed_rows": counts["completed_rows"],
                         "timeout_rows": counts["timeout_rows"],
                         "telemetry_rows": counts["completed_rows"],
                         "strict_pass_rows": summary["strict_pass_count"],
                         "strict_evaluated_rows": summary["strict_evaluated_count"],
                         "final_answer_nonempty_rows": summary["final_answer_nonempty_count"]},
            "mechanism_counters": {key: counts[key] for key in (
                "decision_count", "repair_injections", "activated_rows", "recurrence_rows",
                "passthrough_after_repair", "classified_error_observations", "ambiguous_observations")},
            "observation_class_counts": dict(classes), "decision_reason_counts": dict(decision_reasons),
            "rows": rows}


def build_card(audit_path: Path, summary_path: Path, intent_path: Path,
               candidate_ref_path: Path, launch_manifest_path: Path) -> dict:
    terminal, summary, intent = read(audit_path), read(summary_path), read(intent_path)
    candidate, launch = read(candidate_ref_path), read(launch_manifest_path)
    progress_path = summary_path.parent / "multi_query_progress.json"
    if (terminal.get("schema") != "dab_gen003_tool_error_terminal_audit_v1"
            or terminal.get("mechanism_key") != MECHANISM
            or intent.get("mechanism_key") != MECHANISM or intent.get("generation") != 3
            or terminal.get("summary_sha256") != sha(summary_path)
            or terminal.get("progress_sha256") != sha(progress_path)
            or terminal.get("batch_sha256") != launch.get("frozen_batch_sha256")):
        raise ValueError("Gen3 evidence identity/binding differs")
    if (candidate.get("source_tree_sha256") != launch.get("candidate_source_tree_sha256")
            or summary["execution_context"].get("runner_sha256") != launch.get("candidate_agent_sha256")
            or summary["execution_context"].get("batch_runner_sha256") != launch.get("evaluation_runner_sha256")):
        raise ValueError("Gen3 source/runtime binding differs")
    rows = terminal.get("rows")
    if ([row.get("query_id") for row in rows] != [row["query_id"] for row in summary["per_query_feedback"]]
            or len(rows) != 56 or len(set(row["query_id"] for row in rows)) != 56):
        raise ValueError("Gen3 audit coverage differs")
    coverage, counters = terminal["coverage"], terminal["mechanism_counters"]
    if (coverage["completed_rows"] != summary["successful_run_count"]
            or coverage["strict_pass_rows"] != summary["strict_pass_count"]
            or counters["repair_injections"] != sum(row.get("repair_injections", 0) for row in rows)
            or counters["activated_rows"] != sum(bool(row.get("repair_injections")) for row in rows)):
        raise ValueError("Gen3 compact counters differ")
    return {"schema": "dab_gen003_tool_error_mechanism_card_v1", "generation": 3,
            "mechanism_key": MECHANISM, "coverage": coverage,
            "mechanism_counters": counters,
            "observation_class_counts": terminal["observation_class_counts"],
            "decision_reason_counts": terminal["decision_reason_counts"],
            "measurement_status": {"execution_path": "trace_verified_on_completed_runs",
                                   "directive_delivery": "trace_verified" if counters["repair_injections"] else "measured_zero",
                                   "behavior_after_directive": "requires_independent_review",
                                   "causal_accuracy_gain": "not_established"},
            "evaluation_binding": {"result_type": "gen003_candidate_revision001_frozen_batch",
                                   "homogeneous_runtime": True, "human_accepted_mixed": False,
                                   "comparability": "candidate_batch_internal_only; root_parent_delta_suppressed_for_different_failure_regime",
                                   "repair_policy": "max_iterations_0; bounded class-scoped repair; runner wall timeout remains failure",
                                   "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
                                   "regimes": [{"name": "gen003_candidate_revision001", "row_count": 56,
                                                "source_sha256": candidate["source_tree_sha256"],
                                                "upstream_runtime_sha256": launch["evaluation_runner_sha256"],
                                                "input_policy": "frozen_internal_56_only",
                                                "repair_policy": "bounded_class_scoped_repair", "workers": 4}]},
            "evidence_binding": {"terminal_audit_sha256": sha(audit_path),
                                 "summary_sha256": sha(summary_path), "progress_sha256": sha(progress_path),
                                 "intent_sha256": sha(intent_path), "candidate_ref_sha256": sha(candidate_ref_path),
                                 "launch_manifest_sha256": sha(launch_manifest_path),
                                 "candidate_source_tree_sha256": candidate["source_tree_sha256"],
                                 "evaluation_runner_sha256": launch["evaluation_runner_sha256"],
                                 "frozen_batch_sha256": launch["frozen_batch_sha256"]},
            "evidence_limits": [
                "Four runner-owned timeouts have no completed-run repair telemetry.",
                "A delivered directive proves intervention, not that the next action was corrected.",
                "Aggregate strict outcomes do not establish a causal gain; seven completed runs returned empty answers.",
            ]}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit")
    for name in ("summary", "progress", "batch"):
        a.add_argument("--" + name, type=Path, required=True)
    c = sub.add_parser("card")
    for name in ("audit", "summary", "intent", "candidate_ref", "launch_manifest"):
        c.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    value = (audit(args.summary, args.progress, args.batch) if args.command == "audit" else
             build_card(args.audit, args.summary, args.intent, args.candidate_ref, args.launch_manifest))
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
