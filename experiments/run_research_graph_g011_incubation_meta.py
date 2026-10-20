#!/usr/bin/env python3
"""Run one independent G11 Research Meta revision; stop before candidate work."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_incubation_packet import (
    CAPABILITY_PATH,
    OPPORTUNITY_PATH,
    build_incubation_packet,
    digest,
    incubation_instruction,
    validate_incubation_result,
)
from experiments.run_research_graph_balanced_meta import FROZEN_HASHES, graph_path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
OUT = BASE / "g011_research_meta_002"
GRAPH_HASHES = {
    **FROZEN_HASHES,
    7: "22ffea533d2078bce07d6ef89615de8d9c8649bcb97fbf439f598f0ab3a26d72",
    8: "c769fd157db33e7fe2432285d4e15718307f5c7b91dde91ebcf83b19fbca83e8",
    9: "e49a7c765eef8aea4dd4bc295dfc907f7cf0fa743df41efff94fb4b9e31d0abd",
    10: "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a",
}
OPPORTUNITY_SHA = "8b66eb3b8180ca0acc3cf1b84dec5bac1e46ae90ca55d25d4de703762bab070d"
CAPABILITY_SHA = "bab58645e5b255eb31a3a94fc2002705afefdd028b9fe0c108689a9251544919"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G11 Research Meta revision already exists; refusing overwrite")
    packet = build_incubation_packet(
        {generation: graph_path(generation) for generation in range(11)},
        GRAPH_HASHES,
        OPPORTUNITY_SHA,
        CAPABILITY_SHA,
    )
    if digest(OPPORTUNITY_PATH) != OPPORTUNITY_SHA or digest(CAPABILITY_PATH) != CAPABILITY_SHA:
        raise RuntimeError("G11 research supplements changed before launch")
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    packet_path = OUT / "input_packet.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
                           encoding="utf-8")
    prompt = (
        incubation_instruction(11)
        + " Output ONLY a JSON object with observations, counterexamples, and unknowns "
        "(each an array of {fact_ids, statement}); direction_scan (six packet-order "
        "rows of {axis_id, fact_ids, candidate, counterevidence, uncertainty, "
        "missing_premise}, where missing_premise is a string for null candidates "
        "and null otherwise); direction_comparison (one row per non-null candidate "
        "with axis_id, research_value, evidence_for, counterevidence, information_gain, "
        "de_risk_path, implementation_convenience, selection_reason); "
        "few_directions_reason (null unless fewer than three candidates, then "
        "{fact_ids, statement}); research_target (null or {axis_id, state, problem, "
        "hypothesis, de_risk_questions, no_task_checks, interface_gaps, why_now}); "
        "no_selection_reason (null when a target is selected); and limitations. "
        "For an experiment_ready target, interface_gaps may list residual limits but "
        "does not itself authorize an experiment. Do not output final frozen nodes, "
        "an Experiment, implementation instructions, a candidate patch, or code. "
        "No evaluation or candidate generation occurs in this call. The complete "
        "hash-bound research packet follows:\n"
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
        raise RuntimeError("G11 incubation Research Meta failed; immutable attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_incubation_result(packet, research)
    print(json.dumps({"status": "research_only_validated", "output_dir": str(OUT),
                      "packet_sha256": digest(packet_path),
                      "research_sha256": digest(OUT / "final_raw.txt"),
                      "selected_axis": (research.get("research_target") or {}).get("axis_id"),
                      "target_state": (research.get("research_target") or {}).get("state")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
