import unittest

from experiments.collect_research_graph_g002_exact_repetition import (
    canonical_signature, count_task, summarize,
)


def start(index, args, name="query_db"):
    return {"tool_call_index": index, "tool_name": name, "validated_args": args}


class G002ExactRepetitionTests(unittest.TestCase):
    def test_canonicalization_preserves_values_and_types(self):
        self.assertEqual(canonical_signature(start(1, {"b": [1, 2], "a": True})),
                         canonical_signature(start(2, {"a": True, "b": [1, 2]})))
        self.assertNotEqual(canonical_signature(start(1, {"a": 1})),
                            canonical_signature(start(2, {"a": "1"})))
        self.assertNotEqual(canonical_signature(start(1, [1, 2])),
                            canonical_signature(start(2, [2, 1])))
        self.assertIsNone(canonical_signature(start(1, None)))

    def test_counts_only_within_one_task(self):
        rows = [start(1, {"sql": "x"}), start(2, {"sql": "x"}),
                start(3, None), start(4, {"sql": "y"})]
        self.assertEqual(count_task(rows), {"starts": 4, "eligible": 3,
                                            "repeat": 1, "unknown": 1,
                                            "coverage": "partial"})
        self.assertEqual(count_task([start(1, {"sql": "x"})])["repeat"], 0)

    def test_bad_index_fails_closed(self):
        with self.assertRaises(RuntimeError):
            count_task([start(2, {})])

    def test_cohort_summary_equal_weights_tasks(self):
        rows = [count_task([start(1, {}), start(2, {})]),
                count_task([start(1, {"a": 1})])]
        summary = summarize(rows, 2)
        self.assertEqual(summary["mean_complete_task_rate"], 0.25)
        self.assertEqual(summary["exact_repeats"], 1)
        self.assertEqual(summary["unmeasured_tasks"], 0)
        self.assertEqual(summarize([], 2)["unmeasured_tasks"], 2)


if __name__ == "__main__":
    unittest.main()
