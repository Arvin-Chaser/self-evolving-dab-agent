#!/usr/bin/env python3
"""Return a source-interface mismatch to the same G3 Evidence Implementation Meta."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'experiments/research_graph_baseline_20261016'
FIRST = BASE / 'g003_evidence_impl_meta_001'
OUT = BASE / 'g003_evidence_impl_meta_002'
WORKSPACE = FIRST / 'workspace'
RECORDER = BASE / 'g003_candidate_001/repo/experiments/g003_proposed_call_diagnostic.py'
ADMISSION = BASE / 'g003_candidate_001/admission.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or not (WORKSPACE / 'evidence_extractor.py').is_file():
        raise RuntimeError('Repair attempt exists or first G3 extractor unavailable')
    admission = json.loads(ADMISSION.read_text(encoding='utf-8'))
    if sha(RECORDER) != admission['changed_files']['experiments/g003_proposed_call_diagnostic.py']:
        raise RuntimeError('Frozen G3 recorder source differs')
    OUT.mkdir(exist_ok=False)
    prompt = (
        'You are the same-generation G3 Evidence Implementation Meta repairing a mechanical '
        'source-interface mismatch in your previous extractor. Work only in the existing '
        'isolated workspace. Do not read any real run, trace, sidecar, task, benchmark, answer, '
        'hint, validator, credential, network endpoint, or parent repository. Do not modify the '
        'frozen G3 candidate or measurement_plan. The 32 synthetic tests passed but did not '
        'model the ACTUAL frozen source interface. The bound recorder source hash is '
        + sha(RECORDER) + '. It starts step_index at 1, increments by 1 per hook call, '
        'and emits exactly the five fields step_index, signal_category, repeat_count, '
        'eligible_step_count, coverage_status. Its coverage_status is exactly observed '
        'for repeat/nonrepeat and unknown_step for unknown. The two counts are cumulative; '
        'eligible_step_count increments only on a known canonicalizable pair, while '
        'repeat_count increments only on repeat. No anonymous_task_index field is emitted. '
        'Your previous extractor requires coverage_status==complete and equates eligible '
        'steps with all rows, so it will classify real fully recorded tasks as incomplete. '
        'Correct that mismatch, fix alignment to the actual 1-based step_index, and add '
        'synthetic tests using observed/unknown_step including a full task with one unknown '
        'but complete record presence. Complete-task record coverage is distinct from known '
        'category coverage: unknown must remain unknown and not be imputed, but a present '
        'unknown_step record should not by itself be treated as a missing live record. '
        'Preserve all frozen coverage, concordance, falsification, cohort, and output '
        'constraints; do not invent a new research rule. If a frozen rule truly cannot be '
        'implemented from this interface, document BLOCKED.md rather than manufacture '
        'a result. Only run synthetic local tests. Return changed files and test results.'
    )
    (OUT / 'prompt.txt').write_text(prompt, encoding='utf-8')
    command = [resolve_codex('codex'), '--profile', 'deepseek-standalone-dab',
               '--model', 'deepseek-flash', 'exec', '--sandbox', 'workspace-write',
               '-c', 'approval_policy="never"', '--skip-git-repo-check', '--json',
               '--output-last-message', str(OUT / 'final_raw.txt'), '-']
    result = run_logged_command(
        command, cwd=WORKSPACE, prompt=prompt, stdout_path=OUT / 'events.jsonl',
        stderr_path=OUT / 'stderr.log', env=meta_environment('deepseek-standalone-dab'),
        timeout=None,
    )
    print(json.dumps({'returncode': result.returncode, 'output_dir': str(OUT)}, sort_keys=True))
    if result.returncode:
        raise RuntimeError('G3 Evidence extractor repair failed; artifacts preserved')


if __name__ == '__main__':
    main()
