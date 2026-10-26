import copy
import unittest

from experiments.collect_research_graph_g002_balanced import (
    COHORTS, GRAPH_SHA, MANIFEST_SHA, SUMMARY_SHA, validate_output,
)


def packet():
    counts = (30, 21, 3, 2)
    return {
        "schema_version": "g002_balanced_behavior_answer_blind_v1",
        "answer_blind": True,
        "source_hashes": {
            "g2_graph_sha256": GRAPH_SHA,
            "g2_summary_sha256": SUMMARY_SHA,
            "g2_trace_manifest_sha256": MANIFEST_SHA,
        },
        "frozen_task_count": 56,
        "cohorts": {
            name: {"tasks": count, "traces": count if name != "timeout_failure" else 0,
                   "tool_calls": 0, "tool_failures": 0}
            for name, count in zip(COHORTS, counts)
        },
        "tool_failures_by_name": {},
        "limitations": ["Counts are observational."],
    }


class BalancedG2CollectorTests(unittest.TestCase):
    def test_accepts_fixed_full_partition(self):
        validate_output(packet())

    def test_rejects_answer_bearing_field(self):
        result = packet()
        result["cohorts"]["strict_fail"]["answer"] = "secret"
        with self.assertRaises(RuntimeError):
            validate_output(result)

    def test_rejects_denominator_or_binding_drift(self):
        result = packet()
        result["cohorts"]["strict_fail"]["tasks"] = 20
        with self.assertRaises(RuntimeError):
            validate_output(result)
        result = copy.deepcopy(packet())
        result["source_hashes"]["g2_summary_sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            validate_output(result)

    def test_rejects_unknown_tool_name_and_inconsistent_failures(self):
        result = packet()
        result["tool_failures_by_name"] = {"secret_tool": 1}
        with self.assertRaises(RuntimeError):
            validate_output(result)
        result = packet()
        result["tool_failures_by_name"] = {"query_db": 1}
        with self.assertRaises(RuntimeError):
            validate_output(result)


if __name__ == "__main__":
    unittest.main()
