import unittest
import argparse
import tempfile
from pathlib import Path
from unittest import mock
from experiments.dab_result_health import provider_failure
from experiments.dab_roadmap_protocol import compact_result
from experiments import dab_roadmap_protocol as protocol


class ProviderHealthTests(unittest.TestCase):
    def test_exit_zero_does_not_hide_provider_failures(self):
        rows = [{"run_exit_code": 0, "run_error": None,
                 "terminate_reason": f"llm_response_failed attempt 4/4 (InternalServerError): Error code: {code}"}
                for code in (500, 503)]
        self.assertEqual(compact_result({"per_query_feedback": rows})["provider_error_count"], 2)
        self.assertTrue(all(provider_failure(row) for row in rows))

    def test_normal_answer_and_context_limit_are_not_transient_provider_outages(self):
        self.assertFalse(provider_failure({"terminate_reason": "return_answer"}))
        self.assertFalse(provider_failure({"terminate_reason": "llm_response_failed (BadRequestError): Error code: 400 - context length"}))
        self.assertTrue(provider_failure({"terminate_reason": "llm_response_failed (APITimeoutError)"}))

    def test_formal_record_rejects_provider_failure_before_writing_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            protocol.write_json(summary, {"batch": {"query_ids": ["alpha/query1"]},
                "per_query_feedback": [{"query_id": "alpha/query1", "run_exit_code": 0,
                    "run_error": None, "terminate_reason": "llm_response_failed (InternalServerError): Error code: 503"}]})
            with mock.patch.object(protocol, "load_campaign", return_value=(
                {"query_ids": ["alpha/query1"]}, {"stage": "candidate_admitted", "next_generation": 1})):
                with self.assertRaisesRegex(SystemExit, "provider/transport failures"):
                    protocol.record_result(argparse.Namespace(campaign_root=root, batch_summary=summary))
            self.assertFalse((root / "generations/gen_001/result.json").exists())


if __name__ == "__main__":
    unittest.main()
