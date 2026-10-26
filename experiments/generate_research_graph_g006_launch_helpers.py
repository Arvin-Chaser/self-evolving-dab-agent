#!/usr/bin/env python3
"""Mechanically specialize the proven G5 launch helpers for frozen G6."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments"
G6 = BASE / "research_graph_baseline_20261016/g006_candidate_001"
REPLACEMENTS = (
    ("g005", "g006"),
    ("G5", "G6"),
    ("g004_graph.json", "g005_graph.json"),
    ("evidence:g004", "evidence:g005"),
    ("g4_graph_sha256", "parent_graph_sha256"),
    ("G4_GRAPH_SHA", "G5_GRAPH_SHA"),
    ("g4_manifest", "g5_manifest"),
    ("baseline_g006_provenance", "baseline_g006_tool_class"),
    ("b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95", "845e0f89f3df104d1fcb0ca564256fe8ca0f92c8880127dc4b3c2d4cfb0244c6"),
    ("e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3", "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"),
    ("fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda", "2310f5b7b16e21242ed055577bd148a9989ae4f5107011bfae444693b8a3b42d"),
    ("492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426", "09ca0c4330b5b591d7a52ecdd084021ee8f7c720de93d33192a615f5dba27677"),
    ("8d5e0bf5bd3a368f500510cbd6260d2691e27cb6c42b4062b34a3e98702e4d3d", "be00f03642f1a1ab8a5843dc43728ed196afae2ad9263959705157186fc7f26a"),
    ("d599074b3aac26a2b82a63dc464224f730d14797a7834290b4747ddbdc1839be", hashlib.sha256((G6 / "admission.json").read_bytes()).hexdigest()),
    ("len(rows) != 92", "len(rows) != 96"),
    ("generation\": 5", "generation\": 6"),
)


def main() -> None:
    for stem in (
        "stage_research_graph",
        "deploy_research_graph_launcher",
        "launch_research_graph",
        "start_research_graph_once",
    ):
        names = {
            "stage_research_graph": ("stage_research_graph_g005.py", "stage_research_graph_g006.py"),
            "deploy_research_graph_launcher": ("deploy_research_graph_g005_launcher.py", "deploy_research_graph_g006_launcher.py"),
            "launch_research_graph": ("launch_research_graph_g005.py", "launch_research_graph_g006.py"),
            "start_research_graph_once": ("start_research_graph_g005_once.py", "start_research_graph_g006_once.py"),
        }
        src_name, dst_name = names[stem]
        source = (BASE / src_name).read_text(encoding="utf-8")
        if stem == "stage_research_graph":
            source = source.replace("g005_research_meta_002", "g005_research_meta_001")
            source = source.replace("g006_research_meta_001", "g006_research_meta_001")
        for old, new in REPLACEMENTS:
            source = source.replace(old, new)
        if stem == "stage_research_graph":
            source = source.replace("g006_research_meta_002", "g006_research_meta_001")
        target = BASE / dst_name
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(source)
        print(dst_name)


if __name__ == "__main__":
    main()
