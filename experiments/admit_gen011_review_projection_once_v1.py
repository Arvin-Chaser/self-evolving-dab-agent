"""Admit only a deterministic formatting projection of the saved Gen11 review.

No Meta/model replay. The one missing detailed_analysis field is assembled
verbatim from the independent review's already-authored analysis fields;
all original judgments remain byte-for-byte represented in the projection.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments import dab_native_meta_audit_v4 as native
from experiments.dab_meta_standalone_runtime_v1 import HOME

CAMPAIGN = ROOT / 'experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930'
G11 = CAMPAIGN / 'generations/gen_011'
SESSION = G11 / 'meta_agent/review'
RUN = G11 / 'post_eval_review_graph_v1'
ORIGINAL_SHA = '7be4c5549e0662912c5f612f36131213cfd61fe98f98d97d9cc129a157276abb'
GRAPH_HEAD = '27cc54643481469f19cc01da91c7591a8824b152f989ae103b057c2d9d85c7e2'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def save_new(path: Path, value: dict) -> None:
    if path.exists():
        raise RuntimeError('Immutable Gen11 projection artifact already exists: ' + str(path))
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def project(original: dict) -> dict:
    expected = set(protocol.REVIEW_FIELDS)
    if not isinstance(original, dict) or set(original) != expected:
        raise ValueError('Projection requires exactly the original eleven review fields')
    fields = ('intent_realization', 'behavioral_effect', 'task_effect',
              'next_recommendation')
    if any(not isinstance(original[field], str) or not original[field].strip()
           for field in fields):
        raise ValueError('Required model-authored analysis text missing')
    activation = original['activation_evidence']
    if not isinstance(activation, list) or not activation or any(
        not isinstance(item, str) or not item.strip() for item in activation
    ):
        raise ValueError('Model-authored activation evidence missing')
    detailed = '\n\n'.join((
        original['intent_realization'],
        '\n'.join(activation),
        original['behavioral_effect'],
        original['task_effect'],
        original['next_recommendation'],
    ))
    return {**original, 'detailed_analysis': detailed}


def main() -> dict:
    original_path = SESSION / 'review_response.json'
    terminal = read(RUN / 'terminal_report.json')
    intent = read(SESSION / 'dispatch_intent.json')
    invocation = read(SESSION / 'invocation.json')
    if (sha(original_path) != ORIGINAL_SHA
        or terminal.get('stage') != 'independent_gen011_review_and_graph'
        or terminal.get('passed') is not False
        or terminal.get('bounded_failure', '').find("['detailed_analysis']") < 0
        or intent.get('automatic_transport_replay') is not False
        or invocation.get('status') != 'completed'
        or invocation.get('model') != 'deepseek-flash'):
        raise RuntimeError('Original failed review dispatch or exact response differs')
    state = read(CAMPAIGN / 'campaign_state.json')
    if (state.get('next_generation'), state.get('stage')) != (11, 'result_recorded'):
        raise RuntimeError('Gen11 formal result stage differs')
    graph = protocol.verify_roadmap(CAMPAIGN)
    if (graph.get('ok') is not True or graph.get('record_count') != 10
        or graph.get('head_record_sha256') != GRAPH_HEAD
        or (CAMPAIGN / 'details/review_gen_011.json').exists()
        or (RUN / 'review_graph_receipt.json').exists()):
        raise RuntimeError('Graph or review has changed; no replay')
    original = read(original_path)
    projected = project(original)
    known = {protocol.ROOT_NODE_ID, *[r['node_id'] for r in protocol.load_roadmap(CAMPAIGN)]}
    errors = protocol.validate_review(projected, known)
    schema_required = set(read(SESSION / 'output_schema.json')['required'])
    if errors or set(projected) != schema_required:
        raise RuntimeError('Original review validator/schema rejects projection: ' + '; '.join(errors))
    runtime_audit = native.verify(SESSION, SESSION / 'codex.stdout',
                                  SESSION / 'codex.stderr', HOME, 'read-only')
    if (runtime_audit.get('model') != 'deepseek-flash'
        or runtime_audit.get('model_provider') != 'dab_deepseek_standalone'
        or runtime_audit.get('sandbox') != 'read-only'
        or runtime_audit.get('network') != 'restricted'
        or runtime_audit.get('completed_turn_count') != 1
        or runtime_audit.get('approved_prefix_count') != 0):
        raise RuntimeError('Original independent Meta runtime audit differs')
    save_new(SESSION / 'native_runtime_audit.json', runtime_audit)
    save_new(SESSION / 'review_response_admission_projection_v1.json', projected)
    provenance = {
        'schema': 'gen011_review_projection_provenance_v1',
        'original_response_sha256': ORIGINAL_SHA,
        'projection_sha256': sha(SESSION / 'review_response_admission_projection_v1.json'),
        'native_runtime_audit_sha256': sha(SESSION / 'native_runtime_audit.json'),
        'copied_unchanged_original_fields': list(protocol.REVIEW_FIELDS),
        'new_field': 'detailed_analysis',
        'new_field_exact_sources_in_order': [
            'intent_realization', 'activation_evidence', 'behavioral_effect',
            'task_effect', 'next_recommendation',
        ],
        'new_judgments_added': False,
        'new_model_calls': 0,
        'original_response_preserved': True,
        'original_review_validator_unchanged': True,
    }
    save_new(SESSION / 'review_projection_provenance_v1.json', provenance)
    record = protocol.append_review(CAMPAIGN, projected)
    after = protocol.verify_roadmap(CAMPAIGN)
    if (after.get('ok') is not True or after.get('record_count') != 11
        or after.get('head_record_sha256') != record['record_sha256']):
        raise RuntimeError('Gen11 Graph append verification failed')
    receipt = {
        'schema': 'gen011_review_graph_receipt_v1',
        'node_id': record['node_id'],
        'record_sha256': record['record_sha256'],
        'review_projection_sha256': provenance['projection_sha256'],
        'projection_provenance_sha256': sha(SESSION / 'review_projection_provenance_v1.json'),
        'native_runtime_audit_sha256': provenance['native_runtime_audit_sha256'],
        'original_model_response_sha256': ORIGINAL_SHA,
        'graph_verified': True,
        'new_model_calls': 0,
        'Gen12_intent_candidate_or_evaluation_started': False,
    }
    save_new(RUN / 'review_graph_receipt.json', receipt)
    save_new(RUN / 'posthoc_terminal_report_v1.json', {
        'schema': 'gen011_review_graph_posthoc_terminal_v1',
        'passed': True,
        'prior_terminal_report_preserved': True,
        'stage': 'review_and_graph_complete',
        'record_sha256': record['record_sha256'],
        'no_model_replay': True,
        'new_model_calls': 0,
        'Gen12_started': False,
    })
    return receipt


if __name__ == '__main__':
    print(json.dumps(main(), ensure_ascii=False, indent=2))
