#!/usr/bin/env python3
"""Finalize audited G7 using only its frozen specialized extractor."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G7 = BASE / "g007_revision001"
SOURCE = G7 / "source"
RUN_ID = "baseline_g007_last_pre_exec_elapsed_nohint_56_v1"
RUN = G7 / "evaluation" / RUN_ID
PID = 81909
TREE_SHA = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
EXPECTED = {
    "parent": "f7aa97ae352d827bb34d3e984aea7a38cd4d2082aeb55917dd78bc369b884775",
    "pre": "b13f898b363252b07a8e49898d053e8af00af1f1bdd340658dcbb30cd8eb80bc",
    "preflight": "b688afc7fad1a24270e1d1d4da888bd3214d14dc017334b5f2875414b367eaa9",
    "launch": "a09e50cf92f598090672eb7f8267b7c5639f0de458682de85ae47e735976455e",
    "summary": "b0c09e599e7690baedb80029138b7efde0ebceac132d1d03eee6647cc127541f",
    "progress": "b25f6026e891f435427dd993f5e18efea3eb52609ef88f27f8a61acbee5a80b7",
    "extractor": "ddb281464b921606e1ddad4d6f47b2cfa5eca4b96e8a096f2d8734bf83d87005",
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
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G7 runner still active")
    paths = {
        "parent": GRAPH / "g006_graph.json",
        "pre": GRAPH / "g007_pre_execution.json",
        "preflight": GRAPH / "g007_preflight.json",
        "launch": GRAPH / "g007_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g007_evidence_extractor.py",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G7 audited input hash differs")
    pre, preflight, launch = read(paths["pre"]), read(paths["preflight"]), read(paths["launch"])
    summary, progress = read(paths["summary"]), read(paths["progress"])
    binding = pre["binding"]
    require(binding == preflight["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["parent_graph_sha256"] == EXPECTED["parent"]
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == PID,
            "G7 frozen run identity differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)), "G7 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 52, "timeout": 4} and strict_pass == 32
            and strict_unknown == 3 and known_fail == 17
            and summary.get("strict_pass_count") == strict_pass,
            "G7 result counts differ from terminal audit")

    sys.path.insert(0, str(SOURCE))
    from experiments.g007_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_FAILURE, build_evidence,
    )
    from experiments.g007_last_pre_exec_sidecar import SIDECAR_FILENAME as G007_SIDECAR
    from experiments.g006_tool_class_sidecar import SIDECAR_FILENAME as G006_SIDECAR
    from experiments.g005_provenance_sidecar import SIDECAR_FILENAME as G005_SIDECAR
    from experiments.g004_postrun_structural_sidecar import SIDECAR_FILENAME as NORMALIZED
    from experiments.g004_paired_structural_journal import JOURNAL_FILENAME

    cohort_dirs = {
        COHORT_KNOWN_STRICT_FAIL: [], COHORT_STRICT_PASS: [],
        COHORT_STRICT_VERDICT_UNKNOWN: [], COHORT_TIMEOUT_FAILURE: [],
    }
    entries = []
    run_root = RUN / "runs"
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id and run_id not in seen
                and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "G7 task run binding invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G7 task result directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        g007, g006 = run_dir / G007_SIDECAR, run_dir / G006_SIDECAR
        g005, journal = run_dir / G005_SIDECAR, run_dir / JOURNAL_FILENAME
        normalized = run_dir / NORMALIZED
        require(g007.is_file() and g006.is_file() and g005.is_file() and journal.is_file()
                and (normalized.is_file() or row["status"] == "timeout"),
                "G7 pre-registered Evidence source missing")
        entries.append({
            "anonymous_task_index": index, "terminal_cohort": cohort,
            "g007_sidecar_sha256": digest(g007), "g006_sidecar_sha256": digest(g006),
            "g005_sidecar_sha256": digest(g005), "journal_sha256": digest(journal),
            "normalized_sidecar_sha256": digest(normalized) if normalized.is_file() else None,
        })
    special = build_evidence(cohort_dirs)
    require(special["observed_task_count"] == 56
            and special["observed_denominator_complete"] is True
            and special["protocol_completion"]["protocol_complete"] is True
            and special["raw_content_persisted"] is False
            and special["prohibited_content_persisted"] is False
            and special["overall_status"] in {"supported", "contradicted", "inconclusive"}
            and {name: value["denominator"] for name, value in special["cohorts"].items()}
            == {COHORT_KNOWN_STRICT_FAIL: 17, COHORT_STRICT_PASS: 32,
                COHORT_STRICT_VERDICT_UNKNOWN: 3, COHORT_TIMEOUT_FAILURE: 4},
            "G7 specialized Evidence contract differs")

    input_path = GRAPH / "g007_evidence_input_manifest.json"
    special_path = GRAPH / "g007_specialized_evidence.json"
    evidence_path = GRAPH / "g007_evidence.json"
    graph_path = GRAPH / "g007_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G7 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g007_evidence_input_v1", "generation": 7,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g007", "kind": "evidence",
        "statement": "G7 last pre-execution elapsed-bucket timeout localization on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 52, "timeout_failure_count": 4, "other_terminal_failure_count": 0,
        "strict_pass_count": 32, "strict_pass_rate_all": round(32 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "last_pre_exec_elapsed_bucket_timeout_localization_diagnostic",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "Last pre-execution timing localizes a pending operation, not the cause of timeout or correctness.",
            "Timeouts are failures in the fixed 56 denominator; unavailable records remain unknown.",
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
        "schema_version": "dab_research_graph_evidence_v2", "generation": 7,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 7,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g007", "target": "experiment:g007", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G7 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 52,
        "timeout_failures": 4, "strict_pass": 32, "strict_denominator": 56,
        "strict_unknown_completed": 3, "specialized_status": special["overall_status"],
        "component_statuses": {k: v["status"] for k, v in special["components"].items()},
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
