#!/usr/bin/env python3
"""Read-only, answer-blind terminal audit for the bound G3 attempt 2 run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
from collections import Counter
from pathlib import Path


BASE = Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
G3 = BASE / 'g003_revision001'
GRAPH = BASE / 'graph'
RUN_ID = 'baseline_g003_proposed_calls_nohint_56_v2'
RUN = G3 / 'evaluation' / RUN_ID
UPSTREAM = Path('/srv/text2sql/external/DataAgentBench_official')
PID = 6654
TREE_SHA = '3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99'
BATCH_SHA = '576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7'
SIDECAR_KEYS = {'step_index', 'signal_category', 'repeat_count',
                'eligible_step_count', 'coverage_status'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def option(command: list[str], flag: str) -> str:
    if command.count(flag) != 1:
        raise RuntimeError(f'Expected one {flag} argument')
    return command[command.index(flag) + 1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(not Path(f'/proc/{PID}').exists(), 'G3 runner still exists')
    pre_path = GRAPH / 'g003_pre_execution.json'
    claim_path = GRAPH / 'g003_launch_claim_attempt002.json'
    launch_path = GRAPH / 'g003_launch_manifest_attempt002.json'
    preflight_path = GRAPH / 'g003_preflight_attempt002.json'
    summary_path = RUN / 'multi_query_summary.json'
    progress_path = RUN / 'multi_query_progress.json'
    batch_path = G3 / 'source/dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json'
    pre, claim, launch, preflight, summary, progress, batch = map(
        read, (pre_path, claim_path, launch_path, preflight_path,
               summary_path, progress_path, batch_path))
    binding = pre['binding']
    command = launch['command']
    require(pre.get('generation') == claim.get('generation') == launch.get('generation') == 3,
            'Generation identity differs')
    require(launch.get('attempt') == claim.get('attempt') == preflight.get('attempt') == 2,
            'Attempt identity differs')
    require(launch.get('pid') == PID and claim['binding'] == binding == launch['binding'] == preflight['binding'],
            'Launch binding differs')
    require(claim.get('pre_execution_sha256') == launch.get('pre_execution_sha256') == sha(pre_path),
            'Frozen pre-execution hash differs')
    require(claim.get('preflight_sha256') == launch.get('preflight_sha256') == sha(preflight_path),
            'Preflight hash differs')
    require(preflight.get('status') == 'passed' and preflight.get('model_probe', {}).get('http_status') == 200,
            'Preflight or real model probe was not passed')
    require(binding['candidate_tree_sha256'] == TREE_SHA and binding['batch_sha256'] == BATCH_SHA,
            'Candidate or frozen batch hash differs')
    require(binding['query_count'] == 56 and float(binding['query_timeout_sec']) == 1200,
            'Frozen count or timeout differs')
    require(binding['description_mode'] == 'full_db_description_no_hints' and
            binding['timeout_scoring'] == 'timeout_failure_in_fixed_56_denominator',
            'Frozen input or scoring policy differs')
    require(option(command, '--run-id') == RUN_ID and
            option(command, '--source-root') == str(G3 / 'source') and
            float(option(command, '--query-timeout-sec')) == 1200 and
            '--skip-observer' in command and
            '--use-hints' not in command and '--use-hint-only-db-description' not in command,
            'Executed command protocol differs')
    require(sha(batch_path) == BATCH_SHA, 'Frozen batch changed')
    source = G3 / 'source'
    module_path = source / 'experiments/intent_candidate_workspace.py'
    spec = importlib.util.spec_from_file_location('g3_manifest', module_path)
    require(spec is not None and spec.loader is not None, 'Source manifest loader unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = sorted(module.source_tree_manifest(source), key=lambda row: row['path'].lower())
    require(module.source_manifest_hash(manifest) == TREE_SHA, 'G3 source tree changed during run')
    require(sha(source / 'experiments/run_multi_query_baseline.py') == binding['runner_sha256'] and
            sha(source / 'experiments/run_dab_tool_agent.py') == binding['agent_sha256'] and
            sha(source / 'experiments/g003_proposed_call_diagnostic.py') == binding['diagnostic_sha256'],
            'Frozen candidate source component hash differs')
    expected_ids = batch['query_ids']
    rows = summary['per_query_feedback']
    progress_rows = progress['queries']
    require(summary['query_count'] == len(expected_ids) == len(rows) == len(progress_rows) == 56 and
            len(set(expected_ids)) == 56 and
            [row['query_id'] for row in rows] == expected_ids ==
            [row['query_id'] for row in progress_rows],
            'Formal result set differs from exact frozen batch')
    context = summary['execution_context']
    require(float(context['query_timeout_sec']) == 1200 and
            context['db_description_mode'] == 'base' and
            context['runner_sha256'] == binding['agent_sha256'] and
            context['batch_runner_sha256'] == binding['runner_sha256'] and
            context['source_root'] == str(source),
            'Executed context differs from frozen protocol')
    comparable = ('status', 'strict_match_passed', 'run_exit_code', 'analyze_exit_code',
                  'final_answer_nonempty', 'llm_call_count', 'tool_call_count')
    require(all(all(left.get(key) == right.get(key) for key in comparable)
                for left, right in zip(rows, progress_rows)),
            'Summary and progress terminal rows differ')
    statuses = Counter(row.get('status') for row in rows)
    require(set(statuses) <= {'completed', 'timeout', 'failed'} and sum(statuses.values()) == 56,
            'Terminal statuses do not partition frozen 56')
    for row in rows:
        if row['status'] == 'timeout':
            require(124 in (row.get('run_exit_code'), row.get('analyze_exit_code'),
                            row.get('observer_exit_code')),
                    'Runner timeout lacks exit code 124')
        if row['status'] == 'completed':
            require(row.get('run_exit_code') == 0 and row.get('analyze_exit_code') == 0 and
                    isinstance(row.get('deadline_reserve_trigger'), dict),
                    'Completed task lacks successful run/analyze or reserve record')
        require(not str(row.get('terminate_reason') or '').startswith('llm_response_failed'),
                'Formal run contains model-response infrastructure failure')
    strict_pass = sum(row['status'] == 'completed' and row.get('strict_match_passed') is True
                      for row in rows)
    strict_known = sum(isinstance(row.get('strict_match_passed'), bool) for row in rows)
    unknown = sum(row['status'] == 'completed' and row.get('strict_match_passed') is None
                  for row in rows)
    require(summary['strict_pass_count'] == strict_pass and
            summary['strict_evaluated_count'] == strict_known,
            'Strict summary differs from terminal rows')
    trace_count = 0
    reserve_count = 0
    for index, row in enumerate(rows, start=1):
        run_dir = Path(row['run_dir'])
        require(run_dir.is_relative_to(RUN), 'Trace reference escapes formal run')
        trace = run_dir / 'full_execution_trace.jsonl'
        reserve = run_dir / 'deadline_reserve_trigger.json'
        lifecycle = RUN / 'lifecycle' / f'q{index:02d}.json'
        require(lifecycle.is_file(), 'Task lifecycle record missing')
        require(read(lifecycle).get('answer_blind') is True, 'Task lifecycle is not answer-blind')
        if trace.is_file():
            trace_count += 1
        if reserve.is_file():
            reserve_count += 1
            require(read(reserve) == row.get('deadline_reserve_trigger') and
                    read(reserve).get('answer_blind') is True,
                    'Reserve record differs from task row')
        elif row['status'] == 'completed':
            raise RuntimeError('Completed task reserve artifact missing')
    sidecars = list(UPSTREAM.glob(
        f'query_*/query*/logs/data_agent/{RUN_ID}_q*/g003_proposed_calls.jsonl'))
    require(len(sidecars) == 56, 'G3 sidecar file count differs from frozen 56')
    seen_indices = set()
    categories = Counter()
    sidecar_records = 0
    for path in sidecars:
        match = re.match(re.escape(RUN_ID) + r'_q(\d+)(?:_|$)', path.parent.name)
        require(match is not None, 'G3 sidecar run suffix malformed')
        task_index = int(match.group(1))
        require(1 <= task_index <= 56 and task_index not in seen_indices,
                'G3 sidecar task ordinal missing or duplicated')
        seen_indices.add(task_index)
        previous_repeat = 0
        previous_eligible = 0
        for step, line in enumerate(path.open(encoding='utf-8'), start=1):
            record = json.loads(line)
            require(set(record) == SIDECAR_KEYS and record['step_index'] == step,
                    'G3 sidecar schema or step order differs')
            category = record['signal_category']
            require(category in {'repeat', 'nonrepeat', 'unknown'} and
                    record['coverage_status'] == ('unknown_step' if category == 'unknown' else 'observed'),
                    'G3 sidecar category or coverage status differs')
            repeat = record['repeat_count']
            eligible = record['eligible_step_count']
            require(isinstance(repeat, int) and isinstance(eligible, int) and
                    0 <= previous_repeat <= repeat <= eligible and
                    0 <= previous_eligible <= eligible and
                    repeat - previous_repeat == (category == 'repeat') and
                    eligible - previous_eligible == (category != 'unknown'),
                    'G3 sidecar cumulative counters differ')
            previous_repeat, previous_eligible = repeat, eligible
            categories[category] += 1
            sidecar_records += 1
    require(seen_indices == set(range(1, 57)), 'G3 sidecar ordinal set differs')
    print(json.dumps({
        'status': 'terminal_audit_passed_no_writes', 'attempt': 2,
        'ended': 56, 'completed': statuses['completed'],
        'timeout_failures': statuses['timeout'], 'other_failures': statuses['failed'],
        'strict_pass': strict_pass, 'strict_denominator': 56,
        'strict_unknown_completed': unknown,
        'trace_files': trace_count, 'reserve_records': reserve_count,
        'lifecycle_records': 56, 'sidecar_files': len(sidecars),
        'sidecar_records': sidecar_records, 'sidecar_categories': dict(categories),
        'pre_execution_sha256': sha(pre_path), 'summary_sha256': sha(summary_path),
        'progress_sha256': sha(progress_path), 'launch_sha256': sha(launch_path),
        'free_bytes': shutil.disk_usage(BASE).free,
    }, sort_keys=True))


if __name__ == '__main__':
    main()
