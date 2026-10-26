#!/usr/bin/env python3
"""Overlay admitted G4 Meta changes on the verified G3 source parent."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'experiments/research_graph_baseline_20261016'
PARENT = BASE / 'g003_candidate_001/repo'
SCOPED = BASE / 'g004_candidate_001/scoped_source'
OUT = BASE / 'g004_candidate_001/repo'
BINDINGS = BASE / 'g004_candidate_001/parent_source_bindings.json'
IMPLEMENTATION = SCOPED / 'implementation_manifest.json'
RESEARCH = BASE / 'g004_research_meta_002/final_raw.txt'
PARENT_SHA = '3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99'
RESEARCH_SHA = 'd7f4fc0d479db2371ed9dcc706b288c7450edb3897eb5eed91fd684dde1ec332'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_hash(root: Path) -> str:
    path = root / 'experiments/intent_candidate_workspace.py'
    spec = importlib.util.spec_from_file_location('g4_candidate_manifest', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Candidate source manifest unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = sorted(module.source_tree_manifest(root), key=lambda row: row['path'].lower())
    return module.source_manifest_hash(manifest)


def main() -> None:
    if OUT.exists() or source_tree_hash(PARENT) != PARENT_SHA or sha(RESEARCH) != RESEARCH_SHA:
        raise RuntimeError('G4 full child exists or parent/Research source differs')
    scoped = json.loads(BINDINGS.read_text(encoding='utf-8'))
    implementation = json.loads(IMPLEMENTATION.read_text(encoding='utf-8'))
    if (scoped['parent_tree_sha256'] != PARENT_SHA or
            implementation['parent_tree_sha256'] != PARENT_SHA or
            implementation['research_sha256'] != RESEARCH_SHA or
            implementation['blocked'] is not False):
        raise RuntimeError('G4 Implementation binding or status differs')
    allowed_modified = {
        'experiments/run_dab_tool_agent.py',
        'experiments/run_multi_query_baseline.py',
    }
    allowed_added = {
        'experiments/g004_paired_structural_journal.py',
        'experiments/g004_postrun_structural_sidecar.py',
        'experiments/g004_evidence_extractor.py',
        'tests/test_g004_paired_structural_journal.py',
        'tests/test_g004_evidence_extractor.py',
    }
    changed = {name for name, digest in scoped['scoped_files'].items()
               if sha(SCOPED / name) != digest}
    added = {path.relative_to(SCOPED).as_posix() for path in SCOPED.rglob('*.py')
             if path.relative_to(SCOPED).as_posix() not in scoped['scoped_files']}
    if changed != allowed_modified or added != allowed_added:
        raise RuntimeError('G4 Meta changed files outside admitted boundary')
    manifest_paths = {entry['path'] for entry in implementation['changed_paths']
                      if entry['path'] != 'implementation_manifest.json'}
    if manifest_paths != changed | added:
        raise RuntimeError('G4 Implementation manifest changed path set differs')
    for entry in implementation['changed_paths']:
        name = entry['path']
        if name == 'implementation_manifest.json':
            continue
        if entry['sha256'] != sha(SCOPED / name):
            raise RuntimeError('G4 Implementation manifest source hash differs')
        if name in changed and entry.get('parent_sha256') != sha(PARENT / name):
            raise RuntimeError('G4 Implementation parent file hash differs')
    shutil.copytree(PARENT, OUT, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    for name in sorted(changed | added):
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCOPED / name, target)
    candidate_sha = source_tree_hash(OUT)
    record = {
        'schema_version': 'g004_local_candidate_assembly_v1',
        'code_parent': 'g003',
        'parent_tree_sha256': PARENT_SHA,
        'research_sha256': RESEARCH_SHA,
        'implementation_manifest_sha256': sha(IMPLEMENTATION),
        'candidate_tree_sha256': candidate_sha,
        'modified_paths': sorted(changed),
        'added_paths': sorted(added),
        'formal_evaluation_started': False,
    }
    record_path = BASE / 'g004_candidate_001/assembly.json'
    with record_path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'g004_candidate_assembled',
                      'candidate_tree_sha256': candidate_sha,
                      'modified': len(changed), 'added': len(added)}, sort_keys=True))


if __name__ == '__main__':
    main()
