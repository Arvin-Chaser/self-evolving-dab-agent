#!/usr/bin/env python3
"""Rerun DAB tool-agent child eval for an existing candidate.

This is a thin CLI wrapper around ``run_dab_tool_agent_child_eval``.  It is
useful when candidate generation succeeded but child eval was interrupted by an
external issue such as an API timeout or environment mismatch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.run_meta_agent_evolution_loop import run_dab_tool_agent_child_eval


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--dab-root", required=True)
    parser.add_argument("--loop-dir", required=True)
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--repair-seed")
    parser.add_argument("--query-workspace")
    parser.add_argument("--max-iterations", type=int, default=10)
    args = parser.parse_args()

    if args.query_workspace:
        os.environ["DAB_QUERY_WORKSPACE"] = args.query_workspace
    os.environ["DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS"] = str(args.max_iterations)
    os.environ["DAB_TOOL_AGENT_MAX_ITERATIONS"] = str(args.max_iterations)

    loop_dir = Path(args.loop_dir).resolve()
    loop_dir.mkdir(parents=True, exist_ok=True)

    report = run_dab_tool_agent_child_eval(
        candidate_dir=Path(args.candidate_dir).resolve(),
        case_dir=Path(args.case_dir).resolve(),
        dab_root=Path(args.dab_root).resolve(),
        loop_dir=loop_dir,
        iteration=args.iteration,
        parent_agent_card=None,
        parent_prompt=None,
        repair_seed=load_json(Path(args.repair_seed)) if args.repair_seed else None,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
