#!/usr/bin/env python3
"""Print only answer-blind terminal artifact schemas for G3 attempt 2."""

import json
from pathlib import Path


base = Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
run = base / 'g003_revision001/evaluation/baseline_g003_proposed_calls_nohint_56_v2'
paths = {
    'pre': base / 'graph/g003_pre_execution.json',
    'claim': base / 'graph/g003_launch_claim_attempt002.json',
    'preflight': base / 'graph/g003_preflight_attempt002.json',
    'launch': base / 'graph/g003_launch_manifest_attempt002.json',
    'summary': run / 'multi_query_summary.json',
    'progress': run / 'multi_query_progress.json',
}
output = {}
for name, path in paths.items():
    if not path.is_file():
        output[name] = {'present': False}
        continue
    obj = json.loads(path.read_text(encoding='utf-8'))
    record = {'present': True, 'keys': sorted(obj)}
    if name in {'pre', 'claim', 'launch'}:
        binding = obj.get('binding')
        record['binding_keys'] = sorted(binding) if isinstance(binding, dict) else None
        if name == 'pre' and isinstance(binding, dict):
            record['protocol_binding'] = {key: binding.get(key) for key in
                                          ('description_mode', 'query_count',
                                           'query_timeout_sec', 'timeout_scoring')}
            record['node_types'] = [(node.get('id'), node.get('kind')) for node in obj.get('nodes', [])]
            record['edge_types'] = [(edge.get('source'), edge.get('target'), edge.get('relation'))
                                    for edge in obj.get('edges', [])]
            record['evidence_node_keys'] = sorted(obj.get('evidence_node', {}))
    if name == 'summary':
        context = obj.get('execution_context')
        record['context_keys'] = sorted(context) if isinstance(context, dict) else None
        rows = obj.get('per_query_feedback')
        record['row_count'] = len(rows) if isinstance(rows, list) else None
        record['row_keys'] = sorted(rows[0]) if rows else None
    if name == 'progress':
        rows = obj.get('queries')
        record['row_count'] = len(rows) if isinstance(rows, list) else None
        record['row_keys'] = sorted(rows[0]) if rows else None
    output[name] = record
print(json.dumps(output, sort_keys=True))
