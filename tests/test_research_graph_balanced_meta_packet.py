"""Contract tests for symmetric, hash-bound Research Meta inputs."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.research_graph_balanced_meta_packet import (
    balanced_research_instruction,
    build_balanced_packet,
    validate_balanced_observations,
)
from experiments.run_research_graph_g007_meta import BASE, GRAPH_HASHES
from experiments.run_research_graph_balanced_meta import graph_path, parse_new_hashes


def frozen_graphs() -> tuple[dict[int, Path], dict[int, str]]:
    paths = {
        i: BASE / (f"g{i:03d}_safe_snapshot" if i >= 3 else "") / f"g{i:03d}_graph.json"
        for i in range(7)
    }
    hashes = {int(name[1:4]): value for name, value in GRAPH_HASHES.items()}
    return paths, hashes


def test_all_graphs_and_uniform_fact_slots() -> None:
    paths, hashes = frozen_graphs()
    packet = build_balanced_packet(paths, hashes)
    assert packet["generations"] == list(range(7))
    assert [graph["generation"] for graph in packet["graphs"]] == list(range(7))
    assert len(packet["facts"]) == 14
    for generation in range(7):
        prefix = f"g{generation:03d}"
        assert {key.removeprefix(prefix + "_") for key in packet["facts"] if key.startswith(prefix)} == {
            "outcome_partition", "evidence_scope"
        }
    assert {tuple(card) for key, card in packet["facts"].items()
            if key.endswith("_outcome_partition")} == {
        tuple(packet["facts"]["g000_outcome_partition"])
    }
    assert {tuple(card) for key, card in packet["facts"].items()
            if key.endswith("_evidence_scope")} == {
        tuple(packet["facts"]["g000_evidence_scope"])
    }
    assert packet["graphs"][-1] == json.loads(paths[6].read_text(encoding="utf-8"))
    assert len(packet["research_axes"]) == 6
    assert len({row["axis_id"] for row in packet["research_axes"]}) == 6


def test_all_generation_outcomes_reconcile() -> None:
    paths, hashes = frozen_graphs()
    packet = build_balanced_packet(paths, hashes)
    for generation in packet["generations"]:
        row = packet["facts"][f"g{generation:03d}_outcome_partition"]
        assert row["ended_count"] == row["frozen_task_count"] == 56
        assert row["strict_pass_count"] + row["known_strict_fail_count"] + row[
            "strict_verdict_unknown_completed_count"
        ] == row["completed_count"]
        assert row["completed_count"] + row["timeout_failure_count"] + row[
            "other_terminal_failure_count"
        ] == 56


def test_missing_generation_or_hash_change_is_rejected(tmp_path: Path) -> None:
    paths, hashes = frozen_graphs()
    missing = dict(paths)
    missing.pop(3)
    with pytest.raises(ValueError, match="complete"):
        build_balanced_packet(missing, {i: hashes[i] for i in missing})
    changed = dict(paths)
    copy_path = tmp_path / "g006_graph.json"
    copy_path.write_bytes(paths[6].read_bytes() + b"\n")
    changed[6] = copy_path
    with pytest.raises(ValueError, match="hash differs"):
        build_balanced_packet(changed, hashes)


def test_inconsistent_partition_is_rejected(tmp_path: Path) -> None:
    paths, hashes = frozen_graphs()
    changed = dict(paths)
    graph = copy.deepcopy(json.loads(paths[6].read_text(encoding="utf-8")))
    evidence = next(node for node in graph["nodes"] if node["kind"] == "evidence")
    evidence["completed_count"] += 1
    copy_path = tmp_path / "g006_graph.json"
    copy_path.write_text(json.dumps(graph), encoding="utf-8")
    changed[6] = copy_path
    new_hashes = dict(hashes)
    new_hashes[6] = hashlib.sha256(copy_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="does not reconcile"):
        build_balanced_packet(changed, new_hashes)


def test_instruction_requires_all_generations_without_predetermined_priority() -> None:
    instruction = balanced_research_instruction(8)
    assert "EVERY generation" in instruction
    assert "no queue or generation has preassigned priority" in instruction
    assert "known strict fail" in instruction
    assert "timeouts as failures" in instruction
    assert "direction_scan" in instruction
    assert "direction_comparison" in instruction
    assert "at least three substantively different" in instruction


def test_future_runner_requires_exact_hash_bound_history() -> None:
    h7 = "a" * 64
    h8 = "b" * 64
    assert parse_new_hashes([f"g007={h7}", f"g008={h8}"], 9) == {7: h7, 8: h8}
    assert graph_path(7) == BASE / "g007_safe_snapshot/g007_graph.json"
    with pytest.raises(ValueError, match="every generation"):
        parse_new_hashes([f"g008={h8}"], 9)
    with pytest.raises(ValueError, match="set differs"):
        parse_new_hashes([f"g006={h7}"], 8)


def test_meta_must_cite_both_balanced_facts_for_every_generation() -> None:
    paths, hashes = frozen_graphs()
    packet = build_balanced_packet(paths, hashes)
    research = {
        "observations": [
            {"fact_ids": [f"g{i:03d}_outcome_partition", f"g{i:03d}_evidence_scope"],
             "statement": "bounded observation"}
            for i in range(7)
        ],
        "counterexamples": [{"fact_ids": ["g000_evidence_scope"], "statement": "unknown"}],
        "unknowns": [{"fact_ids": ["g006_evidence_scope"], "statement": "unknown"}],
        "direction_scan": [
            {
                "axis_id": axis["axis_id"],
                "fact_ids": ["g000_outcome_partition", "g006_evidence_scope"],
                "candidate": {
                    "problem_focus": "bounded problem",
                    "mechanism": "testable mechanism",
                    "test": "one fixed-protocol test",
                    "interface_status": "requires verification",
                } if index < 3 else None,
                "counterevidence": "current evidence is incomplete",
                "uncertainty": "cause remains unknown",
            }
            for index, axis in enumerate(packet["research_axes"])
        ],
        "direction_comparison": [
            {
                "axis_id": axis["axis_id"],
                "evidence_strength": "bounded",
                "counterevidence": "limited",
                "measurement_feasibility": "needs verification",
                "why_selected_or_not": "comparison",
            }
            for axis in packet["research_axes"][:3]
        ],
        "selected_direction": packet["research_axes"][0]["axis_id"],
        "problem": {"statement": "one chosen problem"},
        "hypothesis": {"statement": "one chosen hypothesis"},
        "experiment": {"statement": "one chosen experiment"},
    }
    validate_balanced_observations(packet, research)
    research["observations"].pop(0)
    with pytest.raises(ValueError, match="both facts"):
        validate_balanced_observations(packet, research)


def test_meta_must_scan_and_compare_distinct_axes() -> None:
    paths, hashes = frozen_graphs()
    packet = build_balanced_packet(paths, hashes)
    research = {
        "observations": [
            {"fact_ids": [f"g{i:03d}_outcome_partition", f"g{i:03d}_evidence_scope"],
             "statement": "bounded observation"}
            for i in range(7)
        ],
        "counterexamples": [{"fact_ids": ["g000_evidence_scope"], "statement": "limit"}],
        "unknowns": [{"fact_ids": ["g006_evidence_scope"], "statement": "unknown"}],
        "direction_scan": [
            {"axis_id": axis["axis_id"], "fact_ids": ["g006_evidence_scope"],
             "candidate": None, "counterevidence": "not measured", "uncertainty": "unknown"}
            for axis in packet["research_axes"]
        ],
        "direction_comparison": [],
        "selected_direction": None,
        "problem": None,
        "hypothesis": None,
        "experiment": None,
        "few_directions_reason": {"fact_ids": ["g006_evidence_scope"],
                                  "statement": "insufficient safe evidence"},
    }
    validate_balanced_observations(packet, research)
    broken = copy.deepcopy(research)
    broken["direction_scan"].pop()
    with pytest.raises(ValueError, match="six axes"):
        validate_balanced_observations(packet, broken)
    broken = copy.deepcopy(research)
    broken["few_directions_reason"] = None
    with pytest.raises(ValueError, match="fewer than three"):
        validate_balanced_observations(packet, broken)
    broken = copy.deepcopy(research)
    broken["direction_scan"][0]["candidate"] = {
        "problem_focus": "one", "mechanism": "two", "test": "three",
        "interface_status": "unverified",
    }
    with pytest.raises(ValueError, match="compare every"):
        validate_balanced_observations(packet, broken)
