#!/usr/bin/env python3
"""Retry G14 Research Meta after a pre-provider runtime identity rebind."""

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
FAILED = BASE / "g014_research_meta_solution_loop_001"
REBIND = BASE / "g014_meta_runtime_rebind_001/audit.json"
REBIND_SHA = "d19e711cf5c764d30f1180029ec9b10d266d5048b4de8e144c144cf00f4557ea"
OUT = BASE / "g014_research_meta_solution_loop_002"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G14 Research Meta attempt 002 already exists")
    if digest(PACKET) != PACKET_SHA or digest(REBIND) != REBIND_SHA:
        raise RuntimeError("G14 attempt 002 input binding differs")
    if not FAILED.is_dir() or (FAILED / "final_raw.txt").exists():
        raise RuntimeError("G14 attempt 001 is not the bound pre-provider failure")
    if (FAILED / "events.jsonl").exists() or (FAILED / "stderr.log").exists():
        raise RuntimeError("G14 attempt 001 crossed the provider-dispatch boundary")

    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    if packet["formal_evolution_layer"]["generations"] != list(range(14)):
        raise RuntimeError("G14 Research packet generation series differs")
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    packet_copy = OUT / "input_packet.json"
    packet_copy.write_text(
        json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "runtime_rebind_audit.json").write_bytes(REBIND.read_bytes())
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
        raise RuntimeError("G14 Research Meta attempt 002 failed; attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_solution_loop_result(packet, research)
    target = research.get("research_target") or {}
    print(
        json.dumps(
            {
                "status": "research_only_solution_loop_validated",
                "output_dir": str(OUT),
                "packet_sha256": digest(packet_copy),
                "runtime_rebind_sha256": digest(OUT / "runtime_rebind_audit.json"),
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
