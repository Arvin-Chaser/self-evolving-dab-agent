#!/usr/bin/env python3
"""Run one bounded, schema-only G14 Research Meta revision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, run_logged_command
from experiments.dab_meta_standalone_runtime_v1 import CODEX
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result
from experiments.run_research_graph_g014_solution_loop_meta import (
    PACKET,
    PACKET_SHA,
    complete_contract,
)
from experiments.run_research_graph_solution_loop_meta import instruction as base_instruction


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "g014_research_meta_solution_loop_002/final_raw.txt"
PREVIOUS_SHA = "27a11e301d206b007d23663f75ffa93b56a0c5f3688ea389e44f36e105ac4642"
OUT = BASE / "g014_research_meta_solution_loop_003"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision_instruction() -> str:
    instruction = base_instruction()
    old = "G0-G10 generation"
    if instruction.count(old) != 1:
        raise RuntimeError("G14 neutral instruction template differs")
    instruction = instruction.replace(old, "G0-G13 generation")
    return (
        "You are the same independent G14 Research Meta making one bounded, "
        "schema-complete revision of your own immutable attempt 002. Use only "
        "the frozen packet and prior output. No human selected a mechanism. "
        "Re-evaluate and preserve, change, reject, or select none solely from "
        "the packet. The only observed validator failure is that "
        "feasibility_after_selection.minimum_de_risking was a string; it must "
        "be a non-empty array of non-empty strings. Output one complete JSON "
        "object, not a patch or commentary. Do not treat this repair request "
        "as evidence for any mechanism.\n\n"
        + instruction
        + complete_contract()
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G14 Research Meta revision 003 already exists")
    if digest(PACKET) != PACKET_SHA or digest(PREVIOUS) != PREVIOUS_SHA:
        raise RuntimeError("G14 revision 003 input binding differs")
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
        + json.dumps(packet, sort_keys=True, ensure_ascii=True)
        + "\n\nPrevious invalid attempt 002 output:\n"
        + json.dumps(previous, sort_keys=True, ensure_ascii=True)
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
    command = [
        str(CODEX),
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
        raise RuntimeError("G14 Research Meta revision 003 failed; attempt retained")
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
