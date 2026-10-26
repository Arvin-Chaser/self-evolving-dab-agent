#!/usr/bin/env python3
"""Finalize audited G5 with its pre-registered extractor, exactly once."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G5 = BASE / "g005_revision001"
SOURCE = G5 / "source"
RUN_ID = "baseline_g005_provenance_nohint_56_v1"
RUN = G5 / "evaluation" / RUN_ID
PID = 1266
TREE_SHA = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
EXPECTED = {
    "parent": "fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda",
    "pre": "fc938800cb86d5badf6bc2f467aeaac79f77f414db046aeef77957a50c609598",
    "preflight": "a2f78405114c04d18fa2ebb7615f71622d89349832f8821b095e8048d549dc43",
    "launch": "77f3578f8116a6408e3fc0c88d52a544aa795fbf0c8b109b66a62a79ecf0d129",
    "summary": "091499286d2504291d569aa1acd30bc04991b1d978b02afdcffa13f7f6f1448a",
    "progress": "bf7f888958d94bc85f7c0c10c244577ff24833d4fa55308d8a1eb7428e61fbf1",
    "extractor": "81f6ccd056ceb883383fb8bd9288a187f67468612b7347073c6db7a13c357284",
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
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G5 runner still active")
    paths = {
        "parent": GRAPH / "g004_graph.json",
        "pre": GRAPH / "g005_pre_execution.json",
        "preflight": GRAPH / "g005_preflight.json",
        "launch": GRAPH / "g005_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g005_evidence_extractor.py",
    }
    require(all(digest(path) == EXPECTED[name] for name, path in paths.items()),
            "G5 audited input hash differs")
    pre, preflight, launch = read(paths["pre"]), read(paths["preflight"]), read(paths["launch"])
    summary, progress = read(paths["summary"]), read(paths["progress"])
    binding = pre["binding"]
    require(binding == preflight["binding"] == launch["binding"]
            and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200
            and binding["description_mode"] == "full_db_description_no_hints"
            and preflight["status"] == "passed" and launch["pid"] == PID,
            "G5 frozen run identity differs")
    rows, progress_rows = summary.get("per_query_feedback", []), progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)), "G5 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 51, "timeout": 5} and strict_pass == 30
            and strict_unknown == 2 and known_fail == 19
            and summary.get("strict_pass_count") == strict_pass,
            "G5 result counts differ from terminal audit")

    sys.path.insert(0, str(SOURCE))
    from experiments.g005_evidence_extractor import (
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_FAILURE,
        G005_SIDECAR_FILENAME, POSTRUN_SIDECAR_FILENAME, build_evidence,
    )
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
                "G5 task run binding invalid")
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G5 task result directory missing")
        if row["status"] == "timeout":
            cohort = COHORT_TIMEOUT_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        provenance = run_dir / G005_SIDECAR_FILENAME
        journal = run_dir / JOURNAL_FILENAME
        normalized = run_dir / POSTRUN_SIDECAR_FILENAME
        require(provenance.is_file() and journal.is_file()
                and (normalized.is_file() or row["status"] == "timeout"),
                "G5 pre-registered Evidence source missing")
        entries.append({
            "anonymous_task_index": index, "terminal_cohort": cohort,
            "provenance_sha256": digest(provenance), "journal_sha256": digest(journal),
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
            == {COHORT_KNOWN_STRICT_FAIL: 19, COHORT_STRICT_PASS: 30,
                COHORT_STRICT_VERDICT_UNKNOWN: 2, COHORT_TIMEOUT_FAILURE: 5},
            "G5 specialized Evidence contract differs")
    input_path = GRAPH / "g005_evidence_input_manifest.json"
    special_path = GRAPH / "g005_specialized_evidence.json"
    evidence_path = GRAPH / "g005_evidence.json"
    graph_path = GRAPH / "g005_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G5 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g005_evidence_input_v1", "generation": 5,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": EXPECTED["summary"], "progress_sha256": EXPECTED["progress"],
        "extractor_sha256": EXPECTED["extractor"], "entries": entries,
    })
    write_new(special_path, special)
    node = {
        "id": "evidence:g005", "kind": "evidence",
        "statement": "G5 provenance reason-code and timeout elapsed diagnostics on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 51, "timeout_failure_count": 5, "other_terminal_failure_count": 0,
        "strict_pass_count": 30, "strict_pass_rate_all": round(30 / 56, 6),
        "strict_verdict_missing_completed_count": 2,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "provenance_reason_and_timeout_elapsed_diagnostic",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["complete_task_coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "Structural provenance does not establish task correctness or causal gain.",
            "Timeouts are failures in the fixed 56 denominator; unavailable records remain unknown.",
            "Two completed strict verdicts remain unknown and are not reclassified.",
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
        "schema_version": "dab_research_graph_evidence_v2", "generation": 5,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 5,
        "status": "four_nodes_complete", "pre_execution_sha256": EXPECTED["pre"],
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g005", "target": "experiment:g005", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G5 four-node Graph verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 51,
        "timeout_failures": 5, "strict_pass": 30, "strict_denominator": 56,
        "strict_unknown_completed": 2, "specialized_status": special["overall_status"],
        "component_statuses": {k: v["status"] for k, v in special["components"].items()},
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
