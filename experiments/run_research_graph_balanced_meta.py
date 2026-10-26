#!/usr/bin/env python3
"""Run a future Research Meta with symmetric facts for every frozen generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_balanced_meta_packet import (
    balanced_research_instruction,
    build_balanced_packet,
    validate_balanced_observations,
)
from experiments.run_research_graph_g007_meta import GRAPH_HASHES as FROZEN_G0_G6_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
FROZEN_HASHES = {int(name[1:4]): digest for name, digest in FROZEN_G0_G6_HASHES.items()}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_path(generation: int) -> Path:
    name = f"g{generation:03d}_graph.json"
    if generation < 3:
        return BASE / name
    return BASE / f"g{generation:03d}_safe_snapshot" / name


def parse_new_hashes(values: list[str], next_generation: int) -> dict[int, str]:
    expected = set(range(7, next_generation))
    parsed = {}
    for value in values:
        try:
            label, wanted = value.split("=", 1)
            generation = int(label.removeprefix("g"))
        except ValueError as exc:
            raise ValueError("Expected --graph-sha256 g007=<64 hex digits>") from exc
        if (generation not in expected or generation in parsed or len(wanted) != 64
                or any(character not in "0123456789abcdef" for character in wanted)):
            raise ValueError("New Graph hash set differs from exact G7-to-latest range")
        parsed[generation] = wanted
    if set(parsed) != expected:
        raise ValueError("Supply one verified Graph SHA256 for every generation G7-to-latest")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=int, required=True, help="Next Research Meta generation, G8 or later")
    parser.add_argument("--graph-sha256", action="append", default=[],
                        help="Verified completed Graph hash, e.g. g007=<sha256>; repeat through latest")
    args = parser.parse_args()
    if args.generation < 8:
        raise ValueError("Balanced Research Meta applies prospectively from G8")
    hashes = {**FROZEN_HASHES, **parse_new_hashes(args.graph_sha256, args.generation)}
    paths = {generation: graph_path(generation) for generation in range(args.generation)}
    packet = build_balanced_packet(paths, hashes)
    out = BASE / f"g{args.generation:03d}_research_meta_001"
    if out.exists():
        raise RuntimeError("Research Meta attempt already exists; refusing overwrite")
    out.mkdir(exist_ok=False)
    workspace = out / "workspace"
    workspace.mkdir(exist_ok=False)
    packet_path = out / "input_packet.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
                           encoding="utf-8")
    prompt = (
        balanced_research_instruction(args.generation)
        + " The full Graphs and fact cards below are frozen research data. Values are "
        "deterministically checked; cite fact IDs rather than recalculating counts. "
        "Output ONLY one JSON object with observations (array of {fact_ids, statement}), "
        "counterexamples (same), unknowns (same), direction_scan, "
        "direction_comparison, selected_direction, few_directions_reason (null if "
        "at least three candidates), priority_rationale, problem, hypothesis, "
        "experiment, cross_generation_relations, and limitations. "
        "Use null for the three nodes only if no bounded safe experiment can be "
        "specified, and state the concrete missing condition. A non-null experiment "
        "must have one verified code parent, the fixed protocol, and a pre-run "
        "measurement_plan defining sources, hooks, per-task positive/negative/unknown "
        "rules, coverage denominator and threshold if used, cohort aggregation, "
        "supported/contradicted/inconclusive conditions, and no-answer/no-hint "
        "boundary. No evaluation occurs in this call. Packet:\n"
        + json.dumps(packet, sort_keys=True, ensure_ascii=True)
    )
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash",
        "exec", "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        "--skip-git-repo-check", "--json", "--output-last-message", str(out / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=workspace, prompt=prompt, stdout_path=out / "events.jsonl",
        stderr_path=out / "stderr.log", env=meta_environment("deepseek-standalone-dab"), timeout=None,
    )
    if result.returncode:
        raise RuntimeError("Balanced Research Meta failed; immutable attempt retained")
    research = json.loads((out / "final_raw.txt").read_text(encoding="utf-8"))
    validate_balanced_observations(packet, research)
    print(json.dumps({"returncode": result.returncode, "packet_sha256": digest(packet_path),
                      "output_dir": str(out), "balanced_scan_valid": True}, sort_keys=True))


if __name__ == "__main__":
    main()
