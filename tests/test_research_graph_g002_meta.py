import unittest

from experiments.run_research_graph_g002_meta import (
    build_cards,
    validate_observer,
)


class ResearchGraphG002MetaTests(unittest.TestCase):
    def setUp(self):
        self.g0 = {"nodes": [{"strict_pass_count": 33, "timeout_failure_count": 6}]}
        self.g1 = {"nodes": [{"strict_pass_count": 30, "completed_count": 54,
                              "timeout_failure_count": 0,
                              "other_terminal_failure_count": 2,
                              "strict_verdict_missing_completed_count": 3}]}
        self.mechanism = {"cohorts": [
            {"trigger": "bound", "status": "completed", "strict_verdict": "true", "count": 1},
            {"trigger": "bound", "status": "completed", "strict_verdict": "false", "count": 4},
            {"trigger": "unbound", "status": "completed", "strict_verdict": "true", "count": 29},
            {"trigger": "unbound", "status": "completed", "strict_verdict": "false", "count": 17},
            {"trigger": "unbound", "status": "completed", "strict_verdict": "unknown", "count": 3},
            {"trigger": "unbound", "status": "failed", "strict_verdict": "unknown", "count": 2},
        ], "failed_error_classes": {"FatalError": 2}}

    def test_frozen_card_arithmetic(self):
        cards = build_cards(self.g0, self.g1, self.mechanism)
        self.assertEqual(len(cards), 12)
        self.assertIn("one had a strict-true verdict and four had strict-false",
                      cards["g1_bound_outcomes"]["statement"])
        self.mechanism["cohorts"][0]["count"] = 2
        with self.assertRaises(RuntimeError):
            build_cards(self.g0, self.g1, self.mechanism)

    def test_observer_selection_uses_only_bound_fact_ids(self):
        cards = build_cards(self.g0, self.g1, self.mechanism)
        selection = {"observed_scope": "G1 four nodes and answer-blind G0/G1 fact cards",
                     "salient_fact_ids": ["g1_outcome_partition"],
                     "counterexample_fact_ids": ["trigger_not_sufficient_for_strict"],
                     "uncertainty_fact_ids": ["failure_cause_unknown"]}
        validate_observer(selection, cards)
        selection["salient_fact_ids"] = ["not_a_fact"]
        with self.assertRaises(RuntimeError):
            validate_observer(selection, cards)


if __name__ == "__main__":
    unittest.main()
