#!/usr/bin/env python3
"""Return G4 post-run source-boundary violation to Implementation Meta."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'experiments/research_graph_baseline_20261016'
CHILD = BASE / 'g004_candidate_001/scoped_source'
RESEARCH = BASE / 'g004_research_meta_002/final_raw.txt'
OUT = BASE / 'g004_implementation_meta_002'
RESEARCH_SHA = 'd7f4fc0d479db2371ed9dcc706b288c7450edb3897eb5eed91fd684dde1ec332'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError('G4 repair attempt exists or Research hash differs')
    if not (CHILD / 'experiments/g004_evidence_extractor.py').is_file():
        raise RuntimeError('First G4 implementation unavailable')
    OUT.mkdir(exist_ok=False)
    prompt = (
        'You are the SAME G4 Implementation Meta on repair attempt 1 of at most 3. '
        'Work only in the scoped answer-free child. Do not read any real task, benchmark, '
        'answer, hint, validator, raw formal run, old line, credential, or network. '
        'Do not change frozen G4 Problem/Hypothesis/Experiment/measurement_plan. '
        'Mechanical gate failure: your g004_evidence_extractor.py currently reads '
        'post-run tool_calls.jsonl fields tool_name and args and computes canonical '
        'signal_category AFTER the formal run. The frozen measurement_plan permits '
        'the extractor to read only postrun_normalized_step.ordinal, '
        'postrun_normalized_step.signal_category and declared completeness metadata; '
        'raw tool arguments/names are not whitelisted as post-run Evidence extractor '
        'inputs. Existing synthetic tests missed this source boundary. Repair by making '
        'the candidate NORMALIZATION phase, during the formal run, emit a separate '
        'strict allow-list structural sidecar of post-run ordinals/categories and '
        'completeness metadata. The runtime normalizer may compute categories from '
        'transient normal inputs under the frozen canonicalization, but it must persist '
        'no raw names/arguments, messages, results, task IDs, answers, hints, validator '
        'content or digest strings in the new sidecar. The Evidence extractor must read '
        'only that structural sidecar, the paired journal, and bounded terminal status '
        'for cohort assignment; it must not open tool_calls.jsonl, full_execution_trace, '
        'or raw summary message content. Preserve G3 sidecar and all agent behavior. '
        'Provide synthetic tests that fail if the extractor reads raw tool_calls.jsonl '
        'or if normalized sidecar contains forbidden fields, plus positive, negative, '
        'unknown and timeout cases. Update implementation_manifest.json with actual '
        'source fields/hashes/tests and mechanical risks. If this cannot be faithfully '
        'done within the frozen specification and source interfaces, write BLOCKED.md '
        'and do not claim readiness. Run synthetic local tests only. The frozen G4 '
        'Research SHA256 is ' + RESEARCH_SHA + '.'
    )
    (OUT / 'prompt.txt').write_text(prompt, encoding='utf-8')
    command = [resolve_codex('codex'), '--profile', 'deepseek-standalone-dab',
               '--model', 'deepseek-flash', 'exec', '--sandbox', 'workspace-write',
               '-c', 'approval_policy="never"', '--skip-git-repo-check', '--json',
               '--output-last-message', str(OUT / 'final_raw.txt'), '-']
    result = run_logged_command(
        command, cwd=CHILD, prompt=prompt, stdout_path=OUT / 'events.jsonl',
        stderr_path=OUT / 'stderr.log', env=meta_environment('deepseek-standalone-dab'),
        timeout=None,
    )
    print(json.dumps({'returncode': result.returncode,
                      'output_dir': str(OUT)}, sort_keys=True))
    if result.returncode:
        raise RuntimeError('G4 Implementation repair failed; attempt preserved')


if __name__ == '__main__':
    main()
