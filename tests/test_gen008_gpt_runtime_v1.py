import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from experiments.dab_gen008_gpt_runtime_v1 import serialize_gate, validate_gate, GATE_FIELDS, COUNTERS, NativeJournal
from experiments import dab_runtime_repair_v1 as base
from adapters.crs_responses_client_v1 import NativeResponse, NATIVE_FIELD, input_items
from experiments.dab_gpt_isolation_v1 import physical_name, dispatch_once
from experiments.dab_runtime_repair_v1 import UnsafeResume, ProviderFailure


class Gen8InfrastructureTests(unittest.TestCase):
    def agent(self):
        return SimpleNamespace(duplicate_failure_ledger_size=32, duplicate_failure_ledger=[{'signature': 'fixture'}],
            duplicate_failure_gate_counters={name: 0 for name in COUNTERS},
            duplicate_failure_expired_signatures={'b', 'a'}, duplicate_failure_gate_one_shot_signatures={'once'},
            failed_request_suppression_counts={'fixture': 1})

    def test_gate_sets_and_counters_preserved_without_mutation(self):
        agent = self.agent()
        before = copy.deepcopy(vars(agent))
        state = serialize_gate(agent, required=True)
        self.assertEqual(set(state), set(GATE_FIELDS))
        self.assertEqual(state['duplicate_failure_expired_signatures'], ['a', 'b'])
        self.assertEqual(vars(agent), before)
        validate_gate(state)

    def test_missing_gate_never_inferred(self):
        self.assertIsNone(serialize_gate(SimpleNamespace()))
        with self.assertRaises(UnsafeResume):
            serialize_gate(SimpleNamespace(), required=True)
        agent = self.agent()
        del agent.failed_request_suppression_counts
        with self.assertRaises(UnsafeResume):
            serialize_gate(agent)

    def test_missing_counter_rejected(self):
        agent = self.agent()
        agent.duplicate_failure_gate_counters.pop('duplicate_suppression')
        with self.assertRaises(UnsafeResume):
            serialize_gate(agent)

    def test_corrupt_ledger_and_signature_set_rejected(self):
        state = serialize_gate(self.agent())
        for key, value in [('duplicate_failure_ledger_size', 0), ('duplicate_failure_ledger', ['notdict']),
                           ('duplicate_failure_expired_signatures', ['b', 'a']),
                           ('failed_request_suppression_counts', {'fixture': -1})]:
            changed = copy.deepcopy(state)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(UnsafeResume):
                validate_gate(changed)

    def test_physical_destinations_unique_and_narrow(self):
        self.assertNotEqual(physical_name('run1', 'logical'), physical_name('run2', 'logical'))
        self.assertNotEqual(physical_name('run1', 'logical'), physical_name('run1', 'other'))
        self.assertTrue(physical_name('run1', 'logical').startswith('dabg8_'))

    def test_provider_failure_never_replayed(self):
        calls, evidence = [], []
        def fail():
            calls.append(1)
            raise ConnectionError('synthetic')
        with self.assertRaises(ProviderFailure):
            dispatch_once(fail, evidence.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(evidence[0]['attempts'], 1)
        self.assertFalse(evidence[0]['automatic_replay'])

    def test_success_is_single_dispatch(self):
        calls = []
        self.assertEqual(dispatch_once(lambda: calls.append(1) or 'OK', lambda _: self.fail()), 'OK')
        self.assertEqual(calls, [1])

    def test_gen8_state_roundtrips_as_sets_and_exact_counters(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        with tempfile.TemporaryDirectory() as folder:
            agent = FakeAgent(Path(folder))
            vars(agent).update(vars(self.agent()))
            with patch.object(base, 'STATE_FIELDS', (*base.STATE_FIELDS, '_gen8_checkpoint_state')):
                journal = NativeJournal(agent, {'fixture': 'gen8'})
                journal.save()
                payload = journal.read(journal.path, journal.binding, agent.exec_tool_work_dir)
                restored = FakeAgent(Path(folder))
                vars(restored).update(vars(self.agent()))
                restored.duplicate_failure_expired_signatures.clear()
                NativeJournal(restored, journal.binding).restore(payload)
                self.assertEqual(serialize_gate(restored), serialize_gate(agent))
                self.assertIsInstance(restored.duplicate_failure_expired_signatures, set)

    def test_missing_gen8_state_rejected_on_restore(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        with tempfile.TemporaryDirectory() as folder:
            agent = FakeAgent(Path(folder))
            vars(agent).update(vars(self.agent()))
            journal = NativeJournal(agent, {'fixture': 'gen8'})
            with self.assertRaises(UnsafeResume):
                journal.restore({'state': {}})

    def test_native_reasoning_survives_journal_and_dispatch(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        with tempfile.TemporaryDirectory() as folder:
            agent = FakeAgent(Path(folder))
            vars(agent).update(vars(self.agent()))
            raw = {'model': 'gpt-5.5', 'status': 'completed', 'output': [
                {'type': 'reasoning', 'id': 'rs', 'summary': [], 'encrypted_content': 'opaque'},
                {'type': 'function_call', 'call_id': 'native', 'name': 'fixture', 'arguments': '{}'}]}
            message = NativeResponse(raw, [{'name': 'fixture'}]).choices[0].message
            with patch.object(base, 'STATE_FIELDS', (*base.STATE_FIELDS, '_gen8_checkpoint_state')):
                journal = NativeJournal(agent, {'fixture': 'gen8'})
                journal.accept(message)
                self.assertEqual(agent.messages[-1][NATIVE_FIELD], raw['output'])
                journal.dispatch()
                self.assertEqual(agent.executions, ['native'])
                self.assertEqual(input_items(agent.messages)[1:3], raw['output'])
                self.assertIsNone(journal.pending)
                self.assertEqual(journal.cursor, 0)

    def test_committed_tool_never_replayed_by_gen8_journal(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        with tempfile.TemporaryDirectory() as folder:
            agent = FakeAgent(Path(folder))
            vars(agent).update(vars(self.agent()))
            raw = {'model': 'gpt-5.5', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'first', 'name': 'fixture', 'arguments': '{}'},
                {'type': 'function_call', 'call_id': 'second', 'name': 'fixture', 'arguments': '{}'}]}
            with patch.object(base, 'STATE_FIELDS', (*base.STATE_FIELDS, '_gen8_checkpoint_state')):
                journal = NativeJournal(agent, {'fixture': 'gen8'})
                journal.accept(NativeResponse(raw, [{'name': 'fixture'}]).choices[0].message)
                agent._handle_tool_call(SimpleNamespace(id='first'))
                journal.cursor = 1
                journal.save()
                payload = journal.read(journal.path, journal.binding, agent.exec_tool_work_dir)
                restored = FakeAgent(Path(folder))
                vars(restored).update(vars(self.agent()))
                next_journal = NativeJournal(restored, journal.binding)
                next_journal.restore(payload)
                next_journal.dispatch()
                self.assertEqual(restored.executions, ['second'])
