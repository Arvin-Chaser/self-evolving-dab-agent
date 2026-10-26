#!/usr/bin/env python3
"""Finalize the audited G11 run with its frozen structural extractor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
REVISION = BASE / "g011_solution_loop_revision001"
SOURCE = REVISION / "source"
RUN_ID = "g011_structural_plan_evidence_ledger_nohint_56_v1"
RUN = REVISION / "evaluation" / RUN_ID
PID = 606199
TREE_SHA = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
EXPECTED = {
    "parent": "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a",
    "pre": "c6244346c29e85317f2409c05a9665d58801584266a5730f07df8c049a6912b4",
    "preflight": "5b3ce05e07cee508ee6b5b85640a6d677977186fb84f0a155062c429eb7a07ed",
    "claim": "e70f6ce7b76554a1092aefa89e2a4a9c769733995dccbd1d100098fccf635174",
    "launch": "58bf43915b723adadcdabb89c9e5d31b1a35e9b54f9cbcfcc0696a748644bd0f",
    "summary": "5949b6ed83eefbc9eabc897b02f3e522c56c2738ab84a215972c6193ea8f6588",
    "progress": "62c2a9d64a323bb23514cfc8ce33b8ccd88e55625a7c5242256748d8f0e81bb3",
    "extractor": "6d4f1f9ab16004296c6eac31707acf8860c8b37b91c1db71ded1d997afc40cea",
    "incident": "50cc1455d3f12ba9278326dfefaadfc6d3631c16258e602aca3f7300b3db23c0",
}
PATHS = {
    "parent": GRAPH / "g010_graph.json",
    "pre": GRAPH / "g011_solution_loop_pre_execution.json",
    "preflight": GRAPH / "g011_solution_loop_preflight.json",
    "claim": GRAPH / "g011_solution_loop_launch_claim.json",
    "launch": GRAPH / "g011_solution_loop_launch_manifest.json",
    "summary": RUN / "multi_query_summary.json",
    "progress": RUN / "multi_query_progress.json",
    "extractor": SOURCE / "experiments/g011_evidence_extractor.py",
    "incident": REVISION / "bindings/preflight_incident_001.json",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def inspect() -> tuple[dict, dict, dict, list[dict], dict]:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G11 runner remains active")
    require(all(digest(PATHS[key]) == sha for key, sha in EXPECTED.items()), "audited input hash differs")
    pre, preflight, claim, launch = (read(PATHS[key]) for key in ("pre", "preflight", "claim", "launch"))
    binding = pre["binding"]
    args = launch.get("command", [])
    require(
        binding == preflight["binding"] == claim["binding"] == launch["binding"]
        and binding["candidate_tree_sha256"] == TREE_SHA
        and binding["parent_graph_sha256"] == EXPECTED["parent"]
        and binding["research_result_sha256"] == "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
        and binding["implementation_manifest_sha256"] == "44a7a9508f8f1c68ab0ab70dfb3c820ca8f61eeefe880d1bc37453f614c75675"
        and binding["admission_sha256"] == "9121bfb8a6797d55086c18f433b067addd3df8f2ed0a950530442c21423ad068"
        and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
        and binding["description_mode"] == "full_db_description_no_hints"
        and preflight["status"] == "passed"
        and preflight["provider_probe"]["declared_freeform_carrier_accepted"] is True
        and preflight["real_upstream_probe"]["response_boundary_fixture_passed"] is True
        and claim["pre_execution_sha256"] == EXPECTED["pre"]
        and claim["preflight_sha256"] == EXPECTED["preflight"]
        and launch["preflight_sha256"] == EXPECTED["preflight"]
        and launch["pid"] == PID
        and args.count("--enable-g011-plan-evidence-ledger") == 1
        and args[args.index("--run-id") + 1] == RUN_ID
        and len(list(GRAPH.glob("g011_solution_loop_launch_manifest*.json"))) == 1,
        "G11 frozen provenance or unique activation differs",
    )
    spec = importlib.util.spec_from_file_location(
        "g011_source_manifest", SOURCE / "experiments/intent_candidate_workspace.py"
    )
    require(spec is not None and spec.loader is not None, "source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = module.source_manifest_hash(
        sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    )
    require(tree == TREE_SHA, "source tree differs")

    sys.path.insert(0, str(SOURCE))
    from experiments.g011_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_FAILURE, build_evidence,
    )
    from experiments.g011_interface_contract import find_sidecar_violations

    summary, progress = read(PATHS["summary"]), read(PATHS["progress"])
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    context = summary.get("execution_context", {})
    require(
        summary.get("query_count") == len(rows) == len(progress_rows) == 56
        and context.get("db_description_mode") == "base"
        and context.get("query_timeout_sec") == 1200
        and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                for a, b in zip(rows, progress_rows)),
        "G11 result identity or protocol differs",
    )
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(
        statuses == {"completed": 53, "timeout": 3}
        and (strict_pass, known_fail, strict_unknown) == (35, 15, 3)
        and summary.get("strict_pass_count") == 35,
        "G11 result partition differs from terminal audit",
    )

    cohorts = {
        COHORT_KNOWN_STRICT_FAIL: [], COHORT_STRICT_PASS: [],
        COHORT_STRICT_VERDICT_UNKNOWN: [], COHORT_TIMEOUT_FAILURE: [],
    }
    entries: list[dict] = []
    run_root = RUN / "runs"
    seen: set[str] = set()
    filenames = {
        "journal_sha256": "g004_paired_structural_journal.jsonl",
        "normalized_sha256": "g004_postrun_normalized_structural.json",
        "provenance_sha256": "g005_provenance_sidecar.jsonl",
        "tool_class_sha256": "g006_tool_class_sidecar.jsonl",
        "last_pre_exec_sha256": "g007_last_pre_exec_sidecar.jsonl",
        "g011_summary_sha256": "g011_plan_evidence_summary.json",
        "g011_records_sha256": "g011_plan_evidence_sidecar.jsonl",
    }
    for index, row in enumerate(rows, start=1):
        run_id = row.get("run_id")
        require(isinstance(run_id, str) and run_id and run_id not in seen
                and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "task run identity invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(), "task directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohorts[cohort].append(run_dir)
        files = {key: run_dir / name for key, name in filenames.items()}
        require(all(files[key].is_file() for key in (
            "journal_sha256", "provenance_sha256", "tool_class_sha256", "last_pre_exec_sha256"
        )), "inherited task sidecar missing")
        if row["status"] == "completed":
            require(files["normalized_sha256"].is_file() and files["g011_summary_sha256"].is_file(),
                    "completed sidecar missing")
            g011_summary = read(files["g011_summary_sha256"])
            require(not find_sidecar_violations([], g011_summary)
                    and g011_summary.get("record_count") == 0
                    and g011_summary.get("guidance_binding_count") == 0,
                    "G11 summary schema or empirical zero-record result differs")
        entries.append({
            "anonymous_task_index": index, "terminal_cohort": cohort,
            **{key: digest(path) if path.is_file() else None for key, path in files.items()},
        })

    special = build_evidence(cohorts)
    require(
        special["observed_task_count"] == 56
        and special["protocol_complete"] is True
        and special["total_record_count"] == 0
        and special["total_guidance_binding_count"] == 0
        and special["overall_status"] == "untested"
        and special["semantic_boundary"]["semantic_support_claim_allowed"] is False
        and {name: value["denominator"] for name, value in special["cohorts"].items()}
        == {COHORT_KNOWN_STRICT_FAIL: 15, COHORT_STRICT_PASS: 35,
            COHORT_STRICT_VERDICT_UNKNOWN: 3, COHORT_TIMEOUT_FAILURE: 3}
        and all(value["prohibited_content_persisted_count"] == 0
                for value in special["cohorts"].values()),
        "pre-registered structural Evidence differs",
    )
    return pre, binding, special, entries, {
        "completed": 53, "timeout": 3, "strict_pass": 35,
        "strict_unknown": 3, "known_fail": 15,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "finalize"))
    args = parser.parse_args()
    pre, binding, special, entries, facts = inspect()
    if args.action == "verify":
        print(json.dumps({"status": "ready_to_finalize_g011", **facts,
                          "specialized_status": special["overall_status"],
                          "record_count": special["total_record_count"],
                          "guidance_binding_count": special["total_guidance_binding_count"]}, sort_keys=True))
        return

    input_path = GRAPH / "g011_solution_loop_evidence_input_manifest.json"
    special_path = GRAPH / "g011_solution_loop_specialized_evidence.json"
    evidence_path = GRAPH / "g011_solution_loop_evidence.json"
    graph_path = GRAPH / "g011_solution_loop_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G11 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g011_evidence_input_v1",
        "generation": 11, "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g011", "kind": "evidence",
        "statement": "G11 structural plan/evidence ledger on one valid frozen no-hint 56-task run; no model-authored plan record or guidance binding was observed.",
        "frozen_task_count": 56, "ended_count": 56, "completed_count": 53,
        "timeout_failure_count": 3, "other_terminal_failure_count": 0,
        "strict_pass_count": 35, "strict_pass_rate_all": round(35 / 56, 6),
        "known_strict_fail_count": 15, "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "model_authored_structural_plan_evidence_ledger",
        "specialized_status": special["overall_status"],
        "specialized_cohort_coverage": {
            name: {"denominator": value["denominator"],
                   "record_task_count": value["record_task_count"],
                   "guidance_task_count": value["guidance_task_count"]}
            for name, value in special["cohorts"].items()
        },
        "limits": [
            "No model-authored G11 record and no guidance binding were observed; the behavioral mechanism is untested in this run.",
            "All 53 completed tasks have a valid zero-record G11 summary; timeout tasks remain failures in the fixed 56.",
            "Structural validation cannot establish semantic support, task relevance, plan quality, answer correctness, coverage, or truth.",
            "Three completed strict verdicts remain unknown and are not reclassified.",
            "This is one unpaired run; score differences from other generations are descriptive, not causal.",
        ],
        "artifact_refs": {
            "parent_graph_sha256": EXPECTED["parent"],
            "pre_execution_sha256": EXPECTED["pre"],
            "preflight_sha256": EXPECTED["preflight"],
            "launch_claim_sha256": EXPECTED["claim"],
            "launch_manifest_sha256": EXPECTED["launch"],
            "summary_sha256": EXPECTED["summary"],
            "progress_sha256": EXPECTED["progress"],
            "extractor_sha256": EXPECTED["extractor"],
            "input_manifest_sha256": digest(input_path),
            "specialized_evidence_sha256": digest(special_path),
            "preflight_incident_sha256": EXPECTED["incident"],
        },
    }
    write_new(evidence_path, {
        "schema_version": "dab_research_graph_evidence_v2", "generation": 11,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 11,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g011", "target": "experiment:g011", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G11 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", **facts,
        "specialized_status": special["overall_status"],
        "record_count": special["total_record_count"],
        "guidance_binding_count": special["total_guidance_binding_count"],
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path),
        "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
