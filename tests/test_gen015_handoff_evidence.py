import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from experiments import dab_roadmap_protocol as protocol
from experiments.extract_gen015_handoff_evidence import build_card, sha


class Gen15EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'deployment_handoff_r2').mkdir()
        self.intent = root / 'sealed_intent.json'
        self.summary = root / 'summary.json'
        self.audit = root / 'audit.json'
        self.card = root / 'card.json'
        self.launch = root / 'deployment_handoff_r2/launch_manifest.json'
        self.write(self.intent, {'generation': 15, 'mechanism_key': 'two_phase_frozen_evidence_handoff',
                                'canonical_json_sha256': 'intent'})
        self.write(root / 'candidate_ref_revision_002.json', {'source_tree_sha256': 'tree'})
        self.write(self.launch, {'source_tree_sha256': 'tree', 'intent_sha256': 'intent'})
        self.write(self.summary, {'per_query_feedback': [{'query_id': f'fixture/{i}',
                    'status': 'completed', 'strict_match_passed': i == 0} for i in range(56)]})
        self.value = {'schema': 'gen015_handoff_terminal_audit_v1', 'complete': True, 'natural_end': True,
            'hashes_verified': True, 'ids_match_order': True, 'exact_ids': 56, 'completed': 56,
            'runner_timeout': 0, 'strict_pass': 1, 'summary_sha256': sha(self.summary),
            'launch_manifest_sha256': sha(self.launch), 'source_tree_sha256': 'tree', 'intent_sha256': 'intent',
            'mechanism_coverage': {'completed_present': 56, 'fallback_rows': 56, 'sealed_rows': 1,
                                 'context_rebuild_rows': 0, 'composition_request_rows': 0},
            'completed_mechanism_counts': {'bundle_sealed_events': 1, 'context_rebuilds': 0},
            'fallback_reasons': {'phase_a_call_not_read_only': 55, 'composition_context_unavailable': 1},
            'termination_reasons': {'phase_fallback_budget_exhausted': 55, 'return_answer': 1},
            'limitations': ['Fallback cap is a confound; no causal handoff effect established.']}

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def build(self):
        self.write(self.audit, self.value)
        return build_card(self.audit, self.summary, self.intent)

    def test_seal_is_not_delivery_or_uptake(self):
        card = self.build()
        self.assertEqual(card['measurement_status']['sealing'], 'positive')
        self.assertEqual(card['measurement_status']['context_delivery'], 'measured_zero')
        self.assertEqual(card['measurement_status']['model_uptake'], 'unknown_not_measured')
        self.assertNotIn('fixture/', json.dumps(card))

    def test_unbound_summary_is_rejected(self):
        self.value['summary_sha256'] = 'changed'
        with self.assertRaises(ValueError):
            self.build()

    def test_false_completion_is_rejected(self):
        self.value['natural_end'] = False
        with self.assertRaises(ValueError):
            self.build()

    def test_impossible_reach_is_rejected(self):
        self.value['mechanism_coverage']['composition_request_rows'] = 1
        with self.assertRaisesRegex(ValueError, 'causal reach'):
            self.build()

    def test_protocol_requires_exact_recomputed_card(self):
        card = self.build()
        self.write(self.card, card)
        self.assertEqual(protocol.verified_mechanism_evidence(self.card, self.audit, self.summary, self.intent), card)
        card['coverage']['context_rebuild_rows'] = 1
        self.write(self.card, card)
        with self.assertRaises(SystemExit):
            protocol.verified_mechanism_evidence(self.card, self.audit, self.summary, self.intent)

    def test_running_result_requires_terminal_evidence(self):
        with patch.object(protocol, 'load_campaign', return_value=({}, {'stage': 'evaluation_running'})):
            with self.assertRaisesRegex(SystemExit, 'natural-end terminal audit'):
                protocol.record_result(Namespace(campaign_root=self.intent.parent))

    def test_running_result_rejects_nonterminal_audit(self):
        self.value['natural_end'] = False
        self.write(self.audit, self.value)
        with patch.object(protocol, 'load_campaign', return_value=({}, {'stage': 'evaluation_running'})):
            with self.assertRaisesRegex(SystemExit, 'not passed'):
                protocol.record_result(Namespace(campaign_root=self.intent.parent,
                    mechanism_terminal_audit=self.audit, mechanism_evidence_card=self.card))


if __name__ == '__main__':
    unittest.main()
