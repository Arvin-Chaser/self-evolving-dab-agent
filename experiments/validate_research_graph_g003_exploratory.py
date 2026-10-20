"""Validate prospective G3 exploration without imposing a novelty veto."""

from __future__ import annotations

from experiments.run_research_graph_g003_balanced import validate_balanced_research
from experiments.run_research_graph_g003_constrained import INTERFACE_SHA


EXPERIMENT_FIELDS = {
    "intervention", "code_parent", "expected_behavior", "frozen_evaluation",
    "negative_control", "implementation_scope", "safety_questions",
    "engineering_acceptance_criteria", "intervention_class",
    "diagnostic_interface", "measurement_plan", "outcome_claim",
}
PLAN_FIELDS = {
    "unit", "signal_kind", "source_interface_sha256", "source_fields",
    "prior_observation", "task_specific_instantiation", "canonicalization",
    "positive_rule", "negative_rule", "unknown_rule", "coverage_guard",
    "aggregation", "observability_prediction", "falsification_test",
    "negative_control", "logging_fields", "semantic_boundary", "limitations",
    "minimum_complete_task_coverage_per_cohort",
}
LOG_FIELDS = {"anonymous_task_index", "step_index", "signal_category",
              "repeat_count", "eligible_step_count", "coverage_status"}
AUDIT_SHA = "88ff0e5eedbfde9c4d2888102ca2f0f985fc3cbbab82f806c4b886a8b3984233"


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, allowed: set[str]) -> bool:
    return (isinstance(value, list) and bool(value) and
            all(isinstance(item, str) for item in value) and
            len(value) == len(set(value)) and set(value) <= allowed)


def validate_exploratory_research(result: dict, cards: dict, interface: dict) -> None:
    experiment = result.get("experiment")
    if result.get("experiment_spec_ready") is not True:
        validate_balanced_research(result, cards)
        return
    if (not isinstance(experiment, dict) or set(experiment) != EXPERIMENT_FIELDS or
            experiment["intervention_class"] != "diagnostic_instrumentation" or
            experiment["outcome_claim"] != "exploratory_observability_no_strict_gain_prediction"):
        raise RuntimeError("G3 exploratory diagnostic schema differs")
    hook = experiment["diagnostic_interface"]
    if (not isinstance(hook, dict) or set(hook) != {
            "runtime_hook", "observation_phase", "source_fields_used",
            "sidecar_only", "feeds_agent", "alters_execution", "alters_scoring"} or
            hook["runtime_hook"] != interface["live_tool_dispatch"]["hook"] or
            hook["observation_phase"] != "before_exec" or
            hook["sidecar_only"] is not True or
            any(hook[key] is not False for key in
                ("feeds_agent", "alters_execution", "alters_scoring"))):
        raise RuntimeError("G3 exploratory instrument is not specified as inert")
    plan = experiment["measurement_plan"]
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise RuntimeError("G3 exploratory measurement schema differs")
    fields = ["live_tool_dispatch.tool_name", "live_tool_dispatch.parsed_tool_args"]
    if (plan["unit"] != "per_task_step" or
            plan["signal_kind"] != "live_proposed_call_repetition_concordance" or
            plan["source_interface_sha256"] != INTERFACE_SHA or
            plan["source_fields"] != fields or
            hook["source_fields_used"] != fields or
            type(plan["minimum_complete_task_coverage_per_cohort"]) is not float or
            plan["minimum_complete_task_coverage_per_cohort"] != 0.8 or
            not _string_list(plan["logging_fields"], LOG_FIELDS) or
            not {"signal_category", "coverage_status"} <= set(plan["logging_fields"]) or
            any(not _nonempty(plan[key]) for key in PLAN_FIELDS - {
                "unit", "signal_kind", "source_interface_sha256", "source_fields",
                "prior_observation", "logging_fields", "limitations",
                "semantic_boundary",
                "minimum_complete_task_coverage_per_cohort"}) or
            not (_nonempty(plan["semantic_boundary"]) or
                 isinstance(plan["semantic_boundary"], list) and
                 bool(plan["semantic_boundary"]) and
                 all(_nonempty(item) for item in plan["semantic_boundary"])) or
            not isinstance(plan["limitations"], list) or not plan["limitations"] or
            any(not _nonempty(item) for item in plan["limitations"])):
        raise RuntimeError("G3 exploratory plan is incomplete or unbound")
    prior = plan["prior_observation"]
    if (not isinstance(prior, dict) or set(prior) != {
            "audit_sha256", "fact_id", "frozen_parent_signal_available",
            "exploratory_value"} or prior["audit_sha256"] != AUDIT_SHA or
            prior["fact_id"] != "proposed_call_frozen_coverage" or
            prior["fact_id"] not in cards or
            prior["frozen_parent_signal_available"] is not True or
            not _nonempty(prior["exploratory_value"])):
        raise RuntimeError("G3 exploratory plan hides the frozen-parent observation")
    reduced = {**result, "experiment": {
        key: value for key, value in experiment.items()
        if key not in {"measurement_plan", "intervention_class",
                       "diagnostic_interface", "outcome_claim"}}}
    validate_balanced_research(reduced, cards)
