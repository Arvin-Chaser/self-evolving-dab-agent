"""Model-free, hash-bound Gen11 delivery evidence for independent Meta review.

The remote auditor already checked each frozen task's native wire, checkpoint,
candidate fields and isolated input. This card contains only its bounded
aggregate; it never reads task answers, traces, databases or credentials.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = 'dab_mechanism_evidence_card_v3'
MECHANISM = 'delivered_repeat_failure_steering'
COUNTERS = (
    'eligible_intervention_opportunity', 'intervention_raised',
    'delivered_steering', 'consumed_steering', 'delivered_on_result_path',
    'delivery_declined', 'delivery_bound_reached', 'delivery_degraded',
    'bookkeeping_degraded', 'unaccounted_interventions_at_final',
)


def _load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Bound evidence must be a JSON object')
    return value, raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_card(audit_path: Path, summary_path: Path, intent_path: Path) -> dict:
    audit, audit_raw = _load(audit_path)
    summary, summary_raw = _load(summary_path)
    intent, intent_raw = _load(intent_path)
    if intent.get('generation') != 11 or intent.get('mechanism_key') != MECHANISM:
        raise ValueError('Gen11 intent identity differs')
    if (audit.get('schema') != 'gen011_deepseek_terminal_integrity_audit_v1'
        or audit.get('run_id') != 'gen011_deepseek_full17_v2_p4_20261009_111743'
        or audit.get('summary_sha256') != _sha(summary_raw)
        or audit.get('summary_bytes') != len(summary_raw)
        or audit.get('remote_full_audit_sha256') !=
            'b574be161fe0d32bb1aeb34aec4187fce081d486b5966c4293a0ef837c40fe56'):
        raise ValueError('Gen11 exact terminal audit/summary binding differs')
    rows = summary.get('per_query_feedback')
    if not isinstance(rows, list) or len(rows) != 17 or len({r.get('query_id') for r in rows}) != 17:
        raise ValueError('Gen11 frozen result coverage differs')
    if (audit.get('complete') is not True or audit.get('healthy_full17_eligible') is not True
        or audit.get('normal') != 17 or audit.get('strict') !=
            sum(r.get('strict_match_passed') is True for r in rows)
        or any(audit.get(k) != 0 for k in ('run_errors', 'analysis_errors',
                                           'provider_termination', 'failed_check_count', 'audit_error_count'))
        or any(audit.get(k) is not True for k in (
            'all_final_pending_clear', 'all_original_wire_checks_passed',
            'all_isolation_manifests_valid', 'all_source_and_input_binding_checks_passed'))
        or audit.get('Meta_or_Graph_launched') is not False):
        raise ValueError('Gen11 terminal audit is not healthy and pre-review')
    counters = audit.get('delivery_counters')
    if not isinstance(counters, dict) or set(counters) != set(COUNTERS) or any(
        type(counters[name]) is not int or counters[name] < 0 for name in COUNTERS
    ):
        raise ValueError('Gen11 delivery counters incomplete or invalid')
    eligible = counters['eligible_intervention_opportunity']
    raised = counters['intervention_raised']
    delivered = counters['delivered_steering']
    consumed = counters['consumed_steering']
    if not 0 <= consumed <= delivered <= raised <= eligible:
        raise ValueError('Gen11 intervention counters exceed observed opportunities')
    if (audit.get('rows_with_eligible_opportunity') not in range(18)
        or audit.get('rows_with_delivered_steering') not in range(18)
        or audit.get('rows_with_nonempty_final_delivery_ledger') not in range(18)
        or audit['rows_with_eligible_opportunity'] > eligible
        or audit['rows_with_delivered_steering'] > delivered):
        raise ValueError('Gen11 task coverage differs from counters')
    return {
        'schema': SCHEMA,
        'generation': 11,
        'mechanism_key': MECHANISM,
        'run_id': audit['run_id'],
        'evidence_binding': {
            'terminal_audit_sha256': _sha(audit_raw),
            'original_summary_sha256': _sha(summary_raw),
            'sealed_intent_file_sha256': _sha(intent_raw),
            'remote_full_audit_sha256': audit['remote_full_audit_sha256'],
        },
        'coverage': {
            'audited_tasks': 17,
            'mechanism_state_verified_tasks': 17,
            'normal_tasks': 17,
            'strict_pass_tasks': audit['strict'],
            'terminal_error_tasks': 0,
            'tasks_with_eligible_opportunity': audit['rows_with_eligible_opportunity'],
            'tasks_with_delivered_steering': audit['rows_with_delivered_steering'],
        },
        'mechanism_counters': {name: counters[name] for name in COUNTERS},
        'measurement_status': {
            'eligible_tool_failure_opportunity_denominator': 'observed' if eligible else 'measured_zero',
            'intervention_raised': 'observed' if raised else 'measured_zero',
            'steering_delivery': 'observed' if delivered else 'measured_zero',
            'steering_consumption': 'observed' if consumed else 'measured_zero',
            'synthetic_reachability': 'verified_in_bound_preflight_not_real_activation',
            'behavior_after_intervention': (
                'delivery_observed_requires_independent_review' if delivered
                else 'no_delivery_observed_despite_eligible_and_raised_opportunities'
                if eligible and raised else 'not_observable_without_opportunity'),
            'causal_accuracy_gain': 'not_established',
        },
        'evidence_limits': [
            'Eligible opportunities are classified by the candidate, not by an independent observer of every possible failure.',
            'A synthetic forced-delivery test proves reachability, but 0 real delivered/consumed events means the delivered-steering mechanism was not observed activating in this run.',
            'The 10/17 strict outcome and earlier generations are descriptive; no controlled same-source comparison establishes a causal effect.',
        ],
        'review_or_graph_started_by_extractor': False,
    }
