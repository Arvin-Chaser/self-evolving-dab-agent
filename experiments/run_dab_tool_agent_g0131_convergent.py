#!/usr/bin/env python3
"""Run the DAB agent with G13.1's budget-aware convergence policy."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.run_dab_tool_agent import build_parser, run_agent, utc_slug


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "prompts/dab/dab_tool_agent_policy_g0131_convergent.txt"


def configure_args(args: argparse.Namespace) -> argparse.Namespace:
    """Select G13.1 and keep Graph-facing helper/audit surfaces disabled."""
    if not POLICY.exists():
        raise FileNotFoundError(f"G13.1 convergence policy not found: {POLICY}")
    args.tool_agent_policy = POLICY
    args.disable_self_observation_tool = True
    args.disable_evolved_helper_tools = True
    if not args.run_id:
        args.run_id = f"g0131_convergent_{utc_slug()}"
    return args


def main() -> int:
    parser = build_parser()
    parser.description = __doc__
    return run_agent(configure_args(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
