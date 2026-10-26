#!/usr/bin/env python3
"""No-model, no-task probe of G1 reserve behavior on the real upstream dispatcher."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

from experiments import run_dab_tool_agent as runner
from experiments import run_multi_query_baseline as batch


UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")


class Tool:
    def __init__(self):
        self.calls = 0

    def exec(self, args):
        self.calls += 1
        return {"success": True, "result": "ok"}


class Call:
    def __init__(self, name, arguments, index):
        self.id = f"probe_{index}"
        self.function = types.SimpleNamespace(name=name, arguments=json.dumps(arguments))

    def model_dump(self):
        return {"id": self.id, "function": {"name": self.function.name,
                                               "arguments": self.function.arguments}}


def run_case(reserve_window: bool) -> dict:
    sys.path.insert(0, str(UPSTREAM))
    import common_scaffold.DataAgent as upstream

    class Agent(upstream.DataAgent):
        def call_llm(self):
            self.advertised = set(self.tools)
            self.llm_call_count += 1
            return types.SimpleNamespace(content=None, tool_calls=[
                Call("query_db", {"query": "SELECT 1"}, 1),
                Call("return_answer", {"answer": "probe"}, 2),
            ])

    module = types.SimpleNamespace(DataAgent=Agent)
    args = argparse.Namespace(output_root=None, run_id=None)
    seconds_left = 90 if reserve_window else 300
    env = batch.task_deadline_env({}, deadline_monotonic=time.monotonic() + seconds_left)
    with patch.dict(os.environ, env):
        state = runner.install_deadline_reserve_signal(module, args)
    agent = object.__new__(Agent)
    agent.tools = {"query_db": Tool(), "return_answer": Tool()}
    agent.messages = []
    agent.logger = logging.getLogger("g001_upstream_probe")
    agent.result_storage = {}
    agent.final_result = None
    agent.terminate_reason = None
    agent.llm_call_count = 0
    agent.max_iterations = 10
    agent.file_storage_dir = Path("/tmp")
    response = agent.call_llm()
    advertised = agent.advertised
    agent.handle_reponse(response)
    query_calls = agent.tools["query_db"].calls
    if reserve_window:
        assert advertised == {"return_answer"}
        assert query_calls == 0
        assert state["bound"] is True
    else:
        assert advertised == {"query_db", "return_answer"}
        assert query_calls == 1
        assert state["bound"] is False
    assert agent.final_result == "probe" and agent.terminate_reason == "return_answer"
    return {"reserve_window": reserve_window, "query_executed": bool(query_calls),
            "answer_submitted": True, "trigger_bound": state["bound"]}


if __name__ == "__main__":
    print(json.dumps({"status": "passed", "cases": [run_case(False), run_case(True)]}, sort_keys=True))
