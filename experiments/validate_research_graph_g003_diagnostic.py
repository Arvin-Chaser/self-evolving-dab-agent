"""Validate the new G3 diagnostic-generation contract without changing old decisions."""

from __future__ import annotations

from experiments.run_research_graph_g003_balanced import validate_balanced_research
from experiments.run_research_graph_g003_constrained import (
    INTERFACE_SHA, validate_constrained_research,
)


DIAGNOSTIC_FIELDS = {
    "intervention", "code_parent", "expected_behavior", "frozen_evaluation",
    "negative_control", "implementation_scope", "safety_questions",
    "engineering_acceptance_criteria", "intervention_class",
    "diagnostic_interface", "measurement_plan", "outcome_claim",
}
PLAN_FIELDS = {
    "unit", "signal_kind", "source_interface_sha256", "source_fields",
    "parent_gap", "task_specific_instantiation", "canonicalization",
    "positive_rule", "negative_rule", "unknown_rule", "coverage_guard",
    "aggregation", "observability_prediction", "falsification_test",
    "negative_control", "logging_fields", "semantic_boundary", "limitations",
    "minimum_complete_task_coverage_per_cohort",
}
SAFE_LOG_FIELDS = {
    "anonymous_task_index", "step_index", "signal_category", "repeat_count",
    "eligible_step_count", "coverage_status",
}


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_subset(value: object, allowed: set[str]) -> bool:
    return (isinstance(value, list) and bool(value) and
            all(isinstance(item, str) for item in value) and
            len(value) == len(set(value)) and set(value) <= allowed)


def validate_diagnostic_research(result: dict, cards: dict, interface: dict,
                                 expected_interface_sha: str = INTERFACE_SHA) -> None:
    """A diagnostic is one formal child, never a substitute for code admission."""
    experiment = result.get("experiment")
    if result.get("experiment_spec_ready") is not True:
        validate_balanced_research(result, cards)
        return
    if not isinstance(experiment, dict):
        raise RuntimeError("G3 ready experiment is missing")
    if experiment.get("intervention_class") == "agent_behavior_change":
        validate_constrained_research(result, cards, interface, expected_interface_sha)
        return
    if (experiment.get("intervention_class") != "diagnostic_instrumentation" or
            set(experiment) != DIAGNOSTIC_FIELDS or
            experiment["outcome_claim"] != "observability_only_no_strict_gain_prediction"):
        raise RuntimeError("G3 experiment class or diagnostic schema differs")

    runtime = experiment["diagnostic_interface"]
    live = interface["live_tool_dispatch"]
    if (not isinstance(runtime, dict) or set(runtime) != {
            "runtime_hook", "observation_phase", "source_fields_used",
            "sidecar_only", "feeds_agent", "alters_execution", "alters_scoring"} or
            runtime["runtime_hook"] != live["hook"] or
            runtime["observation_phase"] != "before_exec" or
            type(runtime["sidecar_only"]) is not bool or
            runtime["sidecar_only"] is not True or
            any(type(runtime[key]) is not bool or runtime[key] is not False
                for key in ("feeds_agent", "alters_execution", "alters_scoring"))):
        raise RuntimeError("G3 diagnostic is not an inert reviewed observation hook")

    plan = experiment["measurement_plan"]
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise RuntimeError("G3 diagnostic measurement schema differs")
    source_fields = {f"live_tool_dispatch.{field}"
                     for field in live["before_exec_fields"]}
    if (plan["unit"] != "per_task_step" or
            plan["signal_kind"] != "proposed_call_repetition" or
            plan["source_interface_sha256"] != expected_interface_sha or
            not _unique_subset(plan["source_fields"], source_fields) or
            set(plan["source_fields"]) != {"live_tool_dispatch.tool_name",
                                           "live_tool_dispatch.parsed_tool_args"} or
            runtime["source_fields_used"] != plan["source_fields"] or
            type(plan["minimum_complete_task_coverage_per_cohort"]) is not float or
            plan["minimum_complete_task_coverage_per_cohort"] != 0.8 or
            not _unique_subset(plan["logging_fields"], SAFE_LOG_FIELDS) or
            not {"signal_category", "coverage_status"} <= set(plan["logging_fields"]) or
            any(not _nonempty(plan[key]) for key in PLAN_FIELDS - {
                "unit", "signal_kind", "source_interface_sha256", "source_fields",
                "parent_gap", "logging_fields", "limitations",
                "minimum_complete_task_coverage_per_cohort"}) or
            not isinstance(plan["limitations"], list) or
            not plan["limitations"] or
            any(not _nonempty(item) for item in plan["limitations"])):
        raise RuntimeError("G3 diagnostic plan has unbound or unsafe fields")

    gap = plan["parent_gap"]
    if (not isinstance(gap, dict) or set(gap) != {
            "evidence_fact_ids", "missing_live_fields",
            "why_frozen_artifacts_insufficient"} or
            not _unique_subset(gap["evidence_fact_ids"], set(cards)) or
            "exact_repeat_coverage_gap" not in gap["evidence_fact_ids"] or
            any(cards[fact]["kind"] != "uncertainty"
                for fact in gap["evidence_fact_ids"]) or
            not _unique_subset(gap["missing_live_fields"],
                               set(live["before_exec_fields"])) or
            not _nonempty(gap["why_frozen_artifacts_insufficient"])):
        raise RuntimeError("G3 diagnostic does not bind the frozen-parent coverage gap")

    reduced = {**result, "experiment": {
        key: value for key, value in experiment.items()
        if key not in {"measurement_plan", "intervention_class",
                       "diagnostic_interface", "outcome_claim"}}}
    validate_balanced_research(reduced, cards)
