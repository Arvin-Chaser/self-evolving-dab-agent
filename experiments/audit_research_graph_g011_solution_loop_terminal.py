#!/usr/bin/env python3
"""Answer-blind terminal audit of the frozen G11 solution-loop run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
GRAPH = BASE / "graph"
REVISION = BASE / "g011_solution_loop_revision001"
SOURCE = REVISION / "source"
RUN_ID = "g011_structural_plan_evidence_ledger_nohint_56_v1"
RUN = REVISION / "evaluation" / RUN_ID
PID = 606199
TREE_SHA = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
PARENT_SHA = "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a"
RESEARCH_SHA = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA = "44a7a9508f8f1c68ab0ab70dfb3c820ca8f61eeefe880d1bc37453f614c75675"
ADMISSION_SHA = "9121bfb8a6797d55086c18f433b067addd3df8f2ed0a950530442c21423ad068"
ASSEMBLY_SHA = "e251b93d3e1d98b2acbb095a8ea133f3e1a9da16f64ebdd3d471dc1837ad48d7"
MEMORY_V5_SHA = "0c83c560e7c94522ca2b618f7cec6b8b7a81c833c6e054ff0f18dfa7d1d481bf"
FILES = {
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
SIDECARS = {
    "journal": "g004_paired_structural_journal.jsonl",
    "normalized": "g004_postrun_normalized_structural.json",
    "provenance": "g005_provenance_sidecar.jsonl",
    "tool_class": "g006_tool_class_sidecar.jsonl",
    "last_pre_exec": "g007_last_pre_exec_sidecar.jsonl",
    "g011_summary": "g011_plan_evidence_summary.json",
    "g011_records": "g011_plan_evidence_sidecar.jsonl",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cmdline = Path(f"/proc/{PID}/cmdline")
    require(not cmdline.is_file() or not cmdline.read_bytes(), "G11 runner remains active")
    hashes = {name: digest(path) for name, path in FILES.items()}
    require(hashes["parent"] == PARENT_SHA, "parent Graph changed")
    pre = read(FILES["pre"])
    preflight = read(FILES["preflight"])
    claim = read(FILES["claim"])
    launch = read(FILES["launch"])
    incident = read(FILES["incident"])
    binding = pre["binding"]
    args = launch.get("command", [])
    require(
        binding == preflight.get("binding") == claim.get("binding") == launch.get("binding")
        and binding.get("candidate_tree_sha256") == TREE_SHA
        and binding.get("parent_graph_sha256") == PARENT_SHA
        and binding.get("research_result_sha256") == RESEARCH_SHA
        and binding.get("implementation_manifest_sha256") == IMPLEMENTATION_SHA
        and binding.get("admission_sha256") == ADMISSION_SHA
        and binding.get("assembly_sha256") == ASSEMBLY_SHA
        and binding.get("research_memory_v5_sha256") == MEMORY_V5_SHA
        and binding.get("mechanism_id") == "mech_g011_structural_plan_evidence_ledger"
        and binding.get("code_parent_generation") == 7
        and binding.get("formal_activation_flag") == "--enable-g011-plan-evidence-ledger"
        and binding.get("query_count") == 56
        and binding.get("query_timeout_sec") == 1200
        and binding.get("description_mode") == "full_db_description_no_hints"
        and preflight.get("status") == "passed"
        and preflight.get("provider_probe", {}).get("http_status") == 200
        and preflight.get("provider_probe", {}).get("declared_freeform_carrier_accepted") is True
        and preflight.get("real_upstream_probe", {}).get("response_boundary_fixture_passed") is True
        and incident.get("formal_evaluation_started") is False
        and claim.get("pre_execution_sha256") == hashes["pre"]
        and claim.get("preflight_sha256") == hashes["preflight"]
        and launch.get("preflight_sha256") == hashes["preflight"]
        and launch.get("pid") == PID
        and "--run-id" in args
        and args[args.index("--run-id") + 1] == RUN_ID
        and "--enable-g011-plan-evidence-ledger" in args,
        "frozen protocol, claim, preflight, or activation differs",
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
    require(tree == TREE_SHA, "deployed source tree changed")
    sys.path.insert(0, str(SOURCE))
    from experiments.g011_interface_contract import find_sidecar_violations

    summary = read(FILES["summary"])
    progress = read(FILES["progress"])
    rows = summary.get("per_query_feedback", [])
    progress_rows = progress.get("queries", [])
    context = summary.get("execution_context", {})
    require(
        summary.get("query_count") == len(rows) == len(progress_rows) == 56
        and context.get("db_description_mode") == "base"
        and context.get("query_timeout_sec") == 1200
        and all(
            a.get("run_id") == b.get("run_id") and a.get("status") == b.get("status")
            for a, b in zip(rows, progress_rows)
        ),
        "summary, progress, or evaluation protocol differs",
    )
    statuses = Counter(row.get("status") for row in rows)
    require(set(statuses) <= {"completed", "timeout", "failed"}, "unknown terminal status")
    strict_pass = sum(row["status"] == "completed" and row.get("strict_match_passed") is True for row in rows)
    strict_unknown = sum(row["status"] == "completed" and row.get("strict_match_passed") is None for row in rows)
    known_fail = sum(row["status"] == "completed" and row.get("strict_match_passed") is False for row in rows)
    require(
        sum(statuses.values()) == 56
        and strict_pass + strict_unknown + known_fail == statuses["completed"]
        and summary.get("strict_pass_count") == strict_pass,
        "result partition differs",
    )

    counts = Counter()
    seen: set[str] = set()
    run_root = RUN / "runs"
    for row in rows:
        run_id = row.get("run_id")
        require(
            isinstance(run_id, str) and run_id and run_id not in seen
            and "/" not in run_id and "\\" not in run_id and ".." not in run_id,
            "task run identity invalid",
        )
        seen.add(run_id)
        run_dir = run_root / run_id
        require(run_dir.resolve().parent == run_root.resolve() and run_dir.is_dir(), "task run directory missing")
        for key, filename in SIDECARS.items():
            counts[key] += (run_dir / filename).is_file()
        require(
            all((run_dir / SIDECARS[key]).is_file() for key in (
                "journal", "provenance", "tool_class", "last_pre_exec"
            )),
            "inherited task sidecar missing",
        )
        if row["status"] == "completed":
            require(
                (run_dir / SIDECARS["normalized"]).is_file()
                and (run_dir / SIDECARS["g011_summary"]).is_file(),
                "completed task sidecar missing",
            )
            g011_summary = read(run_dir / SIDECARS["g011_summary"])
            require(
                not find_sidecar_violations([], g011_summary)
                and g011_summary.get("record_count") == 0
                and g011_summary.get("guidance_binding_count") == 0,
                "G11 summary schema, no-leak boundary, or zero-record result differs",
            )
    require(statuses["failed"] == 0, "other failures require infrastructure review")
    require(
        counts["journal"] == counts["provenance"] == counts["tool_class"]
        == counts["last_pre_exec"] == 56
        and counts["normalized"] == counts["g011_summary"] == statuses["completed"],
        "sidecar coverage differs",
    )
    print(json.dumps({
        "status": "valid_terminal_run_pending_evidence",
        "ended": 56, "completed": statuses["completed"],
        "timeout_failures": statuses["timeout"], "other_failures": statuses["failed"],
        "strict_pass": strict_pass, "strict_denominator": 56,
        "strict_unknown_completed": strict_unknown, "known_strict_fail": known_fail,
        "sidecar_counts": dict(counts), "hashes": hashes,
        "candidate_tree_sha256": tree,
        "research_sha256_expected": RESEARCH_SHA,
        "implementation_sha256_expected": IMPLEMENTATION_SHA,
        "admission_sha256_expected": ADMISSION_SHA,
        "launch_command_activation_count": args.count("--enable-g011-plan-evidence-ledger"),
        "launch_manifest_count": len(list(GRAPH.glob("g011_solution_loop_launch_manifest*.json"))),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
