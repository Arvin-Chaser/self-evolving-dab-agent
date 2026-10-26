"""Synthetic hook contract check against the installed DAB upstream; no task data."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, "/srv/text2sql/external/DataAgentBench_official")
from common_scaffold.DataAgent import DataAgent  # noqa: E402


class Tool:
    def exec(self, args):
        return {"success": True, "result": {"synthetic": args["value"]}}


class Call:
    def __init__(self, identifier: str, name: str, arguments: str):
        self.id = identifier
        self.function = type("Function", (), {"name": name, "arguments": arguments})()

    def model_dump(self):
        return {"id": self.id, "function": {"name": self.function.name}}


with tempfile.TemporaryDirectory(prefix="g004_upstream_contract_") as location:
    agent = DataAgent.__new__(DataAgent)
    agent.logger = logging.getLogger("g004_upstream_contract")
    agent.tools = {"synthetic_tool": Tool()}
    agent.messages = []
    agent.result_storage = {}
    agent.file_storage_dir = Path(location)
    agent.final_result = None
    agent.terminate_reason = None

    positive = agent._handle_tool_call(Call("positive", "synthetic_tool", '{"value":7}'))
    assert positive is None
    assert agent.result_storage == {"var_positive": {"synthetic": 7}}
    assert agent.messages[-1]["role"] == "tool"
    assert agent.messages[-1]["name"] == "synthetic_tool"

    before = dict(agent.result_storage)
    negative = agent._handle_tool_call(Call("malformed", "synthetic_tool", "{invalid"))
    assert negative is None
    assert agent.result_storage == before
    assert agent.messages[-1]["tool_call_id"] == "malformed"

    unknown = agent._handle_tool_call(Call("unknown", "nonexistent_tool", "{}"))
    assert unknown is None
    assert agent.result_storage == before
    assert agent.messages[-1]["tool_call_id"] == "unknown"

print(json.dumps({
    "status": "synthetic_upstream_hook_contract_passed",
    "positive_writeback": True,
    "malformed_and_unknown_fail_safe": True,
    "task_content_used": False,
}, sort_keys=True))
