#!/usr/bin/env python3
"""Create an answer-free, source-bound G4 Implementation Meta workspace."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'experiments/research_graph_baseline_20261016'
PARENT = BASE / 'g003_candidate_001/repo'
OUT = BASE / 'g004_candidate_001'
SOURCE = OUT / 'scoped_source'
RESEARCH = BASE / 'g004_research_meta_002/final_raw.txt'
PARENT_TREE = '3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError('G4 Implementation workspace already exists')
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    experiment = research['experiment']
    if (experiment['code_parent_generation'] != 'g003' or
            experiment['code_parent_tree_sha256'] != PARENT_TREE or
            [research[part]['id'] for part in ('problem', 'hypothesis', 'experiment')] !=
            ['problem:g004', 'hypothesis:g004', 'experiment:g004']):
        raise RuntimeError('G4 Research decision or parent binding differs')
    manifest_module_path = PARENT / 'experiments/intent_candidate_workspace.py'
    spec = importlib.util.spec_from_file_location('g4_parent_manifest', manifest_module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('G3 parent source manifest unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(PARENT), key=lambda row: row['path'].lower())
    if module.source_manifest_hash(rows) != PARENT_TREE:
        raise RuntimeError('G3 parent source tree changed')
    files = [path for path in (PARENT / 'experiments').rglob('*.py') if path.is_file()]
    files += [path for path in (PARENT / 'adapters').rglob('*.py') if path.is_file()]
    files += [PARENT / 'external/DataAgentBench_official/common_scaffold/DataAgent.py',
              PARENT / 'prompts/dab/dab_tool_agent_policy_zero_start.txt',
              PARENT / 'tests/test_g003_proposed_call_diagnostic.py',
              PARENT / 'tests/test_g002_lifecycle_stage.py',
              PARENT / 'tests/test_deadline_reserve_g001.py',
              PARENT / 'AGENTS.md']
    if any(not path.is_file() for path in files):
        raise RuntimeError('Scoped source file missing')
    SOURCE.mkdir(parents=True, exist_ok=False)
    bound = {}
    for path in files:
        relative = path.relative_to(PARENT)
        destination = SOURCE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        bound[relative.as_posix()] = sha(path)
    (OUT / 'parent_source_bindings.json').write_text(json.dumps({
        'parent_tree_sha256': PARENT_TREE,
        'research_sha256': sha(RESEARCH),
        'scoped_files': bound,
        'excluded': ['dab_corpus', 'logs', 'benchmark inputs', 'raw results'],
    }, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'g004_scoped_workspace_ready',
                      'scoped_file_count': len(bound),
                      'research_sha256': sha(RESEARCH),
                      'parent_tree_sha256': PARENT_TREE}, sort_keys=True))


if __name__ == '__main__':
    main()
