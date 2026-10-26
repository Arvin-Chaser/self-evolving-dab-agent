import copy
import unittest

from experiments.collect_research_graph_g1_structural_v2 import (
    EXPECTED_G0, EXPECTED_G1, validate_output,
)
from experiments.run_research_graph_g002_meta_v2 import (
    SCOPE,
    build_cards,
    validate_observer,
    validate_research_revision,
)


def case(g0_status, g1_status, verdict, bound=False, terminal=1):
    failed = g1_status == "failed"
    return {
        "g0_terminal_status": g0_status,
        "g1_terminal_status": g1_status,
        "g1_strict_verdict": verdict,
        "reserve_bound": bound,
        "return_answer_end_count": 0 if failed else terminal,
        "completed_event_span_sec": None if failed else 1100 if bound else 500,
        "llm_request_count": 0 if failed else 10,
        "llm_response_count": 0 if failed else 10,
        "tool_call_count": 0 if failed else 15,
        "error_signature": ({"outer_class": "FatalError", "pattern": "unclassified"}
                            if failed else None),
    }


class ResearchGraphG002MetaV2Tests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            *[case("timeout", "completed", "false", True) for _ in range(3)],
            case("timeout", "completed", "false"),
            case("timeout", "completed", "true"),
            case("timeout", "failed", "not_completed"),
            case("completed", "completed", "true", True),
            case("completed", "completed", "false", True),
            case("completed", "failed", "not_completed"),
            *[case("completed", "completed", "true") for _ in range(28)],
            *[case("completed", "completed", "false") for _ in range(16)],
            *[case("completed", "completed", "unknown") for _ in range(3)],
        ]
        self.cases[37]["return_answer_end_count"] = 0

    def test_cards_are_derived_from_complete_partition(self):
        cards = build_cards(self.cases)
        self.assertEqual(len(cards), 13)
        self.assertIn("Three of the six", cards["g0_timeout_transition"]["statement"])
        changed = copy.deepcopy(self.cases)
        changed[0]["completed_event_span_sec"] = 1000
        with self.assertRaises(RuntimeError):
            build_cards(changed)

    def test_observer_accepts_only_card_ids(self):
        cards = build_cards(self.cases)
        result = {"observed_scope": SCOPE,
                  "salient_fact_ids": ["fixed_outcomes"],
                  "counterexample_fact_ids": ["timeout_not_success"],
                  "uncertainty_fact_ids": ["fatal_cause_unknown"]}
        validate_observer(result, cards)
        result["uncertainty_fact_ids"] = ["not_a_card"]
        with self.assertRaises(RuntimeError):
            validate_observer(result, cards)

    def test_research_rejects_unbound_evidence(self):
        cards = build_cards(self.cases)
        result = {"alternatives_considered": [
            {"direction": "a", "disposition": "reject",
             "evidence_fact_ids": ["fixed_outcomes"], "reason": "r"},
            {"direction": "b", "disposition": "reject",
             "evidence_fact_ids": ["fatal_cause_unknown"], "reason": "r"}],
            "implementation_ready": False, "problem": None, "hypothesis": None,
            "experiment": None, "uncertainty_fact_ids": ["fatal_cause_unknown"],
            "decision_rationale": "No supported intervention."}
        validate_research_revision(result, cards)
        result["alternatives_considered"][0]["evidence_fact_ids"] = ["old_card"]
        with self.assertRaises(RuntimeError):
            validate_research_revision(result, cards)

    def test_collector_rejects_answer_bearing_output_field(self):
        packet = {"schema_version": "g001_answer_blind_structural_v2",
                  "answer_blind": True,
                  "source_hashes": {"g0_graph_sha256": EXPECTED_G0,
                                    "g1_graph_sha256": EXPECTED_G1},
                  "cases": [{"anonymous_batch_index": index,
                             "g0_terminal_status": "completed",
                             "g0_strict_verdict": "unknown",
                             "g1_terminal_status": "completed",
                             "g1_strict_verdict": "unknown",
                             "reserve_bound": False,
                             "llm_request_count": 0,
                             "llm_response_count": 0,
                             "tool_call_count": 0,
                             "return_answer_end_count": 0,
                             "completed_event_span_sec": None,
                             "error_signature": None,
                             "trace_sha256": "0" * 64} for index in range(56)]}
        validate_output(packet)
        packet["cases"][0]["raw_message"] = "not permitted"
        with self.assertRaises(RuntimeError):
            validate_output(packet)


if __name__ == "__main__":
    unittest.main()
