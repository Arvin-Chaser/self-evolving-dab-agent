"""Gen11 native Meta audit with source-output-safe security diagnostics.

The v4 audit is retained unchanged as historical evidence.  Successful shell
output may contain quoted source code, including the audit's own error strings;
it is not itself a security denial.  Actual stderr, error events, and failed
command output remain fail-closed, and every failed command still blocks
admission independently of its text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_native_meta_audit_v4 import validate_context


SECURITY_MARKERS = (
    'Automatic approval review failed',
    'blocked by policy',
    'helper_unknown_error: setup refresh had errors',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def security_setup_failure(events, stderr_text):
    """Inspect actual error channels, not successful commands displaying text."""
    diagnostics = [stderr_text]
    for event in events:
        item = event.get('item', {})
        if event.get('type') in ('error', 'turn.failed'):
            diagnostics.append(str(event.get('message', '')))
        if item.get('type') == 'error':
            diagnostics.append(str(item.get('message', '')))
        if item.get('type') == 'command_execution' and event.get('type') == 'item.completed':
            if item.get('exit_code') != 0 or item.get('status') == 'failed':
                diagnostics.append(str(item.get('aggregated_output', '')))
    return any(marker in value for value in diagnostics for marker in SECURITY_MARKERS)


def failed_native_command(events):
    return any(event.get('type') == 'item.completed'
               and event.get('item', {}).get('type') == 'command_execution'
               and event['item'].get('exit_code') != 0 for event in events)


def verify(directory, stdout, stderr, home, sandbox):
    events = [json.loads(line) for line in stdout.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = {event['thread_id'] for event in events if event.get('type') == 'thread.started'}
    starts = [i for i, event in enumerate(events) if event.get('type') == 'turn.started']
    ends = [i for i, event in enumerate(events) if event.get('type') == 'turn.completed']
    if (len(ids) != 1 or sum(event.get('type') == 'thread.started' for event in events) != 1
            or len(starts) != 1 or len(ends) != 1 or ends[0] != len(events) - 1
            or starts[0] >= ends[0]):
        raise RuntimeError('Unique completed native Meta session missing')
    session_id = next(iter(ids))
    matches = list((home / 'sessions').rglob('*' + session_id + '.jsonl'))
    if len(matches) != 1:
        raise RuntimeError('Unique native session metadata missing')
    records = [json.loads(line) for line in matches[0].read_text(encoding='utf-8').splitlines() if line.strip()]
    metadata = [record['payload'] for record in records if record.get('type') == 'session_meta']
    contexts = [record['payload'] for record in records if record.get('type') == 'turn_context']
    if len(metadata) != 1 or metadata[0].get('id') != session_id or not contexts:
        raise RuntimeError('Actual session/model/permissions not observable')
    for context in contexts:
        validate_context(metadata[0], context, directory, sandbox)
    worlds = [record['payload'].get('state', {}).get('permissions', {})
              for record in records if record.get('type') == 'world_state']
    if not worlds or any(permissions.get('approved_command_prefixes') != [] for permissions in worlds):
        raise RuntimeError('Unexpected or missing native command-grant evidence')
    if security_setup_failure(events, stderr.read_text(encoding='utf-8')):
        raise RuntimeError('Native security/setup failure; no admission or replay')
    if any(event.get('type') in ('error', 'turn.failed') for event in events):
        raise RuntimeError('Native terminal error')
    completions = [record for record in records if record.get('type') == 'event_msg'
                   and record.get('payload', {}).get('type') == 'task_complete']
    if len(completions) != 1 or not str(completions[0]['payload'].get('last_agent_message', '')).strip():
        raise RuntimeError('Durable native task completion missing')
    if failed_native_command(events):
        raise RuntimeError('Failed native command; no admission')
    return {'model': 'deepseek-flash', 'model_provider': metadata[0]['model_provider'],
            'provider_metadata_location': 'session_meta', 'sandbox': sandbox,
            'network': 'restricted', 'approval_policy': 'on-request',
            'approvals_reviewer': 'auto_review', 'session_id': session_id,
            'session_path': str(matches[0]), 'session_sha256': sha(matches[0]),
            'events_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'completed_turn_count': sum(event.get('type') == 'turn.completed' for event in events),
            'approved_prefix_count': 0, 'audit_schema': 'dab_native_meta_audit_v5'}
