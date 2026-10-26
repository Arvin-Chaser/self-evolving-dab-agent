#!/usr/bin/env python3
"""Collect hash-bound, anonymous G1 outcome/trigger counts without answer text."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/research_graph_baseline_20261016"
TARGET = OUT / "g001_mechanism_counts_v1.json"
SSH = ["ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-i", "C:/Users/34934/.ssh/codex_ct104", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]
REMOTE_CODE = r'''
import hashlib
import json
from collections import Counter
from pathlib import Path

base = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
progress = base / "g001_revision001/evaluation/baseline_g001_deadline_reserve_nohint_56_v1/multi_query_progress.json"
rows = json.loads(progress.read_text(encoding="utf-8"))["queries"]
counts = Counter()
errors = Counter()
for row in rows:
    bound = (row.get("deadline_reserve_trigger") or {}).get("bound") is True
    verdict = row.get("strict_match_passed")
    grade = "true" if verdict is True else "false" if verdict is False else "unknown"
    counts[("bound" if bound else "unbound", row.get("status"), grade)] += 1
    if row.get("status") == "failed":
        message = str(row.get("run_error") or "")
        category = message.split(":", 1)[0] if ":" in message else "unclassified"
        errors[category if category.isidentifier() else "unclassified"] += 1
print(json.dumps({
    "schema_version": "g001_anonymous_mechanism_counts_v1",
    "source_progress_sha256": hashlib.sha256(progress.read_bytes()).hexdigest(),
    "source_graph_sha256": hashlib.sha256((base / "graph/g001_graph.json").read_bytes()).hexdigest(),
    "cohorts": [{"trigger": trigger, "status": status, "strict_verdict": strict,
                 "count": count} for (trigger, status, strict), count in sorted(counts.items())],
    "failed_error_classes": dict(errors),
    "total": len(rows),
    "answer_blind": True,
}, sort_keys=True))
'''


def main() -> None:
    if TARGET.exists():
        raise RuntimeError("G1 mechanism sidecar already exists")
    graph = json.loads((OUT / "g001_graph.json").read_text(encoding="utf-8"))
    evidence = json.loads((OUT / "g001_evidence.json").read_text(encoding="utf-8"))["node"]
    if graph.get("status") != "four_nodes_complete" or graph.get("generation") != 1:
        raise RuntimeError("G1 Graph is not finalized")
    proc = subprocess.run(SSH, input=REMOTE_CODE, text=True, encoding="utf-8",
                          capture_output=True, timeout=60, check=False)
    if proc.returncode:
        raise RuntimeError(f"Remote count collection failed: exit {proc.returncode}")
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError("SSH did not begin with disk check")
    result = json.loads(lines[-1])
    import hashlib
    graph_sha = hashlib.sha256((OUT / "g001_graph.json").read_bytes()).hexdigest()
    if (result["source_graph_sha256"] != graph_sha or
            result["source_progress_sha256"] != evidence["artifact_refs"]["progress_sha256"] or
            result["total"] != 56 or sum(row["count"] for row in result["cohorts"]) != 56 or
            sum(row["count"] for row in result["cohorts"] if row["trigger"] == "bound") != 5):
        raise RuntimeError("Anonymous G1 counts do not match frozen Evidence")
    if any(key not in {"FatalError"} for key in result["failed_error_classes"]):
        raise RuntimeError("Unrecognized failure category; review collector before use")
    with TARGET.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "collected", "cohorts": result["cohorts"],
                      "failed_error_classes": result["failed_error_classes"]}, sort_keys=True))


if __name__ == "__main__":
    main()
