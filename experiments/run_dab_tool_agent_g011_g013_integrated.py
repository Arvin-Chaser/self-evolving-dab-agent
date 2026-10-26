#!/usr/bin/env python3
"""Configure the isolated controller-authored G11-G13 candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.run_dab_tool_agent import build_parser, run_agent, utc_slug


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "prompts" / "dab" / "dab_tool_agent_policy_g011_g013_integrated.txt"


def configure_args(args: argparse.Namespace) -> argparse.Namespace:
    if not POLICY.is_file():
        raise FileNotFoundError(f"Integrated G11-G13 policy not found: {POLICY}")
    args.tool_agent_policy = POLICY
    args.enable_g011_g013_integrated = True
    args.enable_g0132_task_workspace = False
    args.disable_self_observation_tool = False
    args.llm_retries = 1
    args.client_max_retries = 0
    if not args.run_id:
        args.run_id = f"g011_g013_integrated_{utc_slug()}"
    return args


def main() -> int:
    parser = build_parser()
    parser.description = __doc__
    return run_agent(configure_args(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
