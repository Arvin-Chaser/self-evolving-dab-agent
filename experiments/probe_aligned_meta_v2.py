"""One synthetic read/patch/verify session per explicitly selected provider.

No research inputs, rule imports, reviewer overrides, remote uploads or replay.
Runtime fixture/log/report generation is confined to a fresh probe directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command

CAMPAIGN = ROOT / 'experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930'
PROBE_ROOT = CAMPAIGN / 'generations/gen_008'
SHELL = Path('C:/Users/34934/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe')
PROVIDERS = {
    'gpt': ('gpt-5.5', 'crs-gpt55-dab', 'configs/crs_gpt55_meta_runtime_v1', 'configs/dab_crs_gpt55_route_v1.json'),
    'deepseek': ('deepseek-flash', 'deepseek-dab', 'configs/deepseek_meta_runtime_v1', 'configs/dab_active_api_route.json'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config_alignment(config):
    return (config.get('sandbox_mode') == 'workspace-write'
            and config.get('default_permissions') == ':workspace'
            and config.get('approval_policy') == 'on-request'
            and config.get('approvals_reviewer') == 'auto_review'
            and config.get('windows', {}).get('sandbox') == 'elevated'
            and config.get('sandbox_workspace_write', {}).get('network_access') is False)


def build_command(executable, directory, model, profile):
    # Put permission switches on exec itself; do not depend on preset defaults.
    return [executable, '--no-daemon', '-C', str(directory), '--profile', profile,
            'exec', '--model', model, '--sandbox', 'workspace-write',
            '-c', 'approval_policy="on-request"', '-c', 'approvals_reviewer="auto_review"',
            '--skip-git-repo-check', '--json',
            '--output-last-message', str(directory / 'final.txt'), '-']


def failure_classification(stderr, items):
    output = '\n'.join(str(i.get('aggregated_output', '')) for i in items)
    combined = stderr + '\n' + output
    if 'helper_unknown_error: setup refresh had errors' in combined:
        return 'windows_sandbox_setup_refresh_failed'
    if 'Automatic approval review failed' in combined:
        return 'automatic_approval_review_failed'
    if 'blocked by policy' in combined:
        return 'execution_policy_denied'
    return None


def runtime_metadata(home, session_id, directory):
    matches = list((home / 'sessions').rglob(f'*{session_id}.jsonl')) if session_id else []
    if len(matches) != 1:
        return {'valid': False, 'reason': 'unique_session_metadata_missing'}
    context = meta = world = None
    for line in matches[0].read_text(encoding='utf-8').splitlines():
        item = json.loads(line)
        if item['type'] == 'turn_context' and context is None:
            context = item['payload']
        elif item['type'] == 'session_meta':
            meta = item['payload']
        elif item['type'] == 'world_state' and world is None:
            world = item['payload'].get('state', {})
    context = context or {}
    meta = meta or {}
    permission = context.get('permission_profile', {})
    entries = permission.get('file_system', {}).get('entries', [])
    writes = [e['path'].get('path') for e in entries
              if e.get('access') == 'write' and e.get('path', {}).get('type') == 'path']
    writable = any(p and Path(p).resolve() == directory.resolve() for p in writes)
    allowed = (world or {}).get('permissions', {}).get('approved_command_prefixes', [])
    return {'valid': bool(writable and context.get('approval_policy') == 'on-request'
                          and context.get('approvals_reviewer') == 'auto_review'
                          and context.get('sandbox_policy', {}).get('type') == 'workspace-write'),
            'cli_version': meta.get('cli_version'), 'model': context.get('model'),
            'model_provider': meta.get('model_provider'),
            'sandbox': context.get('sandbox_policy', {}).get('type'),
            'network': permission.get('network'),
            'approval_policy': context.get('approval_policy'),
            'approvals_reviewer': context.get('approvals_reviewer'),
            'probe_directory_writable': writable,
            'approved_command_prefix_count': len(allowed),
            'session_log_sha256': sha(matches[0])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', required=True, choices=PROVIDERS)
    parser.add_argument('--attempt', choices=('v3', 'v4', 'v5'), default='v3',
                        help='Fresh authorized attempts only; v5 requires both model-free sandbox checks to have passed')
    args = parser.parse_args()
    model, profile, relative_home, route = PROVIDERS[args.provider]
    home = ROOT / relative_home
    directory = PROBE_ROOT / f'integration_alignment_{args.attempt}' / args.provider
    if directory.exists():
        raise SystemExit('Probe already dispatched; no overwrite or automatic replay')
    config_path = home / 'config.toml'
    config = tomllib.loads(config_path.read_text(encoding='utf-8'))
    if not config_alignment(config) or not SHELL.is_file():
        raise SystemExit('Aligned bounded configuration or existing shell missing')
    if args.attempt == 'v5':
        local_refs = {
            'gpt': PROBE_ROOT / 'sandbox_repair_after_close_v2/gpt/report.json',
            'deepseek': PROBE_ROOT / 'sandbox_repair_after_close_v3/deepseek/report.json',
        }
        for local_ref in local_refs.values():
            value = json.loads(local_ref.read_text(encoding='utf-8'))
            if (value.get('passed') is not True or value.get('model_calls') != 0
                    or value.get('managed_requirements_included') is not True
                    or value.get('permission_configuration_unchanged') is not True):
                raise SystemExit('Required unchanged bounded local sandbox success missing')
    os.environ['DAB_RESEARCH_API_CONFIG'] = str(ROOT / route)
    # Preflight authenticates only to this provider, never outputs credentials.
    environment = meta_environment(profile)
    environment['PYTHONIOENCODING'] = 'utf-8'
    executable = resolve_codex('codex')
    directory.mkdir(parents=True, exist_ok=False)
    token = secrets.token_hex(16)
    fixture = directory / 'synthetic_fixture.txt'
    fixture.write_text(token, encoding='utf-8')
    fixture_hash = sha(fixture)
    command = build_command(executable, directory, model, profile)
    intent = {'schema': f'aligned_meta_probe_dispatch_{args.attempt}', 'provider': args.provider,
              'model': model, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'retry_authority': ('修复吧，怎么一直出问题; align and test both providers after local sandbox repair'
                                  if args.attempt == 'v5' else '重试一下' if args.attempt == 'v4' else None),
              'automatic_retry': False, 'config_sha256': sha(config_path),
              'profile_sha256': sha(home / f'{profile}.config.toml'),
              'executable_sha256': sha(executable), 'command': command,
              'research_stage_launched': False, 'imported_command_rules': False}
    with (directory / 'dispatch_intent.json').open('x', encoding='utf-8') as stream:
        json.dump(intent, stream, indent=2)
    prompt = (
        'This is ONE synthetic integration test, NOT research evolution. '
        'Use the available shell tool to read ONLY synthetic_fixture.txt in the current directory. '
        f'Use shell {SHELL.as_posix()} when the shell tool accepts a shell option. '
        'Use apply_patch to create ONLY synthetic_result.txt containing that exact token plus one newline. '
        'If apply_patch is exposed only through the Codex executable, use its standard apply-patch entry point. '
        'Then use the shell tool to verify the result file. Reply only JSON {"status":"ok"}. '
        'The token is unknown to you; actually use tools. Do not read any other file, environment, '
        'credential, repository, benchmark, history or network. Do not invoke other agents. '
        'Do not request expanded permissions. If any action is denied, stop immediately and report denial; '
        'do not switch commands or tools to get around the denial. '
        'A process-start or sandbox-setup failure also requires immediate stop: do not retry it.')
    started = time.monotonic()
    try:
        proc = run_logged_command(command, cwd=directory, prompt=prompt,
                                  stdout_path=directory / 'events.jsonl',
                                  stderr_path=directory / 'stderr.txt',
                                  env=environment, timeout=300)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124
    event_lines = (directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    events = [json.loads(line) for line in event_lines if line.strip()]
    session_id = next((e.get('thread_id') for e in events if e.get('type') == 'thread.started'), None)
    metadata = runtime_metadata(home, session_id, directory)
    items = [e.get('item', {}) for e in events if e.get('type') == 'item.completed']
    successful_commands = sum(i.get('type') == 'command_execution' and i.get('exit_code') == 0 for i in items)
    edits = sum(i.get('type') == 'file_change' and i.get('status') == 'completed' for i in items)
    result = directory / 'synthetic_result.txt'
    result_exact = result.is_file() and result.read_text(encoding='utf-8') == token + '\n'
    final = directory / 'final.txt'
    try:
        final_ok = json.loads(final.read_text(encoding='utf-8')) == {'status': 'ok'}
    except (OSError, json.JSONDecodeError):
        final_ok = False
    stderr = (directory / 'stderr.txt').read_text(encoding='utf-8')
    denial = 'Automatic approval review failed' in stderr or 'blocked by policy' in stderr
    report = {'schema': f'aligned_meta_read_patch_verify_report_{args.attempt}', 'provider': args.provider,
              'model': model, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': round(time.monotonic() - started, 3), 'exit_code': exit_code,
              'runtime': metadata, 'successful_command_count': successful_commands,
              'completed_file_change_count': edits, 'fixture_unchanged': sha(fixture) == fixture_hash,
              'failure_classification': failure_classification(stderr, items),
              'failed_command_count': sum(i.get('type') == 'command_execution' and i.get('exit_code') != 0 for i in items),
              'result_exact': result_exact, 'final_status_ok': final_ok,
              'review_failure_or_policy_denial': denial,
              'reviewer_403_observed': denial and '403 Forbidden' in stderr,
              'stderr_sha256': sha(directory / 'stderr.txt'),
              'events_sha256': sha(directory / 'events.jsonl'),
              'dispatch_intent_sha256': sha(directory / 'dispatch_intent.json'),
              'automatic_replay': False, 'research_stage_launched': False}
    report['passed'] = (exit_code == 0 and metadata['valid'] and successful_commands >= 2
                        and result_exact and report['fixture_unchanged'] and final_ok and not denial
                        and report['failure_classification'] is None)
    with (directory / 'report.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
