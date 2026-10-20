"""Build and validate cross-lens Research Meta inputs for the solution loop."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from experiments.research_graph_layered_meta_packet import build_layered_meta_packet


SOLUTION_LOOP_LENSES = (
    (
        "task_representation_decomposition",
        "How the agent represents the task, resolves requirements, and decomposes it into subproblems.",
    ),
    (
        "hypothesis_search",
        "How the agent generates competing hypotheses and chooses what to explore next.",
    ),
    (
        "evidence_acquisition_grounding",
        "How the agent locates data, grounds references, designs queries, and fills evidence gaps.",
    ),
    (
        "state_memory_belief_update",
        "How observations revise plans, hypotheses, uncertainty, memory, and evidence state.",
    ),
    (
        "action_tool_policy_recovery",
        "How the agent selects tools and actions, interprets execution state, and recovers from failure.",
    ),
    (
        "synthesis_verification_termination",
        "How the agent synthesizes findings, verifies the result, and decides whether to continue or stop.",
    ),
)
LENS_IDS = tuple(row[0] for row in SOLUTION_LOOP_LENSES)


def build_solution_loop_layered_packet(
    *,
    root: Path,
    graph_paths: Mapping[int, Path],
    graph_hashes: Mapping[int, str],
    memory_path: Path,
    memory_sha256: str,
) -> dict:
    """Version the layered packet without changing any frozen Graph or memory node."""
    packet = build_layered_meta_packet(
        root=root,
        graph_paths=graph_paths,
        graph_hashes=graph_hashes,
        memory_path=memory_path,
        memory_sha256=memory_sha256,
    )
    formal = packet["formal_evolution_layer"]
    formal.pop("research_axes", None)
    formal["solution_loop_lenses"] = [
        {"lens_id": lens_id, "lens": lens}
        for lens_id, lens in SOLUTION_LOOP_LENSES
    ]
    packet["schema_version"] = "research_graph_solution_loop_meta_packet_v2"
    packet["selection_policy"] = {
        "prompt_is_neutral": True,
        "formal_evidence_and_interface_findings_are_distinct": True,
        "lenses_are_nonexclusive_review_prompts": True,
        "mechanisms_are_free_form_and_may_span_lenses": True,
        "selection_unit": "mechanism_candidate_not_lens",
        "selection_order": "research_value_first_then_post_selection_feasibility",
        "implementation_convenience_is_not_research_value": True,
        "one_candidate_per_lens_is_forbidden": True,
        "incubation_history_is_append_only": True,
    }
    packet["legacy_metadata_policy"] = (
        "Any axis_id stored inside a frozen incubation node is a historical label from an earlier "
        "selection protocol. It is not a current lens assignment and cannot constrain new mechanisms."
    )
    packet["mechanism_output_contract"] = {
        "lens_review": "one coverage review per solution-loop lens, with no candidate slot",
        "mechanism_candidates": (
            "a free-length list generated after the lens review; each mechanism has a primary lens "
            "and zero or more related lenses, but is compared and selected by mechanism_id"
        ),
        "minimum_preferred_candidates": 3,
        "selection": "rank mechanisms by research value before assessing selected-mechanism feasibility",
        "allowed_target_states": ["interface_investigation", "experiment_ready"],
        "stopping_boundary": "research_target_only_no_experiment_candidate_or_evaluation",
    }
    return packet


def _validate_refs(
    row: dict,
    *,
    facts: set[str],
    incubation_nodes: set[str],
    require_any: bool = True,
) -> set[str]:
    fact_ids = row.get("fact_ids")
    incubation_refs = row.get("incubation_refs")
    if (
        not isinstance(fact_ids, list)
        or any(value not in facts for value in fact_ids)
        or not isinstance(incubation_refs, list)
        or any(value not in incubation_nodes for value in incubation_refs)
        or (require_any and not (fact_ids or incubation_refs))
    ):
        raise ValueError("Invalid formal or incubation citation")
    return set(fact_ids)


def validate_solution_loop_result(packet: dict, research: dict) -> None:
    """Validate coverage and selection mechanics without judging research content."""
    if packet.get("schema_version") != "research_graph_solution_loop_meta_packet_v2":
        raise ValueError("Solution-loop packet schema differs")
    formal = packet["formal_evolution_layer"]
    facts = set(formal["facts"])
    incubation_nodes = {
        row["id"] for row in packet["research_incubation_layer"]["nodes"]
    }

    seen_facts: set[str] = set()
    seen_incubation: set[str] = set()
    for section in ("observations", "counterexamples", "unknowns"):
        rows = research.get(section)
        if not isinstance(rows, list):
            raise ValueError(f"Missing {section}")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("statement"), str)
                or not row["statement"].strip()
            ):
                raise ValueError(f"Invalid {section} statement")
            cited = _validate_refs(
                row, facts=facts, incubation_nodes=incubation_nodes
            )
            if section == "observations":
                seen_facts.update(cited)
            seen_incubation.update(row["incubation_refs"])
    required = {
        f"g{generation:03d}_{suffix}"
        for generation in formal["generations"]
        for suffix in formal["fact_suffixes_per_generation"]
    }
    if not required <= seen_facts:
        raise ValueError("Observations omit symmetric formal facts for a generation")
    if not incubation_nodes <= seen_incubation:
        raise ValueError("Research scan omits an incubation-memory node")

    reviews = research.get("lens_review")
    if (
        not isinstance(reviews, list)
        or len(reviews) != len(LENS_IDS)
        or [row.get("lens_id") for row in reviews] != list(LENS_IDS)
    ):
        raise ValueError("Solution-loop lens review is incomplete or out of order")
    for row in reviews:
        if "candidate" in row or "mechanism" in row:
            raise ValueError("Lens review cannot contain a candidate slot")
        _validate_refs(row, facts=facts, incubation_nodes=incubation_nodes)
        if (
            not isinstance(row.get("observed_gap"), str)
            or not row["observed_gap"].strip()
        ):
            raise ValueError("Lens review lacks an observed gap")
        relevant_unknowns = row.get("relevant_unknowns")
        if (
            not isinstance(relevant_unknowns, list)
            or not relevant_unknowns
            or any(
                not isinstance(item, str) or not item.strip()
                for item in relevant_unknowns
            )
        ):
            raise ValueError("Lens review lacks explicit unknowns")

    candidates = research.get("mechanism_candidates")
    if not isinstance(candidates, list):
        raise ValueError("Mechanism candidate list is missing")
    mechanism_ids = [row.get("mechanism_id") for row in candidates]
    if (
        any(not isinstance(value, str) or not value for value in mechanism_ids)
        or len(mechanism_ids) != len(set(mechanism_ids))
    ):
        raise ValueError("Mechanism IDs must be unique non-empty strings")
    mechanism_fields = (
        "name",
        "problem_focus",
        "proposed_mechanism",
        "behavioral_change",
        "key_unknown",
        "minimum_no_task_check",
        "runtime_content_use",
        "interface_status",
        "counterevidence",
    )
    for row in candidates:
        _validate_refs(row, facts=facts, incubation_nodes=incubation_nodes)
        if any(
            not isinstance(row.get(field), str) or not row[field].strip()
            for field in mechanism_fields
        ):
            raise ValueError("Mechanism candidate is incomplete")
        primary = row.get("primary_lens")
        related = row.get("related_lenses")
        if (
            primary not in LENS_IDS
            or not isinstance(related, list)
            or any(value not in LENS_IDS for value in related)
            or primary in related
            or len(related) != len(set(related))
        ):
            raise ValueError("Mechanism lens annotations differ")
    if len(candidates) < 3:
        reason = research.get("few_mechanisms_reason")
        if (
            not isinstance(reason, dict)
            or not isinstance(reason.get("statement"), str)
            or not reason["statement"].strip()
        ):
            raise ValueError("Too few mechanisms without a reason")
        _validate_refs(reason, facts=facts, incubation_nodes=incubation_nodes)

    ranking = research.get("mechanism_ranking")
    if (
        not isinstance(ranking, list)
        or len(ranking) != len(candidates)
        or [row.get("rank") for row in ranking] != list(range(1, len(ranking) + 1))
        or {row.get("mechanism_id") for row in ranking} != set(mechanism_ids)
    ):
        raise ValueError("Mechanism ranking must cover every candidate exactly once")
    ranking_fields = (
        "behavioral_leverage",
        "research_value",
        "information_gain",
        "formal_case",
        "counterevidence",
        "implementation_blind_reason",
    )
    for row in ranking:
        if any(
            not isinstance(row.get(field), str) or not row[field].strip()
            for field in ranking_fields
        ):
            raise ValueError("Mechanism ranking is incomplete")

    target = research.get("research_target")
    feasibility = research.get("feasibility_after_selection")
    if target is None:
        if feasibility is not None:
            raise ValueError("No-selection output cannot contain feasibility")
        reason = research.get("no_selection_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("No-selection reason is missing")
    else:
        selected_id = target.get("mechanism_id")
        if (
            not mechanism_ids
            or selected_id != ranking[0]["mechanism_id"]
            or target.get("state") not in ("interface_investigation", "experiment_ready")
            or target.get("primary_lens") not in LENS_IDS
            or not isinstance(target.get("related_lenses"), list)
            or any(value not in LENS_IDS for value in target["related_lenses"])
            or any(
                not isinstance(target.get(field), str) or not target[field].strip()
                for field in ("problem", "hypothesis", "why_now")
            )
            or any(
                not isinstance(target.get(field), list)
                or not target[field]
                or any(not isinstance(item, str) or not item.strip() for item in target[field])
                for field in ("de_risk_questions", "no_task_checks", "interface_gaps")
            )
        ):
            raise ValueError("Selected research target differs from the top mechanism")
        if (
            not isinstance(feasibility, dict)
            or feasibility.get("mechanism_id") != selected_id
            or feasibility.get("interface_state") != target["state"]
        ):
            raise ValueError("Post-selection feasibility is missing or mismatched")
        for field in ("interface_gaps", "minimum_de_risking"):
            value = feasibility.get(field)
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                raise ValueError("Post-selection feasibility details are incomplete")
        assessment = feasibility.get("path_dependence_assessment")
        if not isinstance(assessment, str) or not assessment.strip():
            raise ValueError("Path-dependence assessment is missing")

    if any(
        name in research
        for name in ("experiment", "implementation", "candidate_source", "launch")
    ):
        raise ValueError("Research output crossed the Experiment or candidate boundary")
