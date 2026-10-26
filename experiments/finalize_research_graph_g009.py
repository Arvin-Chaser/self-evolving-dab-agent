#!/usr/bin/env python3
"""Finalize audited G9 using only its frozen specialized extractor."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G9 = BASE / "g009_revision001"
SOURCE = G9 / "source"
RUN_ID = "g009_verification_turn_gate_nohint_56_v1"
RUN = G9 / "evaluation" / RUN_ID
PID = 171027
TREE_SHA = "206c4f5186a66d72b851aa888eb75d975d5ce2085970a322881997b119f16d0d"
EXPECTED = {
    "parent": "c769fd157db33e7fe2432285d4e15718307f5c7b91dde91ebcf83b19fbca83e8",
    "pre": "c0a091d0cbf2133e6d7ed4af8cf104c917cde2fbda2455bdc8cdc0fd685bcd0f",
    "preflight": "1ed18492b7c2b231e846f77e1eda6cdbfbe76bc639018ff0a514ff840263dde4",
    "launch": "b5079128c80b4123510dd04c0b5b92f623197dbcc29b1b3077e4bb03377c6769",
    "summary": "75ef51e506da3695e1a0209286c83b86957daecd99d7d05e5bed05a98e6e2b76",
    "progress": "af9087f4f495c285f7d898bbaf63c3bc1768855e84a85a4df333133c93a3996f",
    "extractor": "20c953086342ad79e5199c66ac2d478691b4c0e26d80b27b90e451d20597fc15",
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
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G9 runner still active")
    paths = {
        "parent": GRAPH / "g008_graph.json",
        "pre": GRAPH / "g009_pre_execution.json",
        "preflight": GRAPH / "g009_preflight.json",
        "launch": GRAPH / "g009_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g009_evidence_extractor.py",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G9 audited input hash differs")
    pre, preflight, launch = read(paths["pre"]), read(paths["preflight"]), read(paths["launch"])
    summary, progress = read(paths["summary"]), read(paths["progress"])
    binding = pre["binding"]
    require(binding == preflight["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["parent_graph_sha256"] == EXPECTED["parent"]
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == PID,
            "G9 frozen run identity differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)), "G9 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 54, "timeout": 2} and strict_pass == 35
            and strict_unknown == 3 and known_fail == 16
            and summary.get("strict_pass_count") == strict_pass,
            "G9 result counts differ from terminal audit")

    sys.path.insert(0, str(SOURCE))
    from experiments.g009_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE,
        build_evidence,
    )
    from experiments.g009_verification_turn_gate_sidecar import SIDECAR_FILENAME as G009
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
                "G9 task run binding invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G9 task result directory missing")
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
            "g009_sidecar_sha256": run_dir / G009,
            "g008_sidecar_sha256": run_dir / G008,
            "g007_sidecar_sha256": run_dir / G007,
            "g006_sidecar_sha256": run_dir / G006,
            "g005_sidecar_sha256": run_dir / G005,
            "journal_sha256": run_dir / JOURNAL_FILENAME,
            "normalized_sidecar_sha256": run_dir / NORMALIZED,
        }
        require(all(path.is_file() for key, path in files.items()
                    if key not in {"g009_sidecar_sha256", "g008_sidecar_sha256", "normalized_sidecar_sha256"})
                and (files["normalized_sidecar_sha256"].is_file() or row["status"] == "timeout"),
                "G9 inherited Evidence source missing")
        require(files["g008_sidecar_sha256"].is_file() == (row["status"] == "completed"),
                "G8 inherited sidecar coverage differs")
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
            == {COHORT_KNOWN_STRICT_FAIL: 16, COHORT_STRICT_PASS: 35,
                COHORT_STRICT_VERDICT_UNKNOWN: 3,
                COHORT_TIMEOUT_OR_OTHER_TERMINAL_FAILURE: 2},
            "G9 specialized Evidence contract differs")

    input_path = GRAPH / "g009_evidence_input_manifest.json"
    special_path = GRAPH / "g009_specialized_evidence.json"
    evidence_path = GRAPH / "g009_evidence.json"
    graph_path = GRAPH / "g009_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G9 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g009_evidence_input_v1", "generation": 9,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g009", "kind": "evidence",
        "statement": "G9 later-model-turn verification gate on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 54, "timeout_failure_count": 2, "other_terminal_failure_count": 0,
        "strict_pass_count": 35, "strict_pass_rate_all": round(35 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "later_model_turn_verification_gate",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "Later-turn audit exposure is structural; semantic verification quality is not observed.",
            "Forcing a later model turn can consume deadline or iteration budget.",
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
        "schema_version": "dab_research_graph_evidence_v2", "generation": 9,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 9,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g009", "target": "experiment:g009", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G9 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 54,
        "timeout_failures": 2, "strict_pass": 35, "strict_denominator": 56,
        "strict_unknown_completed": 3, "specialized_status": special["overall_status"],
        "component_statuses": {k: v["status"] for k, v in special["components"].items()},
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
