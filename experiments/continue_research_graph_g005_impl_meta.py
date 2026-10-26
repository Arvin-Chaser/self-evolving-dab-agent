#!/usr/bin/env python3
"""Resume interrupted G5 Implementation Meta for bounded mechanical completion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g005_candidate_001/scoped_source"
RESEARCH = BASE / "g005_research_meta_002/final_raw.txt"
OUT = BASE / "g005_implementation_meta_002"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"


def main() -> None:
    if OUT.exists() or hashlib.sha256(RESEARCH.read_bytes()).hexdigest() != RESEARCH_SHA:
        raise RuntimeError("G5 continuation exists or frozen Research hash differs")
    required = [
        "experiments/g005_provenance_sidecar.py",
        "experiments/g005_evidence_extractor.py",
        "tests/test_g005_provenance_sidecar.py",
        "tests/test_g005_evidence_extractor.py",
    ]
    if any(not (CHILD / name).is_file() for name in required):
        raise RuntimeError("Interrupted G5 candidate is incomplete")
    OUT.mkdir(exist_ok=False)
    prompt = (
        "You are the SAME G5 Implementation Meta continuing an interrupted first "
        "attempt. This is repair attempt 1 of at most 3 for the same frozen G5 "
        "Problem/Hypothesis/Experiment/measurement_plan; do not change research "
        "semantics. Work only in this scoped answer-free G4 child. Do not read "
        "benchmark tasks, answers, hints, validators, raw traces, results, old lines, "
        "credentials, parent repository, remote server, or network. The first "
        "process wrote G5 recorder, extractor, integration, and synthetic tests but "
        "ended without final response or implementation_manifest.json. Mechanical "
        "check: 17 G5 synthetic tests passed. Four inherited parent test modules "
        "cannot collect in this intentionally minimal scoped workspace because "
        "experiments.dab_answer_utils and test_tool_failure_recovery are absent; "
        "this is not evidence of candidate failure and the full assembled child "
        "will run those tests later. Please inspect existing G5 files, finish any "
        "incomplete implementation, run the G5 synthetic tests, and write a "
        "machine-readable implementation_manifest.json with changed paths, SHA256 "
        "hashes, tests, and unresolved mechanical risks. Focus on the hook and "
        "post-exec boundary, write-only/no-leakage, elapsed fail-closed rules, "
        "extractor's exact unknown/negative precedence, 56-task cohort protocol, "
        "and enabled-vs-disabled inertness. Do not claim full parent test coverage "
        "from this scoped workspace. If faithful implementation is impossible, "
        "write BLOCKED.md with source-level reasons and do not claim readiness. "
        "Do not launch a formal evaluation. Research SHA256: " + RESEARCH_SHA + "."
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab",
        "--model", "deepseek-flash", "exec", "--sandbox", "workspace-write",
        "-c", 'approval_policy="never"', "--skip-git-repo-check", "--json",
        "--output-last-message", str(OUT / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=CHILD, prompt=prompt, stdout_path=OUT / "events.jsonl",
        stderr_path=OUT / "stderr.log", env=meta_environment("deepseek-standalone-dab"), timeout=None,
    )
    print(json.dumps({"returncode": result.returncode, "output_dir": str(OUT)}, sort_keys=True))
    if result.returncode:
        raise RuntimeError("G5 continuation failed; attempt preserved")


if __name__ == "__main__":
    main()
