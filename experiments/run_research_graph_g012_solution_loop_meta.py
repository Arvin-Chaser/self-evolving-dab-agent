#!/usr/bin/env python3
"""Run one neutral G12 solution-loop Research Meta selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_solution_loop_meta_packet import validate_solution_loop_result
from experiments.run_research_graph_solution_loop_meta import instruction as base_instruction


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PACKET = BASE / "research_graph_solution_loop_meta_packet_g012_v1.json"
PACKET_SHA = "d7db6d5a767efbd079e469ff6d18878d9c7f3147d321ea6ac569d504f01b8ab6"
OUT = BASE / "g012_research_meta_solution_loop_001"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G12 Research Meta output already exists")
    if digest(PACKET) != PACKET_SHA:
        raise RuntimeError("G12 Research packet hash differs")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    if packet["formal_evolution_layer"]["generations"] != list(range(12)):
        raise RuntimeError("G12 Research packet generation series differs")
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    packet_copy = OUT / "input_packet.json"
    packet_copy.write_text(json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    instruction = base_instruction()
    old = "G0-G10 generation"
    if instruction.count(old) != 1:
        raise RuntimeError("G12 neutral instruction template differs")
    instruction = instruction.replace(old, "G0-G11 generation")
    prompt = instruction + json.dumps(packet, sort_keys=True, ensure_ascii=True)
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab",
        "--model", "deepseek-flash", "exec", "--sandbox", "workspace-write",
        "-c", 'approval_policy="never"', "--skip-git-repo-check", "--json",
        "--output-last-message", str(OUT / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=workspace, prompt=prompt,
        stdout_path=OUT / "events.jsonl", stderr_path=OUT / "stderr.log",
        env=meta_environment("deepseek-standalone-dab"), timeout=None,
    )
    if result.returncode:
        raise RuntimeError("G12 Research Meta failed; attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_solution_loop_result(packet, research)
    target = research.get("research_target") or {}
    print(json.dumps({
        "status": "research_only_solution_loop_validated",
        "output_dir": str(OUT), "packet_sha256": digest(packet_copy),
        "research_sha256": digest(OUT / "final_raw.txt"),
        "selected_mechanism_id": target.get("mechanism_id"),
        "primary_lens": target.get("primary_lens"),
        "related_lenses": target.get("related_lenses"),
        "target_state": target.get("state"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
