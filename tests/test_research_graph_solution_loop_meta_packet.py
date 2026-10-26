"""Contract tests for cross-lens solution-loop Research Meta selection."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from experiments.research_graph_memory import digest
from experiments.research_graph_solution_loop_meta_packet import (
    LENS_IDS,
    build_solution_loop_layered_packet,
    validate_solution_loop_result,
)
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES
from experiments.run_research_graph_solution_loop_meta import instruction


ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "experiments/research_graph_baseline_20261016/research_graph_memory_v2.json"


def packet() -> dict:
    return build_solution_loop_layered_packet(
        root=ROOT,
        graph_paths={generation: graph_path(generation) for generation in range(11)},
        graph_hashes=GRAPH_HASHES,
        memory_path=MEMORY,
        memory_sha256=digest(MEMORY),
    )


def result(source: dict) -> dict:
    formal = source["formal_evolution_layer"]
    facts = list(formal["facts"])
    incubation = [
        row["id"] for row in source["research_incubation_layer"]["nodes"]
    ]
    mechanisms = [
        {
            "mechanism_id": f"mechanism:{index}",
            "name": f"Synthetic mechanism {index}",
            "problem_focus": "Synthetic bounded problem",
            "proposed_mechanism": "Synthetic cross-lens mechanism",
            "primary_lens": LENS_IDS[0] if index < 2 else LENS_IDS[3],
            "related_lenses": [LENS_IDS[2], LENS_IDS[4]] if index == 0 else [],
            "behavioral_change": "Changes a synthetic decision",
            "key_unknown": "Synthetic unknown",
            "minimum_no_task_check": "Synthetic no-task check",
            "runtime_content_use": "No benchmark content",
            "interface_status": "Unverified",
            "fact_ids": facts[:2],
            "incubation_refs": [],
            "counterevidence": "Synthetic counterevidence",
        }
        for index in range(3)
    ]
    ranking = [
        {
            "rank": index + 1,
            "mechanism_id": mechanism["mechanism_id"],
            "behavioral_leverage": "Synthetic leverage",
            "research_value": "Synthetic value",
            "information_gain": "Synthetic information gain",
            "formal_case": "Synthetic formal case",
            "counterevidence": "Synthetic counterevidence",
            "implementation_blind_reason": "Ranked without implementation convenience",
        }
        for index, mechanism in enumerate(mechanisms)
    ]
    return {
        "observations": [
            {
                "fact_ids": facts,
                "incubation_refs": incubation,
                "statement": "Complete synthetic history review",
            }
        ],
        "counterexamples": [
            {
                "fact_ids": facts[:2],
                "incubation_refs": [],
                "statement": "Synthetic counterexample",
            }
        ],
        "unknowns": [
            {
                "fact_ids": facts[:2],
                "incubation_refs": [],
                "statement": "Synthetic unknown",
            }
        ],
        "lens_review": [
            {
                "lens_id": lens_id,
                "fact_ids": facts[:2],
                "incubation_refs": [],
                "observed_gap": "Synthetic gap",
                "relevant_unknowns": ["Synthetic unknown"],
            }
            for lens_id in LENS_IDS
        ],
        "mechanism_candidates": mechanisms,
        "mechanism_ranking": ranking,
        "few_mechanisms_reason": None,
        "feasibility_after_selection": {
            "mechanism_id": mechanisms[0]["mechanism_id"],
            "interface_state": "interface_investigation",
            "interface_gaps": ["Synthetic gap"],
            "minimum_de_risking": ["Synthetic check"],
            "path_dependence_assessment": "Synthetic assessment",
        },
        "research_target": {
            "mechanism_id": mechanisms[0]["mechanism_id"],
            "primary_lens": mechanisms[0]["primary_lens"],
            "related_lenses": mechanisms[0]["related_lenses"],
            "state": "interface_investigation",
            "problem": "Synthetic problem",
            "hypothesis": "Synthetic hypothesis",
            "de_risk_questions": ["Synthetic question"],
            "no_task_checks": ["Synthetic check"],
            "interface_gaps": ["Synthetic gap"],
            "why_now": "Synthetic rationale",
        },
        "no_selection_reason": None,
        "limitations": ["Synthetic limitation"],
    }


def test_packet_replaces_old_axes_with_solution_loop_lenses() -> None:
    built = packet()
    formal = built["formal_evolution_layer"]
    assert built["schema_version"] == "research_graph_solution_loop_meta_packet_v2"
    assert "research_axes" not in formal
    assert [row["lens_id"] for row in formal["solution_loop_lenses"]] == list(LENS_IDS)
    assert built["selection_policy"]["selection_unit"] == "mechanism_candidate_not_lens"
    assert built["selection_policy"]["one_candidate_per_lens_is_forbidden"] is True


def test_multiple_mechanisms_can_share_a_lens_and_span_other_lenses() -> None:
    built = packet()
    research = result(built)
    assert research["mechanism_candidates"][0]["primary_lens"] == research[
        "mechanism_candidates"
    ][1]["primary_lens"]
    assert len(research["mechanism_candidates"][0]["related_lenses"]) == 2
    validate_solution_loop_result(built, research)


def test_lens_review_cannot_embed_candidate_slots() -> None:
    built = packet()
    research = result(built)
    research["lens_review"][0]["candidate"] = {"synthetic": True}
    with pytest.raises(ValueError, match="candidate slot"):
        validate_solution_loop_result(built, research)


def test_selection_is_top_mechanism_not_primary_lens() -> None:
    built = packet()
    research = result(built)
    research["research_target"]["mechanism_id"] = "mechanism:1"
    with pytest.raises(ValueError, match="top mechanism"):
        validate_solution_loop_result(built, research)


def test_ranking_must_cover_mechanisms_not_lenses() -> None:
    built = packet()
    research = result(built)
    broken = copy.deepcopy(research)
    broken["mechanism_ranking"].pop()
    with pytest.raises(ValueError, match="every candidate"):
        validate_solution_loop_result(built, broken)


def test_output_stops_before_formal_experiment() -> None:
    built = packet()
    research = result(built)
    research["experiment"] = {"synthetic": True}
    with pytest.raises(ValueError, match="Experiment or candidate boundary"):
        validate_solution_loop_result(built, research)


def test_prompt_treats_lenses_as_review_not_candidate_buckets() -> None:
    prompt = instruction()
    assert "Do not generate one candidate per lens" in prompt
    assert "Rank complete mechanisms, not lenses" in prompt
    assert "Lock the first-ranked mechanism" in prompt
    assert "stops at research_target" in prompt
