"""Native audit with narrowly classified recovered connection notifications.

Version 2 remains immutable. No requests are retried by this verifier.
Unknown errors and security failures still fail closed.
"""
from __future__ import annotations
import json
from pathlib import Path
from experiments.dab_native_meta_audit_v2 import sha, validate_context

RECOVERABLE_MESSAGE = 'Reconnecting... waiting for network (Connection failed: error sending request)'


def classify_events(events):
    starts = [i for i, e in enumerate(events) if e.get('type') == 'turn.started']
    ends = [i for i, e in enumerate(events) if e.get('type') == 'turn.completed']
    if len(starts) != 1 or len(ends) != 1 or ends[0] != len(events) - 1 or ends[0] <= starts[0]:
        raise RuntimeError('Unique ordered final completed turn required')
    recovered = []
    for i, event in enumerate(events):
        if event.get('type') == 'turn.failed':
            raise RuntimeError('Native terminal failure')
        if event.get('type') == 'error':
            if event.get('message') != RECOVERABLE_MESSAGE or not starts[0] < i < ends[0]:
                raise RuntimeError('Unknown or unrecovered native error')
            subsequent = events[i + 1:ends[0]]
            if not any(e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'agent_message'
                       and str(e['item'].get('text', '')).strip() for e in subsequent):
                raise RuntimeError('Recovered notification lacks subsequent final content')
            recovered.append({'event_index': i, 'classification': 'connection_notification_recovered_before_completed_turn'})
    return recovered


def verify(directory, stdout, stderr, home, sandbox):
    events = [json.loads(line) for line in stdout.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = {e['thread_id'] for e in events if e.get('type') == 'thread.started'}
    if len(ids) != 1 or sum(e.get('type') == 'thread.started' for e in events) != 1:
        raise RuntimeError('Unique native session required')
    recovered = classify_events(events)
    session_id = next(iter(ids))
    matches = list((home / 'sessions').rglob('*' + session_id + '.jsonl'))
    if len(matches) != 1:
        raise RuntimeError('Unique native session metadata missing')
    records = [json.loads(line) for line in matches[0].read_text(encoding='utf-8').splitlines() if line.strip()]
    metadata = [r['payload'] for r in records if r.get('type') == 'session_meta']
    contexts = [r['payload'] for r in records if r.get('type') == 'turn_context']
    if len(metadata) != 1 or metadata[0].get('id') != session_id or not contexts:
        raise RuntimeError('Actual model/permission metadata unavailable')
    for context in contexts:
        validate_context(metadata[0], context, directory, sandbox)
    worlds = [r['payload'].get('state', {}).get('permissions', {}) for r in records if r.get('type') == 'world_state']
    if not worlds or any(p.get('approved_command_prefixes') != [] for p in worlds):
        raise RuntimeError('Unexpected or missing command-grant evidence')
    diagnostics = stderr.read_text(encoding='utf-8') + '\n' + '\n'.join(
        str(e.get('item', {}).get('aggregated_output', '')) for e in events)
    if any(mark in diagnostics for mark in ('Automatic approval review failed', 'blocked by policy',
                                            'helper_unknown_error: setup refresh had errors')):
        raise RuntimeError('Native security/setup failure')
    completions = [r for r in records if r.get('type') == 'event_msg'
                   and r.get('payload', {}).get('type') == 'task_complete']
    if len(completions) != 1 or not str(completions[0]['payload'].get('last_agent_message', '')).strip():
        raise RuntimeError('Durable native task completion missing')
    return {'schema': 'dab_native_meta_audit_v3', 'model': 'gpt-5.5',
        'model_provider': metadata[0]['model_provider'], 'provider_metadata_location': 'session_meta',
        'sandbox': sandbox, 'network': 'restricted', 'approval_policy': 'on-request',
        'approvals_reviewer': 'auto_review', 'session_id': session_id,
        'session_path': str(matches[0]), 'session_sha256': sha(matches[0]),
        'events_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
        'completed_turn_count': 1, 'approved_prefix_count': 0,
        'recovered_connection_notifications': recovered,
        'historical_errors_preserved': True, 'new_model_requests': 0,
        'provider_transport_replay_status': 'UNKNOWN; CLI reconnect notification alone does not prove request replay',
        'original_permission_validator_unchanged': True}
