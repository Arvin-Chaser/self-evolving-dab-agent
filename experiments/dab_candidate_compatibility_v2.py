"""Versioned candidate compatibility gate; frozen original harnesses unchanged."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
H = Path('C:/Users/34934/.codex/visualizations/2026/09/02/01a060f2-55f4-7c02-b876-da90418d29b9')
CHECKER = ROOT / 'experiments/check_dab_candidate_recovery_revision.py'
DELIVERY = H / 'verify_checkpoint_note_delivery.py'
WORKER = ROOT / 'experiments/audit_gen008_candidate_compatibility_v1.py'
FROZEN_CHECKER = 'ad624c8ef7625d73993d68e5bd4c4ed38aa91775189b8bd39f871435b113c5e6'
FROZEN_DELIVERY = 'c251f9b951c28746b5c8052037b3a3cf235b79e85828aed80ff7e2aa016c1f5c'
NEW_TEST = 'tests/test_gen008_duplicate_failure_gate.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def protected_changes(repo, manifest):
    return [e['path'] for e in manifest['files']
            if (e['path'].startswith('tests/') or e['path'].startswith('adapters/dab_validator'))
            and (not (repo / e['path']).is_file() or sha(repo / e['path']) != e['sha256'])]


def gate_verdict(report):
    """Do not trust a top-level passed flag without its fixed required evidence."""
    tests = report.get('tests', [])
    expected = {'frozen_wrapper38', 'frozen_delivery6', 'frozen_unit13_and_new_mechanism', 'cli_help'}
    return (report.get('protected_existing_files_changed') == []
        and report.get('source_unchanged') is True
        and report.get('model_calls') == 0 and report.get('database_calls') == 0
        and len(tests) == len(expected) and {t.get('name') for t in tests} == expected
        and all(t.get('passed') is True and t.get('returncode') == 0 for t in tests))


def audit(workspace, output, python=sys.executable):
    from experiments.intent_candidate_workspace import source_tree_hash
    from datetime import datetime, timezone
    workspace, output = Path(workspace), Path(output)
    output.mkdir(exist_ok=False)
    repo = workspace / 'repo'
    manifest = read(workspace / 'workspace_manifest.json')
    parent = Path(manifest['source_root'])
    if source_tree_hash(parent) != manifest['parent_source_sha256']:
        raise RuntimeError('Frozen selected parent changed')
    if sha(CHECKER) != FROZEN_CHECKER or sha(DELIVERY) != FROZEN_DELIVERY:
        raise RuntimeError('Trusted compatibility harness bytes changed')
    baseline = {e['path']: e['sha256'] for e in manifest['files']}
    original_test = parent / 'tests/test_dab_turn_checkpoint_recovery.py'
    if sha(original_test) != baseline['tests/test_dab_turn_checkpoint_recovery.py']:
        raise RuntimeError('Frozen parent test changed')
    before = source_tree_hash(repo)
    protected = protected_changes(repo, manifest)
    bindings = {str(p): sha(p) for p in (CHECKER, DELIVERY, WORKER, original_test,
        workspace / 'workspace_manifest.json', workspace / 'context/sealed_intent.json')}
    temp = output / 'temporary'
    temp.mkdir()
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'CRS_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY'):
        env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    tests = []
    def check(name, argv, expected_json=None):
        out, err = output / (name + '.stdout'), output / (name + '.stderr')
        with out.open('x', encoding='utf-8') as stdout, err.open('x', encoding='utf-8') as stderr:
            result = subprocess.run([str(python), *map(str, argv)], cwd=repo, env=env,
                                    stdout=stdout, stderr=stderr, timeout=120, check=False)
        verdict = result.returncode == 0
        payload = None
        if expected_json:
            try:
                payload = json.loads(out.read_text(encoding='utf-8'))
                verdict = verdict and payload.get('passed') is True and len(payload.get('checks', [])) == expected_json
            except ValueError:
                verdict = False
        tests.append({'name': name, 'returncode': result.returncode, 'passed': verdict,
            'stdout_sha256': sha(out), 'stderr_sha256': sha(err),
            'failures': [e for e in (payload or {}).get('checks', []) if e.get('passed') is not True]})
    check('frozen_wrapper38', [WORKER, '--worker', repo, original_test, CHECKER, temp], 38)
    check('frozen_delivery6', [DELIVERY, repo, CHECKER], 6)
    # Exact frozen modules; require new mechanism tests separately, not rewritten
    # parent expectations. Files are checked byte-for-byte by protected_changes.
    unit_paths = [parent / 'tests' / name for name in (
        'test_dab_turn_checkpoints.py', 'test_dab_turn_checkpoint_recovery.py',
        'test_dab_checkpoint_delivery.py', 'test_dab_artifact_recovery_budget.py')]
    unit_paths.append(repo / NEW_TEST)
    suite = ('import importlib.util,unittest,tempfile,sys;tempfile.tempdir=' + repr(str(temp)) + ';'
        'paths=' + repr([str(p) for p in unit_paths]) + ';modules=[]\n'
        'for i,path in enumerate(paths):\n'
        ' spec=importlib.util.spec_from_file_location("frozen_unit_"+str(i),path);'
        'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);modules.append(m)\n'
        's=[unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules];'
        'counts=[x.countTestCases() for x in s];assert counts[:4]==[5,1,3,4],counts;'
        'assert counts[4]>=1,counts;'
        'r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(s));sys.exit(not r.wasSuccessful())')
    check('frozen_unit13_and_new_mechanism', ['-c', suite])
    check('cli_help', ['experiments/run_dab_tool_agent.py', '--help'])
    report = {'schema': 'dab_candidate_compatibility_v2', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'workspace': str(workspace), 'source_sha256': before,
        'patch_sha256': sha(workspace / 'candidate.patch'), 'bindings': bindings,
        'protected_existing_files_changed': protected, 'tests': tests,
        'source_unchanged': source_tree_hash(repo) == before and all(sha(p) == d for p, d in bindings.items()),
        'model_calls': 0, 'database_calls': 0}
    report['passed'] = gate_verdict(report)
    save_new(output / 'report.json', report)
    return report


def bounded_feedback(report):
    """Synthetic failure names/messages only; never rows, task IDs or raw traces."""
    feedback = {'protected_existing_files_changed': report.get('protected_existing_files_changed', []),
        'failures': [{'name': t['name'], 'returncode': t['returncode'],
            'checks': [{k: str(e.get(k, ''))[:300] for k in ('name', 'error_type', 'error')}
                       for e in t.get('failures', [])[:38]]}
            for t in report.get('tests', []) if not t['passed']]}
    return json.dumps(feedback, ensure_ascii=False, indent=2)
