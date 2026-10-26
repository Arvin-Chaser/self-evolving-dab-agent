#!/usr/bin/env python3
"""Mechanically admit G9 source without launching a formal evaluation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash
from experiments.intent_candidate_workspace import source_tree_manifest


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CANDIDATE = BASE / "g009_candidate_001"
CHILD = CANDIDATE / "repo"
ASSEMBLY = CANDIDATE / "assembly.json"
IMPLEMENTATION = CANDIDATE / "scoped_source/implementation_manifest.json"
RESEARCH = BASE / "g009_research_meta_001/final_raw.txt"
OUT = CANDIDATE / "admission.json"
ARCHIVE = CANDIDATE / "source.tar.gz"
PARENT_SHA = "adeefdde02075bc4ea458f6a74ad1c418dd096e92acd1b262ccb25537bcf4105"
CANDIDATE_SHA = "206c4f5186a66d72b851aa888eb75d975d5ce2085970a322881997b119f16d0d"
RESEARCH_SHA = "919b07ed74339d84e338da7ac30a3942196775d542da587b413fcf6702d15581"
PARENT_GRAPH_SHA = "c769fd157db33e7fe2432285d4e15718307f5c7b91dde91ebcf83b19fbca83e8"
INPUT_HASHES = {
    "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json":
        "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7",
    "dab_corpus/registry.json":
        "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff",
    "prompts/dab/dab_tool_agent_policy_zero_start.txt":
        "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797",
}
FOCUSED_TESTS = [
    "tests/test_g009_verification_turn_gate_hook.py",
    "tests/test_g009_evidence_extractor.py",
    "tests/test_g009_interface_contract.py",
    "tests/test_g008_verification_audit_hook.py",
    "tests/test_g008_evidence_extractor.py",
    "tests/test_g008_interface_contract.py",
    "tests/test_g007_last_pre_exec_sidecar.py",
    "tests/test_g007_evidence_extractor.py",
    "tests/test_g007_interface_contract.py",
    "tests/test_g006_tool_class_sidecar.py",
    "tests/test_g006_evidence_extractor.py",
    "tests/test_g005_provenance_sidecar.py",
    "tests/test_g005_evidence_extractor.py",
    "tests/test_g004_paired_structural_journal.py",
    "tests/test_g004_evidence_extractor.py",
    "tests/test_g003_proposed_call_diagnostic.py",
    "tests/test_g002_lifecycle_stage.py",
    "tests/test_deadline_reserve_g001.py",
]
CHANGED = {
    "experiments/run_dab_tool_agent.py",
    "experiments/g009_verification_turn_gate_sidecar.py",
    "experiments/g009_evidence_extractor.py",
    "experiments/g009_interface_contract.py",
    "tests/test_g009_verification_turn_gate_hook.py",
    "tests/test_g009_evidence_extractor.py",
    "tests/test_g009_interface_contract.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Contract check failed ({result.returncode}): {result.stderr[-1000:]}")
    return result.stdout.strip()


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G9 admission or source archive already exists")
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    if (source_tree_hash(CHILD) != CANDIDATE_SHA
            or sha(RESEARCH) != RESEARCH_SHA
            or assembly["parent_tree_sha256"] != PARENT_SHA
            or assembly["candidate_tree_sha256"] != CANDIDATE_SHA
            or assembly["implementation_manifest_sha256"] != sha(IMPLEMENTATION)
            or implementation["status"] != "implemented_synthetic_verified_not_evaluated"
            or implementation["blocked"] is not False
            or implementation["formal_run_performed"] is not False
            or research["selected_direction"] != "verification_answer"
            or research["experiment"]["code_parent_tree_sha256"] != PARENT_SHA
            or research["experiment"]["intervention_class"] != "behavioral_pre_terminal_audit"):
        raise RuntimeError("G9 candidate, implementation, or Research binding differs")
    protocol = research["experiment"]["fixed_protocol"]
    required = {
        "description_mode": "full_db_description_no_hints",
        "frozen_task_count": 56,
        "hints": False,
        "per_task_wall_timeout_seconds": 1200,
        "primary_metric": "completed_and_strict_true_over_all_56",
        "timeouts": "failures_in_fixed_denominator",
        "formal_runs": 1,
        "second_arm": False,
        "sham_run": False,
        "probe_run": False,
    }
    if any(protocol.get(key) != value for key, value in required.items()):
        raise RuntimeError("G9 fixed protocol differs")
    if any(sha(CHILD / path) != digest for path, digest in INPUT_HASHES.items()):
        raise RuntimeError("G9 frozen input hashes differ")
    changed = set(assembly["modified_paths"] + assembly["added_paths"])
    if changed != CHANGED:
        raise RuntimeError("G9 change boundary differs")
    entries = {row["path"]: row["sha256"] for row in implementation["files"]}
    if any(entries.get(path) != sha(CHILD / path) for path in changed):
        raise RuntimeError("G9 changed source differs from manifest")
    tests = check(["python", "-m", "pytest", *FOCUSED_TESTS, "-q", "-p", "no:cacheprovider"], cwd=CHILD)
    if "238 passed" not in tests:
        raise RuntimeError("G9 focused test count differs")
    check(["python", "-m", "experiments.g009_interface_contract", "--repo-root", "."], cwd=CHILD)
    probe = json.loads(check(["python", str(ROOT / "experiments/probe_research_graph_g009_upstream_contract.py")], cwd=ROOT))
    if probe.get("status") != "g009_synthetic_upstream_hook_contract_passed":
        raise RuntimeError("G9 real-upstream synthetic contract differs")

    rows = source_tree_manifest(CHILD)
    included = sorted({row["path"] for row in rows} | {"AGENTS.md", *INPUT_HASHES})
    for name in included:
        path = CHILD / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve()):
            raise RuntimeError(f"Unsafe G9 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)
    record = {
        "schema_version": "dab_research_graph_g009_source_admission_v1",
        "status": "source_admitted_pending_remote_preflight",
        "code_parent": "g008",
        "parent_tree_sha256": PARENT_SHA,
        "parent_graph_sha256": PARENT_GRAPH_SHA,
        "research_result_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": sha(IMPLEMENTATION),
        "candidate_tree_sha256": CANDIDATE_SHA,
        "source_archive_sha256": sha(ARCHIVE),
        "source_file_count": len(rows),
        "changed_files": {name: sha(CHILD / name) for name in sorted(changed)},
        "input_hashes": INPUT_HASHES,
        "runner_sha256": sha(CHILD / "experiments/run_multi_query_baseline.py"),
        "agent_sha256": sha(CHILD / "experiments/run_dab_tool_agent.py"),
        "synthetic_contract_tests_passed": 238,
        "real_upstream_contract": probe,
        "mechanical_review": {
            "source_boundary": "one runner integration and six G9 source/test files",
            "tool_response_pairing": "synthetic real-upstream first/same-response/later-turn check",
            "no_answer_boundary": "new hook reads tool name, tool-call id, response boundary, and ordinals",
            "evaluation_limit": "one exact-56 no-hint run, 1200 seconds per task",
            "research_limit": "structural audit exposure cannot establish semantic quality or causal gain",
        },
        "formal_evaluation_started": False,
    }
    with OUT.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": record["status"], "candidate_tree_sha256": CANDIDATE_SHA,
                      "source_archive_sha256": record["source_archive_sha256"],
                      "focused_tests": 238, "real_upstream_contract": probe["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
