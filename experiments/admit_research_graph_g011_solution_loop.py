#!/usr/bin/env python3
"""Mechanically admit the activation-wired G11 source without evaluation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_hash, source_tree_manifest


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CANDIDATE = BASE / "g011_solution_loop_candidate_003"
CHILD = CANDIDATE / "repo"
ASSEMBLY = CANDIDATE / "assembly.json"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
IMPLEMENTATION = WORK / "implementation_manifest_revision_002.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
PARENT = BASE / "g007_candidate_002/repo"
PARENT_GRAPH = BASE / "g010_safe_snapshot/g010_graph.json"
OUT = CANDIDATE / "admission.json"
ARCHIVE = CANDIDATE / "source.tar.gz"

PARENT_SHA256 = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
CANDIDATE_SHA256 = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA256 = "44a7a9508f8f1c68ab0ab70dfb3c820ca8f61eeefe880d1bc37453f614c75675"
PARENT_GRAPH_SHA256 = "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a"

INPUT_HASHES = {
    "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json":
        "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7",
    "dab_corpus/registry.json":
        "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff",
    "prompts/dab/dab_tool_agent_policy_zero_start.txt":
        "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797",
}
EXPECTED_FAILURES = {
    "tests/test_tool_failure_recovery.py::test_active_dispatch_normal_success_avoids_recovery",
    "tests/test_tool_failure_recovery.py::test_zero_iterations_resolves_unbounded",
    "tests/test_tool_failure_recovery.py::test_active_dispatch_recovery_contract",
    "tests/test_tool_failure_recovery.py::test_active_dispatch_keeps_one_root_and_bounds_two_repairs",
    "tests/test_tool_failure_recovery.py::test_active_dispatch_handles_malformed_json_and_unknown_tools",
}
MODIFIED = {
    "experiments/run_dab_tool_agent.py",
    "experiments/run_multi_query_baseline.py",
}
ADDED = {
    "experiments/g011_admission_checks.py",
    "experiments/g011_evidence_extractor.py",
    "experiments/g011_interface_contract.py",
    "experiments/g011_plan_evidence_record.py",
    "experiments/g011_runtime_plan_evidence.py",
    "prompts/dab/g011_plan_evidence_authoring_policy.txt",
    "tests/g011_support.py",
    "tests/test_g011_evidence_extractor.py",
    "tests/test_g011_interface_contract.py",
    "tests/test_g011_outer_runner_opt_in.py",
    "tests/test_g011_plan_evidence_record.py",
    "tests/test_g011_runtime_plan_evidence.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_python(arguments: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-B", *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def test_failures(root: Path, label: str) -> tuple[set[str], str]:
    basetemp = ROOT / ".g011_admission_tmp" / label
    result = run_python(
        ["-m", "pytest", "tests", "-q", "--tb=no", "-p", "no:cacheprovider", "--basetemp", str(basetemp)],
        cwd=root,
    )
    output = result.stdout + "\n" + result.stderr
    failures = set(re.findall(r"^FAILED (\S+)", output, flags=re.MULTILINE))
    if result.returncode != 1 or failures != EXPECTED_FAILURES:
        raise RuntimeError(f"{label} failure set differs: {sorted(failures)}; tail={output[-1200:]}")
    return failures, output


def main() -> None:
    if OUT.exists() or ARCHIVE.exists():
        raise RuntimeError("G11 admission or source archive already exists; refusing overwrite")
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    spec = research["formal_spec"]
    protocol = spec["fixed_protocol"]
    if (
        source_tree_hash(PARENT) != PARENT_SHA256
        or source_tree_hash(CHILD) != CANDIDATE_SHA256
        or sha256(RESEARCH) != RESEARCH_SHA256
        or sha256(IMPLEMENTATION) != IMPLEMENTATION_SHA256
        or sha256(PARENT_GRAPH) != PARENT_GRAPH_SHA256
        or assembly.get("parent_tree_sha256") != PARENT_SHA256
        or assembly.get("candidate_tree_sha256") != CANDIDATE_SHA256
        or assembly.get("implementation_manifest_sha256") != IMPLEMENTATION_SHA256
        or implementation.get("formal_candidate") is not True
        or implementation.get("evaluation_run") is not False
        or implementation.get("formal_run_performed") is not False
        or research.get("promotion_decision", {}).get("state") != "experiment_ready"
        or spec.get("code_parent", {}).get("generation") != 7
        or spec.get("code_parent", {}).get("candidate_tree_sha256") != PARENT_SHA256
    ):
        raise RuntimeError("G11 source, implementation, Research, or parent binding differs")
    required_protocol = {
        "description_mode": "full_db_description_no_hints",
        "exact56": True,
        "formal_runs": 1,
        "frozen_task_count": 56,
        "hints": False,
        "per_task_wall_timeout_seconds": 1200,
        "primary_metric": "completed_and_strict_true_over_all_56",
        "probe_run": False,
        "second_arm": False,
        "sham_run": False,
        "task_specific_logic": False,
        "answer_hint_validator_or_heldout_access": False,
    }
    if any(protocol.get(key) != value for key, value in required_protocol.items()):
        raise RuntimeError("G11 fixed protocol differs")
    if any(sha256(CHILD / name) != digest for name, digest in INPUT_HASHES.items()):
        raise RuntimeError("G11 frozen input hash differs")
    changed = set(assembly["modified_paths"] + assembly["added_paths"])
    if changed != MODIFIED | ADDED:
        raise RuntimeError("G11 assembled change boundary differs")

    focused_files = sorted(str(path) for path in (CHILD / "tests").glob("test_g011_*.py"))
    focused = run_python(
        ["-m", "pytest", *focused_files, "-q", "--tb=short", "-p", "no:cacheprovider",
         "--basetemp", str(ROOT / ".g011_admission_tmp" / "focused")],
        cwd=CHILD,
    )
    if focused.returncode != 0 or "116 passed" not in focused.stdout:
        raise RuntimeError(f"G11 focused tests differ: {(focused.stdout + focused.stderr)[-1200:]}")
    candidate_failures, _ = test_failures(CHILD, "candidate")
    parent_failures, _ = test_failures(PARENT, "parent")
    if candidate_failures != parent_failures:
        raise RuntimeError("G11 candidate and G7 parent failure sets differ")

    context_dir = WORK / "context"
    contract_code = (
        "import json; from experiments.g011_interface_contract import build_interface_contract; "
        f"print(json.dumps(build_interface_contract(repo_root=r'{CHILD}', context_dir=r'{context_dir}'), sort_keys=True))"
    )
    contract_result = run_python(["-c", contract_code], cwd=CHILD)
    if contract_result.returncode:
        raise RuntimeError(f"G11 explicit-context contract failed: {contract_result.stderr[-1200:]}")
    contract = json.loads(contract_result.stdout)
    mapping_code = (
        "import json; from experiments.g011_admission_checks import verify_admission_mapping; "
        f"print(json.dumps(verify_admission_mapping(repo_root=r'{CHILD}', context_dir=r'{context_dir}'), sort_keys=True))"
    )
    mapping_result = run_python(["-c", mapping_code], cwd=CHILD)
    if mapping_result.returncode:
        raise RuntimeError(f"G11 admission mapping failed: {mapping_result.stderr[-1200:]}")
    mapping = json.loads(mapping_result.stdout)
    if (
        contract.get("status") != "passed"
        or contract.get("failed_check_count") != 0
        or contract.get("admission_context_verified") is not True
        or mapping.get("status") != "passed"
        or mapping.get("required_admission_check_count") != 22
    ):
        raise RuntimeError("G11 interface contract or check mapping differs")

    rows = source_tree_manifest(CHILD)
    included = sorted({row["path"] for row in rows} | {"AGENTS.md", *INPUT_HASHES})
    for name in included:
        path = CHILD / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(CHILD.resolve()):
            raise RuntimeError(f"Unsafe G11 archive source: {name}")
    with tarfile.open(ARCHIVE, "x:gz") as stream:
        for name in included:
            stream.add(CHILD / name, arcname=name, recursive=False)

    record = {
        "schema_version": "dab_research_graph_g011_solution_loop_source_admission_v1",
        "status": "source_admitted_pending_remote_provider_and_runtime_preflight",
        "mechanism_id": "mech_g011_structural_plan_evidence_ledger",
        "code_parent": "g007",
        "parent_tree_sha256": PARENT_SHA256,
        "parent_graph_generation": 10,
        "parent_graph_sha256": PARENT_GRAPH_SHA256,
        "research_result_sha256": RESEARCH_SHA256,
        "implementation_manifest_sha256": IMPLEMENTATION_SHA256,
        "candidate_tree_sha256": CANDIDATE_SHA256,
        "source_archive_sha256": sha256(ARCHIVE),
        "source_file_count": len(rows),
        "changed_files": {name: sha256(CHILD / name) for name in sorted(changed)},
        "input_hashes": INPUT_HASHES,
        "runner_sha256": sha256(CHILD / "experiments/run_multi_query_baseline.py"),
        "agent_sha256": sha256(CHILD / "experiments/run_dab_tool_agent.py"),
        "authoring_policy_sha256": sha256(CHILD / "prompts/dab/g011_plan_evidence_authoring_policy.txt"),
        "focused_tests_passed": 116,
        "complete_candidate_tests_passed": 269,
        "complete_parent_tests_passed": 153,
        "inherited_failure_set": sorted(EXPECTED_FAILURES),
        "interface_contract_check_count": len(contract.get("checks", [])),
        "research_admission_check_count": mapping["required_admission_check_count"],
        "formal_activation": {
            "outer_flag": "--enable-g011-plan-evidence-ledger",
            "outer_default_enabled": False,
            "child_default_enabled": False,
            "formal_launcher_must_pass_flag": True,
        },
        "deferred_to_remote_preflight": [
            "live provider acceptance of the declared self_observation.freeform tool schema",
            "real upstream DataAgent no-task response-boundary and carrier hook",
            "database, Python, DAB, disk, DNS, TLS, credential, model, and response protocol",
        ],
        "mechanical_review": {
            "source_boundary": "G7 parent plus the frozen G11 ledger, extractor, explicit outer opt-in, and no-task tests",
            "no_leak_boundary": "G11 persists only anonymous structural allow-list fields; raw model record remains inside permitted model context",
            "semantic_boundary": "structural validity never means support, relevance, correctness, coverage, or truth",
            "evaluation_limit": "one exact-56 base/no-hint run with 1200 seconds per task",
            "anomalous_research_sentence": "non-operative report-exclusion text; not used as runtime behavior, launch permission, or Evidence",
        },
        "separate_user_authorization": "continue_workflow_received",
        "formal_evaluation_started": False,
    }
    OUT.write_text(json.dumps(record, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": record["status"],
        "candidate_tree_sha256": CANDIDATE_SHA256,
        "source_archive_sha256": record["source_archive_sha256"],
        "focused_tests_passed": 116,
        "inherited_failure_count": len(EXPECTED_FAILURES),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
