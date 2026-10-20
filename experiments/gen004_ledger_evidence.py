"""Build a compact, bound Meta card from Gen4's ledger terminal audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


MECHANISM = "externalized_observation_ledger_with_supersession_and_compact_replay"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def build_card(audit_path: Path, summary_path: Path, intent_path: Path,
               candidate_ref_path: Path, launch_manifest_path: Path) -> dict:
    terminal, summary, intent = read(audit_path), read(summary_path), read(intent_path)
    candidate, launch = read(candidate_ref_path), read(launch_manifest_path)
    progress_path = summary_path.parent / "multi_query_progress.json"
    if (terminal.get("schema") != "dab_gen004_ledger_terminal_audit_v1"
            or terminal.get("mechanism_key") != MECHANISM
            or intent.get("mechanism_key") != MECHANISM or intent.get("generation") != 4
            or terminal.get("summary_sha256") != sha(summary_path)
            or terminal.get("progress_sha256") != sha(progress_path)
            or terminal.get("batch_sha256") != launch.get("frozen_batch_sha256")):
        raise ValueError("Gen4 evidence identity or frozen input binding differs")
    if (candidate.get("source_tree_sha256") != launch.get("candidate_source_tree_sha256")
            or summary["execution_context"].get("runner_sha256") != launch.get("candidate_agent_sha256")
            or summary["execution_context"].get("batch_runner_sha256") != launch.get("evaluation_runner_sha256")):
        raise ValueError("Gen4 source/runtime binding differs")
    rows = terminal["rows"]
    if ([row["query_id"] for row in rows] != [row["query_id"] for row in summary["per_query_feedback"]]
            or len(rows) != 56 or len({row["query_id"] for row in rows}) != 56):
        raise ValueError("Gen4 audit row coverage differs")
    coverage, counters = terminal["coverage"], terminal["mechanism_counters"]
    if (coverage["completed_rows"] != summary["successful_run_count"]
            or coverage["strict_pass_rows"] != summary["strict_pass_count"]
            or coverage["strict_evaluated_rows"] != summary["strict_evaluated_count"]
            or coverage["final_answer_nonempty_rows"] != summary["final_answer_nonempty_count"]
            or counters["telemetry_rows"] != coverage["completed_rows"]
            or counters["over_budget_turns"] != sum(row.get("over_budget_turns", 0) for row in rows)
            or len(terminal["over_budget_rows"]) != sum(row.get("over_budget_turns", 0) > 0 for row in rows)):
        raise ValueError("Gen4 compact counters differ from audited rows")
    return {
        "schema": "dab_gen004_ledger_mechanism_card_v1",
        "generation": 4,
        "mechanism_key": MECHANISM,
        "coverage": coverage,
        "mechanism_counters": counters,
        "over_budget_row_count": len(terminal["over_budget_rows"]),
        "maximum_rendered_observation_chars": max(row.get("max_rendered_chars", 0) for row in rows),
        "render_budget_chars": 6000,
        "supersession_samples": terminal["supersession_samples"][:6],
        "measurement_status": {
            "execution_path": "ledger_log_verified_on_52_completed_runs",
            "activation": "observed_but_bounded_render_invariant_failed",
            "causal_accuracy_gain": "not_established",
        },
        "evaluation_binding": {
            "result_type": "gen004_candidate_revision001_frozen_batch",
            "homogeneous_runtime": True,
            "human_accepted_mixed": False,
            "comparability": "candidate_batch_internal_only; root_parent_delta_suppressed_for_different_failure_regime",
            "repair_policy": "max_iterations_0; runner wall timeout remains failure",
            "input_policy": "internal frozen 56 only; 48 held-out queries excluded",
            "regimes": [{
                "name": "gen004_candidate_revision001", "row_count": 56,
                "source_sha256": candidate["source_tree_sha256"],
                "upstream_runtime_sha256": launch["evaluation_runner_sha256"],
                "input_policy": "frozen_internal_56_only", "workers": 4,
            }],
        },
        "evidence_binding": {
            "terminal_audit_sha256": sha(audit_path),
            "summary_sha256": sha(summary_path), "progress_sha256": sha(progress_path),
            "intent_sha256": sha(intent_path), "candidate_ref_sha256": sha(candidate_ref_path),
            "launch_manifest_sha256": sha(launch_manifest_path),
            "candidate_source_tree_sha256": candidate["source_tree_sha256"],
            "evaluation_runner_sha256": launch["evaluation_runner_sha256"],
            "frozen_batch_sha256": launch["frozen_batch_sha256"],
        },
        "evidence_limits": [
            "Four runner-owned timeouts have no completed-run ledger telemetry.",
            "The 6000-character bound failed on 49 of 52 completed rows because fail-open raw observations persisted across turns.",
            "Activation and a lower strict count do not establish a causal task effect; do not reuse this source as a validated improvement.",
        ],
    }
