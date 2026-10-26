#!/usr/bin/env python3
"""Finalize audited G8 using only its frozen specialized extractor."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G8 = BASE / "g008_revision001"
SOURCE = G8 / "source"
RUN_ID = "g008_verification_audit_nohint_56_v1"
RUN = G8 / "evaluation" / RUN_ID
PID = 124352
TREE_SHA = "adeefdde02075bc4ea458f6a74ad1c418dd096e92acd1b262ccb25537bcf4105"
EXPECTED = {
    "parent": "22ffea533d2078bce07d6ef89615de8d9c8649bcb97fbf439f598f0ab3a26d72",
    "pre": "cac4d6493d59db458b32115c7efc74d2d415f36bc26e35e73fc2bbf4afcf50b6",
    "preflight": "5e3b34520f2a68f1fd551a68a7a3a387b7cafa92a14d42646d8e76ed6913eefe",
    "launch": "4dcdd8fac3383a8c441922cfb8ca58c038e1b1d6539e26e93522b46aa8d11193",
    "summary": "af260ccde4d9a9644fdf043af69bf05e4e10930514dff1a253a2473ad497a38d",
    "progress": "9949eccee29e6c605e79c04d13c7cfe99ab307b86ce61a3ab18738e57c2de18a",
    "extractor": "6cb2a0e785abafd0671fd4b30e2d5eb2bccaa8434958215229e39cba246ae7c5",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def main() -> None:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G8 runner still active")
    paths = {
        "parent": GRAPH / "g007_graph.json",
        "pre": GRAPH / "g008_pre_execution.json",
        "preflight": GRAPH / "g008_preflight.json",
        "launch": GRAPH / "g008_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g008_evidence_extractor.py",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G8 audited input hash differs")
    pre, preflight, launch = read(paths["pre"]), read(paths["preflight"]), read(paths["launch"])
    summary, progress = read(paths["summary"]), read(paths["progress"])
    binding = pre["binding"]
    require(binding == preflight["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["parent_graph_sha256"] == EXPECTED["parent"]
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == PID,
            "G8 frozen run identity differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)), "G8 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 53, "timeout": 3} and strict_pass == 35
            and strict_unknown == 3 and known_fail == 15
            and summary.get("strict_pass_count") == strict_pass,
            "G8 result counts differ from terminal audit")

    sys.path.insert(0, str(SOURCE))
    from experiments.g008_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE,
        build_evidence,
    )
    from experiments.g008_verification_audit_sidecar import SIDECAR_FILENAME as G008
    from experiments.g007_last_pre_exec_sidecar import SIDECAR_FILENAME as G007
    from experiments.g006_tool_class_sidecar import SIDECAR_FILENAME as G006
    from experiments.g005_provenance_sidecar import SIDECAR_FILENAME as G005
    from experiments.g004_postrun_structural_sidecar import SIDECAR_FILENAME as NORMALIZED
    from experiments.g004_paired_structural_journal import JOURNAL_FILENAME

    cohort_dirs = {
        COHORT_KNOWN_STRICT_FAIL: [], COHORT_STRICT_PASS: [],
        COHORT_STRICT_VERDICT_UNKNOWN: [], COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE: [],
    }
    entries = []
    run_root = RUN / "runs"
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id and run_id not in seen
                and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "G8 task run binding invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G8 task result directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        files = {
            "g008_sidecar_sha256": run_dir / G008,
            "g007_sidecar_sha256": run_dir / G007,
            "g006_sidecar_sha256": run_dir / G006,
            "g005_sidecar_sha256": run_dir / G005,
            "journal_sha256": run_dir / JOURNAL_FILENAME,
            "normalized_sidecar_sha256": run_dir / NORMALIZED,
        }
        require(all(path.is_file() for key, path in files.items()
                    if key not in {"g008_sidecar_sha256", "normalized_sidecar_sha256"})
                and (files["normalized_sidecar_sha256"].is_file() or row["status"] == "timeout"),
                "G8 inherited Evidence source missing")
        entries.append({
            "anonymous_task_index": index, "terminal_cohort": cohort,
            **{key: digest(path) if path.is_file() else None for key, path in files.items()},
        })
    special = build_evidence(cohort_dirs)
    require(special["observed_task_count"] == 56
            and special["observed_denominator_complete"] is True
            and special["protocol_completion"]["protocol_complete"] is True
            and special["raw_content_persisted"] is False
            and special["prohibited_content_persisted"] is False
            and special["overall_status"] in {"supported", "contradicted", "inconclusive"}
            and {name: value["denominator"] for name, value in special["cohorts"].items()}
            == {COHORT_KNOWN_STRICT_FAIL: 15, COHORT_STRICT_PASS: 35,
                COHORT_STRICT_VERDICT_UNKNOWN: 3,
                COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE: 3},
            "G8 specialized Evidence contract differs")

    input_path = GRAPH / "g008_evidence_input_manifest.json"
    special_path = GRAPH / "g008_specialized_evidence.json"
    evidence_path = GRAPH / "g008_evidence.json"
    graph_path = GRAPH / "g008_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G8 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g008_evidence_input_v1", "generation": 8,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g008", "kind": "evidence",
        "statement": "G8 generic pre-terminal return_answer verification audit on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 53, "timeout_failure_count": 3, "other_terminal_failure_count": 0,
        "strict_pass_count": 35, "strict_pass_rate_all": round(35 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "generic_preterminal_verification_audit",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "Audit exposure is structural; semantic verification quality is not observed.",
            "A later return_answer in the same model response can precede model-visible audit feedback.",
            "Timeouts are failures in fixed 56; unavailable records remain unknown.",
            "Three completed strict verdicts remain unknown and are not reclassified.",
            "This is one unpaired run; score differences from earlier generations are descriptive only.",
        ],
        "artifact_refs": {
            "parent_graph_sha256": EXPECTED["parent"],
            "pre_execution_sha256": EXPECTED["pre"],
            "preflight_sha256": EXPECTED["preflight"],
            "launch_manifest_sha256": EXPECTED["launch"],
            "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
            "input_manifest_sha256": digest(input_path),
            "extractor_sha256": EXPECTED["extractor"],
            "specialized_evidence_sha256": digest(special_path),
        },
    }
    write_new(evidence_path, {
        "schema_version": "dab_research_graph_evidence_v2", "generation": 8,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 8,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g008", "target": "experiment:g008", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G8 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 53,
        "timeout_failures": 3, "strict_pass": 35, "strict_denominator": 56,
        "strict_unknown_completed": 3, "specialized_status": special["overall_status"],
        "component_statuses": {k: v["status"] for k, v in special["components"].items()},
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
