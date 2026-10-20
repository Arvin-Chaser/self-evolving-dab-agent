"""Build a compact, hash-bound Gen2 tool-economy card for Meta review."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


MECHANISM = "pre_dispatch_tool_call_dedup_and_failure_signature_memoization"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def build_card(audit_path: Path, summary_path: Path, intent_path: Path,
               candidate_ref_path: Path, launch_manifest_path: Path) -> dict:
    audit = read(audit_path)
    summary = read(summary_path)
    intent = read(intent_path)
    candidate = read(candidate_ref_path)
    launch = read(launch_manifest_path)
    progress_path = summary_path.parent / "multi_query_progress.json"
    progress = read(progress_path)
    if (intent.get("generation") != 2 or intent.get("mechanism_key") != MECHANISM
        or audit.get("schema") != "dab_gen002_terminal_audit_v1"
        or audit.get("generation") != 2 or audit.get("mechanism_key") != MECHANISM):
        raise ValueError("Gen2 evidence identity differs")
    bindings = {
        "summary_sha256": sha(summary_path),
        "progress_sha256": sha(progress_path),
        "intent_sha256": sha(intent_path),
        "candidate_ref_sha256": sha(candidate_ref_path),
        "launch_manifest_sha256": sha(launch_manifest_path),
        "candidate_source_tree_sha256": candidate["source_tree_sha256"],
        "evaluation_runner_sha256": launch["evaluation_runner_sha256"],
        "frozen_batch_sha256": launch["frozen_batch_sha256"],
    }
    if any(audit.get(key) != value for key, value in bindings.items()):
        raise ValueError("Gen2 audit binding differs")
    if audit.get("summary_bytes") != summary_path.stat().st_size:
        raise ValueError("Gen2 summary byte count differs")
    if candidate["source_tree_sha256"] != launch["candidate_source_tree_sha256"]:
        raise ValueError("Candidate/launch source hash differs")
    context = summary["execution_context"]
    if (context.get("runner_sha256") != launch["candidate_agent_sha256"]
        or context.get("batch_runner_sha256") != launch["evaluation_runner_sha256"]):
        raise ValueError("Runtime hashes differ")
    rows = audit.get("rows")
    expected_ids = [row["query_id"] for row in summary["per_query_feedback"]]
    if (not isinstance(rows, list) or len(rows) != 56 or len(set(expected_ids)) != 56
        or [row.get("query_id") for row in rows] != expected_ids
        or [row.get("query_id") for row in progress["queries"]] != expected_ids):
        raise ValueError("Gen2 row coverage differs")
    coverage = audit["coverage"]
    complete = sum(row["status"] == "completed" for row in rows)
    timeouts = sum(row["status"] == "timeout" for row in rows)
    if (complete != 52 or timeouts != 4 or coverage.get("batch_rows") != 56
        or coverage.get("completed_rows") != complete or coverage.get("timeout_rows") != timeouts
        or coverage.get("telemetry_rows") != complete
        or coverage.get("strict_pass_rows") != summary["strict_pass_count"]
        or coverage.get("strict_evaluated_rows") != summary["strict_evaluated_count"]):
        raise ValueError("Gen2 coverage or summary aggregate differs")
    if any((row["status"] == "timeout" and (row.get("run_exit_code") != 124
            or row.get("terminate_reason") != "query_wall_timeout_1200s"
            or row.get("memo_telemetry_available") is not False))
           or (row["status"] == "completed" and (row.get("run_exit_code") != 0
            or row.get("memo_telemetry_available") is not True
            or not row.get("memo_sha256"))) for row in rows):
        raise ValueError("Gen2 terminal/telemetry row differs")
    action_counts = Counter()
    for row in rows:
        action_counts.update(row.get("actions") or {})
    counters = audit["mechanism_counters"]
    if (counters.get("decision_count") != sum(row.get("decision_count", 0) for row in rows)
        or counters.get("decision_count") != sum(action_counts.values())
        or counters.get("intercepted_call_count") != action_counts["memo_replay"] + action_counts["repeat_failure"]
        or counters.get("intercepted_rows") != action_counts["memo_replay"]
        or counters.get("strategy_change_injections") != action_counts["repeat_failure"]
        or counters.get("duplicate_signatures") != sum(row.get("duplicate_signatures", 0) for row in rows)):
        raise ValueError("Gen2 mechanism counters differ")
    activation = counters["intercepted_call_count"]
    return {
        "schema": "dab_gen002_mechanism_evidence_card_v1",
        "generation": 2,
        "mechanism_key": MECHANISM,
        "coverage": coverage,
        "mechanism_counters": counters,
        "action_counts": dict(action_counts),
        "classification_counts": audit["classification_counts"],
        "classification_reason_counts": audit["classification_reason_counts"],
        "measurement_status": {
            "execution_path": "observed_on_52_completed_runs",
            "interception": "observed" if activation else "measured_zero_on_52_completed_runs",
            "duplicate_signature_opportunity": "observed" if counters["duplicate_signatures"] else "measured_zero_by_candidate_signature",
            "runner_owned_timeouts": "4_recorded_failures_no_telemetry",
            "causal_accuracy_gain": "not_established",
        },
        "evaluation_binding": {
            "result_type": "gen002_candidate_revision001_frozen_batch",
            "homogeneous_runtime": True,
            "human_accepted_mixed": False,
            "comparability": "candidate_batch_internal_only; root_parent_delta_suppressed_for_different_failure_regime",
            "repair_policy": "max_iterations_0; bounded pre-dispatch memo; runner wall timeout remains failure",
            "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
            "regimes": [{"name": "gen002_candidate_revision001", "row_count": 56,
                         "source_sha256": candidate["source_tree_sha256"],
                         "upstream_runtime_sha256": launch["evaluation_runner_sha256"],
                         "input_policy": "frozen_internal_56_only", "repair_policy": "bounded_pre_dispatch_memo",
                         "workers": 4}],
        },
        "evidence_binding": {"terminal_audit_sha256": sha(audit_path), **bindings},
        "evidence_limits": [
            "Candidate signature telemetry measures no duplicate signatures or interceptions on 52 completed runs; it does not prove semantically equivalent calls never occurred.",
            "Four runner-owned 1200-second timeouts remain failures and have no completed-run memo telemetry.",
            "A source preflight proved synthetic reachability, not activation in this frozen evaluation.",
            "Strict outcomes are descriptive; no matched control establishes a causal accuracy effect.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("audit", "summary", "intent", "candidate_ref", "launch_manifest", "output"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    card = build_card(args.audit, args.summary, args.intent, args.candidate_ref, args.launch_manifest)
    args.output.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "measurement_status": card["measurement_status"]}))


if __name__ == "__main__":
    main()
