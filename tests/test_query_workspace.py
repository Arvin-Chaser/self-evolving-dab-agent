from pathlib import Path

from experiments import run_codex_qwen_repair_launcher as repair_launcher
from experiments import run_dab_tool_agent
from experiments import run_meta_agent_evolution_loop


ROOT = Path(__file__).resolve().parents[1]


def test_query2_workspace_resolves_isolated_policy_and_empty_registry():
    workspace = ROOT / "query_workspaces/PATENTS/query2"
    args = run_dab_tool_agent.build_parser().parse_args(
        ["--query-workspace", str(workspace), "--prepare-only"]
    )
    args = run_dab_tool_agent.resolve_defaults(args)

    assert args.query_dir.name == "query2"
    assert args.tool_agent_policy == workspace / "agent/policy.txt"
    assert args.evolved_helper_registry == workspace / "agent/helpers/registry.py"
    assert run_dab_tool_agent.load_evolved_helper_specs(args) == []


def test_query1_workspace_uses_local_reproduction_patch_chain(monkeypatch):
    monkeypatch.setenv("DAB_QUERY_WORKSPACE", "query_workspaces/PATENTS/query1")
    patches = run_meta_agent_evolution_loop.resolve_parent_candidate_patches({})

    assert [path.name for path in patches] == [
        "001_script_first.patch",
        "002_two_step_selfobs.patch",
        "003_two_step_selfobs_refine.patch",
        "004_near_miss_refine.patch",
    ]
    assert all(path.exists() for path in patches)


def test_project_repair_allows_query_agent_files_but_not_workspace_state():
    profile = repair_launcher.PROFILES["data_agent_project_repair"]

    assert repair_launcher.is_allowed_file(
        "query_workspaces/PATENTS/query2/agent/helpers/new_helper.py", profile
    )
    assert repair_launcher.is_allowed_file(
        "query_workspaces/PATENTS/query2/agent/policy.txt", profile
    )
    assert not repair_launcher.is_allowed_file(
        "query_workspaces/PATENTS/query2/workspace.json", profile
    )
    assert not repair_launcher.is_allowed_file(
        "query_workspaces/PATENTS/query2/state/current_parent.json", profile
    )
