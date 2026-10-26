#!/usr/bin/env python3
"""Validate a citation-only projection of the immutable G11 Research Meta output."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.research_graph_incubation_packet import (
    canonicalize_incubation_citations,
    digest,
    validate_incubation_result,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016/g011_research_meta_002"
RAW = OUT / "final_raw.txt"
PACKET = OUT / "input_packet.json"
CANONICAL = OUT / "final_canonical.json"
NORMALIZATION = OUT / "citation_normalization.json"
RAW_SHA = "67d815da62217184e37cbca481379dd1bd4adfaed1bb31a163ca77dac8cfc4ef"
PACKET_SHA = "7e39baf3caf3c7c941910b22b8e6d50c67bc88ab4fcd4f6e73cad29be238f788"


def write_new(path: Path, value: dict | list) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def main() -> None:
    if CANONICAL.exists() or NORMALIZATION.exists():
        raise RuntimeError("G11 research canonicalization already exists")
    if digest(RAW) != RAW_SHA or digest(PACKET) != PACKET_SHA:
        raise RuntimeError("G11 immutable Research Meta inputs changed")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    research = json.loads(RAW.read_text(encoding="utf-8"))
    canonical, changes = canonicalize_incubation_citations(packet, research)
    validate_incubation_result(packet, canonical)
    if canonical.get("research_target") != research.get("research_target"):
        raise RuntimeError("G11 research target changed during citation normalization")
    write_new(CANONICAL, canonical)
    write_new(NORMALIZATION, {
        "schema_version": "g011_incubation_citation_normalization_v1",
        "raw_sha256": RAW_SHA,
        "packet_sha256": PACKET_SHA,
        "canonical_sha256": digest(CANONICAL),
        "scope": "citations_only_no_research_decision_change",
        "changes": changes,
    })
    print(json.dumps({"status": "research_only_validated", "canonical_sha256": digest(CANONICAL),
                      "normalization_sha256": digest(NORMALIZATION), "citation_changes": len(changes),
                      "selected_axis": canonical["research_target"]["axis_id"],
                      "target_state": canonical["research_target"]["state"]}, sort_keys=True))


if __name__ == "__main__":
    main()
