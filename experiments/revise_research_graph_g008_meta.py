#!/usr/bin/env python3
"""Bounded G8 Research Meta revision after a proven interface block."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_balanced_meta_packet import (
    balanced_research_instruction,
    validate_balanced_observations,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PACKET = BASE / "g008_research_meta_001/input_packet.json"
PREVIOUS = BASE / "g008_research_meta_002/final_raw.txt"
BLOCKED = BASE / "g008_candidate_001/scoped_source/BLOCKED.md"
OUT = BASE / "g008_research_meta_003"
EXPECTED = {
    PACKET: "1b2ce689716db82ce066cd4d4f0599a568338ea44373717c0dd8adfae3fc372f",
    PREVIOUS: "6ee8208c687d224d7c834c312a8d2f1998ef5619ddb0b92f94a4b079b3def161",
    BLOCKED: "f4b09afcbc807121fb144e97a8ceb4458e09b1abb07c3626a3dccba7cc8d1bc9",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or any(digest(path) != expected for path, expected in EXPECTED.items()):
        raise RuntimeError("G8 revision exists or its frozen inputs changed")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    blocked = BLOCKED.read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    prompt = (
        balanced_research_instruction(8)
        + " This is a bounded revision of your G8 Research Meta, not a new generation "
        "or permission to run an evaluation. Your prior unknown-verdict provenance "
        "experiment was blocked before implementation because the proposed status-only "
        "strict-verdict/provenance interface does not exist in the safe scoped runtime. "
        "Treat BLOCKED.md as a concrete interface counterexample, not a benchmark "
        "result, and preserve it. Do not repeat the same impossible interface claim, "
        "invent an enum, read answer_quality or a validator, or weaken the no-answer "
        "boundary. Reconsider the full G0-G7 Graphs and symmetric facts with no "
        "preassigned queue priority. First cite both fact IDs for every generation "
        "in observations; give counterexamples and unknowns with valid fact IDs; "
        "compare strict pass, known strict fail, completed strict unknown, and "
        "timeout/other failure queues and their evidence limits. You may choose any "
        "bounded safe experiment, including a diagnostic or behavior intervention, "
        "with one verified code parent and exact56/base/no-hint/1200-second protocol. "
        "If no safely implementable plan is supported, set problem, hypothesis, and "
        "experiment to null and state the concrete missing condition. For a non-null "
        "plan, specify a run-before measurement_plan with existing source/hook, "
        "positive/negative/unknown rules, denominator, coverage, aggregation, and "
        "support/contradiction/inconclusive criteria. Do not judge a safe plan by "
        "novelty, expected strict gain, or old-trace extractability. Output ONLY one "
        "JSON object with observations, counterexamples, unknowns, "
        "priority_rationale, problem, hypothesis, experiment, "
        "cross_generation_relations, and limitations. Prior frozen G8 proposal:\n"
        + json.dumps(previous, sort_keys=True, ensure_ascii=True)
        + "\nImplementation interface block:\n" + blocked
        + "\nComplete balanced frozen G0-G7 packet:\n"
        + json.dumps(packet, sort_keys=True, ensure_ascii=True)
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash",
        "exec", "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        "--skip-git-repo-check", "--json", "--output-last-message", str(OUT / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=workspace, prompt=prompt, stdout_path=OUT / "events.jsonl",
        stderr_path=OUT / "stderr.log", env=meta_environment("deepseek-standalone-dab"), timeout=None,
    )
    if result.returncode:
        raise RuntimeError("G8 revised Research Meta failed; immutable attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_balanced_observations(packet, research)
    print(json.dumps({"returncode": result.returncode, "packet_sha256": digest(PACKET),
                      "blocked_sha256": digest(BLOCKED), "output_sha256": digest(OUT / "final_raw.txt"),
                      "balanced_scan_valid": True, "experiment_proposed": research.get("experiment") is not None},
                     sort_keys=True))


if __name__ == "__main__":
    main()
