"""Project bound Gen15 audit facts without answers, row IDs, or repair advice."""
import argparse
import hashlib
import json
from pathlib import Path

MECHANISM = 'two_phase_frozen_evidence_handoff'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_card(audit_path, summary_path, intent_path):
    audit, summary, intent = (read(p) for p in (audit_path, summary_path, intent_path))
    candidate = read(intent_path.parent / 'candidate_ref_revision_002.json')
    launch_path = intent_path.parent / 'deployment_handoff_r2/launch_manifest.json'
    launch = read(launch_path)
    rows = summary['per_query_feedback']
    completed = [r for r in rows if r['status'] == 'completed']
    timeouts = [r for r in rows if r['status'] == 'timeout']
    coverage = audit['mechanism_coverage']
    if (audit.get('schema') != 'gen015_handoff_terminal_audit_v1'
            or not all(audit.get(k) is True for k in ('complete', 'natural_end', 'hashes_verified', 'ids_match_order'))
            or intent.get('generation') != 15 or intent.get('mechanism_key') != MECHANISM
            or len(rows) != len({r['query_id'] for r in rows}) or len(rows) != audit['exact_ids'] or len(rows) != 56
            or len(completed) + len(timeouts) != 56 or audit['completed'] != len(completed)
            or audit['runner_timeout'] != len(timeouts)
            or audit['strict_pass'] != sum(r.get('strict_match_passed') is True for r in completed)
            or audit['summary_sha256'] != sha(summary_path)
            or audit['launch_manifest_sha256'] != sha(launch_path)
            or launch['source_tree_sha256'] != candidate['source_tree_sha256'] or audit['source_tree_sha256'] != candidate['source_tree_sha256']
            or launch['intent_sha256'] != intent['canonical_json_sha256'] or audit['intent_sha256'] != intent['canonical_json_sha256']
            or coverage.get('completed_present') != len(completed)):
        raise ValueError('Gen15 terminal evidence binding or coverage differs')
    for key in ('fallback_rows', 'sealed_rows', 'context_rebuild_rows', 'composition_request_rows'):
        if type(coverage.get(key)) is not int or not 0 <= coverage[key] <= len(completed):
            raise ValueError('Gen15 mechanism reach differs')
    if (coverage['composition_request_rows'] > coverage['context_rebuild_rows']
            or coverage['context_rebuild_rows'] > coverage['sealed_rows']):
        raise ValueError('Gen15 causal reach accounting differs')
    return {'schema': 'gen015_handoff_mechanism_evidence_v1', 'generation': 15, 'mechanism_key': MECHANISM,
            'evidence_binding': {'terminal_audit_sha256': sha(audit_path), 'original_summary_sha256': sha(summary_path),
                'sealed_intent_file_sha256': sha(intent_path), 'candidate_tree_sha256': candidate['source_tree_sha256'],
                'launch_manifest_sha256': sha(launch_path)},
            'coverage': coverage, 'mechanism_counters': audit['completed_mechanism_counts'],
            'fallback_reasons': audit['fallback_reasons'], 'termination_reasons': audit['termination_reasons'],
            'first_request_context_chars': audit.get('first_request_context_chars'),
            'measurement_status': {
                'integration': 'observed_on_completed_runs',
                'sealing': 'positive' if coverage['sealed_rows'] else 'measured_zero',
                'context_delivery': 'positive' if coverage['context_rebuild_rows'] else 'measured_zero',
                'composition_requests': 'positive' if coverage['composition_request_rows'] else 'measured_zero',
                'model_uptake': 'unknown_not_measured',
                'timeout_mechanism_state': 'partial_or_unknown_not_zero',
                'causal_accuracy_gain': 'not_established'},
            'evaluation_binding': {'homogeneous_runtime': True, 'input_policy': 'base_only_no_hint',
                'comparability': 'single frozen run; causal strict delta suppressed; candidate fallback cap confounds handoff attribution'},
            'evidence_limits': audit['limitations']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('audit', 'summary', 'intent', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(build_card(args.audit, args.summary, args.intent), stream, indent=2, sort_keys=True)
