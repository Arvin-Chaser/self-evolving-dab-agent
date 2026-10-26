from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.g0132_task_workspace import (
    STATE_MESSAGE_PREFIX,
    TaskWorkspaceEngine,
    TaskWorkspaceRuntime,
    WorkspaceValidationError,
    canonical_action_signature,
    install_task_workspace,
)
from experiments.run_dab_tool_agent_g0132_workspace import (
    POLICY,
    build_workspace_parser,
    configure_args,
)


def plan_rows():
    return [
        {
            "requirement_id": "answer_metric",
            "description": "Compute the requested metric.",
            "priority": "must",
            "success_criterion": "A database-derived value is available.",
        },
        {
            "requirement_id": "format",
            "description": "Return the requested output format.",
            "priority": "should",
            "success_criterion": "The final text follows the requested shape.",
        },
    ]


def test_workspace_requires_real_evidence_before_satisfied():
    engine = TaskWorkspaceEngine()
    engine.set_plan(plan_rows())
    with pytest.raises(WorkspaceValidationError, match="supporting evidence"):
        engine.update(
            [
                {
                    "requirement_id": "answer_metric",
                    "status": "satisfied",
                    "status_reason": "looks done",
                }
            ]
        )

    engine.record_action_result(
        requirement_id="answer_metric",
        tool_name="query_db",
        purpose="compute the metric",
        signature="sig-1",
        success=True,
        result_refs=["var_query_1"],
    )
    engine.update(
        [
            {
                "requirement_id": "answer_metric",
                "evidence_ref": "var_query_1",
                "finding": "The grouped query produced the requested value.",
                "effect": "supports",
                "status": "satisfied",
                "status_reason": "The success criterion is met by var_query_1.",
            }
        ]
    )
    state = engine.public_state()
    assert state["requirements"][0]["status"] == "satisfied"
    assert state["pending_evidence"] == []
    assert state["recommended_action"]["requirement_id"] == "format"


def test_evidence_cannot_be_bound_to_the_wrong_requirement():
    engine = TaskWorkspaceEngine()
    engine.set_plan(plan_rows())
    engine.record_action_result(
        requirement_id="answer_metric",
        tool_name="query_db",
        purpose="compute the metric",
        signature="sig-1",
        success=True,
        result_refs=["var_query_1"],
    )
    with pytest.raises(WorkspaceValidationError, match="belongs to answer_metric"):
        engine.update(
            [
                {
                    "requirement_id": "format",
                    "evidence_ref": "var_query_1",
                    "finding": "wrong binding",
                    "effect": "supports",
                }
            ]
        )


def test_runtime_blocks_repetition_and_enforces_synthesis_budget(tmp_path: Path):
    runtime = TaskWorkspaceRuntime(
        path=tmp_path / "workspace.json",
        synthesis_reserve_turns=6,
        final_verification_actions=1,
        compact_evidence_messages=True,
        max_view_chars=6000,
    )
    runtime.apply({"operation": "set_plan", "requirements": plan_rows()})
    args = {
        "query": "SELECT COUNT(*) FROM items",
        "workspace_requirement_id": "answer_metric",
        "workspace_action_purpose": "count relevant rows",
    }
    allowed, _, metadata = runtime.prepare_action("query_db", args)
    assert allowed is True
    assert metadata is not None
    runtime.record_action_result(
        tool_name="query_db",
        metadata=metadata,
        success=True,
        result_refs=["var_query_1"],
    )
    allowed, reason, _ = runtime.prepare_action("query_db", args)
    assert allowed is False
    assert "repetition" in reason

    runtime.maybe_enter_synthesis(llm_call_count=34, max_iterations=40)
    assert runtime.engine.phase == "synthesis"
    changed = dict(args, query="SELECT COUNT(*) FROM items WHERE active")
    allowed, _, metadata = runtime.prepare_action("query_db", changed)
    assert allowed is True
    assert metadata is not None
    runtime.record_action_result(
        tool_name="query_db",
        metadata=metadata,
        success=True,
        result_refs=["var_query_2"],
    )
    assert runtime.final_only is True
    another = dict(args, query="SELECT COUNT(*) FROM items WHERE archived")
    allowed, reason, _ = runtime.prepare_action("query_db", another)
    assert allowed is False
    assert "no further acquisition" in reason


def test_runtime_enforces_requirement_and_python_action_caps(tmp_path: Path):
    runtime = TaskWorkspaceRuntime(
        path=tmp_path / "workspace.json",
        synthesis_reserve_turns=6,
        final_verification_actions=1,
        compact_evidence_messages=True,
        max_view_chars=6000,
        max_actions_per_requirement=3,
        max_python_actions=3,
    )
    runtime.apply({"operation": "set_plan", "requirements": plan_rows()})

    for index in range(3):
        args = {
            "code": f"print({index})",
            "workspace_requirement_id": "answer_metric",
            "workspace_action_purpose": f"bounded calculation {index}",
        }
        allowed, _, metadata = runtime.prepare_action("execute_python", args)
        assert allowed is True
        assert metadata is not None
        runtime.record_action_result(
            tool_name="execute_python",
            metadata=metadata,
            success=True,
            result_refs=[f"var_python_{index}"],
        )

    allowed, reason, _ = runtime.prepare_action(
        "execute_python",
        {
            "code": "print(4)",
            "workspace_requirement_id": "format",
            "workspace_action_purpose": "one more calculation",
        },
    )
    assert allowed is False
    assert "execute_python action cap" in reason

    allowed, reason, _ = runtime.prepare_action(
        "query_db",
        {
            "query": "SELECT 4",
            "workspace_requirement_id": "answer_metric",
            "workspace_action_purpose": "fourth action for the same requirement",
        },
    )
    assert allowed is False
    assert "requirement action cap" in reason


def test_message_compaction_requires_absorbed_evidence(tmp_path: Path):
    runtime = TaskWorkspaceRuntime(
        path=tmp_path / "workspace.json",
        synthesis_reserve_turns=6,
        final_verification_actions=1,
        compact_evidence_messages=True,
        max_view_chars=6000,
    )
    runtime.apply({"operation": "set_plan", "requirements": plan_rows()})
    runtime.engine.record_action_result(
        requirement_id="answer_metric",
        tool_name="query_db",
        purpose="metric",
        signature="sig-1",
        success=True,
        result_refs=["var_query_1"],
    )
    messages = [
        {"role": "system", "content": "base"},
        {"role": "tool", "content": "large result under var_query_1"},
        *({"role": "tool", "content": f"recent {index}"} for index in range(5)),
    ]
    runtime.compact_messages(messages)
    assert messages[1]["content"] == "large result under var_query_1"
    runtime.apply(
        {
            "operation": "update",
            "updates": [
                {
                    "requirement_id": "answer_metric",
                    "evidence_ref": "var_query_1",
                    "finding": "A bounded aggregate was returned.",
                    "effect": "supports",
                }
            ],
        }
    )
    runtime.compact_messages(messages)
    assert messages[1]["content"].startswith("[WORKSPACE_COMPACTED]")


def test_old_workspace_snapshots_are_replaced_not_accumulated(tmp_path: Path):
    runtime = TaskWorkspaceRuntime(
        path=tmp_path / "workspace.json",
        synthesis_reserve_turns=6,
        final_verification_actions=1,
        compact_evidence_messages=True,
        max_view_chars=6000,
    )
    messages = [
        {"role": "tool", "name": "manage_task_workspace", "content": "old state"},
        {"role": "tool", "name": "manage_task_workspace", "content": "current state"},
    ]
    runtime.compact_messages(messages)
    assert messages[0]["content"].startswith("[WORKSPACE_COMPACTED]")
    assert messages[1]["content"] == "current state"


def test_synthesis_gets_one_tool_visible_turn_then_becomes_final_only(tmp_path: Path):
    runtime = TaskWorkspaceRuntime(
        path=tmp_path / "workspace.json",
        synthesis_reserve_turns=6,
        final_verification_actions=1,
        compact_evidence_messages=True,
        max_view_chars=6000,
    )
    runtime.apply({"operation": "set_plan", "requirements": plan_rows()})
    runtime.maybe_enter_synthesis(llm_call_count=34, max_iterations=40)
    assert runtime.final_only is False
    runtime.maybe_enter_synthesis(llm_call_count=35, max_iterations=40)
    assert runtime.final_only is True


class FakeBaseTool:
    def __init__(self, log_path, name):
        self.log_path = Path(log_path)
        self.name = name

    def to_dict(self):
        return {"name": self.name}

    def get_spec(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.name,
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }

    def _check_args(self, args):
        return args

    def _exec(self, args):
        return {"args": args}

    def exec(self, args):
        try:
            return {"success": True, "result": self._exec(self._check_args(args))}
        except Exception as exc:
            return {"success": False, "result": str(exc)}

    def clean_up(self):
        return None


class FakeAgent:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.tool_log_path = root_dir / "tools.jsonl"
        self.tools = {
            "query_db": FakeBaseTool(self.tool_log_path, "query_db"),
            "return_answer": FakeBaseTool(self.tool_log_path, "return_answer"),
        }
        self.messages = [{"role": "system", "content": "base"}]
        self.result_storage = {}
        self.llm_call_count = 0
        self.max_iterations = 10
        self.last_visible_tools = []

    def _handle_tool_call(self, tool_call):
        args = json.loads(tool_call.function.arguments)
        result = self.tools[tool_call.function.name].exec(args)
        if result["success"]:
            self.result_storage[f"var_{tool_call.id}"] = result["result"]
        return result

    def call_llm(self):
        self.last_visible_tools = list(self.tools)
        return None

    def to_dict(self):
        return {"tools": list(self.tools)}


class FakeToolCall:
    def __init__(self, tool_call_id: str, name: str, arguments: dict):
        self.id = tool_call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))

    def model_dump(self):
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


def test_installation_adds_real_tool_metadata_and_final_only_mode(tmp_path: Path):
    module = SimpleNamespace(BaseTool=FakeBaseTool, DataAgent=FakeAgent)
    args = SimpleNamespace(
        enable_g0132_task_workspace=True,
        g0132_synthesis_reserve_turns=2,
        g0132_final_verification_actions=0,
        disable_g0132_message_compaction=False,
        g0132_workspace_max_view_chars=6000,
    )
    attachment = install_task_workspace(module, args)
    assert attachment["installed"] is True
    agent = module.DataAgent(tmp_path)
    assert "manage_task_workspace" in agent.tools
    query_spec = agent.tools["query_db"].get_spec()["function"]["parameters"]
    assert "workspace_requirement_id" in query_spec["required"]
    assert "workspace_action_purpose" in query_spec["required"]

    agent._handle_tool_call(
        FakeToolCall(
            "plan1",
            "manage_task_workspace",
            {"operation": "set_plan", "requirements": plan_rows()},
        )
    )
    assert "var_plan1" not in agent.result_storage
    call = FakeToolCall(
        "q1",
        "query_db",
        {
            "query": "SELECT 1",
            "workspace_requirement_id": "answer_metric",
            "workspace_action_purpose": "verify connectivity",
        },
    )
    agent._handle_tool_call(call)
    assert agent.result_storage["var_q1"]["args"] == {"query": "SELECT 1"}

    agent.llm_call_count = 8
    agent.call_llm()
    assert agent.last_visible_tools == ["return_answer"]
    assert any(
        message.get("content", "").startswith(STATE_MESSAGE_PREFIX)
        for message in agent.messages
    )
    assert (tmp_path / "task_workspace.json").is_file()


def test_launcher_enables_workspace_and_uses_wider_default():
    assert POLICY.is_file()
    args = SimpleNamespace(
        tool_agent_policy=None,
        enable_g0132_task_workspace=False,
        disable_self_observation_tool=False,
        disable_evolved_helper_tools=False,
        run_id=None,
    )
    configured = configure_args(args)
    assert configured.enable_g0132_task_workspace is True
    assert configured.disable_self_observation_tool is True
    assert configured.disable_evolved_helper_tools is True
    assert configured.tool_agent_policy == POLICY
    assert configured.run_id.startswith("g0132_workspace_")
    parsed = build_workspace_parser().parse_args([])
    assert parsed.max_iterations == 20
    assert parsed.g0132_max_actions_per_requirement == 3
    assert parsed.g0132_max_python_actions == 3


def test_action_signature_normalizes_sql_whitespace_and_case():
    first = canonical_action_signature("query_db", {"query": "SELECT  *  FROM T"})
    second = canonical_action_signature("query_db", {"query": " select * from t "})
    assert first == second
