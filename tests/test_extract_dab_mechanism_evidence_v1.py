"""Synthetic, model-free checks for the bounded mechanism evidence card."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.extract_dab_mechanism_evidence_v1 import build_card
from experiments import dab_roadmap_protocol as protocol


class MechanismEvidenceCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.summary = root / "summary.json"
        self.audit = root / "audit.json"
        self.intent = root / "intent.json"
        self.summary.write_text(json.dumps({"per_query_feedback": [{}, {}]}), encoding="utf-8")
        self.intent.write_text(json.dumps({
            "generation": 9, "mechanism_key": "observable_tool_progress_contract"
        }), encoding="utf-8")
        self.row = {
            "normal": True,
            "strict": True,
            "audit_errors": [],
            "checks": {name: True for name in (
                "actual_execution_paths", "progress_contract_schema_counters",
                "final_generic_state_exact", "final_durable_counters",
                "source_intent_parent_input_model_binding",
            )},
            "progress_counters": {
                "obligation_created": 2, "advancing_results": 3, "completion": 1,
                "continuation_requested": 0, "bound_reached": 0, "pass_through": 0,
            },
        }
        raw = self.summary.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        self.value = {
            "summary_sha256": digest,
            "summary_bytes": len(raw),
            "formal_result_eligible": True,
            "Graph_or_Meta_launched": False,
            "run_id": "synthetic",
            "local_health": {
                "normal": 2, "strict": 2, "run_errors": 0,
                "analysis_errors": 0, "provider_termination": 0,
            },
            "remote": {
                "summary_sha256": digest,
                "complete": True,
                "healthy_full17_eligible": True,
                "global_full_narrow_admitted_upstream_frozen17_bindings_valid": True,
                "rows": [{"task_index": i, **self.row} for i in (1, 2)],
            },
        }

    def build(self):
        self.audit.write_text(json.dumps(self.value), encoding="utf-8")
        return build_card(self.audit, self.summary, self.intent)

    def test_measured_zero_is_not_missing(self):
        card = self.build()
        self.assertEqual(card["mechanism_counters"]["obligation_created"], 4)
        self.assertEqual(card["measurement_status"]["continuation_intervention"], "measured_zero")
        self.assertEqual(card["measurement_status"]["eligible_content_opportunity_denominator"], "not_instrumented")
        self.assertNotIn("per_query_feedback", card)

    def test_positive_intervention_is_not_called_causal(self):
        self.value["remote"]["rows"][0]["progress_counters"] = {
            **self.row["progress_counters"], "continuation_requested": 1,
        }
        card = self.build()
        self.assertEqual(card["measurement_status"]["continuation_intervention"], "observed")
        self.assertEqual(card["measurement_status"]["causal_accuracy_gain"], "not_established")

    def test_summary_binding_tamper_rejected(self):
        self.summary.write_text(json.dumps({"per_query_feedback": [{}, {}]}, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.build()

    def test_missing_verified_counter_rejected(self):
        self.value["remote"]["rows"][0]["progress_counters"].pop("continuation_requested")
        with self.assertRaisesRegex(ValueError, "Invalid progress counter"):
            self.build()

    def test_partial_or_invalid_audit_rejected(self):
        self.value["remote"]["rows"][0]["checks"]["progress_contract_schema_counters"] = False
        with self.assertRaisesRegex(ValueError, "required mechanism"):
            self.build()

    def test_review_and_graph_receive_only_the_bound_card(self):
        card = self.build()
        self.assertEqual(
            protocol.verified_mechanism_evidence(self._card_file(card), self.audit, self.summary, self.intent),
            card,
        )
        result = {"generation": 9, "summary": {}, "mechanism_evidence": card}
        visible = protocol.visible_result(result)
        self.assertEqual(visible["activation_evidence_status"], "measured_in_bound_terminal_audit")
        self.assertEqual(visible["mechanism_evidence"], card)
        graph = protocol.compact_graph_node({
            "node_id": "synthetic", "generation": 9, "intent": {}, "review": {},
            "result": {}, "mechanism_evidence": card,
        })
        self.assertEqual(graph["mechanism_evidence"], card)

    def test_review_rejects_modified_card(self):
        card = self.build()
        card["mechanism_counters"]["continuation_requested"] = 5
        with self.assertRaisesRegex(SystemExit, "differs"):
            protocol.verified_mechanism_evidence(self._card_file(card), self.audit, self.summary, self.intent)

    def _card_file(self, card):
        path = Path(self.temp.name) / "card.json"
        path.write_text(json.dumps(card), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
