"""Bind child Meta tool paths, without inheriting a particular terminal setup."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path


def bind_environment(environment, bindings):
    """Validate exact executables before exposing their directories on PATH.

    This only binds tools. It grants no permissions, network access or command
    approvals, and never examines credentials or changes the system PATH.
    """
    if set(bindings) != {'python', 'codex', 'powershell'}:
        raise RuntimeError('Expected exactly Python, Codex and PowerShell tool bindings')
    directories = []
    expected_names = {'python': 'python.exe', 'codex': 'codex.exe', 'powershell': 'pwsh.exe'}
    for name, entry in bindings.items():
        path = Path(entry['path'])
        if not path.is_absolute() or path.name.lower() != expected_names[name] or not path.is_file():
            raise RuntimeError('Bound tool unavailable: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError('Bound tool changed: ' + name)
        directory = str(path.parent)
        if directory not in directories:
            directories.append(directory)
    result = dict(environment)
    # Windows PATH keys are case-insensitive; remove duplicates before binding.
    prior_path = next((v for k, v in result.items() if k.casefold() == 'path'), '')
    for key in list(result):
        if key.casefold() == 'path':
            del result[key]
    result['PATH'] = os.pathsep.join(directories + ([prior_path] if prior_path else []))
    result.pop('PYTHONPATH', None)
    return result
