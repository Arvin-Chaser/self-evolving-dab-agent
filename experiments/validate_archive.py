#!/usr/bin/env python3
"""Validate the lightweight agent/candidate archive indexes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid JSONL row: {exc}") from exc
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", default="archive", type=Path)
    args = parser.parse_args()

    root = args.archive_root
    agents = load_jsonl(root / "indexes/agents.jsonl")
    candidates = load_jsonl(root / "indexes/candidates.jsonl")
    json_paths = [
        root / "indexes/lineage.json",
        root / "indexes/selection_scores.json",
        root / "indexes/recommended_next_steps.json",
    ]
    missing = []
    for row in agents + candidates:
        card = Path(row["card"])
        if not card.exists():
            missing.append(str(card))
        else:
            json.loads(card.read_text(encoding="utf-8"))
    for path in json_paths:
        if not path.exists():
            missing.append(str(path))
        else:
            json.loads(path.read_text(encoding="utf-8"))
    if missing:
        raise SystemExit("missing archive refs: " + ", ".join(missing))

    summary = {
        "status": "archive_valid",
        "agent_count": len(agents),
        "candidate_count": len(candidates),
        "agents": [row["agent_id"] for row in agents],
        "candidates": [row["candidate_id"] for row in candidates],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

