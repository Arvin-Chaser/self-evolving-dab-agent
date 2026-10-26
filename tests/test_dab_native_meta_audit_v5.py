"""Synthetic source/denial separation for the versioned native audit."""
import unittest

from experiments import dab_native_meta_audit_v5 as audit


def command(output, exit_code=0):
    return {'type': 'item.completed', 'item': {'type': 'command_execution',
            'aggregated_output': output, 'exit_code': exit_code,
            'status': 'completed'}}


class NativeAuditV5Tests(unittest.TestCase):
    def test_successful_source_display_is_not_security_denial(self):
        for marker in audit.SECURITY_MARKERS:
            self.assertFalse(audit.security_setup_failure([command('code: ' + marker)], ''))

    def test_actual_stderr_denial_remains_blocked(self):
        for marker in audit.SECURITY_MARKERS:
            self.assertTrue(audit.security_setup_failure([], 'runtime: ' + marker))

    def test_failed_command_denial_remains_blocked(self):
        self.assertTrue(audit.security_setup_failure([command('blocked by policy', 1)], ''))

    def test_error_event_denial_remains_blocked(self):
        events = [{'type': 'item.completed', 'item': {'type': 'error',
                   'message': 'Automatic approval review failed'}}]
        self.assertTrue(audit.security_setup_failure(events, ''))

    def test_failed_command_gate_is_not_weakened(self):
        self.assertTrue(audit.failed_native_command([command('ordinary test failure', 1)]))
        self.assertFalse(audit.failed_native_command([command('quoted error text', 0)]))


if __name__ == '__main__':
    unittest.main()
