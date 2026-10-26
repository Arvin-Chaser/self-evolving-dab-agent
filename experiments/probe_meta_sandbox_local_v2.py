"""Model-free Windows sandbox check using the installed CLI's flat grammar.

Do not repeat v1 dispatches. Explicit workspace profile and managed requirements
remain in force. No model/key access, policy bypass or shared process shutdown.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.probe_aligned_meta_v2 import PROVIDERS, SHELL, config_alignment
from experiments.probe_meta_sandbox_local_v1 import local_probe_environment
from experiments.dab_meta_runtime import resolve_codex


def build_sandbox_command(executable, directory):
    # Local 0.162.0-alpha.2 help: codex sandbox [OPTIONS] [COMMAND]...
    # "windows" is NOT a subcommand on this installation.
    return [executable, 'sandbox', '-P', ':workspace', '--include-managed-config',
            '-C', str(directory), '--', str(SHELL), '-NoProfile', '-NonInteractive',
            '-Command', "Get-Content -LiteralPath './fixture.txt'"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', required=True, choices=('local_v2', 'after_close_v2', 'after_close_v3'))
    parser.add_argument('--provider', choices=('gpt', 'deepseek', 'both'), default='both')
    args = parser.parse_args()
    base = ROOT / 'experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930/generations/gen_008' / ('sandbox_repair_' + args.attempt)
    if base.exists():
        raise SystemExit('Already dispatched; preserve evidence, no automatic replay')
    if not SHELL.is_file():
        raise SystemExit('Installed shell executable missing; no fallback')
    selected = {name: value for name, value in PROVIDERS.items()
                if args.provider in ('both', name)}
    for _, _, home, _ in selected.values():
        if not config_alignment(tomllib.loads((ROOT / home / 'config.toml').read_text(encoding='utf-8'))):
            raise SystemExit('Bounded sandbox configuration missing')
    executable = resolve_codex('codex')
    # Validate actual installed grammar before creating a dispatch directory.
    help_result = subprocess.run([executable, 'sandbox', '--help'], capture_output=True,
                                 text=True, encoding='utf-8', timeout=15)
    help_text = help_result.stdout
    if help_result.returncode or 'Usage: codex sandbox [OPTIONS] [COMMAND]...' not in help_text or '--include-managed-config' not in help_text:
        raise SystemExit('Installed CLI grammar differs; stop without launch')
    base.mkdir()
    results = []
    for name, (_, _, home, _) in selected.items():
        directory = base / name
        directory.mkdir()
        (directory / 'fixture.txt').write_text('local-sandbox-check-v2', encoding='utf-8')
        env = local_probe_environment(home)
        command = build_sandbox_command(executable, directory)
        intent = {'schema': 'native_sandbox_model_free_v2', 'command': command,
                  'config_sha256': hashlib.sha256((ROOT / home / 'config.toml').read_bytes()).hexdigest(),
                  'installed_help_sha256': hashlib.sha256(help_text.encode()).hexdigest(),
                  'model_calls': 0, 'managed_requirements_included': True,
                  'automatic_replay': False}
        (directory / 'dispatch_intent.json').write_text(json.dumps(intent, indent=2), encoding='utf-8')
        started = time.monotonic()
        try:
            proc = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                  text=True, encoding='utf-8', timeout=90)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            code, out, err = 124, '', 'Local check timed out; no automatic retry'
        report = {'schema': 'native_sandbox_model_free_v2', 'provider': name,
                  'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                  'elapsed_seconds': round(time.monotonic() - started, 3), 'exit_code': code,
                  'passed': code == 0 and out.strip() == 'local-sandbox-check-v2',
                  'permission_configuration_unchanged': True, 'managed_requirements_included': True,
                  'model_calls': 0, 'credential_reads': 0,
                  'stderr_sha256': hashlib.sha256(err.encode()).hexdigest(),
                  'bounded_error': err[-2000:] if code else None}
        (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        results.append(report)
        if code:
            break
    print(json.dumps(results, indent=2))
    return 0 if len(results) == len(selected) and all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
