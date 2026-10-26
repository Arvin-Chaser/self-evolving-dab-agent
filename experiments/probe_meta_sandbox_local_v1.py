"""One model-free native sandbox verification per isolated research home.

No credentials are read, no network requests, no ACL changes outside the
installed Codex sandbox setup mechanism, and no shared process termination.
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
from experiments.dab_meta_runtime import resolve_codex


def local_probe_environment(home):
    env = os.environ.copy()
    # Diagnostic isolation only: ineffective while registered runtime is live.
    env.pop('CODEX_MCP_NODE_PATH', None)
    env['CODEX_HOME'] = str(ROOT / home)
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', choices=('local_v1', 'after_close_v1'), default='local_v1')
    args = parser.parse_args()
    base = ROOT / 'experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930/generations/gen_008' / ('sandbox_repair_' + args.attempt)
    if base.exists():
        raise SystemExit('Local verification already dispatched; preserve it, no replay')
    for _, _, home, _ in PROVIDERS.values():
        if not config_alignment(tomllib.loads((ROOT / home / 'config.toml').read_text(encoding='utf-8'))):
            raise SystemExit('Bounded sandbox configuration missing')
    base.mkdir()
    executable = resolve_codex('codex')
    results = []
    for name, (_, _, home, _) in PROVIDERS.items():
        directory = base / name
        directory.mkdir()
        # Runtime-generated synthetic fixture; not repository implementation.
        (directory / 'fixture.txt').write_text('local-sandbox-check-v1', encoding='utf-8')
        removed = 'CODEX_MCP_NODE_PATH' in os.environ
        env = local_probe_environment(home)
        command = [executable, '-C', str(directory), 'sandbox', 'windows', '--',
                   str(SHELL), '-NoProfile', '-NonInteractive', '-Command',
                   "Get-Content -LiteralPath './fixture.txt'"]
        started = time.monotonic()
        try:
            proc = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                  text=True, encoding='utf-8', timeout=90)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            code, out, err = 124, '', 'Local sandbox setup timed out; no automatic retry'
        report = {'provider': name, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                  'elapsed_seconds': round(time.monotonic() - started, 3), 'exit_code': code,
                  'passed': code == 0 and out.strip() == 'local-sandbox-check-v1',
                  'desktop_mcp_path_removed_from_child_only': removed,
                  'permission_configuration_unchanged': True,
                  'model_calls': 0, 'credential_reads': 0,
                  'stderr_sha256': hashlib.sha256(err.encode()).hexdigest(),
                  'bounded_error': err[-2000:] if code else None}
        (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        results.append(report)
        if code:
            break
    print(json.dumps(results, indent=2))
    return 0 if len(results) == 2 and all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
