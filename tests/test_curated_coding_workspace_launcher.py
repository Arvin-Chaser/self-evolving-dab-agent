"""Provider-free tests for the non-executing Coding Agent launch preflight."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.curated_coding_workspace_launcher import build_coding_agent_launch_spec
from tests.test_curated_coding_workspace_materializer import _prepare


def test_dry_run_launch_spec_verifies_prepared_workspace(tmp_path: Path) -> None:
    _source, workspace, _contract, _handoff, _request, _anchors, receipt = _prepare(tmp_path)
    spec = build_coding_agent_launch_spec(
        workspace=workspace, expected_manifest_sha256=receipt["manifest_sha256"],
        controller_test_commands=["python -m pytest coding_workspace/readonly/test_agent.py"],
    )
    assert spec["mode"] == "dry-run"
    assert spec["cwd"] == str(workspace.resolve())


def test_launch_spec_rejects_tampered_or_extra_files(tmp_path: Path) -> None:
    _source, workspace, _contract, _handoff, _request, _anchors, receipt = _prepare(tmp_path)
    (workspace / "coding_workspace/candidate/patch.py").write_text("tampered\n", encoding="ascii")
    with pytest.raises(ValueError, match="hash or size"):
        build_coding_agent_launch_spec(
            workspace=workspace, expected_manifest_sha256=receipt["manifest_sha256"], controller_test_commands=[],
        )
    (workspace / "coding_workspace/candidate/patch.py").write_text("VALUE = 1\n", encoding="ascii")
    (workspace / "extra.txt").write_text("extra\n", encoding="ascii")
    with pytest.raises(ValueError, match="inventory"):
        build_coding_agent_launch_spec(
            workspace=workspace, expected_manifest_sha256=receipt["manifest_sha256"], controller_test_commands=[],
        )
