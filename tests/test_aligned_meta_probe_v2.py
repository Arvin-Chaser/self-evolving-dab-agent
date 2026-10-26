import copy
from pathlib import Path
import tomllib
import unittest

from experiments import probe_aligned_meta_v2 as probe


class AlignedProbeTests(unittest.TestCase):
    def test_tool_output_failure_is_not_mistaken_for_success_or_review_denial(self):
        self.assertEqual(probe.failure_classification('', [{'aggregated_output':
            'Failed to create unified exec process: helper_unknown_error: setup refresh had errors'}]),
            'windows_sandbox_setup_refresh_failed')
        self.assertEqual(probe.failure_classification('Automatic approval review failed: 403', []),
                         'automatic_approval_review_failed')
        self.assertIsNone(probe.failure_classification('', []))

    def test_both_provider_configs_are_bounded_and_aligned(self):
        for model, profile, home, route in probe.PROVIDERS.values():
            value = tomllib.loads((probe.ROOT / home / 'config.toml').read_text(encoding='utf-8'))
            self.assertTrue(probe.config_alignment(value))
            self.assertEqual(value['model'], model)
            self.assertEqual(value['model_providers'][value['model_provider']]['request_max_retries'], 0)

    def test_reviewer_sandbox_or_network_weakening_rejected(self):
        value = tomllib.loads((probe.ROOT / probe.PROVIDERS['gpt'][2] / 'config.toml').read_text(encoding='utf-8'))
        for key, bad in [('sandbox_mode', 'danger-full-access'), ('default_permissions', ':danger-full-access'),
                         ('approval_policy', 'never'), ('approvals_reviewer', 'user')]:
            changed = copy.deepcopy(value)
            changed[key] = bad
            self.assertFalse(probe.config_alignment(changed))
        changed = copy.deepcopy(value)
        changed['sandbox_workspace_write']['network_access'] = True
        self.assertFalse(probe.config_alignment(changed))

    def test_exec_switches_are_explicit_and_same_for_both(self):
        for model, profile, home, route in probe.PROVIDERS.values():
            command = probe.build_command('codex', Path('synthetic'), model, profile)
            self.assertLess(command.index('exec'), command.index('--sandbox'))
            self.assertEqual(command[command.index('--sandbox') + 1], 'workspace-write')
            self.assertIn('approvals_reviewer="auto_review"', command)
            self.assertIn('approval_policy="on-request"', command)
            self.assertNotIn('--approve-for-me', command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)


if __name__ == '__main__':
    unittest.main()
