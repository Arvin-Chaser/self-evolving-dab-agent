import unittest

from experiments.build_research_graph_g003_runtime_interface_card import build_card
from experiments.run_research_graph_g003_constrained import INTERFACE_SHA
from experiments.validate_research_graph_g003_diagnostic import validate_diagnostic_research
from tests.test_research_graph_g003_balanced import research
from tests.test_research_graph_g003_constrained import plan, runtime_interface


def diagnostic():
    result, cards = research()
    cards["exact_repeat_coverage_gap"] = {"kind": "uncertainty"}
    result["hypothesis"]["evidence_fact_ids"].append("exact_repeat_coverage_gap")
    result["experiment"].update({
        "intervention_class": "diagnostic_instrumentation",
        "outcome_claim": "observability_only_no_strict_gain_prediction",
        "diagnostic_interface": {
            "runtime_hook": "DataAgentWithSelfObservation._handle_tool_call",
            "observation_phase": "before_exec",
            "source_fields_used": ["live_tool_dispatch.tool_name",
                                   "live_tool_dispatch.parsed_tool_args"],
            "sidecar_only": True, "feeds_agent": False,
            "alters_execution": False, "alters_scoring": False,
        },
        "measurement_plan": {
            "unit": "per_task_step", "signal_kind": "proposed_call_repetition",
            "minimum_complete_task_coverage_per_cohort": 0.8,
            "source_interface_sha256": INTERFACE_SHA,
            "source_fields": ["live_tool_dispatch.tool_name",
                              "live_tool_dispatch.parsed_tool_args"],
            "parent_gap": {
                "evidence_fact_ids": ["exact_repeat_coverage_gap"],
                "missing_live_fields": ["parsed_tool_args"],
                "why_frozen_artifacts_insufficient": "Complete per-task coverage is unavailable.",
            },
            "task_specific_instantiation": "Compare only within a task.",
            "canonicalization": "Canonicalize parsed arguments in memory.",
            "positive_rule": "Equal earlier proposal.",
            "negative_rule": "Distinct proposal.",
            "unknown_rule": "Parse failure is unknown.",
            "coverage_guard": "At least 80% complete tasks per cohort.",
            "aggregation": "Equal task weights.",
            "observability_prediction": "The sidecar reaches the coverage guard.",
            "falsification_test": "Coverage below guard refutes observability.",
            "negative_control": "First proposal cannot be a repeat.",
            "logging_fields": ["anonymous_task_index", "signal_category",
                               "coverage_status"],
            "semantic_boundary": "A proposed repeat is not task obstruction.",
            "limitations": ["Cannot establish answer correctness."],
        },
    })
    return result, cards


class G003DiagnosticTests(unittest.TestCase):
    def test_diagnostic_is_a_valid_formal_experiment_specification(self):
        result, cards = diagnostic()
        validate_diagnostic_research(result, cards, build_card())

    def test_behavior_change_uses_the_existing_gate(self):
        result, cards = research()
        result["experiment"].update({
            "intervention_class": "agent_behavior_change",
            "intervention_interface": runtime_interface(),
            "measurement_plan": plan(),
        })
        validate_diagnostic_research(result, cards, build_card())
        result["experiment"]["intervention_interface"]["pre_exec_inputs"] = ["validated_args"]
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())

    def test_rejects_reconstructible_or_unbound_diagnostic(self):
        result, cards = diagnostic()
        result["experiment"]["measurement_plan"]["parent_gap"]["evidence_fact_ids"] = ["semantic_failure_unknown"]
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment"]["measurement_plan"]["parent_gap"]["missing_live_fields"] = ["validated_args"]
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())

    def test_rejects_control_or_output_leakage(self):
        result, cards = diagnostic()
        result["experiment"]["diagnostic_interface"]["feeds_agent"] = True
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment"]["measurement_plan"]["logging_fields"].append("raw_result")
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment"]["measurement_plan"]["source_fields"].append("tool_call_start.validated_args")
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment"]["outcome_claim"] = "strict_gain_expected"
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment"]["measurement_plan"]["minimum_complete_task_coverage_per_cohort"] = 0.0
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())

    def test_rejects_measurement_only_alias_and_accepts_research_draft(self):
        result, cards = diagnostic()
        result["experiment"]["intervention_class"] = "measurement_only"
        with self.assertRaises(RuntimeError):
            validate_diagnostic_research(result, cards, build_card())
        result, cards = diagnostic()
        result["experiment_spec_ready"] = False
        result["experiment"] = None
        validate_diagnostic_research(result, cards, build_card())


if __name__ == "__main__":
    unittest.main()
