#!/usr/bin/env python3
"""Run the DAB agent with G13's requirement-coverage intent, without its audit interfaces."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.run_dab_tool_agent import build_parser, run_agent, utc_slug


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "prompts/dab/dab_tool_agent_policy_g013_intent_first.txt"


def configure_args(args: argparse.Namespace) -> argparse.Namespace:
    """Select the intent-first policy and remove G13's optional audit surfaces."""
    if not POLICY.exists():
        raise FileNotFoundError(f"G13 intent-first policy not found: {POLICY}")
    args.tool_agent_policy = POLICY
    args.disable_self_observation_tool = True
    args.disable_evolved_helper_tools = True
    if not args.run_id:
        args.run_id = f"g013_intent_first_{utc_slug()}"
    return args


def main() -> int:
    parser = build_parser()
    parser.description = __doc__
    return run_agent(configure_args(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
