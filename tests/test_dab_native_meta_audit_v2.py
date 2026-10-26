import copy
from pathlib import Path
import unittest
from experiments.dab_native_meta_audit_v2 import validate_context


class NativeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(__file__).resolve().parent
        self.meta = {'model_provider': 'dab_crs_gpt55'}
        self.context = {'model': 'gpt-5.5', 'cwd': str(self.directory),
            'approval_policy': 'on-request', 'approvals_reviewer': 'auto_review',
            'sandbox_policy': {'type': 'read-only'}, 'permission_profile': {'network': 'restricted',
                'file_system': {'entries': [{'access': 'read', 'path': {'type': 'special', 'value': {'kind':'root'}}}]}}}

    def test_provider_in_session_metadata_and_absent_from_turn_is_valid(self):
        validate_context(self.meta, self.context, self.directory, 'read-only')

    def test_missing_or_wrong_session_provider_rejected(self):
        for meta in ({}, {'model_provider': 'different'}):
            with self.assertRaises(RuntimeError):
                validate_context(meta, self.context, self.directory, 'read-only')

    def test_conflicting_turn_provider_rejected(self):
        context = copy.deepcopy(self.context)
        context['model_provider'] = 'different'
        with self.assertRaises(RuntimeError):
            validate_context(self.meta, context, self.directory, 'read-only')

    def test_each_actual_permission_binding_still_enforced(self):
        for key, value in [('model','gpt-6.1-sol'), ('cwd', str(self.directory.parent)),
                           ('approval_policy','never'), ('approvals_reviewer','user'),
                           ('sandbox_policy',{'type':'workspace-write'})]:
            with self.subTest(key=key):
                context = copy.deepcopy(self.context)
                context[key] = value
                with self.assertRaises(RuntimeError):
                    validate_context(self.meta, context, self.directory, 'read-only')
        context = copy.deepcopy(self.context)
        context['permission_profile']['network'] = 'enabled'
        with self.assertRaises(RuntimeError):
            validate_context(self.meta, context, self.directory, 'read-only')

    def test_selector_write_access_rejected(self):
        context = copy.deepcopy(self.context)
        context['permission_profile']['file_system']['entries'][0]['access'] = 'write'
        with self.assertRaises(RuntimeError):
            validate_context(self.meta, context, self.directory, 'read-only')

    def test_coder_requires_actual_exact_workspace_write_root(self):
        context = copy.deepcopy(self.context)
        context['sandbox_policy']['type'] = 'workspace-write'
        with self.assertRaises(RuntimeError):
            validate_context(self.meta, context, self.directory, 'workspace-write')
        context['permission_profile']['file_system']['entries'].append(
            {'access':'write', 'path':{'type':'path','path':str(self.directory)}})
        validate_context(self.meta, context, self.directory, 'workspace-write')


if __name__ == '__main__':
    unittest.main()
