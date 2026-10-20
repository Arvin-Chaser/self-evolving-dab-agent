#!/usr/bin/env python3
"""Return two mechanical G5 candidate defects to the same Implementation Meta."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g005_candidate_001/scoped_source"
RESEARCH = BASE / "g005_research_meta_002/final_raw.txt"
OUT = BASE / "g005_implementation_meta_003"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"


def main() -> None:
    if OUT.exists() or hashlib.sha256(RESEARCH.read_bytes()).hexdigest() != RESEARCH_SHA:
        raise RuntimeError("G5 repair 2 exists or frozen Research hash differs")
    if not (CHILD / "implementation_manifest.json").is_file():
        raise RuntimeError("G5 repair 1 manifest missing")
    OUT.mkdir(exist_ok=False)
    prompt = (
        "You are the SAME G5 Implementation Meta on repair attempt 2 of at most 3. "
        "Keep the frozen G5 Problem/Hypothesis/Experiment/measurement_plan exact. "
        "Work only in this scoped answer-free child; do not read tasks, answers, "
        "hints, validators, raw traces, results, old lines, credentials, parent "
        "repository, remote server, or network. Do not launch evaluation. Two "
        "concrete mechanical defects were found after repair 1. (1) The frozen "
        "measurement_plan says the observed cohort denominators come from THIS "
        "run and G4 reference counts 16/34/3/3 are NOT reused as denominators. "
        "But build_evidence requires all four cohort counts to equal those G4 "
        "reference counts before protocol_complete or overall supported. This "
        "would reject a valid 56-task G5 run with any cohort shift. Remove "
        "reference-count equality from the gate; require exactly 56 distinct "
        "observed task run directories with recognized disjoint cohort labels, "
        "and retain G4 counts only as explicitly nonbinding historical context "
        "if reported. Add a synthetic 56-task counterexample with shifted cohort "
        "counts and correct observed denominators. (2) implementation_manifest.json "
        "lists only files changed by the repair call and incorrectly labels "
        "experiments/run_dab_tool_agent.py unchanged. Full comparison against "
        "G4 parent shows this runner is MODIFIED by the first G5 implementation "
        "attempt; the new recorder, extractor and two tests are NEW. Update the "
        "manifest to list ALL G5-vs-G4 candidate changes, including the runner "
        "integration and its hash, not just edits from the latest call. Keep "
        "the same source behavior otherwise. Run synthetic G5 tests and update "
        "hashes, test claims and risks. If faithful repair is impossible, write "
        "BLOCKED.md. Research SHA256: " + RESEARCH_SHA + "."
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
        raise RuntimeError("G5 repair 2 failed; attempt preserved")


if __name__ == "__main__":
    main()
