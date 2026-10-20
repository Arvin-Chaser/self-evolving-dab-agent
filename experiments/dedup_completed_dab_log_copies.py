"""Deduplicate immutable DAB run logs without removing either readable path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path("/srv/text2sql")
OFFICIAL = ROOT / "external/DataAgentBench_official"
ARCHIVES = (ROOT / "logs", ROOT / "evolution_runtime/half56_v1/campaigns")
JOURNAL = ROOT / "evolution_runtime/half56_v1/completed_log_dedup_journal.jsonl"
NAMES = {"llm_calls.jsonl", "tool_calls.jsonl", "agent_self_observations.jsonl", "final_agent.json"}
ACTIVE_MARKER = "gen015_handoff_reach_formal_r4_revision001"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for root in ARCHIVES:
        for runs in root.rglob("runs"):
            if not runs.is_dir():
                continue
            for run in runs.iterdir():
                if run.is_dir() and ACTIVE_MARKER not in run.name:
                    index.setdefault(run.name, run)
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).timestamp()
    index = run_index()
    matched = 0
    saved = 0
    examined = 0
    for target in OFFICIAL.glob("query_*/query*/logs/data_agent/*/*"):
        if target.name not in NAMES or target.is_symlink() or not target.is_file():
            continue
        run_name = target.parent.name
        if ACTIVE_MARKER in run_name or target.stat().st_mtime >= cutoff:
            continue
        source = index.get(run_name)
        if source is None:
            continue
        source = source / target.name
        if not source.is_file() or source.is_symlink():
            continue
        source_stat, target_stat = source.stat(), target.stat()
        if source_stat.st_mtime >= cutoff or source_stat.st_size != target_stat.st_size:
            continue
        if source_stat.st_dev != target_stat.st_dev or source_stat.st_ino == target_stat.st_ino:
            continue
        examined += 1
        source_hash = digest(source)
        if source_hash != digest(target):
            continue
        matched += 1
        saved += target_stat.st_blocks * 512
        if not args.apply:
            continue
        entry = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "target": str(target),
            "sha256": source_hash,
            "bytes": target_stat.st_size,
            "source_inode_before": source_stat.st_ino,
            "target_inode_before": target_stat.st_ino,
        }
        with JOURNAL.open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(entry, sort_keys=True) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        temp = target.with_name(target.name + ".dedup-link-tmp")
        if temp.exists() or temp.is_symlink():
            raise RuntimeError(f"Temporary path already exists: {temp}")
        os.link(source, temp)
        os.replace(temp, target)
        if target.stat().st_ino != source.stat().st_ino or digest(target) != source_hash:
            raise RuntimeError(f"Dedup verification failed: {target}")
    print(json.dumps({"examined": examined, "matched": matched, "estimated_saved_bytes": saved,
                      "applied": args.apply, "journal": str(JOURNAL) if args.apply else None}))


if __name__ == "__main__":
    main()
