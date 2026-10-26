"""Build the bounded, model-free evidence card for DeepSeek campaign Gen1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MECHANISM = "evidence_grounded_answer_gate_with_bounded_requery"
SCHEMA = "dab_gen001_mechanism_evidence_card_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value, raw


def build_card(audit_path: Path, summary_path: Path, intent_path: Path,
               candidate_ref_path: Path, launch_manifest_path: Path) -> dict:
    audit, audit_raw = read(audit_path)
    summary, summary_raw = read(summary_path)
    intent, intent_raw = read(intent_path)
    candidate, candidate_raw = read(candidate_ref_path)
    launch, launch_raw = read(launch_manifest_path)

    if intent.get("generation") != 1 or intent.get("mechanism_key") != MECHANISM:
        raise ValueError("Gen1 intent identity differs")
    if audit.get("schema") != "dab_gen001_terminal_audit_v1":
        raise ValueError("Unexpected Gen1 terminal audit schema")
    if audit.get("generation") != 1 or audit.get("mechanism_key") != MECHANISM:
        raise ValueError("Gen1 terminal audit identity differs")
    if audit.get("summary_sha256") != sha(summary_path) or audit.get("summary_bytes") != len(summary_raw):
        raise ValueError("Terminal audit is not bound to the immutable summary")
    if audit.get("progress_sha256") != sha(summary_path.parent / "multi_query_progress.json"):
        raise ValueError("Terminal audit is not bound to the immutable progress file")
    if audit.get("candidate_source_tree_sha256") != candidate.get("source_tree_sha256"):
        raise ValueError("Candidate source binding differs")
    if audit.get("evaluation_runner_sha256") != launch.get("evaluation_runner_sha256"):
        raise ValueError("Evaluation runner binding differs")
    if launch.get("candidate_source_tree_sha256") != candidate.get("source_tree_sha256"):
        raise ValueError("Launch candidate binding differs")
    if audit.get("frozen_batch_sha256") != launch.get("frozen_batch_sha256"):
        raise ValueError("Frozen batch binding differs")

    rows = audit.get("rows")
    ids = [row.get("query_id") for row in rows] if isinstance(rows, list) else []
    expected_ids = [row.get("query_id") for row in summary.get("per_query_feedback", [])]
    if len(rows) != 56 or len(set(ids)) != 56 or ids != expected_ids:
        raise ValueError("Audit rows do not exactly cover the frozen summary")
    checks = audit.get("checks") or {}
    required_checks = {
        "summary_ids_exact": True,
        "row_count_56": True,
        "completed_count_50": True,
        "timeout_count_6": True,
        "all_timeouts_runner_owned": True,
        "telemetry_schema_observed": True,
        "max_requery_rounds_le_1": True,
        "no_trace_mutation_by_observer": True,
    }
    if any(checks.get(key) is not value for key, value in required_checks.items()):
        raise ValueError("Terminal audit checks are incomplete")

    coverage = audit.get("coverage") or {}
    if coverage.get("batch_rows") != 56 or coverage.get("completed_rows") != 50 or coverage.get("timeout_rows") != 6:
        raise ValueError("Terminal audit coverage differs")
    if coverage.get("gate_evaluated_rows") != 50 or coverage.get("gate_triggered_rows") != 38:
        raise ValueError("Gate activation coverage differs")
    if coverage.get("requery_rows") != 38 or coverage.get("max_unsupported_claim_count") != 34:
        raise ValueError("Gate requery coverage differs")

    return {
        "schema": SCHEMA,
        "generation": 1,
        "mechanism_key": MECHANISM,
        "measurement_status": {
            "execution_path": "observed_on_50_completed_runs",
            "gate_activation": "observed_38_of_50_completed_runs",
            "bounded_requery": "observed_38_of_50_completed_runs_maximum_one_round",
            "runner_owned_timeouts": "6_recorded_failures",
            "causal_accuracy_gain": "not_established",
            "f1_hypothesis": "invalid_archived_partial_overlap_excluded_from_meta",
        },
        "coverage": coverage,
        "mechanism_counters": {
            "completed_rows": 50,
            "timeout_rows": 6,
            "gate_evaluated_rows": 50,
            "gate_triggered_rows": 38,
            "requery_rows": 38,
            "max_requery_rounds": 1,
            "max_unsupported_claim_count": 34,
        },
        "evaluation_binding": {
            "result_type": "gen001_candidate_frozen_batch",
            "homogeneous_runtime": True,
            "human_accepted_mixed": False,
            "comparability": "candidate_batch_internal_only; root_parent_delta_suppressed_for_different_failure_regime",
            "repair_policy": "max_iterations_0; one bounded evidence-gate requery; runner wall timeout remains failure",
            "input_policy": "internal frozen 56 only; 48 held-out generalization queries excluded; F1 excluded",
            "regimes": [{
                "name": "gen001_candidate",
                "row_count": 56,
                "source_sha256": candidate.get("source_tree_sha256"),
                "upstream_runtime_sha256": launch.get("evaluation_runner_sha256"),
                "input_policy": "frozen_internal_56_only",
                "repair_policy": "bounded_one_requery",
                "workers": 4,
            }],
        },
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "summary_sha256": sha(summary_path),
            "intent_sha256": sha(intent_path),
            "candidate_ref_sha256": sha(candidate_ref_path),
            "launch_manifest_sha256": sha(launch_manifest_path),
            "candidate_source_tree_sha256": candidate.get("source_tree_sha256"),
            "evaluation_runner_sha256": launch.get("evaluation_runner_sha256"),
            "frozen_batch_sha256": launch.get("frozen_batch_sha256"),
        },
        "evidence_limits": [
            "Activation telemetry is deterministic runtime evidence, not a causal accuracy comparison.",
            "The six runner-owned wall timeouts remain failures and have no gate telemetry.",
            "The sealed F1 expectation is invalid for this mixed-task batch and is not supplied to Meta or promotion.",
            "A single bounded requery can still replace a correct first draft; this card does not claim improvement.",
        ],
        "source_artifact_hashes": {
            "candidate_ref_bytes_sha256": sha(candidate_ref_path),
            "launch_manifest_bytes_sha256": sha(launch_manifest_path),
            "intent_bytes_sha256": sha(intent_path),
            "audit_bytes_sha256": sha(audit_path),
            "summary_bytes_sha256": sha(summary_path),
        },
        "review_or_graph_started_by_extractor": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--candidate-ref", type=Path, required=True)
    parser.add_argument("--launch-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    card = build_card(args.audit, args.summary, args.intent, args.candidate_ref, args.launch_manifest)
    args.output.write_text(json.dumps(card, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "sha256": sha(args.output)}, indent=2))
