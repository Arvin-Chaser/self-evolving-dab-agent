"""Human-authorized versioned repair under an unchanged sealed generation intent.

Preserves the admitted candidate; stops at a separate completion artifact.
No automatic campaign re-admission, remote deployment, or formal evaluation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as workspace_tools


def original_bindings(root: Path, revision: Path, _seen=None):
    seen = set() if _seen is None else _seen
    assert revision.resolve() not in seen, 'Revision provenance cycle'
    seen.add(revision.resolve())
    plan = protocol.read_json(revision / 'revision_plan.json')
    assert protocol.sha256_file(revision / 'implementation_task.md') == plan['repair_prompt_sha256']
    assert protocol.sha256_file(revision / 'context/repair_validation.py') == plan['repair_validation_sha256']
    candidate = protocol.read_json(Path(plan['original_candidate_ref']))
    assert workspace_tools.source_tree_hash(Path(candidate['repo'])) == plan['original_source_sha256']
    assert protocol.sha256_file(Path(candidate['candidate_patch'])) == plan['original_patch_sha256']
    for path, wanted in plan['immutable_artifacts'].items():
        assert protocol.sha256_file(Path(path)) == wanted, 'Immutable original changed: ' + path
    if plan.get('seed_revision'):
        assert workspace_tools.source_tree_hash(Path(plan['seed_revision']) / 'repo') == plan['seed_source_sha256']
        original_bindings(root, Path(plan['seed_revision']), seen)
    assert protocol.verify_roadmap(root)['head_record_sha256'] == plan['graph_head_sha256']
    return plan


def validate_seed_failure(seed_revision: Path, failure_audit: Path, source_hash: str, patch_hash: str):
    """A ready marker is not admission: a bound independent rejection can seed repair."""
    assert failure_audit.parent == seed_revision, 'Failure audit must belong to the seed revision'
    completion = protocol.read_json(seed_revision / 'repair_completion.json')
    audit = protocol.read_json(failure_audit)
    assert audit['status'] == 'audited_candidate_revision_runtime_failure'
    assert audit['seed_source_sha256'] == source_hash and audit['seed_patch_sha256'] == patch_hash
    assert audit['original_bindings_verified'] and not audit['formal_evaluation_run']
    if completion['status'] == 'candidate_revision_ready_for_independent_readmission_audit':
        assert completion['source_tree_sha256'] == source_hash and completion['patch_sha256'] == patch_hash
        assert not completion['formal_evaluation_run']
        assert audit['independent_readmission_passed'] is False
        check_path = Path(audit['independent_runtime_preflight'])
        assert check_path.parent == seed_revision
        assert protocol.sha256_file(check_path) == audit['independent_runtime_preflight_sha256']
        checks = protocol.read_json(check_path)
        assert checks['source_tree_sha256'] == source_hash
        assert checks['passed'] is False and any(item['passed'] is False for item in checks['checks'])
        assert checks['model_calls'] == checks['database_calls'] == 0
        assert audit['previous_test_assertions_and_bodies_preserved'] is True
    else:
        assert completion['status'] == 'versioned_repair_failed_needs_audit'
    return audit


def validate_active_seed_ref(seed_revision: Path, previous: dict, active_ref: Path, generation: int):
    """Permit an already-readmitted exact seed only through its audited ref chain."""
    if previous['original_candidate_ref'] == str(active_ref):
        return
    assert active_ref.resolve() == (seed_revision / 'candidate_ref.json').resolve()
    ref = protocol.read_json(active_ref)
    completion = protocol.read_json(seed_revision / 'repair_completion.json')
    assert ref['generation'] == generation and ref['revision'] == seed_revision.name
    assert Path(ref['repo']).resolve() == (seed_revision / 'repo').resolve()
    assert Path(ref['workspace']).resolve() == seed_revision.resolve()
    assert ref['original_ref'] == previous['original_candidate_ref']
    assert protocol.sha256_file(Path(ref['original_ref'])) == ref['original_ref_sha256']
    assert ref['source_tree_sha256'] == completion['source_tree_sha256']
    assert ref['patch_sha256'] == completion['patch_sha256']
    assert ref['sealed_intent_sha256'] == previous['intent_sha256']
    assert ref['materialization_parent_sha256'] == previous['materialization_parent_sha256']
    assert Path(ref['completion_audit']).resolve() == (seed_revision / 'completion_audit.json').resolve()
    assert protocol.sha256_file(Path(ref['completion_audit'])) == ref['completion_audit_sha256']
    audit = protocol.read_json(Path(ref['completion_audit']))
    assert audit['status'] == 'audited_candidate_revision_ready_for_readmission'
    assert audit['independent_readmission_passed'] and not audit['formal_evaluation_run']
    assert audit['source_tree_sha256'] == ref['source_tree_sha256'] and audit['patch_sha256'] == ref['patch_sha256']


def prepare(root: Path, generation: int, revision: Path, seed_revision: Path | None = None,
            failure_audit: Path | None = None):
    campaign, state = protocol.load_campaign(root)
    assert state['stage'] == 'candidate_admitted' and state['next_generation'] == generation
    assert not (protocol.generation_dir(root, generation) / 'remote_evaluation.json').exists()
    assert not (protocol.generation_dir(root, generation) / 'result.json').exists()
    assert not revision.exists(), 'Never overwrite a repair attempt'
    original_ref = Path(state['active_candidate_ref'])
    candidate = protocol.read_json(original_ref)
    assert (seed_revision is None) == (failure_audit is None), 'Revision seed requires its audited failure'
    seed_repo = Path(candidate['repo'])
    seed_hash = candidate['source_tree_sha256']
    prior_immutable = []
    if seed_revision is not None:
        assert seed_revision.parent == protocol.generation_dir(root, generation).resolve()
        previous = original_bindings(root, seed_revision)
        validate_active_seed_ref(seed_revision, previous, original_ref, generation)
        assert protocol.read_json(seed_revision / 'candidate_admission.json')['status'] == 'source_preflight_passed'
        seed_repo = seed_revision / 'repo'
        seed_hash = workspace_tools.source_tree_hash(seed_repo)
        audit = validate_seed_failure(seed_revision, failure_audit, seed_hash,
                                      protocol.sha256_file(seed_revision / 'candidate.patch'))
        prior_immutable = [seed_revision / name for name in ('revision_plan.json', 'repair_completion.json',
            'candidate_admission.json', 'candidate.patch', 'runtime_preflight.json', 'workspace_manifest.json')]
        prior_immutable += [seed_repo / 'candidate_workspace_report.json', failure_audit]
        if (seed_revision / 'candidate_ref.json').exists():
            prior_immutable += [seed_revision / 'candidate_ref.json', seed_revision / 'completion_audit.json']
        if audit.get('independent_runtime_preflight'):
            prior_immutable.append(Path(audit['independent_runtime_preflight']))
    old_workspace = Path(candidate['workspace'])
    intent_path = Path(state['active_intent'])
    intent = protocol.read_json(intent_path)
    assert not protocol.validate_intent(intent)
    assert workspace_tools.canonical_hash(intent) == intent['canonical_json_sha256']
    assert workspace_tools.source_tree_hash(Path(candidate['repo'])) == candidate['source_tree_sha256']
    assert protocol.sha256_file(Path(candidate['candidate_patch'])) == candidate['patch_sha256']
    base = protocol.resolve_materialization_parent(root, intent['code_parent_node_id'])
    evidence = protocol.generation_dir(root, generation) / 'selected_parent_evidence.json'
    workspace_tools.prepare(argparse.Namespace(source_root=Path(base['source_root']), output=revision,
        intent=intent_path, parent_source=None, parent_context=evidence,
        upstream_source=old_workspace / 'context/upstream_DataAgent.py', mechanism_contract=None))
    # Seed the same failed candidate on the SAME materialization-parent Git baseline.
    # Preserve exact bytes (Windows CRLF makes a textual git-apply round trip
    # unreliable). The baseline remains the selected Gen5 parent, so the new
    # admission patch still describes the complete Gen6 change from that base.
    for source in workspace_tools.source_paths(seed_repo):
        target = revision / 'repo' / source.relative_to(seed_repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    assert workspace_tools.source_tree_hash(revision / 'repo') == seed_hash
    shutil.copy2(seed_repo / 'candidate_workspace_report.json', revision / 'repo/candidate_workspace_report.json')
    shutil.copy2(ROOT / 'experiments/check_dab_candidate_recovery_revision.py', revision / 'context/repair_validation.py')
    task = revision / 'implementation_task.md'
    task.write_text(task.read_text(encoding='utf-8') + '''

## Human-authorized versioned repair of this Gen6 candidate

The adjacent repo is seeded with the previously admitted candidate, not a new
parent selection. This is the same sealed intent and unique Gen5 source base.
Repair the existing mechanism implementation only. Do not change intent, parent
selection, context, infrastructure, benchmark interfaces, or scope. Preserve
the bounded successful-progress checkpoint mechanism and activation counters.
The old candidate elsewhere remains immutable and is not your workspace.

Deterministic source-only failures observed in the CURRENT candidate:
1. First actual _handle_tool_call raises NameError for expire_recovery_windows:
   the helper lives only inside __init__ and is not visible in the dispatch scope.
2. The candidate's own test_recovery_state_is_restorable fails IndexError:
   observe_success persists TurnCheckpoint objects but _restore reads mapping
   items; the resulting TypeError is caught and silently loses valid state.
3. Existing outer admission checked compilation and --help, not actual wrapper
   dispatch or these free-function tests. Passing those checks was insufficient.

Fix the production behavior and add focused regression tests for the exact
installed wrapper path and structured state round-trip, including JSON-safe
durability where appropriate. Do not remove/weaken existing tests or mask these
exceptions. Keep failure outcomes visible and preserve normal base dispatch.
The read-only ../context/repair_validation.py invokes all existing new tests
and calls the actual install_self_observation_tool with stub base tools/agent;
it checks success, failed-result restore, exact signature suppression, expiry,
and content flow without any model or DB calls. This is unit evidence, NOT
formal activation evidence. You may inspect this harness; do not edit context.

Update candidate_workspace_report.json honestly with changed implementation
claim bindings and selected-parent influence. No benchmark task IDs, rows,
traces, database values or ground truth are supplied or permitted. No new
evolution objective, manually assigned review label, or performance claim.
''', encoding='utf-8')
    if seed_revision is not None:
        current_task = task.read_text(encoding='utf-8')
        start = current_task.index('Deterministic source-only failures observed in the CURRENT candidate:')
        end = current_task.index('Fix the production behavior', start)
        current_task = current_task[:start] + (
            'The CURRENT seed is the preserved previous repaired candidate. Its constructor-scope\n'
            'NameError and checkpoint object/mapping serialization defects are resolved.\n'
            'Current deterministic source-only failures from the independently audited runtime check:\n'
            + json.dumps(audit['current_failure_evidence'], ensure_ascii=False, indent=2) + '\n\n'
        ) + current_task[end:]
        current_task += (
            '\nA Python runtime IS available at: ' + sys.executable + '\n'
            'Run that explicit executable with ../context/repair_validation.py and the absolute repo path.\n'
            'Preserve all original and previous revision tests; repair production behavior, not assertions.\n'
            'Do not report tests as passed without executing them. No formal evaluation is authorized here.\n'
        )
        task.write_text(current_task, encoding='utf-8')
    immutable = [original_ref, intent_path, Path(candidate['candidate_patch']),
        Path(candidate['repo']) / 'candidate_workspace_report.json', old_workspace / 'candidate_admission.json',
        old_workspace / 'workspace_manifest.json', evidence] + prior_immutable
    graph = protocol.verify_roadmap(root)
    assert graph['ok']
    plan = {'generation': generation, 'human_authorized': True, 'same_sealed_intent': True,
        'original_candidate_ref': str(original_ref), 'original_source_sha256': candidate['source_tree_sha256'],
        'original_patch_sha256': candidate['patch_sha256'], 'intent_sha256': intent['canonical_json_sha256'],
        'seed_source_sha256': seed_hash, 'seed_revision': str(seed_revision) if seed_revision else None,
        'graph_head_sha256': graph['head_record_sha256'], 'materialization_parent_sha256': intent['code_parent_hash'],
        'immutable_artifacts': {str(path): protocol.sha256_file(path) for path in immutable},
        'repair_validation_sha256': protocol.sha256_file(revision / 'context/repair_validation.py'),
        'repair_prompt_sha256': protocol.sha256_file(task),
        'meta_agent': campaign['meta_agent'], 'formal_evaluation_run': False,
        'prepared_at': protocol.utc_now()}
    protocol.write_json(revision / 'revision_plan.json', plan)
    print(json.dumps({'status': 'versioned_repair_prepared', 'workspace': str(revision)}))


def run(root: Path, revision: Path):
    completion = revision / 'repair_completion.json'
    assert not completion.exists()
    status = root / 'continuation_gen006.json'
    plan = original_bindings(root, revision)
    assert workspace_tools.source_tree_hash(revision / 'repo') == plan.get('seed_source_sha256', plan['original_source_sha256']), 'Repair seed changed before launch'
    now = protocol.utc_now()
    protocol.write_json(status, {'status': 'versioned_candidate_repair_running', 'pid': os.getpid(),
        'generation': plan['generation'], 'workers': 3, 'started_at': now,
        'revision_workspace': str(revision), 'completion': str(completion),
        'original_candidate_ref': plan['original_candidate_ref'], 'intent_sha256': plan['intent_sha256']})
    try:
        meta = plan['meta_agent']
        result = workspace_tools.generate(argparse.Namespace(workspace=revision, codex=meta['codex'],
            model=meta['model'], profile=meta['profile'], python=Path(sys.executable), timeout=0, max_repairs=1))
        assert result == 0, 'Repair did not pass source admission'
        assert protocol.sha256_file(revision / 'context/repair_validation.py') == plan['repair_validation_sha256']
        proc = subprocess.run([sys.executable, str(revision / 'context/repair_validation.py'), str(revision / 'repo')],
                              cwd=revision / 'repo', capture_output=True, text=True, encoding='utf-8', timeout=90)
        checks = json.loads(proc.stdout)
        protocol.write_json(revision / 'runtime_preflight.json', checks)
        original_bindings(root, revision)
        assert proc.returncode == 0 and checks['passed'], 'Repaired candidate runtime checks failed'
        original_bindings(root, revision)
        payload = {'status': 'candidate_revision_ready_for_independent_readmission_audit',
            'generation': plan['generation'], 'intent_sha256': plan['intent_sha256'],
            'source_tree_sha256': workspace_tools.source_tree_hash(revision / 'repo'),
            'patch_sha256': protocol.sha256_file(revision / 'candidate.patch'),
            'original_candidate_ref': plan['original_candidate_ref'], 'original_preserved': True,
            'runtime_preflight_passed': True, 'formal_evaluation_run': False, 'completed_at': protocol.utc_now()}
    except BaseException as error:
        payload = {'status': 'versioned_repair_failed_needs_audit', 'generation': plan['generation'],
            'error_type': type(error).__name__, 'error': str(error), 'formal_evaluation_run': False,
            'completed_at': protocol.utc_now()}
        protocol.write_json(completion, payload)
        protocol.write_json(status, {**payload, 'revision_workspace': str(revision), 'completion': str(completion)})
        raise
    protocol.write_json(completion, payload)
    protocol.write_json(status, {**payload, 'revision_workspace': str(revision), 'completion': str(completion)})
    print(json.dumps(payload), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--campaign-root', type=Path, required=True)
    parser.add_argument('--generation', type=int, default=6)
    parser.add_argument('--revision', type=Path, required=True)
    parser.add_argument('--seed-revision', type=Path)
    parser.add_argument('--failure-audit', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.campaign_root.resolve(), args.generation, args.revision.resolve(),
                args.seed_revision.resolve() if args.seed_revision else None,
                args.failure_audit.resolve() if args.failure_audit else None)
    else:
        run(args.campaign_root.resolve(), args.revision.resolve())
