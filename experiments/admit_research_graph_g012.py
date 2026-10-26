#!/usr/bin/env python3
"""Freeze and independently check G12 source; never launch an evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_hash, source_tree_manifest


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g011_solution_loop_candidate_003/repo"
WORK = BASE / "g012_formal_implementation_002"
PATCH = WORK / "candidate_patch"
PARENT_HASH = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
MANIFEST_HASH = "20d71e71ddfdae7f6a23001407d46c9a718ada6572f055e4ea3d60d258579516"
BINDING_HASH = "310d63744aebefb51e926373ae211d4ce37d16c2c3a117103e5feab701e881c9"
RESEARCH_HASH = "67086825a82f1bd3bcc34297c85410ced236c965085c2ec94723bfc567c0b190"
EXPECTED_MODIFIED = {"experiments/run_dab_tool_agent.py", "experiments/run_multi_query_baseline.py"}
EXPECTED_ADDED = {
    "experiments/g012_interface_contract.py",
    "experiments/g012_runtime_gap_action.py",
    "experiments/g012_evidence_extractor.py",
    "prompts/dab/g012_uncertainty_gap_action_authoring_policy.txt",
    "tests/g012_support.py",
    "tests/test_g012_formal_runtime.py",
    "tests/test_g012_outer_runner_opt_in.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_new(path: Path, value: dict | list) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=True, indent=2)
        stream.write("\n")


def inventory(root: Path) -> list[dict[str, str]]:
    return [
        {"path": p.relative_to(root).as_posix(), "sha256": digest(p)}
        for p in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix())
        if p.is_file() and not any(
            part in {"__pycache__", ".pytest_cache", ".tmp"}
            for part in p.relative_to(root).parts
        )
    ]


def inventory_hash(rows: list[dict[str, str]]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def copy_sources(source: Path, target: Path) -> None:
    names = {row["path"] for row in source_tree_manifest(source)} | {"AGENTS.md"}
    # Upstream fixtures are outside the historical bounded-source hash. Bind
    # them separately in the full-file manifest instead of silently omitting them.
    names.update(
        str(p.relative_to(source).as_posix()) for p in (source / "external").rglob("*.py")
        if "__pycache__" not in p.parts
    )
    for name in sorted(names):
        src = source / name
        if src.is_symlink() or not src.resolve().is_relative_to(source.resolve()):
            raise RuntimeError("Unsafe source path")
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def run_tests(repo: Path, output: Path, label: str, focused: bool = False) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    arguments = ["-m", "pytest", "tests", "-q", "--tb=no", "-p", "no:cacheprovider"]
    if focused:
        arguments[2:3] = [str(p.relative_to(repo)) for p in sorted((repo / "tests").glob("test_g01[12]_*.py"))]
    result = subprocess.run(
        [sys.executable, "-B", *arguments], cwd=repo, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    text = result.stdout + "\n" + result.stderr
    log = output / f"{label}.txt"
    with log.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    failures = sorted(set(re.findall(r"^FAILED (\S+)", text, re.MULTILINE)))
    passed = re.findall(r"(\d+) passed", text)
    return {
        "exit_code": result.returncode, "failures": failures,
        "passed_count": int(passed[-1]) if passed else 0,
        "log": log.name, "log_sha256": digest(log),
        "command": [sys.executable, "-B", *arguments],
        "scope": "synthetic_no_task_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "g012_admission_001")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != BASE.resolve() or output.exists():
        raise RuntimeError("Output must be a new direct child of the research directory")
    if digest(PATCH / "implementation_manifest.json") != MANIFEST_HASH:
        raise RuntimeError("Implementation manifest changed")
    if digest(WORK / "input_binding.json") != BINDING_HASH or source_tree_hash(PARENT) != PARENT_HASH:
        raise RuntimeError("Sole parent or input binding changed")
    binding = json.loads((WORK / "input_binding.json").read_text(encoding="utf-8"))
    manifest = json.loads((PATCH / "implementation_manifest.json").read_text(encoding="utf-8"))
    research = json.loads((WORK / "context/research_contract.json").read_text(encoding="utf-8"))
    if research["state"] != "experiment_ready" or digest(WORK / "context/research_contract.json") != RESEARCH_HASH:
        raise RuntimeError("Research contract changed")
    if research["formal_spec"]["experiment"]["code_parent"]["candidate_tree_sha256"] != PARENT_HASH:
        raise RuntimeError("Research sole parent differs")
    for name, sha in binding["context_sha256"].items():
        if digest(WORK / "context" / name) != sha:
            raise RuntimeError(f"Context binding changed: {name}")
    for name, sha in binding["scoped_parent_source_sha256"].items():
        parent_file = PARENT / name
        if name.startswith("external/") and not parent_file.exists():
            parent_file = ROOT / name
        if digest(parent_file) != sha:
            raise RuntimeError(f"Scoped parent changed: {name}")
    modified = {row["path"] for row in manifest["modified_paths"]}
    added = {row["path"] for row in manifest["new_paths"]}
    if modified != EXPECTED_MODIFIED or added != EXPECTED_ADDED:
        raise RuntimeError("Candidate change surface differs")
    scoped_rows = manifest["unchanged_scoped_parent_paths"] + manifest["modified_paths"] + manifest["new_paths"]
    for row in scoped_rows:
        if digest(PATCH / row["path"]) != row["sha256"]:
            raise RuntimeError(f"Patch hash differs: {row['path']}")
    surface = "".join(f"{row['path']}\0{row['sha256']}\n" for row in sorted(scoped_rows, key=lambda row: row["path"]))
    if hashlib.sha256(surface.encode()).hexdigest() != manifest["candidate_source_surface"]["sha256"]:
        raise RuntimeError("Combined scoped surface differs")
    output.mkdir()
    child = output / "repo"
    control = output / "parent_control"
    copy_sources(PARENT, child)
    copy_sources(PARENT, control)
    for row in manifest["unchanged_scoped_parent_paths"]:
        if row["path"].startswith("external/"):
            for repo in (child, control):
                destination = repo / row["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(PATCH / row["path"], destination)
    for row in manifest["modified_paths"] + manifest["new_paths"]:
        destination = child / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PATCH / row["path"], destination)
    before = {row["path"]: row["sha256"] for row in source_tree_manifest(PARENT)}
    after = {row["path"]: row["sha256"] for row in source_tree_manifest(child)}
    actual_modified = {p for p in before.keys() & after.keys() if before[p] != after[p]}
    if actual_modified != modified or after.keys() - before.keys() != added or before.keys() - after.keys():
        raise RuntimeError("Complete child change surface differs")
    files = inventory(child)
    tree = source_tree_hash(child)
    write_new(output / "child_files.json", files)
    archive = output / "source.tar.gz"
    with tarfile.open(archive, "x:gz") as stream:
        for row in files:
            stream.add(child / row["path"], arcname=row["path"], recursive=False)
    assembly = {
        "schema_version": "g012_full_source_assembly_v1", "created_at_utc": now(),
        "code_parent_generation": 11, "parent_tree_sha256": PARENT_HASH,
        "candidate_tree_sha256": tree, "source_file_count": len(after),
        "complete_file_count": len(files), "complete_file_inventory_sha256": inventory_hash(files),
        "child_files_sha256": digest(output / "child_files.json"),
        "source_archive_sha256": digest(archive),
        "implementation_manifest_sha256": MANIFEST_HASH, "research_sha256": RESEARCH_HASH,
        "input_binding_sha256": BINDING_HASH,
        "modified_paths": sorted(modified), "added_paths": sorted(added),
        "removed_paths": [], "scoped_patch_hashes_verified": len(scoped_rows),
        "source_scope": "Complete inherited active source tree plus hash-bound upstream fixtures; no benchmark inputs, databases, credentials, caches or logs",
        "protocol": research["formal_spec"]["experiment"]["fixed_protocol"],
        "formal_evaluation_started": False, "launch_authorized": False,
        "admission_tool_sha256": digest(Path(__file__)),
    }
    write_new(output / "assembly.json", assembly)
    focused = run_tests(child, output, "focused", focused=True)
    candidate = run_tests(child, output, "candidate_full")
    parent = run_tests(control, output, "parent_full")
    expected = sorted(json.loads((PARENT.parent / "admission.json").read_text())["inherited_failure_set"])
    tests_passed = (
        focused["exit_code"] == 0 and focused["passed_count"] == 149
        and candidate["exit_code"] == parent["exit_code"] == 1
        and candidate["failures"] == parent["failures"] == expected
        and candidate["passed_count"] - parent["passed_count"] == 33
    )
    unchanged = inventory(child) == files and source_tree_hash(PARENT) == PARENT_HASH
    record = {
        "schema_version": "g012_source_admission_v1", "created_at_utc": now(),
        "status": "source_checks_passed_pending_runtime_gates" if tests_passed and unchanged else "source_checks_failed",
        "assembly_sha256": digest(output / "assembly.json"), "candidate_tree_sha256": tree,
        "complete_file_inventory_sha256": inventory_hash(files), "source_unchanged_after_tests": unchanged,
        "focused": focused, "candidate_full": candidate, "parent_full": parent,
        "exact_inherited_failures_only": candidate["failures"] == parent["failures"] == expected,
        "remaining_gates": [
            "real_upstream_response_boundary", "live_provider_schema_and_carrier",
            "real_model_visible_ref_authorship", "raw_context_no_leak",
            "enabled_disabled_timing_scoring_equivalence", "transport_failure_fallback",
        ],
        "formal_evaluation_started": False, "launch_authorized": False,
    }
    write_new(output / "source_admission.json", record)
    print(json.dumps({"output": str(output), "status": record["status"], "candidate_tree_sha256": tree,
                      "focused_passed": focused["passed_count"], "candidate_passed": candidate["passed_count"],
                      "parent_passed": parent["passed_count"], "inherited_failure_count": len(candidate["failures"])}))
    if not tests_passed or not unchanged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
