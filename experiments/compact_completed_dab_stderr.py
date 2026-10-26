"""Losslessly replace only completed Gen12-14 run stderr with verified gzip."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN = Path("/srv/text2sql/evolution_runtime/half56_v1/campaigns/dataset17_half56_deepseek_v1_20261011")
RUNS = (
    "gen_012_obligation_r2/evaluation/gen012_obligation_formal_r2",
    "gen_013_grounding_r3/evaluation/gen013_grounding_formal_r3",
    "gen_014_recovery_r3/evaluation/gen014_recovery_formal_r3",
)
TARGET_FREE = 11 * 1024**3


def stream_hash(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024**2), b""):
        digest.update(block)
    return digest.hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return stream_hash(stream)


def append_record(journal, record):
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def compact(path, journal):
    original_stat = path.stat()
    original_sha = file_hash(path)
    compressed = path.with_name(path.name + ".gz")
    assert not compressed.exists(), compressed
    with path.open("rb") as source, compressed.open("xb") as target:
        with gzip.GzipFile(filename="", fileobj=target, mode="wb", compresslevel=1, mtime=0) as archive:
            shutil.copyfileobj(source, archive, length=1024**2)
        target.flush()
        os.fsync(target.fileno())
    with gzip.open(compressed, "rb") as restored:
        assert stream_hash(restored) == original_sha, "Lossless verification failed"
    assert path.stat().st_size == original_stat.st_size
    assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert file_hash(path) == original_sha, "Original changed during compression"
    record = {"original": str(path), "archive": str(compressed), "original_bytes": original_stat.st_size,
              "compressed_bytes": compressed.stat().st_size, "original_sha256": original_sha,
              "archive_sha256": file_hash(compressed), "restore_sha256_verified": True,
              "original_mtime_ns": original_stat.st_mtime_ns, "at_utc": datetime.now(timezone.utc).isoformat()}
    # Persist recovery metadata before unlinking the verified uncompressed copy.
    append_record(journal, {"state": "verified_before_unlink", **record})
    path.unlink()
    append_record(journal, {"state": "uncompressed_copy_removed", **record})
    return record


def inventory():
    targets = []
    for relative in RUNS:
        run = (CAMPAIGN / relative).resolve(strict=True)
        assert run.is_relative_to(CAMPAIGN.resolve(strict=True))
        summary = json.loads((run / "multi_query_summary.json").read_text(encoding="utf-8"))
        assert len(summary["per_query_feedback"]) == 56, run
        launch = json.loads((run.parent.parent / "launch_manifest.json").read_text(encoding="utf-8"))
        assert not Path("/proc").joinpath(str(launch["pid"])).exists(), "Old launcher PID still exists"
        for path in (run / "logs").glob("*.run.stderr"):
            assert not path.is_symlink()
            resolved = path.resolve(strict=True)
            assert resolved.parent == (run / "logs").resolve(strict=True)
            if path.stat().st_size >= 1024**2 and not path.with_name(path.name + ".gz").exists():
                targets.append(path)
    return sorted(targets, key=lambda path: path.stat().st_size, reverse=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    assert os.name == "posix"
    running = subprocess.run(["pgrep", "-f", "[r]un_multi_query_baseline.py"], capture_output=True)
    assert running.returncode == 1, "Evaluation running or process inspection failed"
    targets = inventory()
    plan = {"exact_targets": [str(path) for path in targets], "count": len(targets),
            "uncompressed_bytes": sum(path.stat().st_size for path in targets),
            "free_bytes": shutil.disk_usage(CAMPAIGN).free, "target_free_bytes": TARGET_FREE}
    print(json.dumps(plan), flush=True)
    if not args.execute:
        return
    journal = CAMPAIGN / "stderr_lossless_compaction_v1.jsonl"
    append_record(journal, {"state": "plan", **plan})
    for path in targets:
        if shutil.disk_usage(CAMPAIGN).free >= TARGET_FREE:
            break
        record = compact(path, journal)
        print(json.dumps(record), flush=True)
    final = {"state": "finished", "free_bytes": shutil.disk_usage(CAMPAIGN).free}
    append_record(journal, final)
    print(json.dumps(final), flush=True)


if __name__ == "__main__":
    main()
