#!/usr/bin/env python3
"""Bind audited G3 attempt 2 results and Meta extraction into four nodes."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
GRAPH = BASE / 'graph'
RUN_ID = 'baseline_g003_proposed_calls_nohint_56_v2'
RUN = BASE / 'g003_revision001/evaluation' / RUN_ID
PRE_SHA = '6cf77f0715812dabca98c41f6765406f42e116d77108180d4375133aa1811145'
LAUNCH_SHA = '9ecd9ca9171fdc040dbbab2f3feab39adabf0b612e1912ce4340d75bb1693103'
SUMMARY_SHA = '5ca329da4efa60b389d76773204d4ab38c140c68afdb8a797020e5a7ebbfbc2a'
PROGRESS_SHA = 'd7a75e3469641145eaf84e05531701f40a919855b8e4e4370b458a8a100247f8'
INPUT_SHA = 'b46a7f13588eb8cdb156a3ccbfb9619b7ebc20b08d1775ce65d9c19183ff7325'
SPECIAL_SHA = '45e2ef06a60783a5d5de2a37f81003a2113573f66aca976cee34288d2018283c'
EXTRACTOR_SHA = '8d0567ba5b83154abdd01c4f1f862fbbf06385084a8af1e8fe4a151807c32dd8'
TREE_SHA = '3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path: Path, obj: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write('\n')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(not Path('/proc/6654').exists(), 'G3 runner still active')
    paths = {
        'pre': GRAPH / 'g003_pre_execution.json',
        'launch': GRAPH / 'g003_launch_manifest_attempt002.json',
        'summary': RUN / 'multi_query_summary.json',
        'progress': RUN / 'multi_query_progress.json',
        'input': GRAPH / 'g003_evidence_input_manifest_attempt002.json',
        'special': GRAPH / 'g003_specialized_evidence_attempt002_v2.json',
        'extractor': GRAPH / 'g003_evidence_extractor_v1.py',
    }
    expected = {'pre': PRE_SHA, 'launch': LAUNCH_SHA, 'summary': SUMMARY_SHA,
                'progress': PROGRESS_SHA, 'input': INPUT_SHA, 'special': SPECIAL_SHA,
                'extractor': EXTRACTOR_SHA}
    require(all(sha(paths[name]) == digest for name, digest in expected.items()),
            'Terminal source, extractor, or Evidence hash differs')
    pre, summary, input_manifest, special = map(
        read, (paths['pre'], paths['summary'], paths['input'], paths['special']))
    binding = pre['binding']
    require(binding['candidate_tree_sha256'] == TREE_SHA and
            binding['query_count'] == 56 and
            binding['timeout_scoring'] == 'timeout_failure_in_fixed_56_denominator',
            'Pre-execution candidate or protocol differs')
    rows = summary['per_query_feedback']
    tasks = input_manifest['tasks']
    require(len(rows) == len(tasks) == 56 and special['task_count'] == 56 and
            special['task_denominator'] == 56 and special['cohort_denominator_sum'] == 56,
            'Result, input, or specialization cardinality differs')
    require(special['implementation_sha256'] == EXTRACTOR_SHA and
            special['status'] in {'supported', 'contradicted', 'inconclusive'} and
            special['binding']['signal_kind'] == 'live_proposed_call_repetition_concordance' and
            special['safety']['raw_content_included'] is False and
            special['safety']['source_paths_included'] is False,
            'Specialized extractor output fails frozen protocol')
    statuses = Counter(row['status'] for row in rows)
    require(set(statuses) <= {'completed', 'timeout', 'failed'} and sum(statuses.values()) == 56,
            'Terminal result partition differs')
    strict_pass = sum(row['status'] == 'completed' and row.get('strict_match_passed') is True
                      for row in rows)
    unknown = sum(row['status'] == 'completed' and row.get('strict_match_passed') is None
                  for row in rows)
    known_fail = sum(row['status'] == 'completed' and row.get('strict_match_passed') is False
                     for row in rows)
    cohorts = special['cohort_task_denominators']
    require(cohorts == {'known_strict_fail': known_fail,
                        'strict_pass': strict_pass,
                        'strict_verdict_unknown': unknown,
                        'timeout_failure': statuses['timeout']} and
            statuses['failed'] == 0 and
            summary['strict_pass_count'] == strict_pass,
            'Specialized cohorts or strict score differ from terminal result')
    entries = []
    for index, (task, row) in enumerate(zip(tasks, rows), start=1):
        require(task['anonymous_task_index'] == index and
                task['status'] == row['status'] and
                task['strict_match_passed'] == row.get('strict_match_passed'),
                'Anonymous manifest and formal result differ')
        sidecar = Path(task['sidecar_path'])
        trace = Path(task['trace_path']) if task['trace_path'] else None
        require(sidecar.is_file() and (trace is None or trace.is_file()),
                'Evidence source artifact missing')
        entries.append({
            'anonymous_task_index': index, 'status': row['status'],
            'sidecar_sha256': sha(sidecar),
            'trace_sha256': sha(trace) if trace else None,
        })
    trace_path = GRAPH / 'g003_trace_manifest_attempt002.json'
    evidence_path = GRAPH / 'g003_evidence.json'
    graph_path = GRAPH / 'g003_graph.json'
    require(not any(path.exists() for path in (trace_path, evidence_path, graph_path)),
            'G3 Evidence or Graph already exists')
    write_new(trace_path, {
        'schema_version': 'dab_research_graph_trace_manifest_v3',
        'generation': 3, 'attempt': 2, 'run_id': RUN_ID,
        'summary_sha256': SUMMARY_SHA, 'input_manifest_sha256': INPUT_SHA,
        'entries': entries,
    })
    now = datetime.now(timezone.utc).isoformat()
    node = {
        'id': 'evidence:g003', 'kind': 'evidence',
        'statement': 'G3 live proposed-call structural concordance on the frozen no-hint 56.',
        'frozen_task_count': 56, 'ended_count': 56,
        'completed_count': statuses['completed'],
        'timeout_failure_count': statuses['timeout'],
        'other_terminal_failure_count': statuses['failed'],
        'strict_pass_count': strict_pass,
        'strict_pass_rate_all': round(strict_pass / 56, 6),
        'strict_verdict_missing_completed_count': unknown,
        'score_policy': 'completed_and_strict_true_over_all_56;timeout_is_failure',
        'query_wall_timeout_sec': 1200,
        'specialized_signal_kind': 'live_proposed_call_repetition_concordance',
        'specialized_status': special['status'],
        'specialized_complete_task_count': special['complete_task_count'],
        'specialized_cohort_coverage': {
            cohort: {
                'complete': data['complete_task_numerator'],
                'denominator': data['task_denominator'],
                'low_coverage': data['low_coverage'],
            }
            for cohort, data in special['cohorts'].items()
        },
        'specialized_unknown_reason_counts': special['unknown_reason_counts'],
        'limits': [
            'Structural concordance does not establish task progress, answer correctness, or causal gain.',
            'The two runner timeouts are failures in the fixed 56 denominator and lack normalized full traces.',
            'Three completed strict verdicts remain unknown and are not reclassified as adjudicated failures.',
            'This is one unpaired run; score differences from earlier generations are descriptive only.',
        ],
        'artifact_refs': {
            'pre_execution_sha256': PRE_SHA,
            'launch_manifest_sha256': LAUNCH_SHA,
            'summary_sha256': SUMMARY_SHA,
            'progress_sha256': PROGRESS_SHA,
            'input_manifest_sha256': INPUT_SHA,
            'extractor_sha256': EXTRACTOR_SHA,
            'specialized_evidence_sha256': SPECIAL_SHA,
            'trace_manifest_sha256': sha(trace_path),
        },
    }
    write_new(evidence_path, {
        'schema_version': 'dab_research_graph_evidence_v2',
        'generation': 3, 'attempt': 2,
        'recorded_at_utc': now, 'node': node,
    })
    write_new(graph_path, {
        'schema_version': 'dab_research_graph_generation_v1',
        'generation': 3, 'status': 'four_nodes_complete',
        'pre_execution_sha256': PRE_SHA,
        'evidence_sha256': sha(evidence_path),
        'binding': binding,
        'nodes': [*pre['nodes'], node],
        'edges': [*pre['edges'], {
            'source': 'evidence:g003', 'target': 'experiment:g003', 'relation': 'observes',
        }],
    })
    persisted = read(graph_path)
    require(len(persisted['nodes']) == 4 and
            [part['kind'] for part in persisted['nodes']] ==
            ['problem', 'hypothesis', 'experiment', 'evidence'] and
            persisted['evidence_sha256'] == sha(evidence_path),
            'Persisted four-node Graph failed structural verification')
    print(json.dumps({
        'status': 'four_nodes_complete', 'ended': 56,
        'completed': statuses['completed'], 'timeout_failures': statuses['timeout'],
        'other_failures': statuses['failed'], 'strict_pass': strict_pass,
        'strict_denominator': 56, 'strict_unknown_completed': unknown,
        'specialized_status': special['status'],
        'specialized_complete_task_count': special['complete_task_count'],
        'trace_manifest_sha256': sha(trace_path),
        'evidence_sha256': sha(evidence_path), 'graph_sha256': sha(graph_path),
    }, sort_keys=True))


if __name__ == '__main__':
    main()
