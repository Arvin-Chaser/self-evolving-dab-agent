"""The next-intent prompt asks for evidence-based exploration, not novelty by name."""
import unittest

from experiments.dab_roadmap_protocol import build_intent_prompt, intent_output_schema


class IntentDiversityPromptTests(unittest.TestCase):
    def test_stagnating_lineage_requires_comparison_not_forced_branch(self):
        prompt = build_intent_prompt({'latest_result': None, 'mechanism_index': {}})
        self.assertIn('without demonstrated behavioral effect', prompt)
        self.assertIn('materially different cross-task hypothesis', prompt)
        self.assertIn('explain why you continue', prompt)
        self.assertIn('a new mechanism_key alone does not establish novelty', prompt)
        self.assertIn('Exactly one must have role `code_base`', prompt)
        self.assertIn('Missing activation evidence is unknown', prompt)

    def test_historical_dimensions_are_optional_and_open_ended(self):
        prompt = build_intent_prompt({'latest_result': None, 'mechanism_index': {}})
        for dimension in (
            'state_externalization', 'control_topology', 'processing_granularity',
            'uncertainty_representation', 'evidence_composition', 'implementation_locus',
        ):
            self.assertIn(dimension, prompt)
        self.assertIn('optional lenses', prompt)
        self.assertIn('not an exhaustive menu', prompt)
        self.assertIn('outside this list', prompt)
        self.assertIn('plausible alternatives', prompt)
        self.assertIn('not an observed property or a performance claim', prompt)
        self.assertEqual(intent_output_schema()['properties']['primary_dimension'], {'type': 'string'})


if __name__ == '__main__':
    unittest.main()
