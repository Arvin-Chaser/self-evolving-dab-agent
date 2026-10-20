"""Synthetic, model-free Gen10 evidence-card binding checks."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.extract_dab_mechanism_evidence_v2 import build_card, COUNTERS, REQUIRED_CHECKS
from experiments import dab_roadmap_protocol as protocol


class Gen10EvidenceCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.summary = root / "summary.json"
        self.audit = root / "audit.json"
        self.intent = root / "intent.json"
        self.card = root / "card.json"
        self.summary.write_text(json.dumps({"per_query_feedback": [{} for _ in range(17)]}), encoding="utf-8")
        self.intent.write_text(json.dumps({"generation": 10, "mechanism_key":
                                          "failure_triggered_obligation_steering"}), encoding="utf-8")
        raw = self.summary.read_bytes()
        counters = dict.fromkeys(COUNTERS, 0)
        counters.update(obligation_created=1, eligible_intervention_opportunity=2,
                        intervention_raised=1, continuation_requested=1)
        self.value = {
            "summary_sha256": hashlib.sha256(raw).hexdigest(), "summary_bytes": len(raw),
            "formal_result_eligible": True, "Graph_or_Meta_launched": False,
            "run_id": "synthetic", "local_health": {
                "normal": 17, "strict": 4, "run_errors": 0, "analysis_errors": 0,
                "provider_termination": 0,
            },
            "remote": {
                "summary_sha256": hashlib.sha256(raw).hexdigest(), "complete": True,
                "healthy_full17_eligible": True,
                "global_full_narrow_admitted_upstream_frozen17_bindings_valid": True,
                "forced_injection_synthetic_test_passed": True,
                "rows": [{"task_index": i, "normal": True, "strict": i <= 4,
                          "audit_errors": [], "checks": dict.fromkeys(REQUIRED_CHECKS, True),
                          "progress_counters": dict(counters)} for i in range(1, 18)],
            },
        }

    def build(self):
        self.audit.write_text(json.dumps(self.value), encoding="utf-8")
        return build_card(self.audit, self.summary, self.intent)

    def test_measured_denominator_and_intervention(self):
        card = self.build()
        self.assertEqual(card["mechanism_counters"]["eligible_intervention_opportunity"], 34)
        self.assertEqual(card["measurement_status"]["continuation_intervention"], "observed")
        self.assertEqual(card["measurement_status"]["causal_accuracy_gain"], "not_established")
        self.assertNotIn("per_query_feedback", card)

    def test_measured_zero_is_not_missing(self):
        for row in self.value["remote"]["rows"]:
            row["progress_counters"]["continuation_requested"] = 0
        card = self.build()
        self.assertEqual(card["measurement_status"]["continuation_intervention"], "measured_zero")
        self.assertEqual(card["measurement_status"]["eligible_tool_failure_opportunity_denominator"], "observed")
        self.assertEqual(card["measurement_status"]["behavior_after_intervention"],
                         "no_continuation_observed_despite_raised_obligations")

    def test_missing_bound_synthetic_self_test_rejected(self):
        self.value["remote"]["forced_injection_synthetic_test_passed"] = False
        with self.assertRaisesRegex(ValueError, "synthetic forced-injection"):
            self.build()

    def test_live_task_does_not_fabricate_self_test(self):
        self.assertNotIn("progress_contract_self_test_valid", REQUIRED_CHECKS)
        self.assertEqual(self.build()["measurement_status"]["forced_injection_reachability"],
                         "verified_synthetic_not_real_activation")

    def test_counter_exceeding_denominator_rejected(self):
        self.value["remote"]["rows"][0]["progress_counters"]["intervention_raised"] = 40
        with self.assertRaisesRegex(ValueError, "exceed measured opportunities"):
            self.build()

    def test_original_protocol_recomputes_exact_card(self):
        card = self.build()
        self.card.write_text(json.dumps(card), encoding="utf-8")
        self.assertEqual(protocol.verified_mechanism_evidence(self.card, self.audit, self.summary, self.intent), card)
        card["mechanism_counters"]["continuation_requested"] += 1
        self.card.write_text(json.dumps(card), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "differs"):
            protocol.verified_mechanism_evidence(self.card, self.audit, self.summary, self.intent)


if __name__ == "__main__":
    unittest.main()
