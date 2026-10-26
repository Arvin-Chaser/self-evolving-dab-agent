import unittest

from experiments.collect_research_graph_g0_timeout_partial import event_epoch, number


class TimeoutPartialExtractionTests(unittest.TestCase):
    def test_upstream_tool_timestamp_is_seconds(self):
        value = event_epoch("20261016_063917")
        self.assertGreater(value, 1_500_000_000)
        self.assertLess(value, 2_500_000_000)

    def test_unix_llm_timestamp_is_preserved(self):
        self.assertEqual(event_epoch(1792132755.922823), 1792132755.922823)

    def test_invalid_mixed_timestamp_is_not_interpreted_as_epoch(self):
        self.assertIsNone(event_epoch("20261016063917"))

    def test_duration_is_separate_from_event_time(self):
        self.assertEqual(number("1.5"), 1.5)
        self.assertIsNone(event_epoch(1.5))


if __name__ == "__main__":
    unittest.main()
