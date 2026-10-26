#!/usr/bin/env python3
"""Stage hash-bound G10 source and bindings without launching evaluation."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path


BASE = Path(__file__).resolve().parent / "research_graph_baseline_20261016"
FILES = {
    "source.tar.gz": BASE / "g010_candidate_001/source.tar.gz",
    "admission.json": BASE / "g010_candidate_001/admission.json",
    "research_result.json": BASE / "g010_research_meta_001/final_raw.txt",
    "implementation_manifest.json": BASE / "g010_candidate_001/scoped_source/implementation_manifest.json",
}
SSH = [
    "ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes", "root@100.83.10.33",
]
REMOTE_CODE = r'''
import hashlib,io,json,shutil,sys,tarfile
from pathlib import Path
base=Path('/srv/text2sql/evolution_runtime/research_graph_baseline_20261016')
target_revision=base/'g010_revision001'
if target_revision.exists():
    raise RuntimeError('G10 revision already exists; refusing overwrite')
if shutil.disk_usage(base).free < 5*1024**3:
    raise RuntimeError('G10 staging space below 5 GiB')
payload=sys.stdin.buffer.read()
with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as envelope:
    names={item.name for item in envelope.getmembers()}
    expected={'source.tar.gz','admission.json','research_result.json','implementation_manifest.json'}
    if names!=expected:
        raise RuntimeError('G10 envelope entries differ')
    files={name:envelope.extractfile(name).read() for name in names}
admission=json.loads(files['admission.json'])
if (hashlib.sha256(files['source.tar.gz']).hexdigest()!=admission['source_archive_sha256'] or
    hashlib.sha256(files['research_result.json']).hexdigest()!=admission['research_result_sha256'] or
    hashlib.sha256(files['implementation_manifest.json']).hexdigest()!=admission['implementation_manifest_sha256'] or
    hashlib.sha256((base/'graph/g009_graph.json').read_bytes()).hexdigest()!=admission['parent_graph_sha256']):
    raise RuntimeError('G10 envelope or parent Graph binding differs')
with tarfile.open(fileobj=io.BytesIO(files['source.tar.gz']),mode='r:gz') as source:
    members=source.getmembers()
    if any(not member.isfile() or member.name.startswith('/') or
           '..' in Path(member.name).parts for member in members):
        raise RuntimeError('Unsafe G10 source archive member')
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
for name in ('admission.json','research_result.json','implementation_manifest.json'):
    with (bindings/name).open('xb') as stream:
        stream.write(files[name])
import importlib.util
module_path=target/'experiments/intent_candidate_workspace.py'
spec=importlib.util.spec_from_file_location('g010_manifest',module_path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tree=module.source_manifest_hash(sorted(module.source_tree_manifest(target),key=lambda row:row['path'].lower()))
if tree!=admission['candidate_tree_sha256']:
    raise RuntimeError('Staged G10 source tree differs')
print(json.dumps({'status':'staged_no_evaluation','candidate_tree_sha256':tree,
                  'free_bytes':shutil.disk_usage(base).free},sort_keys=True))
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
    proc = subprocess.run(SSH + [remote], input=payload, capture_output=True, timeout=120)
    if proc.returncode:
        raise RuntimeError(
            f"G10 stage failed: exit {proc.returncode}: "
            + proc.stderr.decode("utf-8", errors="replace")[-1200:]
        )
    lines = proc.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G10 stage did not begin with disk check")
    print(json.dumps(json.loads(lines[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
