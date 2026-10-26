#!/usr/bin/env python3
"""Finalize the user-authorized, two-run G10 repair view without altering either run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G10 = BASE / "g010_revision001"
SOURCE = G10 / "source"
ORIGINAL = G10 / "evaluation/g010_verification_reconciliation_nohint_56_v1"
RECOVERY = G10 / "recovery/g010_pgload_subset_v1"
REPAIRED = RECOVERY / "evaluation/g010_pgload_subset_recovery_v1"
SOURCE_SHA = "80f002ac7a2d90b3cfed0fda7fec03c64c0a442c69a0ae27c7506852b32d36b9"
EXPECTED = {
    "parent": "e49a7c765eef8aea4dd4bc295dfc907f7cf0fa743df41efff94fb4b9e31d0abd",
    "pre": "f62c6d2f21894744838473557ea8e4030f1fa63ee9905cce905476fe5d61e46d",
    "preflight": "2b32d1b49bbdcfe2ab2ed138925925001365c3d1955903c154fc885ffddacc04",
    "claim": "e068ea830e0142b4ff393a256717b19b493eb04ee1fa8605b477b3dd8818468d",
    "launch": "7c1f6c4d41af7e047aaa10219d84c205b416ebd517d0fad37bc3c9cab9283392",
    "summary": "158a46757001991281f4feedf8bc20aba72bd7771e4f2b77bd2658b484b62abe",
    "progress": "cc3022f8c1d4209c48abe603172720b5825a8b95e755439cc242cdb08c2581a9",
    "extractor": "32b390bbf949ac8af87c392ff14a465e35709b9b0986a52aebc50030aa2d9752",
    "reconciled_report": "2fc6497001b4c3824a82ac95172e1a93d4e7c06afc057069573c0f063185eb19",
}
SIDECARS = (
    "g004_paired_structural_journal.jsonl",
    "g005_provenance_sidecar.jsonl",
    "g006_tool_class_sidecar.jsonl",
    "g007_last_pre_exec_sidecar.jsonl",
    "g008_verification_audit_sidecar.jsonl",
    "g009_verification_turn_gate_sidecar.jsonl",
    "g004_postrun_normalized_structural.json",
)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def inspect() -> tuple[dict, dict, list[dict], dict, list[dict]]:
    paths = {
        "parent": GRAPH / "g009_graph.json",
        "pre": GRAPH / "g010_pre_execution.json",
        "preflight": GRAPH / "g010_preflight.json",
        "claim": GRAPH / "g010_launch_claim.json",
        "launch": GRAPH / "g010_launch_manifest.json",
        "summary": ORIGINAL / "multi_query_summary.json",
        "progress": ORIGINAL / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g010_evidence_extractor.py",
        "reconciled_report": RECOVERY / "reconciled_report.json",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G10 frozen or reconciled input hash differs")
    incident = read(GRAPH / "g010_execution_incident.json")
    require(incident["status"] == "invalid_infrastructure_hypothesis_not_tested"
            and incident["original_summary_sha256"] == EXPECTED["summary"]
            and incident["affected_task_count"] == 5, "original incident differs")
    pre, preflight, claim, launch = (read(paths[name]) for name in ("pre", "preflight", "claim", "launch"))
    binding = pre["binding"]
    require(binding == preflight["binding"] == claim["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == SOURCE_SHA
            and binding["parent_graph_sha256"] == EXPECTED["parent"]
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == 225760,
            "original G10 binding differs")
    recovery_manifest = read(RECOVERY / "launch_manifest.json")
    recovery_preflight = read(RECOVERY / "preflight.json")
    recovery_claim = read(RECOVERY / "launch_claim.json")
    report = read(paths["reconciled_report"])
    require(recovery_manifest["source_tree_sha256"] == SOURCE_SHA
            and recovery_manifest["preflight_sha256"] == digest(RECOVERY / "preflight.json")
            and recovery_manifest["claim_sha256"] == digest(RECOVERY / "launch_claim.json")
            and recovery_manifest["target_batch_sha256"] == digest(RECOVERY / "target_batch.json")
            and recovery_preflight["status"] == "passed"
            and recovery_claim["status"] == "claimed_exclusive_recovery"
            and report["status"] == "supplementary_not_official_full_run"
            and report["original_summary_sha256"] == EXPECTED["summary"]
            and report["source_tree_sha256"] == SOURCE_SHA
            and report["recovery_summary_sha256"] == digest(REPAIRED / "multi_query_summary.json")
            and report["original_strict_pass_over_56"] == 27
            and report["supplementary_recovered_strict_pass_over_56"] == 32,
            "recovery provenance differs")
    for pid in (225760, recovery_manifest["pid"]):
        cmdline = Path(f"/proc/{pid}/cmdline")
        require(not cmdline.is_file() or not cmdline.read_bytes(), "an input runner remains active")

    original = read(paths["summary"])
    recovered = read(REPAIRED / "multi_query_summary.json")
    original_rows = original["per_query_feedback"]
    recovered_rows = recovered["per_query_feedback"]
    original_ids = read(ORIGINAL / "batch.json")["query_ids"]
    recovery_ids = read(RECOVERY / "target_batch.json")["query_ids"]
    require(len(original_rows) == len(original_ids) == 56
            and len(recovered_rows) == len(recovery_ids) == 5
            and all(row["query_id"] == query_id for row, query_id in zip(original_rows, original_ids))
            and all(row["query_id"] == query_id for row, query_id in zip(recovered_rows, recovery_ids)),
            "original or recovery batch identity differs")
    require(recovered["execution_context"]["db_description_mode"] == "base"
            and recovered["execution_context"]["query_timeout_sec"] == 1200
            and original["execution_context"]["db_description_mode"] == "base"
            and original["execution_context"]["query_timeout_sec"] == 1200,
            "original or recovery evaluation protocol differs")
    recovery_by_id = {row["query_id"]: row for row in recovered_rows}
    require(len(recovery_by_id) == 5
            and set(recovery_by_id) == {row["query_id"] for row in original_rows if row["status"] == "failed"}
            and all(row["status"] == "completed" for row in recovered_rows),
            "recovery did not exclusively complete the five failed tasks")
    selected = []
    for position, row in enumerate(original_rows, start=1):
        replacement = recovery_by_id.get(row["query_id"])
        if replacement is not None:
            require(row["status"] == "failed", "nonfailed original task replaced")
            selected.append({"position": position, "row": replacement, "source": "recovery",
                             "run_dir": REPAIRED / "runs" / replacement["run_id"], "original_row": row})
        else:
            selected.append({"position": position, "row": row, "source": "original",
                             "run_dir": ORIGINAL / "runs" / row["run_id"], "original_row": row})
    statuses = Counter(item["row"]["status"] for item in selected)
    strict_pass = sum(item["row"]["status"] == "completed"
                      and item["row"].get("strict_match_passed") is True for item in selected)
    strict_unknown = sum(item["row"]["status"] == "completed"
                         and item["row"].get("strict_match_passed") is None for item in selected)
    require(statuses == {"completed": 55, "timeout": 1}
            and strict_pass == 32 and strict_unknown == 3
            and len(report["task_mapping"]) == 5,
            "reconciled result partition differs")
    return pre, binding, selected, report, recovery_manifest


def build(pre: dict, binding: dict, selected: list[dict], report: dict,
          recovery_manifest: dict) -> tuple[dict, dict, dict, dict]:
    sys.path.insert(0, str(SOURCE))
    from experiments.g010_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE,
        build_evidence,
    )

    cohort_dirs = {
        COHORT_KNOWN_STRICT_FAIL: [], COHORT_STRICT_PASS: [],
        COHORT_STRICT_VERDICT_UNKNOWN: [], COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE: [],
    }
    entries = []
    for item in selected:
        row, run_dir = item["row"], item["run_dir"]
        require(run_dir.is_dir(), "selected run directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        files = {name: run_dir / name for name in SIDECARS}
        require(all(path.is_file() for name, path in files.items()
                    if name not in {"g008_verification_audit_sidecar.jsonl",
                                    "g009_verification_turn_gate_sidecar.jsonl",
                                    "g004_postrun_normalized_structural.json"}),
                "inherited sidecar missing")
        if row["status"] == "completed":
            require(all(path.is_file() for path in files.values()), "completed sidecar missing")
        entries.append({
            "anonymous_task_index": item["position"], "selected_source": item["source"],
            "original_status": item["original_row"]["status"],
            "selected_status": row["status"], "terminal_cohort": cohort,
            "selected_run_summary_sha256": (
                digest(run_dir / "summary.json")
                if (run_dir / "summary.json").is_file() else None
            ),
            "sidecar_sha256": {name: digest(path) if path.is_file() else None
                                for name, path in files.items()},
        })
    specialized = build_evidence(cohort_dirs)
    require(specialized["observed_task_count"] == 56
            and specialized["protocol_completion"]["protocol_complete"] is True
            and specialized["raw_content_persisted"] is False
            and specialized["prohibited_content_persisted"] is False
            and specialized["overall_status"] in {"supported", "contradicted", "inconclusive"}
            and {name: cohort["denominator"] for name, cohort in specialized["cohorts"].items()}
            == {COHORT_STRICT_PASS: 32, COHORT_KNOWN_STRICT_FAIL: 20,
                COHORT_STRICT_VERDICT_UNKNOWN: 3, COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE: 1},
            "pre-registered G10 extractor result differs")
    manifest = {
        "schema_version": "g010_reconciled_evidence_input_v1", "generation": 10,
        "execution_basis": "user_authorized_two_run_reconciliation",
        "original_summary_sha256": EXPECTED["summary"],
        "original_progress_sha256": EXPECTED["progress"],
        "recovery_summary_sha256": digest(REPAIRED / "multi_query_summary.json"),
        "recovery_progress_sha256": digest(REPAIRED / "multi_query_progress.json"),
        "reconciled_report_sha256": EXPECTED["reconciled_report"],
        "incident_sha256": digest(GRAPH / "g010_execution_incident.json"),
        "extractor_sha256": EXPECTED["extractor"],
        "original_task_count": 56, "selected_original_task_count": 51,
        "selected_recovery_task_count": 5, "selected_task_count": 56,
        "entries": entries,
    }
    node = {
        "id": "evidence:g010", "kind": "evidence",
        "statement": "G10 checklist intervention: user-authorized two-run repair view, not a single complete valid run; 32/56 supplementary strict versus 27/56 original infrastructure-affected strict.",
        "frozen_task_count": 56, "ended_count": 56, "completed_count": 55,
        "timeout_failure_count": 1, "other_terminal_failure_count": 0,
        "strict_pass_count": 32, "strict_pass_rate_all": round(32 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure;five_pre_model_environment_failures_replaced_by_bound_recovery",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "fixed_task_agnostic_evidence_reconciliation_checklist",
        "specialized_status": specialized["overall_status"],
        "specialized_components": specialized["components"],
        "specialized_cohort_coverage": {
            name: value["coverage"] for name, value in specialized["cohorts"].items()
        },
        "execution_basis": "user_authorized_two_run_reconciliation",
        "original_strict_pass_count": 27,
        "reconciled_strict_pass_count": 32,
        "recovery_task_count": 5,
        "limits": [
            "This is a user-authorized two-run repair view, not one uninterrupted valid 56-task execution.",
            "The original 56-task run remains marked invalid_infrastructure; its 27/56 score and incident are preserved.",
            "Five pre-model PostgreSQL load failures were replaced only by their own bound recovery outcomes; all other 51 original outcomes were retained.",
            "The 32/56 reconciled score is supplementary and not the original official single-run result.",
            "Checklist exposure is structural; semantic verification quality and causal score effects are not observed.",
            "Three completed strict verdicts remain unknown; the timeout remains a failure in fixed 56.",
        ],
        "artifact_refs": {
            "parent_graph_sha256": EXPECTED["parent"],
            "pre_execution_sha256": EXPECTED["pre"],
            "original_preflight_sha256": EXPECTED["preflight"],
            "original_launch_manifest_sha256": EXPECTED["launch"],
            "original_summary_sha256": EXPECTED["summary"],
            "original_progress_sha256": EXPECTED["progress"],
            "recovery_launch_manifest_sha256": digest(RECOVERY / "launch_manifest.json"),
            "recovery_summary_sha256": digest(REPAIRED / "multi_query_summary.json"),
            "recovery_progress_sha256": digest(REPAIRED / "multi_query_progress.json"),
            "reconciled_report_sha256": EXPECTED["reconciled_report"],
            "incident_sha256": digest(GRAPH / "g010_execution_incident.json"),
            "extractor_sha256": EXPECTED["extractor"],
        },
    }
    return manifest, specialized, node, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 10,
        "status": "four_nodes_complete", "execution_basis": "user_authorized_two_run_reconciliation",
        "pre_execution_sha256": EXPECTED["pre"], "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g010", "target": "experiment:g010", "relation": "observes",
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "finalize"))
    args = parser.parse_args()
    pre, binding, selected, report, recovery_manifest = inspect()
    manifest, specialized, node, graph = build(pre, binding, selected, report, recovery_manifest)
    if args.action == "verify":
        print(json.dumps({
            "status": "ready_to_finalize_reconciled_g010", "selected_task_count": len(selected),
            "selected_recovery_task_count": sum(item["source"] == "recovery" for item in selected),
            "strict_pass": node["strict_pass_count"], "strict_denominator": 56,
            "completed": node["completed_count"], "timeout": node["timeout_failure_count"],
            "strict_unknown_completed": node["strict_verdict_missing_completed_count"],
            "specialized_status": specialized["overall_status"],
            "component_statuses": {name: value["status"] for name, value in specialized["components"].items()},
        }, sort_keys=True))
        return
    input_path = GRAPH / "g010_evidence_input_manifest.json"
    specialized_path = GRAPH / "g010_specialized_evidence.json"
    evidence_path = GRAPH / "g010_evidence.json"
    graph_path = GRAPH / "g010_graph.json"
    require(not any(path.exists() for path in (input_path, specialized_path, evidence_path, graph_path)),
            "G10 Evidence or Graph already exists")
    write_new(input_path, manifest)
    write_new(specialized_path, specialized)
    node["artifact_refs"].update({
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(specialized_path),
    })
    write_new(evidence_path, {
        "schema_version": "dab_research_graph_evidence_v2", "generation": 10,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    graph["evidence_sha256"] = digest(evidence_path)
    graph["reconciled_report_sha256"] = EXPECTED["reconciled_report"]
    graph["incident_sha256"] = digest(GRAPH / "g010_execution_incident.json")
    write_new(graph_path, graph)
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "reconciled G10 Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete_reconciled_execution", "strict_pass": 32,
        "strict_denominator": 56, "original_strict_pass": 27,
        "specialized_status": specialized["overall_status"],
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(specialized_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
