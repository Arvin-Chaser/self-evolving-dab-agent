#!/usr/bin/env python3
"""Run the task-facing G13 successor with a real requirement/evidence workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_dab_tool_agent import build_parser, run_agent, utc_slug


POLICY = ROOT / "prompts/dab/dab_tool_agent_policy_g0132_workspace.txt"


def configure_args(args: argparse.Namespace) -> argparse.Namespace:
    if not POLICY.exists():
        raise FileNotFoundError(f"G13.2 workspace policy not found: {POLICY}")
    args.tool_agent_policy = POLICY
    args.enable_g0132_task_workspace = True
    args.disable_self_observation_tool = True
    args.disable_evolved_helper_tools = True
    if not args.run_id:
        args.run_id = f"g0132_workspace_{utc_slug()}"
    return args


def build_workspace_parser() -> argparse.ArgumentParser:
    parser = build_parser()
    parser.description = __doc__
    # Keep the exploratory replay comparable to the frozen G13/G13.1 panel.
    # The runtime reserves the final turns for synthesis instead of widening
    # the model-call budget.
    parser.set_defaults(max_iterations=20)
    return parser


def main() -> int:
    return run_agent(configure_args(build_workspace_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
