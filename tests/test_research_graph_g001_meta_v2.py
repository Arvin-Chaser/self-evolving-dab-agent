import unittest

from experiments.run_research_graph_g001_meta_v2 import (
    flatten_metrics, validate_observer, validate_observer_cards,
)


class ResearchGraphObserverV2Tests(unittest.TestCase):
    def setUp(self):
        self.metrics = {"frozen_tasks", "tasks_strict_pass"}
        self.valid = {
            "observed_scope": "baseline root and answer-blind aggregate behavior counts",
            "observations": [{"interpretation": "Some frozen tasks passed strict scoring.",
                              "metric_keys": ["tasks_strict_pass"]}],
            "counterexamples": [],
            "uncertainties": [{"interpretation": "The mechanism is not determined by these counts.",
                               "metric_keys": ["frozen_tasks"]}],
        }

    def test_accepts_grounded_qualitative_output(self):
        validate_observer(self.valid, self.metrics)

    def test_rejects_model_arithmetic(self):
        self.valid["observations"][0]["interpretation"] = "There were 17 failures."
        with self.assertRaises(RuntimeError):
            validate_observer(self.valid, self.metrics)

    def test_rejects_answer_bearing_request(self):
        self.valid["uncertainties"][0]["interpretation"] = "Read final answers to determine the mechanism."
        with self.assertRaises(RuntimeError):
            validate_observer(self.valid, self.metrics)

    def test_rejects_unknown_metric(self):
        self.valid["observations"][0]["metric_keys"] = ["made_up_metric"]
        with self.assertRaises(RuntimeError):
            validate_observer(self.valid, self.metrics)

    def test_rejects_extra_proposal_field(self):
        self.valid["hypothesis"] = "change agent"
        with self.assertRaises(RuntimeError):
            validate_observer(self.valid, self.metrics)

    def test_cohorts_must_cover_frozen_batch(self):
        packet = {
            "frozen_task_count": 56,
            "trace_hashes_verified": 50,
            "task_cohorts": {"strict_pass": 33, "strict_fail": 14,
                             "strict_unknown": 3, "timeout_failure": 6},
            "trace_behavior_by_cohort": {},
            "tool_calls_by_name": {},
            "tool_failures_by_name": {},
        }
        self.assertEqual(flatten_metrics(packet)["tasks_strict_fail"], 14)
        packet["task_cohorts"]["strict_fail"] = 13
        with self.assertRaises(RuntimeError):
            flatten_metrics(packet)

    def test_card_selection_rejects_unbound_claim(self):
        cards = {"fact": {"kind": "observation"},
                 "counter": {"kind": "counterexample"},
                 "unknown": {"kind": "uncertainty"}}
        answer = {"observed_scope": "baseline root and answer-blind fact cards",
                  "salient_fact_ids": ["fact"],
                  "counterexample_fact_ids": ["counter"],
                  "uncertainty_fact_ids": ["unknown"]}
        validate_observer_cards(answer, cards)
        answer["salient_fact_ids"] = ["made_up"]
        with self.assertRaises(RuntimeError):
            validate_observer_cards(answer, cards)


if __name__ == "__main__":
    unittest.main()
