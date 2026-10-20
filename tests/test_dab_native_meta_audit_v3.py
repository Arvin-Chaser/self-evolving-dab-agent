import unittest
from experiments.dab_native_meta_audit_v3 import classify_events, RECOVERABLE_MESSAGE


class RecoveredEventsTests(unittest.TestCase):
    def events(self):
        return [{'type': 'thread.started', 'thread_id': 'fixture'}, {'type': 'turn.started'},
                {'type': 'error', 'message': RECOVERABLE_MESSAGE},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'done'}},
                {'type': 'turn.completed'}]

    def test_recovered_connection_and_successful_completion(self):
        self.assertEqual(len(classify_events(self.events())), 1)

    def test_normal_completion(self):
        self.assertEqual(classify_events([e for e in self.events() if e['type'] != 'error']), [])

    def test_unknown_error_rejected(self):
        events = self.events()
        events[2]['message'] = 'unknown failure'
        with self.assertRaises(RuntimeError):
            classify_events(events)

    def test_missing_completion_rejected(self):
        with self.assertRaises(RuntimeError):
            classify_events(self.events()[:-1])

    def test_terminal_failure_always_rejected(self):
        events = self.events()
        events.insert(3, {'type': 'turn.failed'})
        with self.assertRaises(RuntimeError):
            classify_events(events)

    def test_error_after_completion_rejected(self):
        with self.assertRaises(RuntimeError):
            classify_events(self.events() + [{'type': 'error', 'message': RECOVERABLE_MESSAGE}])

    def test_recovered_error_requires_later_final_content(self):
        with self.assertRaises(RuntimeError):
            classify_events([e for e in self.events() if e['type'] != 'item.completed'])

    def test_multiple_completions_rejected(self):
        with self.assertRaises(RuntimeError):
            classify_events(self.events() + [{'type': 'turn.completed'}])


if __name__ == '__main__':
    unittest.main()
