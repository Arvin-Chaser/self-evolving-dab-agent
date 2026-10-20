"""Single Gen8 entry point, currently stopped at the independent source gate.

This is NOT yet an end-to-end evaluation launcher. The current candidate fails
the source gate and no audited GPT Data runtime has been prepared. A readiness
report makes that limitation explicit; no placeholder stage silently succeeds.
Existing selector/coding sessions and failed audits must never be replayed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import audit_gen008_candidate_compatibility_v1 as compatibility
from experiments import run_gen008_gpt55_meta_once_v1 as prior
from experiments import dab_native_meta_audit_v2 as native
from experiments.intent_candidate_workspace import source_tree_hash
from experiments.dab_bound_meta_tools_v1 import bind_environment

OUTPUT = compatibility.OUTPUT


def validate_cached_audit(audit):
    """Reuse only a complete exact-bound report, including failed reports."""
    ref = compatibility.read(prior.GEN / 'candidate_ref.json')
    if (audit.get('schema') != 'gen008_independent_candidate_compatibility_v1'
            or audit.get('candidate_ref_sha256') != compatibility.sha(prior.GEN / 'candidate_ref.json')
            or audit.get('source_sha256') != ref['source_tree_sha256']
            or source_tree_hash(Path(ref['repo'])) != ref['source_tree_sha256']
            or audit.get('expected_wrapper_checks') != 38
            or audit.get('observed_checks') != 38
            or audit.get('model_calls') != 0 or audit.get('database_calls') != 0
            or audit.get('candidate_modified') is not False):
        raise RuntimeError('Cached source audit binding incomplete or changed')
    for path, digest in audit['bindings'].items():
        if compatibility.sha(path) != digest:
            raise RuntimeError('Cached audit dependency changed')
    for name in ('stdout', 'stderr'):
        if compatibility.sha(OUTPUT / ('compatibility.' + name)) != audit[name + '_sha256']:
            raise RuntimeError('Cached audit diagnostic bytes changed')
    checks = audit['wrapper_report']['checks']
    expected_pass = (not audit['protected_existing_files_changed']
                     and audit['returncode'] == 0 and audit['wrapper_report']['passed'] is True
                     and all(c.get('passed') is True for c in checks)
                     and audit['source_and_bindings_unchanged'] is True)
    if audit['passed'] is not expected_pass:
        raise RuntimeError('Cached audit verdict conflicts with evidence')
    return audit


def inspect_readiness():
    # Does not read keys, contact models, inspect remote traces or launch tasks.
    state = compatibility.read(prior.CAMPAIGN / 'campaign_state.json')
    if state.get('stage') != 'candidate_admitted' or state.get('next_generation') != 8:
        raise RuntimeError('Expected admitted Gen8 stage changed; no automatic resume')
    if Path(state.get('active_candidate_ref', '')).resolve() != (prior.GEN / 'candidate_ref.json').resolve():
        raise RuntimeError('Active candidate changed')
    tools = {name: {'path': str(path), 'sha256': compatibility.sha(path)}
             for name, path in (('python', prior.PYTHON), ('codex', prior.CODEX), ('powershell', prior.NATIVE))}
    bind_environment({}, tools)
    coding = prior.GEN / 'coding_continuation_v1/terminal_report.json'
    if compatibility.read(coding).get('passed') is not True:
        raise RuntimeError('Completed coding evidence missing')
    # Native audit is local read-only metadata verification, not another session.
    repo = Path(compatibility.read(prior.GEN / 'candidate_ref.json')['repo'])
    actual = native.verify(repo, repo.parent / 'generation_0.stdout',
                           repo.parent / 'generation_0.stderr', prior.HOME, 'workspace-write')
    audit_path = OUTPUT / 'candidate_compatibility_audit.json'
    if not audit_path.exists():
        compatibility.audit()
    audit = validate_cached_audit(compatibility.read(audit_path))
    failures = audit['failed_checks']
    blockers = []
    if not audit['passed']:
        blockers.append({'stage': 'candidate_compatibility',
            'reason': 'Frozen original tests fail or existing protected tests changed',
            'evidence': str(audit_path), 'failed_checks': len(failures),
            'protected_existing_files_changed': audit['protected_existing_files_changed']})
    # Explicitly pending, not implemented hooks pretending to be successful.
    blockers.append({'stage': 'fresh_gpt_data_runtime',
        'reason': 'Candidate-specific Responses runtime, server staging and terminal audit are not yet built/verified'})
    return {'schema': 'gen008_continuous_cycle_readiness_v1',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'ready_for_end_to_end_run': False,
        'generation': 8, 'model': 'gpt-5.5', 'workers': 4, 'max_iterations': 0,
        'existing_selector_replayed': False, 'existing_coding_replayed': False,
        'coding_native_runtime': actual, 'tool_bindings': tools,
        'candidate_compatibility_passed': audit['passed'], 'blockers': blockers,
        'planned_stages': ['reuse_verified_intent_and_candidate', 'candidate_compatibility',
            'fresh_runtime_local_and_remote_audits', 'exclusive_single_evaluation_dispatch',
            'wait_30_minutes_between_end_state_checks', 'terminal_state_and_result_audit',
            'temporary_credential_cleanup', 'original_record_result',
            'independent_gpt_review_and_native_audit', 'original_graph_append_and_verify'],
        'new_model_calls': 0, 'credential_reads': 0, 'remote_commands': 0,
        'formal_evaluation_started': False, 'gen9_started': False,
        'automatic_retry': False, 'permissions_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', required=True,
                        help='Model-free readiness check; no formal run is currently available')
    parser.parse_args()
    report = inspect_readiness()
    path = OUTPUT / 'readiness_report_v1.json'
    if not path.exists():
        compatibility.new_json(path, report)
    print(json.dumps({'ready': report['ready_for_end_to_end_run'],
        'blockers': report['blockers'], 'report': str(path),
        'new_model_calls': 0, 'formal_evaluation_started': False}, ensure_ascii=False, indent=2))
    return 0 if report['ready_for_end_to_end_run'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
