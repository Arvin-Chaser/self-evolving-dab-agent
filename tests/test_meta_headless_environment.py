import os
import unittest
from unittest.mock import patch

from experiments.probe_meta_sandbox_local_v1 import local_probe_environment
from experiments.dab_api_routing import routed_meta_environment


class HeadlessMetaEnvironmentTests(unittest.TestCase):
    def test_only_optional_desktop_runtime_is_removed(self):
        original = {'CODEX_MCP_NODE_PATH': 'desktop/node.exe',
                    'CODEX_SANDBOX_NETWORK_DISABLED': '1',
                    'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY': 'original-family',
                    'PATH': 'unchanged-path', 'UNRELATED': 'unchanged'}
        with patch.dict(os.environ, original, clear=True):
            actual = local_probe_environment('configs/synthetic')
            self.assertNotIn('CODEX_MCP_NODE_PATH', actual)
            for key in original.keys() - {'CODEX_MCP_NODE_PATH'}:
                self.assertEqual(actual[key], original[key])
            self.assertEqual(os.environ['CODEX_MCP_NODE_PATH'], 'desktop/node.exe')

    def test_unselected_profile_is_not_modified(self):
        with patch('experiments.dab_api_routing.active_route', return_value={'meta_profile': 'selected'}):
            self.assertIsNone(routed_meta_environment('other'))


if __name__ == '__main__':
    unittest.main()
