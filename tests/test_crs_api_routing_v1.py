import copy
import json
import os
import unittest
from unittest import mock
from experiments import dab_api_routing as routing


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads((routing.ROOT / 'configs/dab_crs_gpt55_route_v1.json').read_text(encoding='utf-8'))

    def route(self, value):
        with mock.patch.object(routing.Path, 'is_file', return_value=True), mock.patch.object(routing.Path, 'read_text', return_value=json.dumps(value)):
            return routing.active_route()

    def test_exact_route(self):
        self.assertEqual(self.route(self.value), self.value)

    def test_other_bindings_rejected(self):
        for key in ('provider', 'base_url', 'model', 'api_key_env', 'api_key_file', 'meta_profile', 'meta_codex_home', 'meta_bridge_config', 'wire_api'):
            with self.subTest(key=key):
                value = copy.deepcopy(self.value)
                value[key] = 'unapproved'
                with self.assertRaises(RuntimeError):
                    self.route(value)

    def test_meta_original_unchanged(self):
        original = {'model': 'old', 'profile': 'old'}
        with mock.patch.object(routing, 'active_route', return_value=self.value):
            value = routing.meta_route(original)
        self.assertEqual(value['model'], 'gpt-5.5')
        self.assertEqual(value['active_api_route'], 'crs_gpt55')
        self.assertEqual(original['model'], 'old')

    def test_key_only_in_child(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(routing, 'active_route', return_value=self.value), mock.patch.object(routing, 'read_explicit_key', return_value='synthetic'):
            env = routing.routed_meta_environment('crs-gpt55-dab')
            self.assertEqual(env['CRS_API_KEY'], 'synthetic')
            self.assertNotIn('CRS_API_KEY', os.environ)


if __name__ == '__main__':
    unittest.main()
