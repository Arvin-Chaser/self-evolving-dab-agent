"""Synthetic checks for the answer-blind research-incubation schema."""

from __future__ import annotations

import pytest

from experiments.research_graph_incubation_packet import (
    AXES,
    build_incubation_packet,
    canonicalize_incubation_citations,
    validate_incubation_result,
)
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import (
    CAPABILITY_SHA,
    GRAPH_HASHES,
    OPPORTUNITY_SHA,
)


def packet():
    return build_incubation_packet(
        {generation: graph_path(generation) for generation in range(11)},
        GRAPH_HASHES,
        OPPORTUNITY_SHA,
        CAPABILITY_SHA,
    )


def research_result(source):
    facts = list(source["facts"])
    candidate = {
        "problem_focus": "synthetic focus", "mechanism": "synthetic mechanism",
        "key_unknown": "synthetic unknown", "minimum_no_task_check": "synthetic check",
        "runtime_content_use": "none", "interface_status": "unverified",
    }
    scan = [
        {"axis_id": axis, "fact_ids": facts[:2], "candidate": candidate if index < 3 else None,
         "counterevidence": "synthetic counterexample", "uncertainty": "synthetic uncertainty",
         "missing_premise": None if index < 3 else "synthetic gap"}
        for index, axis in enumerate(AXES)
    ]
    comparison = [
        {"axis_id": axis, "research_value": "synthetic value",
         "evidence_for": "synthetic evidence", "counterevidence": "synthetic counterexample",
         "information_gain": "synthetic gain", "de_risk_path": "synthetic check",
         "implementation_convenience": "synthetic convenience", "selection_reason": "synthetic reason"}
        for axis in AXES[:3]
    ]
    return {
        "observations": [{"fact_ids": facts, "statement": "synthetic historical scan"}],
        "counterexamples": [{"fact_ids": facts[:2], "statement": "synthetic counterexample"}],
        "unknowns": [{"fact_ids": facts[:2], "statement": "synthetic unknown"}],
        "direction_scan": scan,
        "direction_comparison": comparison,
        "research_target": {
            "axis_id": AXES[0], "state": "interface_investigation",
            "problem": "synthetic problem", "hypothesis": "synthetic hypothesis",
            "de_risk_questions": ["synthetic question"],
            "no_task_checks": ["synthetic check"],
            "interface_gaps": ["synthetic gap"], "why_now": "synthetic rationale",
        },
    }


def test_packet_keeps_all_graphs_and_six_equal_axis_cards():
    built = packet()
    assert built["generations"] == list(range(11))
    assert len(built["facts"]) == 22
    assert [row["axis_id"] for row in built["research_opportunities"]["axes"]] == list(AXES)
    assert built["research_phase"]["implementation_or_evaluation_authorized"] is False


def test_unverified_interface_target_is_valid_without_experiment():
    built = packet()
    validate_incubation_result(built, research_result(built))


def test_candidate_or_experiment_output_is_rejected():
    built = packet()
    result = research_result(built)
    result["experiment"] = {"synthetic": True}
    with pytest.raises(ValueError, match="stop before an Experiment"):
        validate_incubation_result(built, result)


def test_wrong_supplement_hash_is_rejected():
    with pytest.raises(ValueError, match="Research input hash differs"):
        build_incubation_packet(
            {generation: graph_path(generation) for generation in range(11)},
            GRAPH_HASHES,
            "0" * 64,
            CAPABILITY_SHA,
        )


def test_supplement_references_are_separate_from_graph_facts():
    built = packet()
    result = research_result(built)
    result["unknowns"].append({
        "fact_ids": ["research_opportunities.task_planning"],
        "statement": "synthetic opportunity is not Graph Evidence",
    })
    result["counterexamples"][0]["fact_ids"].append("g008_outcome_scope")
    canonical, changes = canonicalize_incubation_citations(built, result)
    validate_incubation_result(built, canonical)
    assert canonical["unknowns"][-1]["fact_ids"] == []
    assert canonical["unknowns"][-1]["source_refs"] == ["research_opportunities.task_planning"]
    assert "g008_outcome_partition" in canonical["counterexamples"][0]["fact_ids"]
    assert len(changes) == 2
    assert canonical["research_target"] == result["research_target"]


def test_unknown_reference_is_not_silently_normalized():
    built = packet()
    result = research_result(built)
    result["observations"][0]["fact_ids"].append("unknown.source")
    with pytest.raises(ValueError, match="Unrecognized research citation"):
        canonicalize_incubation_citations(built, result)
