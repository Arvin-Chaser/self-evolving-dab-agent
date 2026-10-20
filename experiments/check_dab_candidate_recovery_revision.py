"""Source-only candidate checks: real wrapper installation, no model or database."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def check(repo: Path) -> dict:
    sys.path.insert(0, str(repo))
    from experiments import run_dab_tool_agent as runner
    results = []
    path = repo / 'tests/test_dab_turn_checkpoint_recovery.py'
    spec = importlib.util.spec_from_file_location('revision_tests', path)
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    for name, function in sorted(vars(tests).items()):
        if name.startswith('test_') and callable(function):
            try:
                function()
                results.append({'name': name, 'passed': True})
            except Exception as error:
                results.append({'name': name, 'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
    try:
        with tempfile.TemporaryDirectory(prefix='dab_revision_wrapper_') as temporary:
            class BaseTool:
                def __init__(self, log_path, name):
                    self.log_path, self.name = log_path, name
                def get_spec(self):
                    return {'type': 'function', 'function': {'name': self.name, 'description': 'deterministic stub',
                            'parameters': {'type': 'object', 'properties': {}}}}
                def _check_args(self, args):
                    return args
                def _exec(self, args):
                    return None
            class BaseAgent:
                def __init__(self, **kwargs):
                    self.root_dir = Path(temporary)
                    self.tool_log_path = self.root_dir / 'tool_calls.jsonl'
                    self.file_storage_dir = self.root_dir
                    self.tools = {'query_db': BaseTool(self.tool_log_path, 'query_db')}
                    self.messages, self.result_storage = [], {}
                    self.llm_call_count, self.base_dispatches = 0, 0
                    self.final_result = None
                def _handle_tool_call(self, call):
                    self.base_dispatches += 1
                    try:
                        arguments = json.loads(call.function.arguments)
                    except json.JSONDecodeError:
                        # Match upstream's error-safe parse path: visible tool
                        # failure message, no tool execution or new tool-log row.
                        self.messages.append({'role': 'tool', 'tool_call_id': call.id,
                                              'content': 'Arguments JSON decode error'})
                        return None
                    failed = bool(arguments.get('fail'))
                    value = None if failed else {'rows': [1], 'step': arguments.get('step')}
                    self.result_storage['var_' + call.id] = value
                    self.messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': json.dumps(value)})
                    with self.tool_log_path.open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps({'tool_name': call.function.name,
                            'dispatch_sequence': self.base_dispatches, 'result': {
                            'success': not failed, 'preview': None if failed else json.dumps(value)}}) + '\n')
                    return value
                def _handle_content(self, content):
                    self.final_result = content
                    return content
            module = SimpleNamespace(BaseTool=BaseTool, DataAgent=BaseAgent)
            runner.install_self_observation_tool(module, SimpleNamespace(disable_self_observation_tool=False,
                                                                         self_observation_tool_name='record_self_observation'))
            agent = module.DataAgent()
            def dispatch(ident, arguments):
                return agent._handle_tool_call(SimpleNamespace(id=ident, function=SimpleNamespace(
                    name='query_db', arguments=json.dumps(arguments))))
            dispatch('success', {'step': 1})
            assert agent.base_dispatches == 1, 'First successful tool did not reach unchanged base dispatch'
            assert agent.checkpoint_creation_count >= 1, 'Successful advancing result did not create checkpoint'
            dispatch('failure', {'fail': True})
            assert agent.base_dispatches == 2
            assert agent.checkpoint_restore_count >= 1, 'Failure did not restore valid checkpoint'
            dispatch('duplicate', {'fail': True})
            assert agent.base_dispatches == 2, 'Exact failed request was not suppressed in its window'
            assert agent.request_suppression_count >= 1
            for turn in range(5):
                dispatch('advance_' + str(turn), {'step': turn + 2})
            prior = agent.base_dispatches
            dispatch('retry_after_window', {'fail': True})
            assert agent.base_dispatches == prior + 1, 'Expired exact request remained suppressed'
            assert agent.recovery_window_expiration_count >= 1
            assert agent._handle_content('complete') == 'complete'
            assert agent.final_result == 'complete'
            results.append({'name': 'installed_production_wrapper_success_failure_suppression_expiration_content', 'passed': True})
            # A bounded turn window must advance on unrelated activations too.
            # Keep the earlier regression unchanged; these checks are additive.
            for window in (0, 1, 3):
                name = 'installed_wrapper_unrelated_turn_expiration_window_' + str(window)
                try:
                    with tempfile.TemporaryDirectory(prefix='dab_revision_expiry_') as temporary:
                        agent = module.DataAgent(recovery_suppression_turns=window)
                        dispatch('checkpoint', {'step': 1})
                        dispatch('first_failure', {'fail': True})
                        for turn in range(window):
                            before = agent.base_dispatches
                            dispatch('unrelated_' + str(turn), {'step': turn + 20})
                            assert agent.base_dispatches == before + 1, 'Unrelated request was suppressed'
                        before = agent.base_dispatches
                        dispatch('retry_after_unrelated_window', {'fail': True})
                        assert agent.base_dispatches == before + 1, (
                            'Exact failed request remained suppressed after all configured unrelated turns')
                        assert agent.request_suppression_count == 0
                        if window:
                            assert agent.recovery_window_expiration_count >= 1
                    results.append({'name': name, 'passed': True})
                except Exception as error:
                    results.append({'name': name, 'passed': False,
                                    'error_type': type(error).__name__, 'error': str(error)})
            name = 'installed_wrapper_other_suppressed_signature_advances_all_windows'
            try:
                with tempfile.TemporaryDirectory(prefix='dab_revision_interleaved_') as temporary:
                    agent = module.DataAgent(recovery_suppression_turns=3)
                    dispatch('checkpoint', {'step': 1})
                    dispatch('failure_A', {'fail': True, 'request': 'A'})
                    dispatch('failure_B', {'fail': True, 'request': 'B'})
                    before = agent.base_dispatches
                    dispatch('duplicate_B_1', {'fail': True, 'request': 'B'})
                    dispatch('duplicate_B_2', {'fail': True, 'request': 'B'})
                    assert agent.base_dispatches == before, 'Active exact B duplicates did not suppress'
                    dispatch('retry_A_after_three_turns', {'fail': True, 'request': 'A'})
                    assert agent.base_dispatches == before + 1, (
                        'Suppressed B activations did not expire the unrelated A window')
                    before = agent.base_dispatches
                    dispatch('retry_B_after_three_turns', {'fail': True, 'request': 'B'})
                    assert agent.base_dispatches == before + 1, 'Expired B window remained active'
                results.append({'name': name, 'passed': True})
            except Exception as error:
                results.append({'name': name, 'passed': False,
                                'error_type': type(error).__name__, 'error': str(error)})
            for window in (0, 1, 3):
                name = 'installed_wrapper_malformed_request_bounded_window_' + str(window)
                try:
                    with tempfile.TemporaryDirectory(prefix='dab_revision_malformed_') as temporary:
                        agent = module.DataAgent(recovery_suppression_turns=window)
                        dispatch('checkpoint', {'step': 1})
                        def malformed(ident):
                            return agent._handle_tool_call(SimpleNamespace(id=ident, function=SimpleNamespace(
                                name='query_db', arguments='{not-json')))
                        malformed('first_malformed_failure')
                        before = agent.base_dispatches
                        assert before == 2, 'Original malformed request failure was hidden'
                        assert any('JSON decode error' in m.get('content', '') for m in agent.messages)
                        for turn in range(window):
                            malformed('malformed_duplicate_' + str(turn))
                            assert agent.base_dispatches == before, 'Exact malformed request bypassed active suppression'
                        malformed('malformed_retry_after_window')
                        assert agent.base_dispatches == before + 1, 'Expired malformed request was suppressed'
                        assert agent.request_suppression_count == window
                    results.append({'name': name, 'passed': True})
                except Exception as error:
                    results.append({'name': name, 'passed': False,
                                    'error_type': type(error).__name__, 'error': str(error)})
            # Suppression budget zero disables suppression, not recovery or
            # failure instrumentation. Every first failure retains the same
            # sealed checkpoint recovery contract, including malformed input.
            for malformed_input in (False, True):
                for window in (0, 1, 3):
                    name = ('installed_wrapper_first_failure_recovery_' +
                            ('malformed' if malformed_input else 'parsed') +
                            '_window_' + str(window))
                    try:
                        with tempfile.TemporaryDirectory(prefix='dab_revision_first_failure_') as temporary:
                            agent = module.DataAgent(recovery_suppression_turns=window)
                            dispatch('checkpoint', {'step': 1})
                            checkpoint_before = runner.read_valid_turn_checkpoints(
                                agent.checkpoints_path, agent.max_turn_checkpoints)[-1]
                            failures_before = agent.recovery_state.state.failure_outcome_count
                            restores_before = agent.checkpoint_restore_count
                            if malformed_input:
                                agent._handle_tool_call(SimpleNamespace(id='new_failure', function=SimpleNamespace(
                                    name='query_db', arguments='{not-json')))
                            else:
                                dispatch('new_failure', {'fail': True})
                            violations = []
                            if agent.checkpoint_restore_count != restores_before + 1:
                                violations.append('First failed result did not restore its valid checkpoint')
                            if agent.recovery_state.state.failure_outcome_count != failures_before + 1:
                                violations.append('First failed result was not counted exactly once')
                            if agent.last_checkpoint != checkpoint_before:
                                violations.append('Recovery replaced retained successful checkpoint')
                            if agent.base_dispatches != 2 or agent.request_suppression_count != 0:
                                violations.append('First failed request was hidden or suppressed')
                            if malformed_input and not any('JSON decode error' in m.get('content', '')
                                                            for m in agent.messages):
                                violations.append('Original malformed failure visibility was lost')
                            if not malformed_input and agent.result_storage.get('var_new_failure', 'missing') is not None:
                                violations.append('Original failed result was mutated or removed')
                            if window == 0 and agent.failed_request_suppressions:
                                violations.append('Zero budget created suppression state')
                            assert not violations, '; '.join(violations)
                        results.append({'name': name, 'passed': True})
                    except Exception as error:
                        results.append({'name': name, 'passed': False,
                                        'error_type': type(error).__name__, 'error': str(error)})
            # Match actual upstream/Journal conversation framing, not only a
            # direct handler invocation. A bypassed call still needs its own
            # correlated tool outcome before the next model request.
            for malformed_input in (False, True):
                for window in (1, 3):
                    name = ('installed_wrapper_suppressed_tool_response_' +
                            ('malformed' if malformed_input else 'parsed') + '_window_' + str(window))
                    try:
                        with tempfile.TemporaryDirectory(prefix='dab_revision_protocol_') as temporary:
                            agent = module.DataAgent(recovery_suppression_turns=window)
                            def framed_call(ident, raw):
                                call = {'id': ident, 'type': 'function', 'function': {
                                    'name': 'query_db', 'arguments': raw}}
                                agent.messages.append({'role': 'assistant', 'tool_calls': [call]})
                                return agent._handle_tool_call(SimpleNamespace(id=ident,
                                    function=SimpleNamespace(**call['function'])))
                            framed_call('checkpoint', json.dumps({'step': 1}))
                            raw = '{not-json' if malformed_input else json.dumps({'fail': True})
                            framed_call('original_failure', raw)
                            before = agent.base_dispatches
                            framed_call('suppressed_duplicate', raw)
                            assert agent.base_dispatches == before, 'Active duplicate actually executed'
                            replies = [m for m in agent.messages if m.get('role') == 'tool'
                                       and m.get('tool_call_id') == 'suppressed_duplicate']
                            assert len(replies) == 1, 'Suppressed call lacks exactly one matching tool response'
                            assert isinstance(replies[0].get('content'), str) and replies[0]['content'].strip(), (
                                'Suppressed call has no explicit planning outcome')
                            assert any(m.get('role') == 'tool' and m.get('tool_call_id') == 'original_failure'
                                       for m in agent.messages), 'Original failure response was removed'
                        results.append({'name': name, 'passed': True})
                    except Exception as error:
                        results.append({'name': name, 'passed': False,
                                        'error_type': type(error).__name__, 'error': str(error)})
            # Validate the COMPLETE actual conversation, not just the newly
            # correlated duplicate. Checkpoint notes are not independent tools.
            def validate_closed_conversation(messages):
                pending = set()
                for index, message in enumerate(messages):
                    role = message.get('role')
                    if role == 'assistant' and message.get('tool_calls'):
                        assert not pending, 'New assistant turn before all tool results'
                        identifiers = [call.get('id') for call in message['tool_calls']]
                        assert all(isinstance(i, str) and i for i in identifiers)
                        assert len(set(identifiers)) == len(identifiers)
                        pending = set(identifiers)
                    elif role == 'tool':
                        ident = message.get('tool_call_id')
                        assert isinstance(ident, str) and ident and ident in pending, (
                            'Orphan or duplicate tool response at message ' + str(index) +
                            ': name=' + str(message.get('name')) + ', tool_call_id=' + str(ident))
                        pending.remove(ident)
                    else:
                        assert not pending, 'Non-tool note interrupts pending tool-result group'
                assert not pending, 'Model request would retain unanswered tool calls'
            for malformed_input, window in [(m, w) for m in (False, True) for w in (0, 1, 3)]:
                name = ('installed_wrapper_complete_conversation_' +
                        ('malformed' if malformed_input else 'parsed') + '_window_' + str(window))
                try:
                    with tempfile.TemporaryDirectory(prefix='dab_revision_conversation_') as temporary:
                        agent = module.DataAgent(recovery_suppression_turns=window)
                        def framed_group(entries):
                            calls = [{'id': ident, 'type': 'function', 'function': {
                                'name': 'query_db', 'arguments': raw}} for ident, raw in entries]
                            agent.messages.append({'role': 'assistant', 'tool_calls': calls})
                            for call in calls:
                                agent._handle_tool_call(SimpleNamespace(id=call['id'],
                                    function=SimpleNamespace(**call['function'])))
                            validate_closed_conversation(agent.messages)
                        framed_group([('checkpoint', json.dumps({'step': 1}))])
                        raw = '{not-json' if malformed_input else json.dumps({'fail': True})
                        framed_group([('first_failure', raw)])
                        framed_group([('duplicate_or_retry', raw)])
                        framed_group([('unrelated', json.dumps({'step': 2}))])
                        assert any(m.get('tool_call_id') == 'first_failure' for m in agent.messages)
                    results.append({'name': name, 'passed': True})
                except Exception as error:
                    results.append({'name': name, 'passed': False,
                                    'error_type': type(error).__name__, 'error': str(error)})
            name = 'installed_wrapper_complete_conversation_multicall_group'
            try:
                with tempfile.TemporaryDirectory(prefix='dab_revision_multicall_') as temporary:
                    agent = module.DataAgent(recovery_suppression_turns=3)
                    framed_group([('checkpoint', json.dumps({'step': 1}))])
                    framed_group([('failed_first', json.dumps({'fail': True})),
                                  ('successful_second', json.dumps({'step': 2}))])
                    framed_group([('suppressed_first', json.dumps({'fail': True})),
                                  ('malformed_second', '{not-json')])
                    assert agent.request_suppression_count == 1
                results.append({'name': name, 'passed': True})
            except Exception as error:
                results.append({'name': name, 'passed': False,
                                'error_type': type(error).__name__, 'error': str(error)})
    except Exception as error:
        results.append({'name': 'installed_production_wrapper_success_failure_suppression_expiration_content',
                        'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
    return {'passed': bool(results) and all(item['passed'] for item in results), 'checks': results,
            'model_calls': 0, 'database_calls': 0}


if __name__ == '__main__':
    report = check(Path(sys.argv[1]).resolve())
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)
