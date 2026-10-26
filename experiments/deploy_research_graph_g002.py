#!/usr/bin/env python3
"""Deploy admitted G2 source and bindings without touching G1."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
ADMISSION = BASE / "g002_candidate_001/admission.json"
ARCHIVE = BASE / "g002_candidate_001/source.tar.gz"
META = BASE / "g002_research_meta_004/canonical_result.json"
META_BINDING = BASE / "g002_research_meta_004/canonical_binding.json"
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33"]

REMOTE_SOURCE = r'''
import hashlib,io,json,shutil,sys,tarfile
from pathlib import Path,PurePosixPath
import importlib.util

base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
parent=base/"g001_revision001/source"
target=base/"g002_revision001/source"
data=sys.stdin.buffer.read()
if hashlib.sha256(data).hexdigest()!="af9f345e0c256d817223d6baef1d70e1b1c8d1f91395af6600c502ba4d446c96":
    raise RuntimeError("G2 source archive hash differs")
if target.exists() or shutil.disk_usage(base).free < 5*1024**3:
    raise RuntimeError("G2 source target exists or disk is below 5 GiB")
spec=importlib.util.spec_from_file_location("parent_manifest",parent/"experiments/intent_candidate_workspace.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
parent_rows=sorted(module.source_tree_manifest(parent),key=lambda row:row["path"].lower())
parent_tree=module.source_manifest_hash(parent_rows)
if parent_tree!="8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d":
    raise RuntimeError("G1 remote code parent changed: "+parent_tree)
archive=tarfile.open(fileobj=io.BytesIO(data),mode="r:gz")
members=archive.getmembers()
for member in members:
    path=PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or not member.isfile():
        raise RuntimeError("Unsafe G2 archive member")
target.mkdir(parents=True,exist_ok=False)
archive.extractall(target,members=members,filter="data")
spec=importlib.util.spec_from_file_location("g2_manifest",target/"experiments/intent_candidate_workspace.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
child_rows=sorted(module.source_tree_manifest(target),key=lambda row:row["path"].lower())
tree=module.source_manifest_hash(child_rows)
if tree!="87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208":
    raise RuntimeError("G2 deployed source tree differs")
print(json.dumps({"status":"source_deployed","candidate_tree_sha256":tree,"member_count":len(members)},sort_keys=True))
'''

REMOTE_BINDINGS = r'''
import base64,hashlib,importlib.util,json,sys
from pathlib import Path

base=Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
g2=base/"g002_revision001"
source=g2/"source"
if not source.is_dir():
    raise RuntimeError("G2 source missing")
spec=importlib.util.spec_from_file_location("g2_manifest",source/"experiments/intent_candidate_workspace.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
rows=sorted(module.source_tree_manifest(source),key=lambda row:row["path"].lower())
if module.source_manifest_hash(rows)!="87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208":
    raise RuntimeError("G2 deployed source tree differs")
payload=json.load(sys.stdin)
expected={
    "admission.json":"c3205fb07022a778cff9a76c0f2e8f1b3c21c6fa0378c444a029993b8b7233bb",
    "research_result.json":"56d5a3b376a335cca3f4289ee955addaa5ae017a6d7c3b14915bfe9b2b5411e3",
    "research_canonical_binding.json":"b72dbd78f0dc112ccb08467ad8024a66bba2b86366b7612b49f6a611272091d5",
}
for name,wanted in expected.items():
    raw=base64.b64decode(payload[name],validate=True)
    if hashlib.sha256(raw).hexdigest()!=wanted:
        raise RuntimeError("G2 binding hash differs: "+name)
bindings=g2/"bindings"
if bindings.exists():
    raise RuntimeError("G2 bindings already exist")
bindings.mkdir()
for name in expected:
    (bindings/name).write_bytes(base64.b64decode(payload[name],validate=True))
print(json.dumps({"status":"bindings_deployed","file_count":len(expected)},sort_keys=True))
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ssh(code: str, payload: bytes) -> dict:
    command = ("df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -c '" +
               code.replace("'", "'\"'\"'") + "'")
    proc = subprocess.run(SSH + [command], input=payload, capture_output=True, timeout=180)
    if proc.returncode:
        raise RuntimeError(f"G2 deploy remote failed: exit {proc.returncode}; "
                           f"stderr={proc.stderr.decode('utf-8', errors='replace')[-1200:]}")
    lines = proc.stdout.decode("utf-8").splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("G2 deploy SSH did not begin with disk check")
    return json.loads(lines[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindings-only", action="store_true")
    args = parser.parse_args()
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    if (digest(ARCHIVE) != admission["source_archive_sha256"] or
            digest(META) != admission["research_result_sha256"] or
            admission["candidate_tree_sha256"] !=
            "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"):
        raise RuntimeError("Local G2 deployment inputs differ from admission")
    if not args.bindings_only:
        print(json.dumps(ssh(REMOTE_SOURCE, ARCHIVE.read_bytes()), sort_keys=True))
    payload = {"admission.json": base64.b64encode(ADMISSION.read_bytes()).decode("ascii"),
               "research_result.json": base64.b64encode(META.read_bytes()).decode("ascii"),
               "research_canonical_binding.json": base64.b64encode(META_BINDING.read_bytes()).decode("ascii")}
    print(json.dumps(ssh(REMOTE_BINDINGS, json.dumps(payload).encode("utf-8")), sort_keys=True))


if __name__ == "__main__":
    main()
