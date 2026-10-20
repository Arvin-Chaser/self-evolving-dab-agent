"""The revised gate records ordinary failures while retaining denial checks."""
import unittest

from experiments import dab_native_meta_audit_v6 as audit
from experiments.dab_native_meta_audit_v5 import security_setup_failure


class NativeAuditV6Tests(unittest.TestCase):
    def test_intermediate_failure_is_counted_not_hidden(self):
        events = [
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 1}},
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 0}},
        ]
        self.assertEqual(audit.command_outcome_counts(events), {
            'completed_command_count': 2, 'failed_intermediate_command_count': 1})

    def test_real_denial_is_still_detected(self):
        events = [{'type': 'item.completed', 'item': {'type': 'command_execution',
                   'exit_code': 1, 'aggregated_output': 'blocked by policy'}}]
        self.assertTrue(security_setup_failure(events, ''))

    def test_successful_source_display_is_not_denial(self):
        events = [{'type': 'item.completed', 'item': {'type': 'command_execution',
                   'exit_code': 0, 'aggregated_output': 'blocked by policy'}}]
        self.assertFalse(security_setup_failure(events, ''))


if __name__ == '__main__':
    unittest.main()
