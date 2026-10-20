"""Read native CLI metadata from its actual event locations; fail closed."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_context(meta, context, directory, sandbox):
    # Provider is a session_meta field. Some versions repeat it in turn_context.
    # Never accept a missing session binding or a conflicting duplicate field.
    if meta.get('model_provider') != 'dab_crs_gpt55':
        raise RuntimeError('Native session provider mismatch or missing')
    if context.get('model_provider') not in (None, 'dab_crs_gpt55'):
        raise RuntimeError('Conflicting turn provider')
    if (context.get('model') != 'gpt-5.5'
            or Path(context.get('cwd', '')).resolve() != directory.resolve()
            or context.get('approval_policy') != 'on-request'
            or context.get('approvals_reviewer') != 'auto_review'
            or context.get('sandbox_policy', {}).get('type') != sandbox
            or context.get('permission_profile', {}).get('network') != 'restricted'):
        raise RuntimeError('Actual model or bounded permission binding mismatch')
    entries = context.get('permission_profile', {}).get('file_system', {}).get('entries', [])
    if not entries or any(e.get('access') not in ('read', 'write') for e in entries):
        raise RuntimeError('Filesystem permission metadata missing or unknown')
    if sandbox == 'read-only' and any(e.get('access') == 'write' for e in entries):
        raise RuntimeError('Selector unexpectedly writable')
    if sandbox == 'workspace-write' and not any(
        e.get('access') == 'write' and e.get('path', {}).get('type') == 'path'
        and Path(e['path']['path']).resolve() == directory.resolve() for e in entries):
        raise RuntimeError('Candidate workspace write binding missing')


def verify(directory, stdout, stderr, home, sandbox):
    events = [json.loads(line) for line in stdout.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = {e['thread_id'] for e in events if e.get('type') == 'thread.started'}
    if len(ids) != 1 or not any(e.get('type') == 'turn.completed' for e in events):
        raise RuntimeError('Unique completed native Meta session missing')
    session_id = next(iter(ids))
    matches = list((home / 'sessions').rglob('*' + session_id + '.jsonl'))
    if len(matches) != 1:
        raise RuntimeError('Unique native session metadata missing')
    records = [json.loads(line) for line in matches[0].read_text(encoding='utf-8').splitlines() if line.strip()]
    metadata = [r['payload'] for r in records if r.get('type') == 'session_meta']
    contexts = [r['payload'] for r in records if r.get('type') == 'turn_context']
    if len(metadata) != 1 or metadata[0].get('id') != session_id or not contexts:
        raise RuntimeError('Actual session/model/permissions not observable')
    for context in contexts:
        validate_context(metadata[0], context, directory, sandbox)
    worlds = [r['payload'].get('state', {}).get('permissions', {})
              for r in records if r.get('type') == 'world_state']
    if not worlds or any(p.get('approved_command_prefixes') != [] for p in worlds):
        raise RuntimeError('Unexpected or missing native command-grant evidence')
    diagnostics = stderr.read_text(encoding='utf-8') + '\n' + '\n'.join(
        str(e.get('item', {}).get('aggregated_output', '')) for e in events)
    if any(mark in diagnostics for mark in ('Automatic approval review failed', 'blocked by policy',
                                            'helper_unknown_error: setup refresh had errors')):
        raise RuntimeError('Native security/setup failure; no admission or replay')
    if any(e.get('type') in ('error', 'turn.failed') for e in events):
        raise RuntimeError('Native terminal error')
    return {'model': 'gpt-5.5', 'model_provider': metadata[0]['model_provider'],
        'provider_metadata_location': 'session_meta', 'sandbox': sandbox,
        'network': 'restricted', 'approval_policy': 'on-request', 'approvals_reviewer': 'auto_review',
        'session_id': session_id, 'session_path': str(matches[0]), 'session_sha256': sha(matches[0]),
        'events_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
        'completed_turn_count': sum(e.get('type') == 'turn.completed' for e in events),
        'approved_prefix_count': 0}
