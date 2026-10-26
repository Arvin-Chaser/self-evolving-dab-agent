#!/usr/bin/env python3
"""Independently verify the G11 solution-loop interface artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g011_solution_loop_interface_investigation_001"
SCOPED = WORK / "scoped_source"
META_OUT = BASE / "g011_solution_loop_implementation_meta_001"
MANIFEST = SCOPED / "exploratory_implementation_manifest.json"
OUT = WORK / "independent_verification.json"

EXPECTED_RESEARCH_SHA = "8ac5183d11f4ff1eb948abb0eec95990ebd644be4addddb0a18209f973f8b934"
EXPECTED_PARENT_SHA = "206c4f5186a66d72b851aa888eb75d975d5ce2085970a322881997b119f16d0d"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Independent verification already exists")
    binding = json.loads((WORK / "input_binding.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        binding.get("research_sha256") != EXPECTED_RESEARCH_SHA
        or binding.get("parent_tree_sha256") != EXPECTED_PARENT_SHA
    ):
        raise RuntimeError("Frozen input binding differs")
    if (
        manifest.get("status") != "feasible_bounded"
        or manifest.get("not_formal_candidate") is not True
    ):
        raise RuntimeError("Implementation manifest status differs")
    authorization = manifest.get("authorization")
    if not isinstance(authorization, dict) or any(authorization.values()):
        raise RuntimeError("Implementation manifest crossed an authorization boundary")

    output_hashes = manifest.get("output_files_sha256")
    if not isinstance(output_hashes, dict) or not output_hashes:
        raise RuntimeError("Implementation output hashes are missing")
    verified_hashes = {}
    for relative, expected in output_hashes.items():
        path = (SCOPED / relative).resolve()
        if not path.is_relative_to(SCOPED.resolve()) or not path.is_file():
            raise RuntimeError(f"Implementation output is unavailable: {relative}")
        actual = sha(path)
        if actual != expected:
            raise RuntimeError(f"Implementation output hash differs: {relative}")
        verified_hashes[relative] = actual

    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]
    completed = subprocess.run(
        command,
        cwd=SCOPED,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    test_output = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests", test_output)
    tests_run = int(match.group(1)) if match else None
    if completed.returncode != 0 or tests_run != 66 or "OK" not in test_output:
        raise RuntimeError("Independent synthetic test run failed")

    event_rows = [
        json.loads(line)
        for line in (META_OUT / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terminal_event = event_rows[-1]
    if (
        terminal_event.get("type") != "turn.failed"
        or "idle timeout" not in terminal_event.get("error", {}).get("message", "")
        or (META_OUT / "final_raw.txt").exists()
    ):
        raise RuntimeError("Implementation Meta transport incident differs")

    coverage = manifest.get("intent_coverage", {})
    expected_coverage = {
        "record_lifecycle": "implemented_bounded",
        "structural_validation": "implemented_bounded",
        "behavior_use": "implemented_bounded_synthetic",
    }
    if any(
        coverage.get(name, {}).get("status") != status
        for name, status in expected_coverage.items()
    ):
        raise RuntimeError("Intent coverage status differs")

    report = {
        "schema_version": "g011_solution_loop_interface_independent_verification_v1",
        "status": "artifacts_verified_transport_incomplete",
        "research_sha256": EXPECTED_RESEARCH_SHA,
        "parent_tree_sha256": EXPECTED_PARENT_SHA,
        "manifest_sha256": sha(MANIFEST),
        "manifest_status": manifest["status"],
        "intent_coverage": expected_coverage,
        "tests": {
            "command": "python -B -m unittest discover -s tests -t . -v",
            "tests_run": tests_run,
            "returncode": completed.returncode,
            "status": "passed_independently",
        },
        "verified_output_sha256": verified_hashes,
        "transport_incident": {
            "meta_process_returned_success": False,
            "final_message_present": False,
            "terminal_event": terminal_event,
            "interpretation": (
                "The model wrote the prototype, tests, findings, and manifest before the SSE idle timeout. "
                "The independent verification establishes artifact integrity only; it does not repair or "
                "invent a missing final model message."
            ),
        },
        "boundary": {
            "not_formal_candidate": True,
            "benchmark_run": False,
            "real_model_behavior_tested": False,
            "semantic_support_verified": False,
            "score_or_causal_benefit_established": False,
        },
    }
    OUT.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "path": str(OUT),
                "sha256": sha(OUT),
                "tests_run": tests_run,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
