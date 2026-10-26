"""Guarded versioned readmission; preserve original candidate and sealed intent.

No stage reset, Meta labels, deployment, or evaluation. Human authority required.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as p
from experiments import intent_candidate_workspace as w
from experiments.run_dab_candidate_revision import original_bindings


def check_evidence(state, plan, completion, manifest, admission, audit, checks, intent, graph, source, patch, generation):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(state['stage'] == 'candidate_admitted' and state['next_generation'] == generation, 'Wrong campaign stage/generation')
    require(state['active_candidate_ref'] == plan['original_candidate_ref'], 'Active ref changed')
    require(plan['human_authorized'] and plan['same_sealed_intent'] and plan['generation'] == generation, 'Unbound authority/generation')
    require(completion['status'] == 'candidate_revision_ready_for_independent_readmission_audit' and completion['generation'] == generation, 'Revision not ready')
    require(completion['original_candidate_ref'] == plan['original_candidate_ref'] and completion['original_preserved'], 'Original binding changed')
    require(not completion['formal_evaluation_run'] and not audit['formal_evaluation_run'], 'Evaluation already occurred')
    require(source == completion['source_tree_sha256'] == audit['source_tree_sha256'], 'Source mismatch')
    require(patch == completion['patch_sha256'] == admission['patch_sha256'] == audit['patch_sha256'], 'Patch mismatch')
    require(intent['canonical_json_sha256'] == plan['intent_sha256'] == manifest['intent_canonical_sha256'] == completion['intent_sha256'] == audit['intent_sha256'], 'Intent mismatch')
    require(intent['code_parent_hash'] == plan['materialization_parent_sha256'] == manifest['parent_source_sha256'] == audit['materialization_parent_sha256'], 'Parent mismatch')
    require(graph['ok'] and graph['head_record_sha256'] == plan['graph_head_sha256'] == audit['graph_head_sha256'], 'Graph mismatch')
    require(admission['status'] == 'source_preflight_passed' and admission['claim_to_source_valid'] and admission['implementation_files'] and not admission['failures'] and not admission['forbidden_files'] and all(c['passed'] for c in admission['checks']), 'Source admission failed')
    require(audit['status'] == 'audited_candidate_revision_ready_for_readmission' and audit['generation'] == generation and audit['independent_readmission_passed'] is True and audit['original_bindings_verified'] and audit['previous_test_assertions_and_bodies_preserved'] and audit['report_claims_reviewed'], 'Independent audit failed')
    require(checks['source_tree_sha256'] == source and checks['passed'] is True and checks['checks'] and all(c['passed'] is True for c in checks['checks']), 'Actual runtime checks failed')
    require(checks['model_calls'] == checks['database_calls'] == 0 and audit['independent_runtime_checks_failed'] == 0 and audit['independent_runtime_checks_passed'] == len(checks['checks']), 'Runtime evidence mismatch')
    require(completion['runtime_preflight_passed'], 'Supervisor runtime check failed')


def admit(campaign_root: Path, generation: int, revision: Path):
    campaign_root, revision = campaign_root.resolve(), revision.resolve()
    gen_dir = p.generation_dir(campaign_root, generation)
    if revision.parent != gen_dir.resolve() or not revision.name.startswith('repair_'):
        raise ValueError('Revision outside generation')
    authority = campaign_root / 'overnight_authorization_20261007.json'
    if not authority.is_file():
        raise ValueError('Missing durable human authority')
    for name in ('result.json', 'remote_evaluation.json'):
        if (gen_dir / name).exists():
            raise ValueError('Existing result/evaluation; reconcile instead of readmission')
    new_ref = revision / 'candidate_ref.json'
    p.require_new(new_ref)
    state_path = campaign_root / 'campaign_state.json'
    before_hash = p.sha256_file(state_path)
    _, state = p.load_campaign(campaign_root)
    plan = original_bindings(campaign_root, revision)
    completion = p.read_json(revision / 'repair_completion.json')
    manifest = p.read_json(revision / 'workspace_manifest.json')
    admission = p.read_json(revision / 'candidate_admission.json')
    audit_path = revision / 'completion_audit.json'
    audit = p.read_json(audit_path)
    check_path = Path(audit['independent_runtime_preflight'])
    if check_path.resolve().parent != revision or p.sha256_file(check_path) != audit['independent_runtime_preflight_sha256']:
        raise ValueError('Independent checks path/hash mismatch')
    checks = p.read_json(check_path)
    if checks['harness_sha256'] != p.sha256_file(ROOT / 'experiments/check_dab_candidate_recovery_revision.py'):
        raise ValueError('Independent harness changed')
    intent_path = Path(state['active_intent'])
    if intent_path.resolve() != (gen_dir / 'sealed_intent.json').resolve():
        raise ValueError('Active intent path changed')
    intent = p.read_json(intent_path)
    if p.validate_intent(intent) or w.canonical_hash(intent) != intent['canonical_json_sha256']:
        raise ValueError('Invalid sealed intent')
    parent = p.resolve_materialization_parent(campaign_root, intent['code_parent_node_id'])
    if w.source_tree_hash(Path(parent['source_root'])) != intent['code_parent_hash']:
        raise ValueError('Materialization source changed')
    if manifest['selected_parent_evidence_sha256'] != p.sha256_file(revision / 'context/selected_parent_evidence.json') or manifest['upstream_data_agent_sha256'] != p.sha256_file(revision / 'context/upstream_DataAgent.py'):
        raise ValueError('Read-only compact context changed')
    report = p.read_json(revision / 'repo/candidate_workspace_report.json')
    if not w.valid_claim_source_bindings(report['claim_to_source'], admission['changed_files'], admission['implementation_files']):
        raise ValueError('Claim bindings invalid')
    source, patch = w.source_tree_hash(revision / 'repo'), p.sha256_file(revision / 'candidate.patch')
    graph = p.verify_roadmap(campaign_root)
    check_evidence(state, plan, completion, manifest, admission, audit, checks, intent, graph, source, patch, generation)
    original_path = Path(plan['original_candidate_ref'])
    original_hash = p.sha256_file(original_path)
    ref = {'schema_version': p.SCHEMA_VERSION, 'generation': generation,
        'workspace': str(revision), 'repo': str(revision / 'repo'), 'candidate_patch': str(revision / 'candidate.patch'),
        'patch_sha256': patch, 'source_tree_sha256': source, 'changed_files': admission['changed_files'],
        'implementation_files': admission['implementation_files'], 'claim_to_source_valid': True, 'recorded_at': p.utc_now(),
        'original_ref': str(original_path), 'original_ref_sha256': original_hash, 'revision': revision.name,
        'revision_plan': str(revision / 'revision_plan.json'), 'revision_plan_sha256': p.sha256_file(revision / 'revision_plan.json'),
        'completion_audit': str(audit_path), 'completion_audit_sha256': p.sha256_file(audit_path),
        'sealed_intent_sha256': plan['intent_sha256'], 'materialization_parent_sha256': plan['materialization_parent_sha256'],
        'human_authority': str(authority), 'human_authority_sha256': p.sha256_file(authority)}
    # Only the fresh revision ref and mutable active pointer are written.
    if p.sha256_file(state_path) != before_hash:
        raise ValueError('Campaign changed during audit')
    original_bindings(campaign_root, revision)
    p.write_json(new_ref, ref)
    if p.sha256_file(state_path) != before_hash:
        raise ValueError('Campaign changed after ref creation; reconcile saved ref')
    state.update(active_candidate_ref=str(new_ref), updated_at=p.utc_now())
    p.write_json(state_path, state)
    if p.sha256_file(original_path) != original_hash:
        raise RuntimeError('Original ref changed unexpectedly')
    event = {'time': p.utc_now(), 'generation': generation, 'action': 'versioned_readmission_and_active_ref_switch',
        'why_it_might_previously_have_required_approval': 'Switch the mutable active candidate reference to independently audited repaired source.',
        'authority': str(authority), 'evidence': {'candidate_ref': str(new_ref), 'candidate_ref_sha256': p.sha256_file(new_ref), 'source': source, 'patch': patch, 'audit_sha256': ref['completion_audit_sha256']},
        'risk_and_guards': 'Same generation/intent/unique parent/Graph, original and previous hash guards, honest source claims and zero-model/DB actual runtime checks. Reject existing result/evaluation and changed state. Original ref retained; stage unchanged; no deployment or labels.',
        'outcome': 'Fresh versioned ref admitted; only active ref and update timestamp changed in campaign state.'}
    with (campaign_root / 'autonomous_decision_log.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=True) + '\n')
    return ref


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-root', type=Path, required=True)
    parser.add_argument('--generation', type=int, required=True)
    parser.add_argument('--revision', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(admit(args.campaign_root, args.generation, args.revision), ensure_ascii=True))
