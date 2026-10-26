import copy
import unittest

from experiments.run_research_graph_g003_balanced import (
    COHORT_SIZES, build_cards, validate_balanced_research,
)
from tests.test_research_graph_g003_meta_v3 import ready_result


def sidecar():
    return {"cohorts": {
        "strict_pass": {"tasks": 30, "tasks_with_return_answer": 30,
                        "tasks_with_tool_failure": 30, "llm_requests": 719,
                        "tool_calls": 1018},
        "strict_fail": {"tasks": 21, "tasks_with_return_answer": 20,
                        "tasks_with_tool_failure": 20, "llm_requests": 745,
                        "tool_calls": 990},
        "strict_unknown": {"tasks": 3},
        "timeout_failure": {"tasks": 2},
    }}


def research():
    result = ready_result()
    cards = build_cards(sidecar())
    result["alternative_directions"][0]["evidence_fact_ids"] = ["known_failure_mass"]
    result["alternative_directions"][1]["evidence_fact_ids"] = ["timeout_trace_gap"]
    result["problem"]["evidence_fact_ids"] = ["outcome_partition"]
    result["hypothesis"]["evidence_fact_ids"] = ["terminal_coverage"]
    result["uncertainty_fact_ids"] = ["semantic_failure_unknown"]
    result["cohort_comparison"] = [
        {"cohort": name, "size": size, "evidence_fact_ids": ["outcome_partition"],
         "priority_assessment": "Compare population and testability.",
         "uncertainty": "Mechanism unknown."}
        for name, size in COHORT_SIZES.items()
    ]
    result["target_cohort"] = "known_strict_fail"
    result["priority_rationale"] = "Larger known failure bucket, not a proven cause."
    return result, cards


class G003BalancedTests(unittest.TestCase):
    def test_all_cohort_cards_and_comparison(self):
        result, cards = research()
        self.assertEqual(len(cards), 11)
        validate_balanced_research(result, cards)

    def test_missing_cohort_and_unbound_fact_rejected(self):
        result, cards = research()
        result["cohort_comparison"] = result["cohort_comparison"][:2]
        with self.assertRaises(RuntimeError):
            validate_balanced_research(result, cards)
        result, cards = research()
        result["cohort_comparison"][0]["evidence_fact_ids"] = ["old_line"]
        with self.assertRaises(RuntimeError):
            validate_balanced_research(result, cards)

    def test_mutated_frozen_behavior_rejected(self):
        modified = copy.deepcopy(sidecar())
        modified["cohorts"]["strict_fail"]["tasks"] = 20
        with self.assertRaises(RuntimeError):
            build_cards(modified)


if __name__ == "__main__":
    unittest.main()
