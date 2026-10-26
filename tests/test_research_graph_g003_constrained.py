import unittest

from experiments.build_research_graph_g003_runtime_interface_card import build_card
from experiments.run_research_graph_g003_constrained import (
    INTERFACE_SHA, validate_constrained_research,
)
from tests.test_research_graph_g003_balanced import research


def plan():
    return {
        "unit": "per_task_step", "signal_kind": "exact_call_repetition",
        "source_interface_sha256": INTERFACE_SHA,
        "source_fields": ["tool_call_start.tool_name",
                          "tool_call_start.validated_args"],
        "task_specific_instantiation": "Compare signatures only within each task.",
        "canonicalization": "Canonical JSON of local validated args; hash internally.",
        "positive_rule": "Exact prior signature means repeated call.",
        "negative_rule": "New signature means not repeated.",
        "unknown_rule": "Missing args remain unknown.",
        "coverage_guard": "Report unknown fraction by task.",
        "aggregation": "Equal-weighted per-task repeated-call fraction.",
        "mechanism_prediction": "Known failures repeat more exact calls.",
        "falsification_test": "No group difference refutes this prediction.",
        "negative_control": "A unique signature must not be repeated.",
        "logging_fields": ["anonymous_task_index", "step_index",
                           "signal_category", "coverage_status"],
        "semantic_boundary": "Exact repetition is not lack of task progress.",
        "limitations": ["Repeated calls may be rational verification."],
    }


def runtime_interface():
    return {
        "runtime_hook": "DataAgentWithSelfObservation._handle_tool_call",
        "pre_exec_inputs": ["tool_name", "parsed_tool_args"],
        "post_run_fields_used_pre_exec": [],
        "blocking_response_contract": "requires_new_verified_contract",
    }


class G003ConstrainedTests(unittest.TestCase):
    def test_ready_structural_signal_can_be_validated(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["intervention_class"] = "agent_behavior_change"
        result["experiment"]["intervention_interface"] = runtime_interface()
        validate_constrained_research(result, cards, build_card())

    def test_measurement_only_child_is_rejected(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["intervention_class"] = "measurement_only"
        result["experiment"]["intervention_interface"] = runtime_interface()
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())

    def test_post_run_field_cannot_be_claimed_at_dispatch(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["intervention_class"] = "agent_behavior_change"
        result["experiment"]["intervention_interface"] = runtime_interface()
        result["experiment"]["intervention_interface"]["pre_exec_inputs"].append("validated_args")
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())
        result["experiment"]["intervention_interface"] = runtime_interface()
        result["experiment"]["intervention_interface"]["post_run_fields_used_pre_exec"] = ["tool_call_index"]
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())
        result["experiment"]["intervention_interface"] = runtime_interface()
        result["experiment"]["intervention_interface"]["pre_exec_inputs"] = []
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())

    def test_nonexistent_obligation_key_is_rejected(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["intervention_class"] = "agent_behavior_change"
        result["experiment"]["intervention_interface"] = runtime_interface()
        result["experiment"]["measurement_plan"]["signal_kind"] = "task_obligation_progress"
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())

    def test_unlisted_field_and_output_are_rejected(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["intervention_class"] = "agent_behavior_change"
        result["experiment"]["intervention_interface"] = runtime_interface()
        result["experiment"]["measurement_plan"]["source_fields"] = ["tool_call_end.obligation_id"]
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())
        result["experiment"]["measurement_plan"] = plan()
        result["experiment"]["measurement_plan"]["logging_fields"].append("raw_result")
        with self.assertRaises(RuntimeError):
            validate_constrained_research(result, cards, build_card())

    def test_research_only_result_is_valid(self):
        result, cards = research()
        result["experiment_spec_ready"] = False
        result["experiment"] = None
        validate_constrained_research(result, cards, build_card())


if __name__ == "__main__":
    unittest.main()
