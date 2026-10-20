"""Synthetic, model-free tests for Gen11 delivery evidence admission."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments import dab_roadmap_protocol as protocol
from experiments.extract_dab_mechanism_evidence_v3 import build_card, COUNTERS


class Gen11EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.summary = root / 'summary.json'
        self.audit = root / 'audit.json'
        self.intent = root / 'intent.json'
        self.card = root / 'card.json'
        rows = [{'query_id': f'fixture/{index}', 'strict_match_passed': index < 10}
                for index in range(17)]
        self.summary.write_text(json.dumps({'per_query_feedback': rows}), encoding='utf-8')
        self.intent.write_text(json.dumps({'generation': 11, 'mechanism_key':
                                           'delivered_repeat_failure_steering'}), encoding='utf-8')
        counts = dict.fromkeys(COUNTERS, 0)
        counts.update(eligible_intervention_opportunity=56, intervention_raised=56)
        self.value = {
            'schema': 'gen011_deepseek_terminal_integrity_audit_v1',
            'run_id': 'gen011_deepseek_full17_v2_p4_20261009_111743',
            'summary_sha256': hashlib.sha256(self.summary.read_bytes()).hexdigest(),
            'summary_bytes': len(self.summary.read_bytes()),
            'remote_full_audit_sha256':
                'b574be161fe0d32bb1aeb34aec4187fce081d486b5966c4293a0ef837c40fe56',
            'complete': True, 'healthy_full17_eligible': True,
            'normal': 17, 'strict': 10, 'run_errors': 0, 'analysis_errors': 0,
            'provider_termination': 0, 'failed_check_count': 0, 'audit_error_count': 0,
            'all_final_pending_clear': True, 'all_original_wire_checks_passed': True,
            'all_isolation_manifests_valid': True,
            'all_source_and_input_binding_checks_passed': True,
            'Meta_or_Graph_launched': False, 'delivery_counters': counts,
            'rows_with_eligible_opportunity': 17,
            'rows_with_delivered_steering': 0,
            'rows_with_nonempty_final_delivery_ledger': 0,
        }

    def build(self):
        self.audit.write_text(json.dumps(self.value), encoding='utf-8')
        return build_card(self.audit, self.summary, self.intent)

    def test_measured_opportunity_not_activation(self):
        card = self.build()
        self.assertEqual(card['mechanism_counters']['eligible_intervention_opportunity'], 56)
        self.assertEqual(card['measurement_status']['steering_delivery'], 'measured_zero')
        self.assertEqual(card['coverage']['tasks_with_eligible_opportunity'], 17)

    def test_excess_delivery_rejected(self):
        self.value['delivery_counters']['delivered_steering'] = 57
        with self.assertRaisesRegex(ValueError, 'exceed observed opportunities'):
            self.build()

    def test_missing_wire_evidence_rejected(self):
        self.value['all_original_wire_checks_passed'] = False
        with self.assertRaisesRegex(ValueError, 'not healthy'):
            self.build()

    def test_summary_tampering_rejected(self):
        self.summary.write_text(json.dumps({'per_query_feedback': []}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'binding differs'):
            self.build()

    def test_original_protocol_recomputes_exact_card(self):
        card = self.build()
        self.card.write_text(json.dumps(card), encoding='utf-8')
        self.assertEqual(protocol.verified_mechanism_evidence(
            self.card, self.audit, self.summary, self.intent), card)
        card['mechanism_counters']['delivered_steering'] = 1
        self.card.write_text(json.dumps(card), encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'differs'):
            protocol.verified_mechanism_evidence(
                self.card, self.audit, self.summary, self.intent)


if __name__ == '__main__':
    unittest.main()
