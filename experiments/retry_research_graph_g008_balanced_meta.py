#!/usr/bin/env python3
"""Repair G8 Meta citations and clarify G7's stale pre-execution node status."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.research_graph_balanced_meta_packet import validate_balanced_observations


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
FIRST = BASE / "g008_research_meta_001"
OUT = BASE / "g008_research_meta_002"
G7_SHA = "22ffea533d2078bce07d6ef89615de8d9c8649bcb97fbf439f598f0ab3a26d72"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if digest(BASE / "g007_safe_snapshot/g007_graph.json") != G7_SHA:
        raise RuntimeError("G7 frozen Graph changed")
    packet = json.loads((FIRST / "input_packet.json").read_text(encoding="utf-8"))
    original = json.loads((FIRST / "final_raw.txt").read_text(encoding="utf-8"))
    if OUT.exists():
        raise RuntimeError("G8 Meta clarification attempt already exists")
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    prompt = (
        "You are correcting your prior G8 Research Meta JSON, not running a new "
        "experiment or inspecting task content. Preserve the full G0-G7 symmetric "
        "scan and independently reconsider only conclusions that depend on these "
        "two clarified facts. (1) Citation IDs must be keys in packet.facts; "
        "experiment:g007 and evidence:g007 are Graph node IDs, not fact IDs. "
        "The valid G7 fact IDs are g007_outcome_partition and g007_evidence_scope. "
        "(2) G7's experiment node retains stale pre-execution text "
        "specified_not_implemented_not_run. The enclosing frozen G7 Graph has "
        "status four_nodes_complete, Evidence_7 has 56 ended outcomes and run "
        "artifact hashes, and a separate terminal audit verified its execution. "
        "The stale node text must not be interpreted as G7 not having run or as "
        "a reason to exclude G7 as a verified code parent. Do not edit that frozen "
        "Graph or claim a causal score effect. Output ONLY a corrected JSON object "
        "with the same required Research Meta fields. Every observation, "
        "counterexample, and unknown row must cite valid fact IDs; observations "
        "must cite both fact IDs for every generation. Here is your prior JSON: "
        + json.dumps(original, sort_keys=True, ensure_ascii=True)
        + "\nFrozen balanced packet: "
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
        raise RuntimeError("G8 Meta clarification failed; immutable attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate_balanced_observations(packet, research)
    print(json.dumps({"returncode": result.returncode, "packet_sha256": digest(FIRST / "input_packet.json"),
                      "output_sha256": digest(OUT / "final_raw.txt"), "balanced_scan_valid": True},
                     sort_keys=True))


if __name__ == "__main__":
    main()
