#!/usr/bin/env python3
"""Project G3 specialized Evidence to bounded answer-blind counts."""

import hashlib
import json
from pathlib import Path


path = Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/graph/g003_specialized_evidence_attempt002_v2.json')
obj = json.loads(path.read_text(encoding='utf-8'))
cohorts = {}
for name, value in obj['cohorts'].items():
    cohorts[name] = {
        'denominator': value.get('task_denominator'),
        'complete': value.get('complete_task_numerator'),
        'coverage': value.get('complete_coverage_ratio'),
        'low_coverage': value.get('low_coverage'),
        'concordance_status': value.get('cohort_concordance_status'),
    }
print(json.dumps({
    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    'task_count': obj.get('task_count'),
    'cohort_denominator_sum': obj.get('cohort_denominator_sum'),
    'status': obj.get('status'),
    'falsified': obj.get('falsified'),
    'complete_task_count': obj.get('complete_task_count'),
    'inconclusive_reasons': obj.get('inconclusive_reasons'),
    'unknown_reason_counts': obj.get('unknown_reason_counts'),
    'implementation_sha256': obj.get('implementation_sha256'),
    'measurement_plan_sha256': obj.get('measurement_plan_sha256'),
    'cohorts': cohorts,
}, sort_keys=True))
