#!/usr/bin/env python3
"""Run bounded no-task G12 checks remotely; credentials travel only over stdin."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "experiments/research_graph_baseline_20261016/g012_admission_001"
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "root@100.83.10.33"]
PYTHON = "/srv/text2sql/.venv/bin/python"
UPSTREAM = "/srv/text2sql/external/DataAgentBench_official"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def remote_python(code):
    encoded = base64.b64encode(code.encode()).decode()
    command = f"{PYTHON} -B -c \"exec(__import__('base64').b64decode('{encoded}'))\""
    result = subprocess.run(SSH + [command], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError("Remote preparation failed; no credentials were sent")
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--modes", nargs="+", choices=["enabled", "disabled", "transport_enabled", "transport_disabled", "provider"], default=["enabled", "disabled", "transport_enabled", "transport_disabled"])
    args = parser.parse_args()
    remote = args.remote_root
    if not remote.startswith("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g012_admission_") or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/" for c in remote):
        raise RuntimeError("Remote scratch directory boundary differs")
    if not args.label.isalnum():
        raise RuntimeError("Label must be alphanumeric")
    destination = LOCAL / f"remote_{args.label}.json"
    if destination.exists():
        raise RuntimeError("Refusing to overwrite remote receipt")
    if args.prepare:
        assembly = json.loads((LOCAL / "assembly.json").read_text())
        code = f"""
import hashlib,json,tarfile
from pathlib import Path
root=Path({remote!r})
archive=root/'source.tar.gz'
if hashlib.sha256(archive.read_bytes()).hexdigest()!={assembly['source_archive_sha256']!r}:
    raise RuntimeError('archive hash mismatch')
repo=root/'repo'
if repo.exists():raise RuntimeError('refusing overwrite')
repo.mkdir()
with tarfile.open(archive) as stream:
    for member in stream.getmembers():
        if not member.isfile() or not (repo/member.name).resolve().is_relative_to(repo):
            raise RuntimeError('unsafe archive path')
    stream.extractall(repo, filter='data')
rows=json.loads((root/'child_files.json').read_text())
if any(hashlib.sha256((repo/r['path']).read_bytes()).hexdigest()!=r['sha256'] for r in rows):
    raise RuntimeError('file hash mismatch')
print(json.dumps({{'status':'verified_remote_source_only_scratch','file_count':len(rows)}}))
"""
        preparation = remote_python(code)
    else:
        preparation = {"status": "existing_hash_bound_scratch"}
    results = {}
    for mode in args.modes:
        command = (
            f"cd {remote} && {PYTHON} -B probe_research_graph_g012_admission.py "
            f"--repo {remote}/repo --upstream {UPSTREAM} "
            f"--output {remote}/{args.label}_{mode} --mode {mode}"
        )
        credential_input = None
        if mode == "provider":
            from experiments.dab_api_routing import active_route, read_explicit_key
            route = active_route()
            if route is None or route.get("provider") != "deepseek_official" or route.get("model") != "deepseek-flash":
                raise RuntimeError("Explicit approved provider route is unavailable")
            credential_input = read_explicit_key(route) + "\n"
        completed = subprocess.run(SSH + [command], input=credential_input, capture_output=True, text=True, timeout=420)
        credential_input = None
        # Only the probe's structural JSON is copied out of the scratch area.
        # Avoid printing stderr from provider/SDK exceptions.
        lines = completed.stdout.strip().splitlines()
        try:
            record = json.loads(lines[-1]) if lines else {"status": "no_probe_output"}
        except ValueError:
            record = {"status": "invalid_probe_output"}
        results[mode] = {"exit_code": completed.returncode, "result": record}
        write_new(LOCAL / f"remote_{args.label}_{mode}.json", results[mode])
        print(json.dumps({"mode": mode, "exit_code": completed.returncode, "status": record.get("status", "probe_completed"),
                          "active_unique_ref_count": record.get("active_unique_ref_count"),
                          "directive_count": record.get("directive_observed_at_provider_boundary_count")}), flush=True)
    write_new(destination, {
        "schema_version": "g012_remote_admission_receipt_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "remote_synthetic_scratch": remote, "preparation": preparation, "results": results,
        "source_archive_sha256": sha(LOCAL / "source.tar.gz"),
        "probe_sha256": sha(ROOT / "experiments/probe_research_graph_g012_admission.py"),
        "driver_sha256": sha(Path(__file__)),
        "benchmark_accessed": False, "formal_evaluation_started": False,
    })


if __name__ == "__main__":
    main()
