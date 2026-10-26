"""Project bound Gen16 digest facts without query IDs, answers, or repair advice."""
import argparse
import hashlib
import json
from pathlib import Path

MECHANISM = 'tool_result_digest_replacement_with_expansion_handles'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_card(audit_path, summary_path, intent_path):
    audit, summary, intent = (read(path) for path in (audit_path, summary_path, intent_path))
    candidate = read(intent_path.parent / 'candidate_ref_revision_002.json')
    launch_path = intent_path.parent / 'deployment_digest_r1/launch_manifest.json'
    launch = read(launch_path)
    rows = summary['per_query_feedback']
    completed = [row for row in rows if row['status'] == 'completed']
    timeouts = [row for row in rows if row['status'] == 'timeout']
    coverage = audit['mechanism_coverage']
    counts = audit['completed_mechanism_counts']
    if (audit.get('schema') != 'gen016_digest_terminal_audit_v1'
            or not all(audit.get(key) is True for key in ('complete', 'natural_end', 'hashes_verified', 'ids_match_order'))
            or intent.get('generation') != 16 or intent.get('mechanism_key') != MECHANISM
            or len(rows) != len({row['query_id'] for row in rows}) or len(rows) != audit['exact_ids']
            or len(rows) != 56 or len(completed) + len(timeouts) != 56
            or audit['completed'] != len(completed) or audit['runner_timeout'] != len(timeouts)
            or audit['strict_pass'] != sum(row.get('strict_match_passed') is True for row in completed)
            or audit['summary_sha256'] != sha(summary_path)
            or audit['launch_manifest_sha256'] != sha(launch_path)
            or launch['source_tree_sha256'] != candidate['source_tree_sha256']
            or audit['source_tree_sha256'] != candidate['source_tree_sha256']
            or launch['intent_sha256'] != intent['canonical_json_sha256']
            or audit['intent_sha256'] != intent['canonical_json_sha256']
            or coverage.get('completed_present') != len(completed)):
        raise ValueError('Gen16 terminal evidence binding or coverage differs')
    for key in ('replacement_rows', 'expansion_rows', 'exception_fallback_rows',
                'disabled_rows', 'request_delivered_replacement_rows'):
        if type(coverage.get(key)) is not int or not 0 <= coverage[key] <= len(completed):
            raise ValueError('Gen16 mechanism reach differs')
    if (coverage['request_delivered_replacement_rows'] > coverage['replacement_rows']
            or coverage['expansion_rows'] > coverage['replacement_rows']
            or counts['expansions_served'] + counts['expansions_refused'] != counts['expansion_requests']):
        raise ValueError('Gen16 mechanism accounting differs')
    if (counts['handles_delivered'] != counts['actual_replacements']
            or counts['replacement_bytes'] > counts['replaced_bytes']):
        raise ValueError('Gen16 mechanism byte accounting differs')
    return {'schema': 'gen016_digest_mechanism_evidence_v1', 'generation': 16,
            'mechanism_key': MECHANISM,
            'evidence_binding': {'terminal_audit_sha256': sha(audit_path),
                'original_summary_sha256': sha(summary_path),
                'sealed_intent_file_sha256': sha(intent_path),
                'candidate_tree_sha256': candidate['source_tree_sha256'],
                'launch_manifest_sha256': sha(launch_path)},
            'coverage': coverage, 'mechanism_counters': counts,
            'passthrough_reasons': audit['passthrough_reasons'],
            'termination_reasons': audit['termination_reasons'],
            'measurement_status': {
                'integration': 'observed_on_completed_runs',
                'replacement': 'positive' if coverage['replacement_rows'] else 'measured_zero',
                'request_delivery': 'positive' if coverage['request_delivered_replacement_rows'] else 'measured_zero',
                'expansion': 'positive' if coverage['expansion_rows'] else 'measured_zero',
                'semantic_model_uptake': 'unknown_not_measured',
                'timeout_mechanism_state': 'partial_or_unknown_not_zero',
                'causal_accuracy_gain': 'not_established'},
            'evaluation_binding': {'homogeneous_runtime': True, 'input_policy': 'base_only_no_hint',
                'comparability': 'single frozen run; unmatched strict outcomes cannot isolate stochastic effects'},
            'evidence_limits': audit['limitations']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('audit', 'summary', 'intent', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(build_card(args.audit, args.summary, args.intent), stream, indent=2, sort_keys=True)
