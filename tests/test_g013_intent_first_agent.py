from __future__ import annotations

from experiments.run_dab_tool_agent import build_parser
from experiments.run_dab_tool_agent_g013_intent_first import POLICY, configure_args


def test_intent_first_launcher_selects_policy_and_removes_audit_tools() -> None:
    args = configure_args(build_parser().parse_args([]))

    assert args.tool_agent_policy == POLICY
    assert args.disable_self_observation_tool is True
    assert args.disable_evolved_helper_tools is True
    assert args.run_id.startswith("g013_intent_first_")


def test_intent_first_policy_drives_real_task_actions_without_carrier() -> None:
    policy = POLICY.read_text(encoding="utf-8")

    assert "requirement checklist" in policy
    assert "highest-impact unresolved" in policy
    assert "Use Python when cross-database joins" in policy
    assert "Before `return_answer`" in policy
    assert "Do not call a special\nrecording tool" in policy
