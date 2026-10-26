#!/usr/bin/env python3
"""Run one schema-complete, neutral G14 solution-loop Research Meta selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result
from experiments.run_research_graph_solution_loop_meta import instruction as base_instruction


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PACKET = BASE / "research_graph_solution_loop_meta_packet_g014_v1.json"
PACKET_SHA = "0e4525b5f8378f536eb68fa36125d076f319b08ecd6dc60a80625a4824711b04"
OUT = BASE / "g014_research_meta_solution_loop_001"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_contract() -> str:
    return """

Output ONLY one complete JSON object. The complete structural contract below is
mandatory and supplements, without changing, the neutral selection policy.

Top-level keys: observations, counterexamples, unknowns, lens_review,
mechanism_candidates, mechanism_ranking, few_mechanisms_reason,
feasibility_after_selection, research_target, no_selection_reason, limitations.

Every observations/counterexamples/unknowns row is an object with statement
(non-empty string), fact_ids (array of exact packet fact IDs), and
incubation_refs (array of exact packet node IDs). Each row cites at least one
fact or node. Observations collectively cite both symmetric facts for every
G0-G13 generation. Across those three sections, all 27 incubation nodes are
cited at least once.

lens_review contains exactly six rows in packet order. Every row has only
lens_id, fact_ids, incubation_refs, observed_gap (non-empty string), and
relevant_unknowns (non-empty array of non-empty strings). It has no candidate
or mechanism field.

Every mechanism_candidates row has mechanism_id, name, problem_focus,
proposed_mechanism, primary_lens, related_lenses, behavioral_change,
key_unknown, minimum_no_task_check (a non-empty STRING, not an array),
runtime_content_use, interface_status, fact_ids, incubation_refs, and
counterevidence. IDs are unique. Lens IDs are exact; related_lenses are unique
and exclude primary_lens. Each row cites at least one valid fact or node. If
there are fewer than three candidates, few_mechanisms_reason is an object with
statement, fact_ids, and incubation_refs satisfying the same citation rules.

mechanism_ranking covers every candidate exactly once with consecutive ranks
from 1. Every row has rank, mechanism_id, behavioral_leverage, research_value,
information_gain, formal_case, counterevidence, and
implementation_blind_reason; all narrative fields are non-empty strings.

If research_target is null, feasibility_after_selection is null and
no_selection_reason is a non-empty string. If selected, research_target's
mechanism_id equals rank 1; state is interface_investigation or
experiment_ready; primary_lens and related_lenses are valid; problem,
hypothesis, and why_now are non-empty strings; de_risk_questions,
no_task_checks, and interface_gaps are non-empty arrays of non-empty strings.
feasibility_after_selection then has the same mechanism_id and state plus
non-empty interface_gaps, minimum_de_risking, and
path_dependence_assessment. Do not output experiment, implementation,
candidate_source, or launch.

The frozen packet follows:
"""


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G14 Research Meta output already exists")
    if digest(PACKET) != PACKET_SHA:
        raise RuntimeError("G14 Research packet hash differs")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    if packet["formal_evolution_layer"]["generations"] != list(range(14)):
        raise RuntimeError("G14 Research packet generation series differs")
    if len(packet["research_incubation_layer"]["nodes"]) != 27:
        raise RuntimeError("G14 incubation-node count differs")

    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    packet_copy = OUT / "input_packet.json"
    packet_copy.write_text(
        json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    instruction = base_instruction()
    old = "G0-G10 generation"
    if instruction.count(old) != 1:
        raise RuntimeError("G14 neutral instruction template differs")
    instruction = instruction.replace(old, "G0-G13 generation")
    prompt = instruction + complete_contract() + json.dumps(
        packet, sort_keys=True, ensure_ascii=True
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
    command = [
        resolve_codex("codex"),
        "--profile",
        "deepseek-standalone-dab",
        "--model",
        "deepseek-flash",
        "exec",
        "--sandbox",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "--skip-git-repo-check",
        "--json",
        "--output-last-message",
        str(OUT / "final_raw.txt"),
        "-",
    ]
    result = run_logged_command(
        command,
        cwd=workspace,
        prompt=prompt,
        stdout_path=OUT / "events.jsonl",
        stderr_path=OUT / "stderr.log",
        env=meta_environment("deepseek-standalone-dab"),
        timeout=None,
    )
    if result.returncode:
        raise RuntimeError("G14 Research Meta failed; attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_solution_loop_result(packet, research)
    target = research.get("research_target") or {}
    print(
        json.dumps(
            {
                "status": "research_only_solution_loop_validated",
                "output_dir": str(OUT),
                "packet_sha256": digest(packet_copy),
                "research_sha256": digest(OUT / "final_raw.txt"),
                "selected_mechanism_id": target.get("mechanism_id"),
                "primary_lens": target.get("primary_lens"),
                "related_lenses": target.get("related_lenses"),
                "target_state": target.get("state"),
                "code_parent_frozen": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
