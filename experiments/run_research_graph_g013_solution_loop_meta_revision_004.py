#!/usr/bin/env python3
"""Run one schema-complete, bounded G13 Research Meta revision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result
from experiments.run_research_graph_g013_solution_loop_meta import PACKET, PACKET_SHA


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "g013_research_meta_solution_loop_003/final_raw.txt"
PREVIOUS_SHA = "57fae282f550fe4cd479f227232912262ad14c9aa12306aaa982ff10cf09a8cc"
OUT = BASE / "g013_research_meta_solution_loop_004"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision_instruction() -> str:
    return """You are the independent G13 Research Meta making one bounded schema-complete
revision of your own immutable third attempt.

Use only:
1. the hash-bound frozen G13 packet; and
2. the previous invalid _003 output as data.

No human has selected a mechanism. Re-evaluate the evidence and preserve,
change, or reject the previous ranking solely according to the frozen packet.
Do not treat this repair request as support for any mechanism.

The third attempt failed mechanical validation for exactly the currently
observed reasons:
- the required top-level unknowns array is absent;
- every mechanism_ranking row lacks the required non-empty string fields
  formal_case and implementation_blind_reason.
The extra field evidence_position does not substitute for either required field.

Output ONLY one complete JSON object. Do not output commentary or a patch.
The complete structural contract is:

Top-level keys:
- observations: array
- counterexamples: array
- unknowns: array
- lens_review: array
- mechanism_candidates: array
- mechanism_ranking: array
- few_mechanisms_reason: object or null
- feasibility_after_selection: object or null
- research_target: object or null
- no_selection_reason: string or null
- limitations: array

Every observations, counterexamples, and unknowns row:
{
  "statement": non-empty string,
  "fact_ids": array of exact packet fact IDs,
  "incubation_refs": array of exact packet incubation node IDs
}
Each row must cite at least one fact or incubation node.
Observations collectively must cite both symmetric formal fact IDs for every
G0-G12 generation. Across observations, counterexamples, and unknowns,
all 20 incubation node IDs must be cited at least once.

lens_review must contain exactly six rows in packet lens order. Every row:
{
  "lens_id": exact packet lens ID,
  "fact_ids": valid array,
  "incubation_refs": valid array,
  "observed_gap": non-empty string,
  "relevant_unknowns": non-empty array of non-empty strings
}
It must not contain a candidate or mechanism field.

Every mechanism_candidates row:
{
  "mechanism_id": unique non-empty string,
  "name": non-empty string,
  "problem_focus": non-empty string,
  "proposed_mechanism": non-empty string,
  "primary_lens": exact packet lens ID,
  "related_lenses": unique valid lens IDs excluding primary_lens,
  "behavioral_change": non-empty string,
  "key_unknown": non-empty string,
  "minimum_no_task_check": non-empty STRING, not an array,
  "runtime_content_use": non-empty string,
  "interface_status": non-empty string,
  "fact_ids": valid array,
  "incubation_refs": valid array,
  "counterevidence": non-empty string
}
Each candidate must cite at least one valid fact or incubation node.
If fewer than three candidates are returned, few_mechanisms_reason must be
an object with statement, fact_ids, and incubation_refs satisfying the same
citation rules.

mechanism_ranking must cover every candidate exactly once, with consecutive
ranks starting at 1. Every row:
{
  "rank": integer,
  "mechanism_id": candidate mechanism ID,
  "behavioral_leverage": non-empty string,
  "research_value": non-empty string,
  "information_gain": non-empty string,
  "formal_case": non-empty string,
  "counterevidence": non-empty string,
  "implementation_blind_reason": non-empty string
}

If research_target is null:
- feasibility_after_selection must be null;
- no_selection_reason must be a non-empty string.

If research_target is non-null:
- its mechanism_id must equal rank 1;
- state must be interface_investigation or experiment_ready;
- it must contain valid primary_lens and related_lenses;
- problem, hypothesis, and why_now must be non-empty strings;
- de_risk_questions, no_task_checks, and interface_gaps must each be a
  non-empty array of non-empty strings.
feasibility_after_selection must then contain:
{
  "mechanism_id": same selected ID,
  "interface_state": same target state,
  "interface_gaps": non-empty array of non-empty strings,
  "minimum_de_risking": non-empty array of non-empty strings,
  "path_dependence_assessment": non-empty string
}

Do not output top-level experiment, implementation, candidate_source, or launch.
Do not use raw tasks, answers, hints, validators, messages, tool arguments or
results, answer-bearing logs, credentials, old research lines, or the invalid
manual G13 implementation directory. Stop at research_target.
"""


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G13 Research Meta revision 004 output already exists")
    if digest(PACKET) != PACKET_SHA or digest(PREVIOUS) != PREVIOUS_SHA:
        raise RuntimeError("G13 Research Meta revision 004 input hash differs")

    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    (OUT / "input_packet.json").write_text(
        json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "previous_attempt.json").write_text(
        json.dumps(previous, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    prompt = (
        revision_instruction()
        + "\nFrozen packet:\n"
        + json.dumps(packet, sort_keys=True, ensure_ascii=True)
        + "\n\nPrevious invalid _003 output:\n"
        + json.dumps(previous, sort_keys=True, ensure_ascii=True)
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
        raise RuntimeError("G13 Research Meta revision 004 failed; attempt retained")

    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_solution_loop_result(packet, research)
    target = research.get("research_target") or {}
    print(
        json.dumps(
            {
                "status": "research_only_solution_loop_validated",
                "output_dir": str(OUT),
                "packet_sha256": digest(OUT / "input_packet.json"),
                "previous_sha256": digest(OUT / "previous_attempt.json"),
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
