"""Synthetic no-model checks for the narrow Gen11 review format projection."""

import copy
import unittest

from experiments import dab_roadmap_protocol as protocol
from experiments.admit_gen011_review_projection_once_v1 import project


class Gen11ReviewProjectionTests(unittest.TestCase):
    def setUp(self):
        self.review = {name: 'model authored text' for name in protocol.REVIEW_FIELDS}
        self.review.update(
            outcome_label='integrated_not_activated',
            source_reuse_recommendation='evidence_only',
            activation_evidence=['eligible=56', 'delivered=0'],
            evidence_refs=['result.mechanism_evidence'],
            relations_to_prior=[],
        )

    def test_only_detailed_field_added_and_original_unchanged(self):
        before = copy.deepcopy(self.review)
        result = project(self.review)
        self.assertEqual(self.review, before)
        self.assertEqual(set(result) - set(before), {'detailed_analysis'})
        self.assertTrue(all(result[name] == before[name] for name in before))
        self.assertIn('eligible=56\ndelivered=0', result['detailed_analysis'])

    def test_other_missing_original_field_rejected(self):
        self.review.pop('task_effect')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            project(self.review)

    def test_existing_detailed_field_rejected(self):
        self.review['detailed_analysis'] = 'other'
        with self.assertRaisesRegex(ValueError, 'exactly'):
            project(self.review)

    def test_missing_model_analysis_rejected(self):
        self.review['activation_evidence'] = []
        with self.assertRaisesRegex(ValueError, 'activation'):
            project(self.review)


if __name__ == '__main__':
    unittest.main()
