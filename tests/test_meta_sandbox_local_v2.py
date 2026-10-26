import unittest
from pathlib import Path
from experiments.probe_meta_sandbox_local_v2 import build_sandbox_command, SHELL


class LocalSandboxCommandTests(unittest.TestCase):
    def test_flat_installed_cli_grammar(self):
        cmd = build_sandbox_command('codex', Path('fixture'))
        self.assertEqual(cmd[1], 'sandbox')
        self.assertNotIn('windows', cmd)
        self.assertEqual(cmd[cmd.index('--') + 1], str(SHELL))

    def test_bounded_managed_profile_is_explicit(self):
        cmd = build_sandbox_command('codex', Path('fixture'))
        self.assertEqual(cmd[cmd.index('-P') + 1], ':workspace')
        self.assertIn('--include-managed-config', cmd)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)
        self.assertEqual(cmd[cmd.index('-C') + 1], 'fixture')


if __name__ == '__main__':
    unittest.main()
