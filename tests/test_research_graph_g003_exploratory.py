import json
import unittest
from pathlib import Path

from experiments.run_research_graph_g003_constrained import verified_interface
from experiments.run_research_graph_g003_exploratory_meta import fact_cards
from experiments.validate_research_graph_g003_exploratory import validate_exploratory_research


RESULT = (Path(__file__).resolve().parents[1] /
          "experiments/research_graph_baseline_20261016/g003_research_meta_012/result.json")


class G003ExploratoryTests(unittest.TestCase):
    def result(self):
        return json.loads(RESULT.read_text(encoding="utf-8"))

    def test_frozen_revision_passes_specification(self):
        validate_exploratory_research(self.result(), fact_cards(), verified_interface())

    def test_prior_signal_cannot_be_hidden(self):
        result = self.result()
        result["experiment"]["measurement_plan"]["prior_observation"]["frozen_parent_signal_available"] = False
        with self.assertRaises(RuntimeError):
            validate_exploratory_research(result, fact_cards(), verified_interface())

    def test_diagnostic_cannot_affect_agent_or_export_content(self):
        result = self.result()
        result["experiment"]["diagnostic_interface"]["feeds_agent"] = True
        with self.assertRaises(RuntimeError):
            validate_exploratory_research(result, fact_cards(), verified_interface())
        result = self.result()
        result["experiment"]["measurement_plan"]["logging_fields"].append("raw_args")
        with self.assertRaises(RuntimeError):
            validate_exploratory_research(result, fact_cards(), verified_interface())


if __name__ == "__main__":
    unittest.main()
