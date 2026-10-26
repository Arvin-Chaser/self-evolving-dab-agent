"""Synthetic G5 hook check against real installed DAB upstream; no task data."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(
    "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/"
    "g005_revision001/source"
)
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, "/srv/text2sql/external/DataAgentBench_official")
from common_scaffold import DataAgent as upstream_module  # noqa: E402
from experiments.g005_provenance_sidecar import (  # noqa: E402
    SIDECAR_FILENAME,
    install_provenance_sidecar,
    read_sidecar,
)


class Tool:
    def exec(self, args):
        return {"success": True, "result": {"synthetic": args["value"]}}


class Call:
    def __init__(self, identifier: str, name: str, arguments: str):
        self.id = identifier
        self.function = type("Function", (), {"name": name, "arguments": arguments})()

    def model_dump(self):
        return {"id": self.id, "function": {"name": self.function.name}}


with tempfile.TemporaryDirectory(prefix="g005_upstream_contract_") as location:
    sidecar = Path(location) / SIDECAR_FILENAME
    install_provenance_sidecar(
        upstream_module,
        SimpleNamespace(g005_provenance_sidecar=True, g005_sidecar_path=sidecar),
    )
    agent = upstream_module.DataAgent.__new__(upstream_module.DataAgent)
    agent.logger = logging.getLogger("g005_upstream_contract")
    agent.tools = {"synthetic_tool": Tool()}
    agent.messages = []
    agent.result_storage = {}
    agent.file_storage_dir = Path(location)
    agent.tool_log_path = Path(location) / "tool_calls.jsonl"
    agent.final_result = None
    agent.terminate_reason = None

    assert agent._handle_tool_call(Call("positive", "synthetic_tool", '{"value":7}')) is None
    assert agent.result_storage == {"var_positive": {"synthetic": 7}}
    assert agent.messages[-1]["name"] == "synthetic_tool"
    before = dict(agent.result_storage)
    assert agent._handle_tool_call(Call("malformed", "synthetic_tool", "{invalid")) is None
    assert agent.result_storage == before
    assert agent.messages[-1]["tool_call_id"] == "malformed"
    assert agent._handle_tool_call(Call("unknown", "nonexistent_tool", "{}")) is None
    assert agent.result_storage == before
    assert agent.messages[-1]["tool_call_id"] == "unknown"
    rows = read_sidecar(sidecar)
    assert rows["exists"] is True
    assert len(rows["events"]) == 6
    raw = sidecar.read_text(encoding="utf-8")
    assert "synthetic_tool" not in raw and "nonexistent_tool" not in raw
    assert "value" not in raw and "malformed" not in raw

print(json.dumps({
    "status": "g005_synthetic_upstream_hook_contract_passed",
    "positive_writeback": True,
    "malformed_and_unknown_fail_safe": True,
    "sidecar_events": 6,
    "task_content_used": False,
}, sort_keys=True))
