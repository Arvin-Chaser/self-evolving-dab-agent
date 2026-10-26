#!/usr/bin/env python3
"""Normalize only the G2 Meta code-parent label, preserving its raw output."""

from __future__ import annotations

import copy
import json

from experiments.run_research_graph_g001_meta_v2 import sha, write_new
from experiments.run_research_graph_g002_meta import verified_inputs
from experiments.run_research_graph_g002_meta_v2 import (
    BASE, CARDS, build_cards, read, verified_structural,
)
from experiments.run_research_graph_g002_research_v4 import validate


SOURCE = BASE / "g002_research_meta_004/result.json"
TARGET = BASE / "g002_research_meta_004/canonical_result.json"
BINDING = BASE / "g002_research_meta_004/canonical_binding.json"
EXPECTED_SOURCE_SHA = "7d938135e13fbecb2dd7437a23fd23f2af9a01a680898b4a690a8a9df971c623"
PARENT_WITH_HASH = (
    "g001_deadline_reserve (source_tree_sha256 "
    "8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d)"
)


def main() -> None:
    if sha(SOURCE) != EXPECTED_SOURCE_SHA:
        raise RuntimeError("G2 Meta raw result differs")
    g0, g1, _ = verified_inputs()
    cards = read(CARDS)
    if cards != build_cards(verified_structural(g0, g1)):
        raise RuntimeError("G2 fact cards differ")
    raw = read(SOURCE)
    if (raw.get("research_ready") is not True or
            raw.get("implementation_ready") is not True or
            raw.get("experiment", {}).get("code_parent") != PARENT_WITH_HASH):
        raise RuntimeError("G2 Meta code-parent field is not the expected formatting deviation")
    canonical = copy.deepcopy(raw)
    canonical["experiment"]["code_parent"] = "g001_deadline_reserve"
    validate(canonical, cards)
    write_new(TARGET, canonical)
    write_new(BINDING, {
        "schema_version": "g002_meta_code_parent_canonicalization_v1",
        "source_result_sha256": EXPECTED_SOURCE_SHA,
        "canonical_result_sha256": sha(TARGET),
        "transformation": "Remove the exact parent-tree hash suffix from experiment.code_parent; no other field changed.",
    })
    print(json.dumps({"status": "canonicalized", "canonical_result_sha256": sha(TARGET)},
                     sort_keys=True))


if __name__ == "__main__":
    main()
