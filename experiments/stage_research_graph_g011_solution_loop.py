#!/usr/bin/env python3
"""Stage the hash-bound G11 solution-loop source without starting evaluation."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
FILES = {
    "source.tar.gz": BASE / "g011_solution_loop_candidate_003/source.tar.gz",
    "admission.json": BASE / "g011_solution_loop_candidate_003/admission.json",
    "assembly.json": BASE / "g011_solution_loop_candidate_003/assembly.json",
    "research_result.json": BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt",
    "implementation_manifest.json": BASE / "g011_solution_loop_formal_implementation_001/implementation_manifest_revision_002.json",
    "research_memory_v5.json": BASE / "research_graph_memory_v5.json",
}
SSH = [
    "ssh",
    "-i",
    "C:/Users/34934/.ssh/codex_ct104",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "root@100.83.10.33",
]
REMOTE_CODE = r'''
import hashlib,io,json,shutil,sys,tarfile
from pathlib import Path
base=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
target_revision=base/'g011_solution_loop_revision001'
if target_revision.exists():
    raise RuntimeError('G11 solution-loop revision already exists; refusing overwrite')
if shutil.disk_usage(base).free < 5*1024**3:
    raise RuntimeError('G11 solution-loop staging space below 5 GiB')
payload=sys.stdin.buffer.read()
with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as envelope:
    names={item.name for item in envelope.getmembers()}
    expected={'source.tar.gz','admission.json','assembly.json','research_result.json','implementation_manifest.json','research_memory_v5.json'}
    if names!=expected:
        raise RuntimeError('G11 solution-loop envelope entries differ')
    files={name:envelope.extractfile(name).read() for name in names}
admission=json.loads(files['admission.json'])
assembly=json.loads(files['assembly.json'])
if (hashlib.sha256(files['source.tar.gz']).hexdigest()!=admission['source_archive_sha256'] or
    hashlib.sha256(files['research_result.json']).hexdigest()!=admission['research_result_sha256'] or
    hashlib.sha256(files['implementation_manifest.json']).hexdigest()!=admission['implementation_manifest_sha256'] or
    hashlib.sha256((base/'graph/g010_graph.json').read_bytes()).hexdigest()!=admission['parent_graph_sha256'] or
    assembly['candidate_tree_sha256']!=admission['candidate_tree_sha256']):
    raise RuntimeError('G11 solution-loop envelope or parent Graph binding differs')
with tarfile.open(fileobj=io.BytesIO(files['source.tar.gz']),mode='r:gz') as source:
    members=source.getmembers()
    if any(not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts for member in members):
        raise RuntimeError('Unsafe G11 solution-loop source archive member')
    target_revision.mkdir()
    target=target_revision/'source'
    target.mkdir()
    for member in members:
        path=target/member.name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:
            stream.write(source.extractfile(member).read())
bindings=target_revision/'bindings'
bindings.mkdir()
for name in ('admission.json','assembly.json','research_result.json','implementation_manifest.json','research_memory_v5.json'):
    with (bindings/name).open('xb') as stream:
        stream.write(files[name])
import importlib.util
module_path=target/'experiments/intent_candidate_workspace.py'
spec=importlib.util.spec_from_file_location('g011_solution_loop_manifest',module_path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows=sorted(module.source_tree_manifest(target),key=lambda row:row['path'].lower())
tree=module.source_manifest_hash(rows)
if tree!=admission['candidate_tree_sha256'] or len(rows)!=admission['source_file_count']:
    raise RuntimeError('Staged G11 solution-loop source tree differs')
print(json.dumps({'status':'staged_no_evaluation','candidate_tree_sha256':tree,'source_file_count':len(rows),'free_bytes':shutil.disk_usage(base).free},sort_keys=True))
'''


def main() -> None:
    with io.BytesIO() as buffer:
        with tarfile.open(fileobj=buffer, mode="w:gz") as envelope:
            for name, path in FILES.items():
                data = path.read_bytes()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                envelope.addfile(info, io.BytesIO(data))
        payload = buffer.getvalue()
    code = base64.b64encode(REMOTE_CODE.encode("utf-8")).decode("ascii")
    remote = (
        "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c "
        f'"exec(__import__(\'base64\').b64decode(\'{code}\'))"'
    )
    result = subprocess.run(SSH + [remote], input=payload, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(
            f"G11 solution-loop stage failed: exit {result.returncode}: "
            + result.stderr.decode("utf-8", errors="replace")[-1600:]
        )
    lines = result.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G11 solution-loop stage did not begin with disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
