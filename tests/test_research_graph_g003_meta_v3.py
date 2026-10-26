import copy
import unittest

from experiments.run_research_graph_g003_meta_v3 import validate_research_spec


CARDS = {
    "observation": {"kind": "observation"},
    "counterexample": {"kind": "counterexample"},
    "uncertainty": {"kind": "uncertainty"},
}


def ready_result():
    return {
        "alternative_directions": [
            {"direction": "a", "evidence_fact_ids": ["observation"],
             "assessment": "bounded"},
            {"direction": "b", "evidence_fact_ids": ["counterexample"],
             "assessment": "rejected"},
        ],
        "research_ready": True,
        "experiment_spec_ready": True,
        "problem": {"evidence_fact_ids": ["observation"]},
        "hypothesis": {
            "evidence_fact_ids": ["observation", "uncertainty"],
            "statement": "s", "prediction": "p",
            "falsification_condition": "f", "possible_counterexample": "c",
        },
        "experiment": {
            "intervention": "bounded hook", "code_parent": "g002_lifecycle_stage",
            "expected_behavior": "event", "frozen_evaluation": "56 no-hint",
            "negative_control": "unchanged normal tasks",
            "implementation_scope": "runner only",
            "safety_questions": ["Can an in-flight call be cancelled safely?"],
            "engineering_acceptance_criteria": ["A failed cancel remains timeout."],
        },
        "uncertainty_fact_ids": ["uncertainty"],
        "decision_rationale": "Specific specification; source safety remains unverified.",
    }


class ResearchGraphG003MetaV3Tests(unittest.TestCase):
    def test_spec_ready_does_not_claim_engineering_admission(self):
        validate_research_spec(ready_result(), CARDS)

    def test_incomplete_spec_remains_research_draft(self):
        result = ready_result()
        result["experiment_spec_ready"] = False
        result["experiment"] = None
        validate_research_spec(result, CARDS)

    def test_rejects_false_ready_and_unbound_evidence(self):
        result = ready_result()
        result["experiment"]["safety_questions"] = []
        with self.assertRaises(RuntimeError):
            validate_research_spec(result, CARDS)
        result = copy.deepcopy(ready_result())
        result["hypothesis"]["evidence_fact_ids"] = ["not_a_card"]
        with self.assertRaises(RuntimeError):
            validate_research_spec(result, CARDS)
        result = ready_result()
        result["research_ready"] = False
        with self.assertRaises(RuntimeError):
            validate_research_spec(result, CARDS)


if __name__ == "__main__":
    unittest.main()
