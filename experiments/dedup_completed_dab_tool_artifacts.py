"""Hard-link byte-identical historical tool artifacts, retaining every path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path("/srv/text2sql")
OFFICIAL = ROOT / "external/DataAgentBench_official"
JOURNAL = ROOT / "evolution_runtime/half56_v1/completed_tool_artifact_dedup_journal.jsonl"
ACTIVE_MARKER = "gen015_handoff_reach_formal_r4_revision001"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).timestamp()
    groups: dict[int, list[Path]] = defaultdict(list)
    for path in OFFICIAL.glob("query_*/query*/logs/data_agent/*/exec_tool_work_dir/file_storage/*"):
        if not path.is_file() or path.is_symlink() or ACTIVE_MARKER in str(path):
            continue
        stat = path.stat()
        if stat.st_size >= 1024 * 1024 and stat.st_mtime < cutoff:
            groups[stat.st_size].append(path)

    examined = matched = saved = 0
    for size, paths in sorted(groups.items(), reverse=True):
        if len(paths) < 2:
            continue
        hashes: dict[str, Path] = {}
        for target in sorted(paths):
            examined += 1
            value = digest(target)
            source = hashes.setdefault(value, target)
            if source == target or source.stat().st_ino == target.stat().st_ino:
                continue
            if source.stat().st_dev != target.stat().st_dev:
                continue
            matched += 1
            saved += target.stat().st_blocks * 512
            if not args.apply:
                continue
            entry = {"at_utc": datetime.now(timezone.utc).isoformat(), "source": str(source),
                     "target": str(target), "sha256": value, "bytes": size,
                     "source_inode_before": source.stat().st_ino,
                     "target_inode_before": target.stat().st_ino}
            with JOURNAL.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(entry, sort_keys=True) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
            temp = target.with_name(target.name + ".dedup-link-tmp")
            if temp.exists() or temp.is_symlink():
                raise RuntimeError(f"Temporary path already exists: {temp}")
            os.link(source, temp)
            os.replace(temp, target)
            if source.stat().st_ino != target.stat().st_ino or digest(target) != value:
                raise RuntimeError(f"Dedup verification failed: {target}")
    print(json.dumps({"examined": examined, "matched": matched, "estimated_saved_bytes": saved,
                      "applied": args.apply, "journal": str(JOURNAL) if args.apply else None}))


if __name__ == "__main__":
    main()
