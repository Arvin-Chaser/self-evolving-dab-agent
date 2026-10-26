#!/usr/bin/env python3
"""Bind audited G4 results and pre-registered extraction into four Graph nodes."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
G4 = BASE / "g004_revision001"
SOURCE = G4 / "source"
RUN_ID = "baseline_g004_paired_journal_nohint_56_v1"
RUN = G4 / "evaluation" / RUN_ID
PID = 50136
TREE_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
G3_GRAPH_SHA = "039fc4fbc51410d87f7adc6e0c9017fb963d7979e9b10bce22f1c38949e67f29"
PRE_SHA = "f80e6f542991d478da4764288c7e4985b7dac46532b20a7389c46c5b501e31a3"
LAUNCH_SHA = "16f1cc78338159146382f9e97fbe489d3f69723d36140fbe19f913dc7393acc1"
SUMMARY_SHA = "ae2a433dbb2f29ed7ff1a311c1a523c2e6bb2f4f72682faf0832f969d754bf8f"
PROGRESS_SHA = "722bf5621af01d056fdb3fef58c02fa9dbb9746426b64cc14b3ef8eb938a3b48"
EXTRACTOR_SHA = "0cde1e258abe2c4f6d3656ff025a7da3e6669582249b3520be0d2226fb7b7bbd"


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
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G4 runner still active")
    paths = {
        "g3": GRAPH / "g003_graph.json",
        "pre": GRAPH / "g004_pre_execution.json",
        "launch": GRAPH / "g004_launch_manifest.json",
        "summary": RUN / "multi_query_summary.json",
        "progress": RUN / "multi_query_progress.json",
        "extractor": SOURCE / "experiments/g004_evidence_extractor.py",
    }
    expected = {
        "g3": G3_GRAPH_SHA, "pre": PRE_SHA, "launch": LAUNCH_SHA,
        "summary": SUMMARY_SHA, "progress": PROGRESS_SHA, "extractor": EXTRACTOR_SHA,
    }
    require(all(digest(paths[name]) == wanted for name, wanted in expected.items()),
            "G4 terminal source, parent Graph, or extractor hash differs")
    pre = read(paths["pre"])
    launch = read(paths["launch"])
    summary = read(paths["summary"])
    progress = read(paths["progress"])
    binding = pre["binding"]
    require(binding == launch["binding"] and binding["candidate_tree_sha256"] == TREE_SHA
            and binding["query_count"] == 56 and binding["query_timeout_sec"] == 1200,
            "G4 frozen protocol or source differs")
    rows = summary.get("per_query_feedback", [])
    progress_rows = progress.get("queries", [])
    require(len(rows) == len(progress_rows) == 56 and summary.get("query_count") == 56
            and all(a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
                    for a, b in zip(rows, progress_rows)),
            "G4 result partition differs")
    statuses = Counter(row.get("status") for row in rows)
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(statuses == {"completed": 53, "timeout": 3} and strict_pass == 34
            and strict_unknown == 3 and known_fail == 16
            and summary.get("strict_pass_count") == strict_pass,
            "G4 terminal results differ from audited counts")
    sys.path.insert(0, str(SOURCE))
    from experiments.g004_evidence_extractor import (  # noqa: E402
        COHORT_KNOWN_STRICT_FAIL, COHORT_STRICT_PASS,
        COHORT_STRICT_VERDICT_UNKNOWN, COHORT_TIMEOUT_FAILURE,
        JOURNAL_FILENAME, SIDECAR_FILENAME, build_evidence,
    )

    cohort_dirs = {
        COHORT_KNOWN_STRICT_FAIL: [], COHORT_STRICT_PASS: [],
        COHORT_STRICT_VERDICT_UNKNOWN: [], COHORT_TIMEOUT_FAILURE: [],
    }
    entries = []
    seen_ids = set()
    run_root = RUN / "runs"
    for index, row in enumerate(rows, start=1):
        run_id = row["run_id"]
        require(isinstance(run_id, str) and run_id not in seen_ids
                and run_id and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
                "G4 task run binding invalid")
        seen_ids.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(),
                "G4 task result directory missing")
        status = row["status"]
        if status == "timeout":
            cohort = COHORT_TIMEOUT_FAILURE
        elif row.get("strict_match_passed") is True:
            cohort = COHORT_STRICT_PASS
        elif row.get("strict_match_passed") is False:
            cohort = COHORT_KNOWN_STRICT_FAIL
        else:
            cohort = COHORT_STRICT_VERDICT_UNKNOWN
        cohort_dirs[cohort].append(run_dir)
        journal = run_dir / JOURNAL_FILENAME
        sidecar = run_dir / SIDECAR_FILENAME
        require(journal.is_file() and (sidecar.is_file() or status == "timeout"),
                "G4 pre-registered Evidence source missing")
        entries.append({
            "anonymous_task_index": index,
            "terminal_cohort": cohort,
            "journal_sha256": digest(journal),
            "normalized_sidecar_sha256": digest(sidecar) if sidecar.is_file() else None,
        })
    special = build_evidence(cohort_dirs)
    require(special["observed_task_count"] == 56 and special["observed_denominator_complete"] is True
            and special["raw_content_persisted"] is False
            and special["overall_status"] in {"supported", "contradicted", "inconclusive"}
            and {name: value["denominator"] for name, value in special["cohorts"].items()}
            == {COHORT_KNOWN_STRICT_FAIL: 16, COHORT_STRICT_PASS: 34,
                COHORT_STRICT_VERDICT_UNKNOWN: 3, COHORT_TIMEOUT_FAILURE: 3},
            "G4 specialized extraction differs from pre-registered contract")
    input_path = GRAPH / "g004_evidence_input_manifest.json"
    special_path = GRAPH / "g004_specialized_evidence.json"
    evidence_path = GRAPH / "g004_evidence.json"
    graph_path = GRAPH / "g004_graph.json"
    require(not any(path.exists() for path in (input_path, special_path, evidence_path, graph_path)),
            "G4 Evidence or Graph already exists")
    write_new(input_path, {
        "schema_version": "dab_research_graph_g004_evidence_input_v1", "generation": 4,
        "run_id": RUN_ID, "frozen_task_count": 56,
        "summary_sha256": SUMMARY_SHA, "progress_sha256": PROGRESS_SHA,
        "extractor_sha256": EXTRACTOR_SHA, "entries": entries,
    })
    write_new(special_path, special)
    now = datetime.now(timezone.utc).isoformat()
    node = {
        "id": "evidence:g004", "kind": "evidence",
        "statement": "G4 paired live/post-run structural alignment and timeout terminal localization on the frozen no-hint 56.",
        "frozen_task_count": 56, "ended_count": 56,
        "completed_count": 53, "timeout_failure_count": 3, "other_terminal_failure_count": 0,
        "strict_pass_count": 34, "strict_pass_rate_all": round(34 / 56, 6),
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "paired_live_postrun_structural_alignment",
        "specialized_status": special["overall_status"],
        "specialized_components": special["components"],
        "specialized_cohort_coverage": {
            name: value["complete_task_coverage"] for name, value in special["cohorts"].items()
        },
        "limits": [
            "A structural alignment result does not establish task progress, correctness, or causal gain.",
            "Timeouts are failures in the fixed 56 denominator; missing post-run sidecars remain unknown.",
            "Three completed strict verdicts remain unknown and are not reclassified.",
            "This is one unpaired run; score differences from earlier generations are descriptive only.",
        ],
        "artifact_refs": {
            "pre_execution_sha256": PRE_SHA, "launch_manifest_sha256": LAUNCH_SHA,
            "summary_sha256": SUMMARY_SHA, "progress_sha256": PROGRESS_SHA,
            "input_manifest_sha256": digest(input_path),
            "extractor_sha256": EXTRACTOR_SHA,
            "specialized_evidence_sha256": digest(special_path),
        },
    }
    write_new(evidence_path, {
        "schema_version": "dab_research_graph_evidence_v2", "generation": 4,
        "recorded_at_utc": now, "node": node,
    })
    write_new(graph_path, {
        "schema_version": "dab_research_graph_generation_v1", "generation": 4,
        "status": "four_nodes_complete", "pre_execution_sha256": PRE_SHA,
        "evidence_sha256": digest(evidence_path), "binding": binding,
        "nodes": [*pre["nodes"], node],
        "edges": [*pre["edges"], {
            "source": "evidence:g004", "target": "experiment:g004", "relation": "observes",
        }],
    })
    persisted = read(graph_path)
    require(len(persisted["nodes"]) == 4
            and [part["kind"] for part in persisted["nodes"]]
            == ["problem", "hypothesis", "experiment", "evidence"]
            and persisted["evidence_sha256"] == digest(evidence_path),
            "G4 four-node Graph structural verification failed")
    print(json.dumps({
        "status": "four_nodes_complete", "ended": 56, "completed": 53,
        "timeout_failures": 3, "other_failures": 0, "strict_pass": 34,
        "strict_denominator": 56, "strict_unknown_completed": 3,
        "specialized_status": special["overall_status"],
        "alignment_status": special["components"]["alignment"]["status"],
        "timeout_localization_status": special["components"]["timeout_terminal_localization"]["status"],
        "input_manifest_sha256": digest(input_path),
        "specialized_evidence_sha256": digest(special_path),
        "evidence_sha256": digest(evidence_path), "graph_sha256": digest(graph_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
