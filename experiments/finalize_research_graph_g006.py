#!/usr/bin/env python3
"""Finalize audited G6 using only its frozen specialized extractor."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G6 = BASE / "g006_revision001"
SOURCE = G6 / "source"
RUN_ID = "baseline_g006_tool_class_nohint_56_v1"
RUN = G6 / "evaluation" / RUN_ID
PID = 42155
TREE_SHA = "845e0f89f3df104d1fcb0ca564256fe8ca0f92c8880127dc4b3c2d4cfb0244c6"
EXPECTED = {
    "parent": "2310f5b7b16e21242ed055577bd148a9989ae4f5107011bfae444693b8a3b42d",
    "pre": "baf76b74a4f897397f891d13d8886a5412e8d8032f4ae205e2d2d501d6055c14",
    "preflight": "d27eb65ff64832cfe46029c6771f3ae869df9529c5a1cf8db1e8e1ea08f649fa",
    "launch": "b13503944a2225f8589d070fb6f8df6fe1a651dffe3354220e1077debbe35b9a",
    "summary": "bf1670ed2f639d926833875fb0e27bb1bdaff98fb141b9d05abfeecf43628eb4",
    "progress": "9197acd1b6cf5ed66d39e15b0cd1e3f546da260ba26359f0445416cf98d3b859",
    "extractor": "4d969ac47c9ecb4c396c769443026275d0b2e3e344bb5cb8fd9c53ea98c730ee",
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
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G6 runner still active")
    paths = {
        "parent": GRAPH / "g005_graph.json",
        "pre": GRAPH / "g006_pre_execution.json",
        "preflight": GRAPH / "g006_preflight.json",
        "launch": GRAPH / "g006_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g006_evidence_extractor.py",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G6 audited input hash differs")
    pre, preflight, launch = read(paths["pre"]), read(paths["preflight"]), read(paths["launch"])
    summary, progress = read(paths["summary"]), read(paths["progress"])
    binding = pre["binding"]
    require(binding == preflight["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["parent_graph_sha256"] == EXPECTED["parent"]
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == PID,
            "G6 frozen run identity differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)), "G6 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 53, "timeout": 3} and strict_pass == 37
            and strict_unknown == 3 and known_fail == 13
            and summary.get("strict_pass_count") == strict_pass,
            "G6 result counts differ from terminal audit")

    sys.path.insert(0, str(SOURCE))
    from experiments.g006_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_FAILURE,
        build_evidence,
    )
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
                "G6 task run binding invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G6 task result directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        g006 = run_dir / G006_SIDECAR
        g005 = run_dir / G005_SIDECAR
        journal = run_dir / JOURNAL_FILENAME
        normalized = run_dir / NORMALIZED
        require(g006.is_file() and g005.is_file() and journal.is_file()
                and (normalized.is_file() or row["status"] == "timeout"),
                "G6 pre-registered Evidence source missing")
        entries.append({
            "anonymous_task_index": index, "terminal_cohort": cohort,
            "g006_sidecar_sha256": digest(g006), "g005_sidecar_sha256": digest(g005),
            "journal_sha256": digest(journal),
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
            == {COHORT_KNOWN_STRICT_FAIL: 13, COHORT_STRICT_PASS: 37,
                COHORT_STRICT_VERDICT_UNKNOWN: 3, COHORT_TIMEOUT_FAILURE: 3},
            "G6 specialized Evidence contract differs")

    input_path = GRAPH / "g006_evidence_input_manifest.json"
    special_path = GRAPH / "g006_specialized_evidence.json"
    evidence_path = GRAPH / "g006_evidence.json"
    graph_path = GRAPH / "g006_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G6 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g006_evidence_input_v1", "generation": 6,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g006", "kind": "evidence",
        "statement": "G6 coarse tool-class and elapsed-bucket timeout localization on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 53, "timeout_failure_count": 3, "other_terminal_failure_count": 0,
        "strict_pass_count": 37, "strict_pass_rate_all": round(37 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "coarse_tool_class_timeout_localization_diagnostic",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "A coarse in-flight class localizes an operation, not the cause of timeout or task correctness.",
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
        "schema_version": "dab_research_graph_evidence_v2", "generation": 6,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 6,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g006", "target": "experiment:g006", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G6 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 53,
        "timeout_failures": 3, "strict_pass": 37, "strict_denominator": 56,
        "strict_unknown_completed": 3, "specialized_status": special["overall_status"],
        "component_statuses": {k: v["status"] for k, v in special["components"].items()},
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
