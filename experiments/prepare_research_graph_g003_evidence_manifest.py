#!/usr/bin/env python3
"""Bind G3 attempt 2's terminal tasks to anonymous extractor inputs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


BASE = Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
RUN_ID = 'baseline_g003_proposed_calls_nohint_56_v2'
RUN = BASE / 'g003_revision001/evaluation' / RUN_ID
GRAPH = BASE / 'graph'
UPSTREAM = Path('/srv/text2sql/external/DataAgentBench_official')
OUT = GRAPH / 'g003_evidence_input_manifest_attempt002.json'
SUMMARY_SHA = '5ca329da4efa60b389d76773204d4ab38c140c68afdb8a797020e5a7ebbfbc2a'
PROGRESS_SHA = 'd7a75e3469641145eaf84e05531701f40a919855b8e4e4370b458a8a100247f8'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or Path('/proc/6654').exists():
        raise RuntimeError('Input manifest already exists or runner still active')
    summary_path = RUN / 'multi_query_summary.json'
    progress_path = RUN / 'multi_query_progress.json'
    if sha(summary_path) != SUMMARY_SHA or sha(progress_path) != PROGRESS_SHA:
        raise RuntimeError('Terminal audit source hash differs')
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    rows = summary['per_query_feedback']
    if len(rows) != 56:
        raise RuntimeError('Formal result does not have exact 56 rows')
    sidecars = list(UPSTREAM.glob(
        f'query_*/query*/logs/data_agent/{RUN_ID}_q*/g003_proposed_calls.jsonl'))
    by_index = {}
    for path in sidecars:
        match = re.match(re.escape(RUN_ID) + r'_q(\d+)(?:_|$)', path.parent.name)
        if not match:
            raise RuntimeError('Sidecar run suffix malformed')
        index = int(match.group(1))
        if index in by_index:
            raise RuntimeError('Sidecar task index duplicated')
        by_index[index] = path
    if set(by_index) != set(range(1, 57)):
        raise RuntimeError('Sidecar task index set differs from fixed 56')
    tasks = []
    for index, row in enumerate(rows, start=1):
        run_dir = Path(row['run_dir'])
        if not run_dir.is_relative_to(RUN):
            raise RuntimeError('Trace path escapes formal run')
        trace = run_dir / 'full_execution_trace.jsonl'
        tasks.append({
            'anonymous_task_index': index,
            'status': row['status'],
            'strict_match_passed': row.get('strict_match_passed'),
            'sidecar_path': str(by_index[index]),
            'trace_path': str(trace) if trace.is_file() else None,
        })
    manifest = {
        'schema_version': 'g003_evidence_input_manifest_attempt002_v1',
        'generation': 3, 'attempt': 2, 'run_id': RUN_ID,
        'summary_sha256': SUMMARY_SHA, 'progress_sha256': PROGRESS_SHA,
        'tasks': tasks,
    }
    with OUT.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write('\n')
    print(json.dumps({'status': 'manifest_created', 'manifest_sha256': sha(OUT),
                      'task_count': len(tasks), 'sidecar_files': len(sidecars),
                      'trace_files': sum(task['trace_path'] is not None for task in tasks)},
                     sort_keys=True))


if __name__ == '__main__':
    main()
