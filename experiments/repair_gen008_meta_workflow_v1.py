"""Same-intent independent Meta repair -> frozen compatibility -> retry admission.

This repairs only Gen8. No selector replay, benchmark access, evaluation launch,
automatic transport replay, permissions change, or new-generation dispatch.
Each deliberate source repair gets a fresh immutable workspace and dispatch.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as workspace
from experiments import run_gen008_gpt55_meta_once_v1 as prior
from experiments import dab_native_meta_audit_v2 as native
from experiments import dab_candidate_compatibility_v2 as compatibility
from experiments.dab_bound_meta_tools_v1 import bind_environment
from experiments.dab_meta_runtime import meta_environment, run_logged_command

RUN = prior.GEN / 'meta_repair_workflow_v1'
FAILED_AUDIT = prior.GEN / 'continuous_cycle_v1/candidate_compatibility_audit.json'
FAILED_REF = prior.GEN / 'candidate_ref.json'
MAX_REPAIR_SESSIONS = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    compatibility.save_new(path, value)


def validate_retry(state, intent, manifest, admission, audit, failure):
    """Original source admission/bindings PLUS frozen compatibility, no bypass."""
    if state.get('stage') != 'candidate_admitted' or state.get('next_generation') != 8:
        raise RuntimeError('Not the exact Gen8 implementation retry stage')
    if failure.get('passed') is not False:
        raise RuntimeError('Missing archived failed compatibility evidence')
    if intent.get('generation') != 8 or workspace.canonical_hash(intent) != intent.get('canonical_json_sha256'):
        raise RuntimeError('Sealed Gen8 intent changed')
    edges = intent['parent_selection']['parents']
    bases = [e['node_id'] for e in edges if e['role'] == 'code_base']
    if bases != [intent['code_parent_node_id']] or intent['parent_selection']['materialization_base_node_id'] != bases[0]:
        raise RuntimeError('Exactly one unchanged Meta-selected materialization base required')
    if manifest.get('intent_canonical_sha256') != intent['canonical_json_sha256']:
        raise RuntimeError('Candidate intent binding mismatch')
    if manifest.get('parent_source_sha256') != intent['code_parent_hash']:
        raise RuntimeError('Candidate parent binding mismatch')
    if (admission.get('status') != 'source_preflight_passed'
            or admission.get('claim_to_source_valid') is not True
            or admission.get('failures') or admission.get('forbidden_files')
            or admission.get('formal_dab_evaluation_run') is not False):
        raise RuntimeError('Original source preflight did not pass')
    if (audit.get('schema') != 'dab_candidate_compatibility_v2'
            or audit.get('passed') is not True or not compatibility.gate_verdict(audit)
            or audit.get('patch_sha256') != admission.get('patch_sha256')):
        raise RuntimeError('Independent frozen compatibility or patch binding failed')


def assert_plan(plan):
    for path, digest in plan['bindings'].items():
        if sha(path) != digest:
            raise RuntimeError('Prepared repair binding changed: ' + Path(path).name)
    failed = protocol.read_json(FAILED_REF)
    if workspace.source_tree_hash(Path(failed['repo'])) != failed['source_tree_sha256']:
        raise RuntimeError('Original failed candidate changed')
    if workspace.source_tree_hash(Path(plan['parent_repo'])) != plan['parent_source_sha256']:
        raise RuntimeError('Selected Meta parent changed')
    state = protocol.read_json(prior.CAMPAIGN / 'campaign_state.json')
    if (state.get('stage') != 'candidate_admitted' or state.get('next_generation') != 8
            or Path(state.get('active_candidate_ref', '')).resolve() != FAILED_REF.resolve()
            or Path(state.get('active_intent', '')).resolve() != (prior.GEN / 'sealed_intent.json').resolve()):
        raise RuntimeError('Active state changed; no automatic resume')


def prepare():
    """Model/credential/network-free task preparation, existing failure reused."""
    if RUN.exists():
        raise RuntimeError('Repair plan exists; preserve it, no duplicate preparation')
    os.environ['DAB_RESEARCH_API_CONFIG'] = str(prior.ROUTE)
    prior.assert_config()
    state = prior.assert_stage('candidate_admitted')
    if Path(state['active_candidate_ref']).resolve() != FAILED_REF.resolve():
        raise RuntimeError('Unexpected active Gen8 candidate')
    # Verify the existing audit without repeating unchanged synthetic tests.
    from experiments.run_gen008_continuous_cycle_v1 import validate_cached_audit
    failure = validate_cached_audit(protocol.read_json(FAILED_AUDIT))
    if failure['passed'] is not False:
        raise RuntimeError('No candidate compatibility failure to repair')
    ref = protocol.read_json(FAILED_REF)
    old_manifest = protocol.read_json(Path(ref['workspace']) / 'workspace_manifest.json')
    parent = Path(old_manifest['source_root'])
    intent = protocol.read_json(prior.GEN / 'sealed_intent.json')
    if workspace.canonical_hash(intent) != intent['canonical_json_sha256']:
        raise RuntimeError('Original sealed intent hash invalid')
    if workspace.source_tree_hash(parent) != intent['code_parent_hash']:
        raise RuntimeError('Original selected parent changed')
    tools = {name: {'path': str(path), 'sha256': sha(path)} for name, path in (
        ('python', prior.PYTHON), ('codex', prior.CODEX), ('powershell', prior.NATIVE))}
    bind_environment({}, tools)
    dependencies = [Path(__file__), ROOT / 'experiments/dab_candidate_compatibility_v2.py',
        ROOT / 'experiments/dab_bound_meta_tools_v1.py', ROOT / 'experiments/dab_native_meta_audit_v2.py',
        ROOT / 'experiments/dab_meta_runtime.py', ROOT / 'experiments/dab_api_routing.py',
        ROOT / 'experiments/intent_candidate_workspace.py', ROOT / 'experiments/dab_roadmap_protocol.py',
        ROOT / 'experiments/run_gen008_gpt55_meta_once_v1.py',
        ROOT / 'experiments/run_gen008_continuous_cycle_v1.py', compatibility.WORKER,
        compatibility.CHECKER, compatibility.DELIVERY, prior.ROUTE,
        prior.HOME / 'config.toml', prior.HOME / 'crs-gpt55-dab.config.toml',
        prior.GEN / 'sealed_intent.json', FAILED_REF, FAILED_AUDIT,
        prior.CAMPAIGN / 'campaign_state.json', prior.CAMPAIGN / 'campaign.json',
        prior.CAMPAIGN / 'roadmap.jsonl', Path(ref['candidate_patch']),
        Path(ref['workspace']) / 'workspace_manifest.json',
        Path(ref['workspace']) / 'context/upstream_DataAgent.py',
        Path(ref['workspace']) / 'context/selected_parent_evidence.json',
        Path(ref['repo']) / 'candidate_workspace_report.json']
    dependencies.extend(Path(entry['safe_mechanism_detail']) for entry in
        protocol.read_json(Path(ref['workspace']) / 'context/selected_parent_evidence.json').get('safe_detail_access', {}).get('nodes', [])
        if entry.get('status') == 'available')
    bindings = {str(p): sha(p) for p in dependencies}
    RUN.mkdir()
    authority = {'schema': 'gen008_meta_repair_authority_v1', 'recorded_at': now(),
        'human_direction': '嗯，行吧，我们先把meta任务做好然后启动gen8，我觉得没问题',
        'scope': 'Independent GPT-5.5 same-intent same-parent compatibility repair before Gen8 evaluation',
        'maximum_deliberate_repair_sessions': MAX_REPAIR_SESSIONS,
        'transport_retries': 0, 'selector_replay': False, 'gen9_authorized': False,
        'permissions_weakened': False}
    save_new(RUN / 'authority.json', authority)
    bindings[str(RUN / 'authority.json')] = sha(RUN / 'authority.json')
    save_new(RUN / 'plan.json', {'schema': 'gen008_meta_repair_plan_v1', 'prepared_at': now(),
        'bindings': bindings, 'tools': tools, 'model': 'gpt-5.5', 'profile': 'crs-gpt55-dab',
        'reasoning_effort': 'medium', 'intent_sha256': intent['canonical_json_sha256'],
        'parent_repo': str(parent), 'parent_source_sha256': intent['code_parent_hash'],
        'failed_source_sha256': ref['source_tree_sha256'], 'failed_workspace': ref['workspace'],
        'maximum_deliberate_repair_sessions': MAX_REPAIR_SESSIONS,
        'automatic_transport_replay': False, 'formal_evaluation_started': False,
        'next_stage': 'Fresh GPT Data runtime local+remote audits; never unrepaired deploy_evaluation'})
    print(json.dumps({'status': 'same_intent_meta_repair_prepared', 'model_calls': 0,
        'maximum_repair_sessions': MAX_REPAIR_SESSIONS, 'formal_evaluation_started': False}))


def failure_feedback(failure):
    """Allowlist synthetic diagnostics; never send raw formal artifacts to Meta."""
    return json.dumps({'protected_existing_files_changed': failure.get('protected_existing_files_changed', []),
        'failed_checks': [{k: str(c.get(k, ''))[:300] for k in ('name', 'error_type', 'error')}
                          for c in failure.get('failed_checks', [])[:38]]}, ensure_ascii=False, indent=2)


def prepare_attempt(plan, index, seed_workspace, feedback):
    attempt = prior.GEN / f'meta_retry{index:03d}'
    if attempt.exists():
        raise RuntimeError('Repair attempt already exists; no replay')
    old = Path(plan['failed_workspace'])
    with (RUN / f'prepare_{index:03d}.stdout').open('x', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log):
            workspace.prepare(argparse.Namespace(source_root=Path(plan['parent_repo']), output=attempt,
                intent=prior.GEN / 'sealed_intent.json', parent_source=None,
                parent_context=old / 'context/selected_parent_evidence.json',
                upstream_source=old / 'context/upstream_DataAgent.py', mechanism_contract=None))
    # Copy exact independent Meta-produced source bytes, not a manually authored
    # repair. Each attempt's Git baseline remains the SAME selected parent.
    source = Path(seed_workspace) / 'repo'
    baseline_names = {e['path'] for e in workspace.source_tree_manifest(Path(plan['parent_repo']))}
    seed_names = {e['path'] for e in workspace.source_tree_manifest(source)}
    for name in sorted(baseline_names | seed_names):
        target = attempt / 'repo' / name
        origin = source / name
        if origin.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        elif target.exists():
            raise RuntimeError('Seed removed source; preserve original and stop')
    shutil.copy2(source / 'candidate_workspace_report.json', attempt / 'repo/candidate_workspace_report.json')
    if workspace.source_tree_hash(attempt / 'repo') != workspace.source_tree_hash(source):
        raise RuntimeError('New repair workspace is not an exact source copy')
    temp = attempt / 'repo' / '.repair_test_tmp'
    temp.mkdir()
    test = Path(plan['parent_repo']) / 'tests/test_dab_turn_checkpoint_recovery.py'
    command = f'& "{prior.PYTHON}" "{compatibility.WORKER}" --worker "{attempt / "repo"}" "{test}" "{compatibility.CHECKER}" "{temp}"'
    task = (attempt / 'implementation_task.md').read_text(encoding='utf-8')
    task += ('\n\n# Independent compatibility repair of the existing Meta implementation\n\n'
        'The adjacent repo is an EXACT copy of the previous independent Meta candidate, '
        'with the Git baseline still bound to the original materialization parent. '
        'This is a repair, not another direction selection. Keep the sealed intent and parent unchanged. '
        'Resolve the synthetic compatibility failures below while preserving all original tests, guards, '
        'validator and upstream bytes. Restore previously changed original tests byte-for-byte from HEAD; '
        'do not alter their assertions to make your implementation pass. Add focused unittest methods only '
        f'in `{compatibility.NEW_TEST}` to cover the new mechanism separately. '
        'If the sealed mechanism genuinely conflicts with an original contract, report that conflict instead '
        'of silently changing the intent, tests or guards. Update candidate_workspace_report.json truthfully.\n\n'
        'You MUST run the synthetic production-wrapper checks and your new tests; use the exact Python path '
        'below. Python, Codex and PowerShell directories are hash-bound in this child PATH. '
        'Use the available native apply_patch tool for edits. Do not invoke subagents. '
        'Do not access benchmark tasks, IDs, answers, DBs, raw traces, credentials, historical patches, '
        'or network. Stop on sandbox/security denial; no bypass or alternative permission route. '
        'Do not launch formal evaluation. Source repair after explicit test diagnostics is authorized; '
        'request replay after transport ambiguity/security failure is not.\n\n'
        f'Synthetic check (38 unchanged checks, no model or database):\n```powershell\n{command}\n```\n\n'
        'Run your new test file with this exact Python executable too. The outer gate additionally checks '
        'all prior test bytes, 6 delivery probes, 13 frozen unit methods and the real CLI help.\n\n'
        '# Bounded synthetic failure feedback\n\n```json\n' + feedback + '\n```\n')
    (attempt / 'implementation_task.md').write_text(task, encoding='utf-8')
    return attempt


def admit(plan, attempt, audit, runtime):
    assert_plan(plan)
    state = protocol.read_json(prior.CAMPAIGN / 'campaign_state.json')
    intent = protocol.read_json(prior.GEN / 'sealed_intent.json')
    manifest = protocol.read_json(attempt / 'workspace_manifest.json')
    admission = protocol.read_json(attempt / 'candidate_admission.json')
    validate_retry(state, intent, manifest, admission, audit, protocol.read_json(FAILED_AUDIT))
    if workspace.source_tree_hash(attempt / 'repo') != audit['source_sha256']:
        raise RuntimeError('Actual repaired candidate changed after compatibility audit')
    if sha(attempt / 'candidate.patch') != audit['patch_sha256']:
        raise RuntimeError('Actual repaired patch changed')
    ref_path = attempt / 'candidate_ref.json'
    ref = {'schema_version': protocol.SCHEMA_VERSION, 'generation': 8,
        'workspace': str(attempt), 'repo': str(attempt / 'repo'),
        'candidate_patch': str(attempt / 'candidate.patch'), 'patch_sha256': admission['patch_sha256'],
        'source_tree_sha256': audit['source_sha256'], 'changed_files': admission['changed_files'],
        'implementation_files': admission['implementation_files'], 'claim_to_source_valid': True,
        'recorded_at': now(), 'implementation_retry': {
            'same_sealed_intent': True, 'same_materialization_base': True,
            'previous_failed_candidate_ref': str(FAILED_REF), 'previous_failed_candidate_ref_sha256': sha(FAILED_REF),
            'failure_audit': str(FAILED_AUDIT), 'failure_audit_sha256': sha(FAILED_AUDIT),
            'compatibility_audit': str(attempt / 'compatibility/report.json'),
            'compatibility_audit_sha256': sha(attempt / 'compatibility/report.json'),
            'authority_ref': str(RUN / 'authority.json'), 'authority_sha256': sha(RUN / 'authority.json'),
            'normal_record_candidate_validator_unchanged': True,
            'actual_meta_runtime': runtime, 'evaluation_not_started': True}}
    save_new(ref_path, ref)
    if protocol.read_json(prior.CAMPAIGN / 'campaign_state.json') != state:
        raise RuntimeError('Concurrent state change; reference saved but pointer unchanged')
    state.update(active_candidate_ref=str(ref_path), implementation_retry_audit=str(attempt / 'compatibility/report.json'),
                 updated_at=now())
    protocol.write_json(prior.CAMPAIGN / 'campaign_state.json', state)
    return ref_path


def run_once():
    os.environ['DAB_RESEARCH_API_CONFIG'] = str(prior.ROUTE)
    plan = protocol.read_json(RUN / 'plan.json')
    assert_plan(plan)
    prior.assert_config()
    prior.assert_released()  # Before consuming the dispatch or reading a credential.
    save_new(RUN / 'dispatch_intent.json', {'recorded_at': now(), 'plan_sha256': sha(RUN / 'plan.json'),
        'maximum_deliberate_repair_sessions': MAX_REPAIR_SESSIONS, 'automatic_transport_replay': False})
    status = {'schema': 'gen008_meta_repair_workflow_terminal_v1', 'started_at': now(),
        'model': 'gpt-5.5', 'selector_replayed': False, 'formal_evaluation_started': False,
        'automatic_transport_replay': False, 'attempts': []}
    seed = Path(plan['failed_workspace'])
    feedback = failure_feedback(protocol.read_json(FAILED_AUDIT))
    try:
        for index in range(1, MAX_REPAIR_SESSIONS + 1):
            assert_plan(plan)
            prior.assert_released()
            status['stage'] = 'prepare_repair_workspace'
            attempt = prepare_attempt(plan, index, seed, feedback)
            task = attempt / 'implementation_task.md'
            save_new(attempt / 'dispatch_intent.json', {'recorded_at': now(), 'model': 'gpt-5.5',
                'task_sha256': sha(task), 'intent_sha256': plan['intent_sha256'],
                'parent_source_sha256': plan['parent_source_sha256'], 'seed_source_sha256': workspace.source_tree_hash(seed / 'repo'),
                'automatic_transport_replay': False, 'reason': 'Explicit synthetic source repair feedback'})
            env = bind_environment(meta_environment('crs-gpt55-dab'), plan['tools'])
            env.update(TEMP=str(attempt / 'repo/.repair_test_tmp'), TMP=str(attempt / 'repo/.repair_test_tmp'),
                       TMPDIR=str(attempt / 'repo/.repair_test_tmp'))
            command = [str(prior.CODEX), '--no-daemon', '-C', str(attempt / 'repo'),
                '--model', 'gpt-5.5', '--profile', 'crs-gpt55-dab', 'exec', '--sandbox', 'workspace-write',
                '-c', 'approval_policy="on-request"', '-c', 'approvals_reviewer="auto_review"',
                '--json', '--skip-git-repo-check', '-']
            status['stage'] = 'independent_meta_repair'
            result = run_logged_command(command, cwd=attempt / 'repo', prompt=task.read_text(encoding='utf-8'),
                stdout_path=attempt / 'meta.stdout', stderr_path=attempt / 'meta.stderr', env=env, timeout=None)
            if result.returncode != 0:
                raise RuntimeError('Meta process failed; no automatic replay or source admission')
            runtime = native.verify(attempt / 'repo', attempt / 'meta.stdout', attempt / 'meta.stderr', prior.HOME, 'workspace-write')
            assert_plan(plan)
            status['stage'] = 'original_source_preflight'
            with (attempt / 'source_preflight.stdout').open('x', encoding='utf-8') as log:
                with contextlib.redirect_stdout(log):
                    source_code = workspace.audit(argparse.Namespace(workspace=attempt, python=prior.PYTHON))
            status['stage'] = 'independent_frozen_compatibility'
            audit = compatibility.audit(attempt, attempt / 'compatibility', prior.PYTHON)
            item = {'index': index, 'workspace': str(attempt), 'source_preflight_passed': source_code == 0,
                    'compatibility_passed': audit['passed'], 'actual_runtime': runtime,
                    'source_sha256': audit['source_sha256'], 'finished_at': now()}
            save_new(attempt / 'terminal_report.json', item)
            status['attempts'].append(item)
            if source_code == 0 and audit['passed']:
                status['stage'] = 'same_intent_retry_admission'
                ref = admit(plan, attempt, audit, runtime)
                status.update(passed=True, stage='candidate_compatibility_passed', candidate_ref=str(ref),
                    candidate_ref_sha256=sha(ref), source_sha256=audit['source_sha256'],
                    evaluation_gate='PENDING fresh candidate-specific GPT Data runtime local+remote audits')
                break
            # Normal synthetic failure only: dispatch a DISTINCT deliberate Meta
            # repair with exact feedback. Previous attempt remains immutable.
            admission = protocol.read_json(attempt / 'candidate_admission.json')
            feedback = compatibility.bounded_feedback(audit)
            feedback += '\nSource preflight failures:\n' + json.dumps(admission.get('failures', []), ensure_ascii=False)[:3000]
            seed = attempt
        else:
            status.update(passed=False, stage='bounded_repair_exhausted',
                          failure='Two independent source repair sessions did not clear the original compatibility gate')
    except (Exception, SystemExit) as exc:
        # Never expose provider exceptions, environment or token values.
        status.update(passed=False, failure_type=type(exc).__name__,
            failure='Workflow stopped; see stage and local bounded diagnostic artifacts. No automatic replay.')
    status['finished_at'] = now()
    save_new(RUN / 'terminal_report.json', status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get('passed') else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    option = parser.add_mutually_exclusive_group(required=True)
    option.add_argument('--prepare', action='store_true')
    option.add_argument('--run-once', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        raise SystemExit(run_once())
