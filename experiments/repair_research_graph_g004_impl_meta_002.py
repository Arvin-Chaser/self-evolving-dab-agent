#!/usr/bin/env python3
"""Return a G4 completeness-metadata counterexample to Implementation Meta."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
CHILD = BASE / "g004_candidate_001/scoped_source"
RESEARCH = BASE / "g004_research_meta_002/final_raw.txt"
OUT = BASE / "g004_implementation_meta_003"
RESEARCH_SHA = "d7f4fc0d479db2371ed9dcc706b288c7450edb3897eb5eed91fd684dde1ec332"


def main() -> None:
    if OUT.exists() or hashlib.sha256(RESEARCH.read_bytes()).hexdigest() != RESEARCH_SHA:
        raise RuntimeError("G4 repair attempt exists or Research hash differs")
    if not (CHILD / "experiments/g004_postrun_structural_sidecar.py").is_file():
        raise RuntimeError("G4 implementation repair 1 is unavailable")
    OUT.mkdir(exist_ok=False)
    prompt = (
        "You are the SAME G4 Implementation Meta on repair attempt 2 of at most 3. "
        "Work only in this scoped, answer-free child. Do not read benchmark tasks, "
        "answers, hints, validators, formal logs, old research lines, credentials, "
        "or the network. Preserve the frozen G4 Problem, Hypothesis, Experiment, "
        "and measurement_plan exactly. A mechanical completeness counterexample "
        "was found: build_structural_sidecar([], tool_calls_present=False, "
        "declared_tool_call_count=0) currently reports trace_complete=true and "
        "missing_reference=false. If a journal has a completed live call while "
        "the upstream tool-call file is absent, the extractor can therefore label "
        "that absent post-run record a negative zero-match on a falsely complete "
        "trace. Missing source data must not be treated as a provably complete "
        "normalized trace. Repair this conservatively within the frozen rule: "
        "make absent tool-call source fail completeness, and add synthetic tests "
        "covering missing file, a completed live step with missing post-run source, "
        "and a genuinely present zero-row file as a distinct case. Keep journal "
        "write-only and all existing agent/dispatch/results/scoring paths inert. "
        "Review whether any other source-absence or partial-record path can "
        "incorrectly assert completeness; do not alter research signals or "
        "post-run thresholds. Update implementation_manifest.json source hashes, "
        "tests and risks. Run only local synthetic tests. If faithful repair is "
        "impossible, write BLOCKED.md and do not claim readiness. Frozen Research "
        "SHA256: " + RESEARCH_SHA + "."
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
        stderr_path=OUT / "stderr.log", env=meta_environment("deepseek-standalone-dab"),
        timeout=None,
    )
    print(json.dumps({"returncode": result.returncode, "output_dir": str(OUT)}, sort_keys=True))
    if result.returncode:
        raise RuntimeError("G4 Implementation repair 2 failed; attempt preserved")


if __name__ == "__main__":
    main()
