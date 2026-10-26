import unittest

from experiments.run_research_graph_g003_measurement import (
    validate_measurement_research,
)
from tests.test_research_graph_g003_balanced import research


def measurement_plan():
    return {
        "unit": "per_task_step",
        "allowed_inputs": ["agent_visible_task_request", "base_db_description",
                           "tool_event_metadata"],
        "task_specific_instantiation": "Apply one rule to each task's visible request.",
        "progress_rule": "Count a new bounded evidence reference.",
        "no_progress_rule": "Count repeated completed evidence references.",
        "unknown_rule": "Unrecorded steps stay unknown.",
        "coverage_guard": "Reject interpretation below full step coverage.",
        "aggregation": "Compare per-task rates by cohort.",
        "mechanism_prediction": "Known failures have more no-progress steps.",
        "falsification_test": "No difference refutes the signal prediction.",
        "negative_control": "Progress labels should not follow strict verdict input.",
        "logging_fields": ["anonymous_task_index", "step_index",
                           "progress_category", "coverage_status"],
        "limitations": ["A proxy cannot establish answer correctness."],
    }


class G003MeasurementTests(unittest.TestCase):
    def test_ready_experiment_requires_task_level_plan(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = measurement_plan()
        validate_measurement_research(result, cards)
        del result["experiment"]["measurement_plan"]
        with self.assertRaises(RuntimeError):
            validate_measurement_research(result, cards)

    def test_unsafe_inputs_and_outputs_rejected(self):
        result, cards = research()
        result["experiment"]["measurement_plan"] = measurement_plan()
        result["experiment"]["measurement_plan"]["allowed_inputs"].append("official_answer")
        with self.assertRaises(RuntimeError):
            validate_measurement_research(result, cards)
        result["experiment"]["measurement_plan"] = measurement_plan()
        result["experiment"]["measurement_plan"]["logging_fields"].append("raw_result")
        with self.assertRaises(RuntimeError):
            validate_measurement_research(result, cards)

    def test_research_only_draft_remains_valid(self):
        result, cards = research()
        result["experiment_spec_ready"] = False
        result["experiment"] = None
        validate_measurement_research(result, cards)


if __name__ == "__main__":
    unittest.main()
