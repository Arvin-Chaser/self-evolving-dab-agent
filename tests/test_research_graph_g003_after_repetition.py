import unittest

from experiments.run_research_graph_g003_after_repetition import (
    build_cards, verified_recount,
)


class G003AfterRepetitionTests(unittest.TestCase):
    def test_frozen_recount_is_not_promoted_to_a_mechanism(self):
        cards = build_cards(verified_recount())
        self.assertIn("3/21", cards["exact_repeat_coverage_gap"]["statement"])
        self.assertIn("4/30", cards["exact_repeat_coverage_gap"]["statement"])
        self.assertEqual(cards["exact_repeat_coverage_gap"]["kind"], "uncertainty")
        self.assertIn("untested", cards["exact_repeat_coverage_gap"]["statement"])
        self.assertIn("not task progress", cards["exact_repeat_rule"]["statement"])


if __name__ == "__main__":
    unittest.main()
