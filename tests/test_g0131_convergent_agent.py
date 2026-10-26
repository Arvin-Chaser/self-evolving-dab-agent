from __future__ import annotations

from experiments.run_dab_tool_agent import build_parser
from experiments.run_dab_tool_agent_g0131_convergent import POLICY, configure_args


def test_g0131_launcher_selects_policy_and_removes_audit_tools() -> None:
    args = configure_args(build_parser().parse_args([]))

    assert args.tool_agent_policy == POLICY
    assert args.disable_self_observation_tool is True
    assert args.disable_evolved_helper_tools is True
    assert args.run_id.startswith("g0131_convergent_")


def test_g0131_policy_contains_explicit_convergence_controls() -> None:
    policy = POLICY.read_text(encoding="utf-8")
    compact = " ".join(policy.split())

    assert "necessary" in compact and "optional" in compact
    assert "at most two materially different acquisition attempts" in compact
    assert "normally use no more than three Python calls" in compact
    assert "reserve the remaining turns for synthesis" in compact
    assert "The synthesis phase is irreversible" in compact
    assert "An honest bounded answer is better than hitting the turn limit" in compact
    assert "do not emit a sidecar" in compact
