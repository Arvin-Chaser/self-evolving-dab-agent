import copy
import ast
from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import logging
import os
import time
from unittest.mock import patch

from experiments.dab_runtime_repair_v1 import (
    Journal, ProviderFailure, UnsafeResume, atomic_json, compose_description,
    request_with_recovery,
    install,
)


class StatusError(Exception):
    def __init__(self, status):
        self.status_code = status


@dataclass
class Controller:
    trace_emitter: object = None
    checkpoints: list = field(default_factory=list)
    restored_intents: set = field(default_factory=set)


class Crash(BaseException):
    pass


class FakeAgent:
    def __init__(self, root):
        self.root_dir = root
        self.exec_tool_work_dir = root / "workspace"
        self.exec_tool_work_dir.mkdir(exist_ok=True)
        self.messages = [{"role": "user", "content": "question"}]
        self.result_storage = {}
        self.llm_call_count = 7
        self.final_result = None
        self.terminate_reason = None
        self.turn_state = {"progress": "known"}
        self.checkpoint_controller = Controller(restored_intents={"query_db"})
        self.executions = []

    def _handle_tool_call(self, call):
        self.executions.append(call.id)
        self.result_storage[call.id] = "completed"
        self.messages.append({"role": "tool", "tool_call_id": call.id, "content": "completed"})
        (self.exec_tool_work_dir / (call.id + ".txt")).write_text("side effect")

    def _handle_content(self, content):
        self.final_result = content


class RuntimeRepairTests(unittest.TestCase):
    def test_actual_upstream_agent_retry_and_restart_retains_completed_tool(self):
        # Execute actual upstream DataAgent methods, replacing only external
        # client/DB/Docker dependencies; no provider or database inference call.
        official = Path(__file__).resolve().parents[1] / "external/DataAgentBench_official"
        if not official.exists():
            official = Path("/srv/text2sql/external/DataAgentBench_official")
        source = official / "common_scaffold/DataAgent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
                     and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call))]
        executions = []
        db_loads = []
        requests = []
        faults = []
        def msg(name, ident, arguments):
            data = {"content": None, "tool_calls": [{"id": ident, "type": "function",
                      "function": {"name": name, "arguments": json.dumps(arguments)}}]}
            return SimpleNamespace(model_dump=lambda: copy.deepcopy(data))
        answers = [msg("query_db", "one", {"db_name": "db", "query": "SELECT 1"}),
                   msg("return_answer", "two", {"answer": "done"})]
        def create(**kw):
            requests.append(copy.deepcopy(kw))
            if faults:
                raise faults.pop(0)
            message = answers.pop(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                                   to_dict=lambda: {"choices": [{"message": message.model_dump()}]})
        class Tool:
            def __init__(self, log_path, name, *pos, **kwargs):
                self.log_path = log_path; self.name = name
                if name == "query_db":
                    db_loads.append(kwargs.get("check_load"))
            def get_spec(self):
                return {"type": "function", "function": {"name": self.name}}
            def exec(self, args):
                executions.append(self.name)
                return {"success": True, "result": [1]}
            def to_dict(self):
                return {"name": self.name}
            def clean_up(self):
                pass
        prompt = SimpleNamespace(PREVIEW_LENGTH=10000,
            init_messages=lambda **kw: [{"role": "user", "content": kw["db_description"]}])
        ns = {"Path": Path, "datetime": __import__("datetime").datetime, "time": time,
              "logging": logging, "os": os, "json": json, "load_dotenv": lambda: None,
              "AzureOpenAI": lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
              "OpenAI": None, "prompt_builder": prompt, "BaseTool": Tool,
              "QueryDBTool": Tool, "ListDBTool": Tool, "ExecTool": Tool, "ReturnAnswerTool": Tool,
              "ChatCompletionMessage": object, "ChatCompletionMessageToolCall": object}
        exec(compile(tree, str(source), "exec"), ns)
        class Wrapped(ns["DataAgent"]):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.turn_state = {"known": "state"}
                self.checkpoint_controller = Controller()
        module = SimpleNamespace(DataAgent=Wrapped, ExecTool=Tool)
        with tempfile.TemporaryDirectory() as folder:
            family = Path(folder); query = family / "query1"; query.mkdir()
            (query / "query.json").write_text(json.dumps({"query": "q"}))
            cfg = family / "db_config.yaml"; cfg.write_text("db_clients: {}")
            args = SimpleNamespace(dab_upstream_root=official, query_dir=query, db_config=cfg,
                repaired_db_description="db: SQLite", deployment_name="gpt-test", openai_compatible_base_url="fake",
                exec_python_timeout=600, llm_timeout=600, run_id="same_run")
            install(module, args)
            init = dict(query_dir=query, db_description="wrong hint", db_config_path=str(cfg),
                        deployment_name="gpt-test", root_name="same_run")
            a = module.DataAgent(**init)
            a.call_llm(); a.journal.dispatch()
            self.assertEqual(executions, ["query_db"])
            faults.append(StatusError(503))
            from experiments import dab_runtime_repair_v1 as repair
            original = repair.request_with_recovery
            with patch.object(repair, "request_with_recovery", side_effect=lambda req, save: original(req, save, lambda delay: (_ for _ in ()).throw(Crash()))):
                with self.assertRaises(Crash):
                    a.call_llm()
            if hasattr(a, "_recovery_lease"):
                a._recovery_lease.close()
            with patch.dict(os.environ, {"DAB_REPAIR_RESUME": "1"}):
                b = module.DataAgent(**init)
            self.assertEqual(b.result_storage, {"var_one": [1]})
            self.assertEqual(b.turn_state, {"known": "state"})
            self.assertEqual(b.llm_call_count, 1)
            self.assertEqual(b.run(), "done")
            self.assertEqual(executions, ["query_db", "return_answer"])
            self.assertEqual(db_loads, [True, False])
            self.assertEqual(requests[1], requests[2])
            self.assertIn("db: SQLite", requests[0]["messages"][0]["content"])
            if hasattr(b, "_recovery_lease"):
                b._recovery_lease.close()

    def test_description_with_hints_only_and_full_description(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "db_description.txt").write_text("stockinfo_database; stocktrade_database")
            (p / "db_description_withhint.txt").write_text("HINTS: financial status")
            self.assertEqual(compose_description(p), "stockinfo_database; stocktrade_database\n\nHINTS: financial status")
            (p / "db_description_withhint.txt").write_text("stockinfo_database; stocktrade_database\nHINTS")
            self.assertEqual(compose_description(p), "stockinfo_database; stocktrade_database\nHINTS")
            (p / "db_description_withhint.txt").unlink()
            self.assertEqual(compose_description(p), "stockinfo_database; stocktrade_database")

    def test_retry_same_request_after_500_503_429_transport(self):
        request = {"messages": [{"role": "tool", "content": "already executed"}], "tools": ["spec"]}
        seen, events, sleeps = [], [], []
        faults = [StatusError(500), StatusError(503), StatusError(429), ConnectionError(), TimeoutError()]
        def call():
            seen.append(copy.deepcopy(request))
            if faults:
                raise faults.pop(0)
            return "answer"
        self.assertEqual(request_with_recovery(call, events.append, sleeps.append), "answer")
        self.assertTrue(all(r == request for r in seen))
        self.assertEqual(sleeps, [5, 10, 20, 40, 80])
        self.assertEqual(len(events), 5)

    def test_permanent_auth_validation_not_retried(self):
        for code in (400, 401, 403, 404, 422):
            events, sleeps = [], []
            with self.assertRaises(ProviderFailure):
                request_with_recovery(lambda: (_ for _ in ()).throw(StatusError(code)), events.append, sleeps.append)
            self.assertEqual(sleeps, [])
            self.assertEqual(events[0]["classification"], "permanent_provider_failure")

    def test_completed_tool_not_replayed_and_pending_continues(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = FakeAgent(root)
            j = Journal(a, {"source": "source1", "config": "cfg1"})
            response = {"tool_calls": [{"id": "a", "function": {"name": "side_effect", "arguments": "{}"}},
                                       {"id": "b", "function": {"name": "side_effect", "arguments": "{}"}}]}
            j.accept(SimpleNamespace(model_dump=lambda: response))
            original_save = j.save
            def crash_after_first_commit(*args):
                original_save(*args)
                if j.cursor == 1 and j.inflight is None:
                    raise Crash()
            j.save = crash_after_first_commit
            with self.assertRaises(Crash):
                j.dispatch()
            self.assertEqual(a.executions, ["a"])
            b = FakeAgent(root)
            resumed = Journal(b, j.binding)
            resumed.restore(Journal.read(j.path, j.binding, b.exec_tool_work_dir))
            self.assertEqual(b.result_storage, {"a": "completed"})
            self.assertEqual(b.llm_call_count, 7)
            self.assertEqual(b.turn_state, a.turn_state)
            self.assertEqual(b.checkpoint_controller.restored_intents, {"query_db"})
            resumed.dispatch()
            self.assertEqual(b.executions, ["b"])
            self.assertEqual(b.result_storage, {"a": "completed", "b": "completed"})
            self.assertEqual(len([x for x in b.messages if x.get("role") == "assistant"]), 1)

    def test_ambiguous_tool_rejects_resume_without_reexecution(self):
        with tempfile.TemporaryDirectory() as folder:
            a = FakeAgent(Path(folder)); j = Journal(a, {"source": "1"})
            j.inflight = {"tool_call_id": "a"}; j.save()
            with self.assertRaisesRegex(UnsafeResume, "Ambiguous"):
                Journal.read(j.path, j.binding, a.exec_tool_work_dir)
            self.assertEqual(a.executions, [])

    def test_mismatch_artifact_change_and_integrity_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a = FakeAgent(Path(folder)); j = Journal(a, {"source": "1", "config": "c1"}); j.save()
            for binding in ({"source": "2", "config": "c1"}, {"source": "1", "config": "c2"}):
                with self.assertRaises(UnsafeResume):
                    Journal.read(j.path, binding, a.exec_tool_work_dir)
            (a.exec_tool_work_dir / "changed").write_text("different")
            with self.assertRaisesRegex(UnsafeResume, "Workspace"):
                Journal.read(j.path, j.binding, a.exec_tool_work_dir)
            envelope = json.loads(j.path.read_text()); envelope["payload"]["state"]["llm_call_count"] = 0
            j.path.write_text(json.dumps(envelope))
            with self.assertRaises(UnsafeResume):
                Journal.read(j.path, j.binding, a.exec_tool_work_dir)

    def test_atomic_replace_failure_preserves_previous_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "state.json"; atomic_json(p, {"old": 1})
            with patch("experiments.dab_runtime_repair_v1.os.replace", side_effect=OSError("fault")):
                with self.assertRaises(OSError):
                    atomic_json(p, {"new": 2})
            self.assertEqual(json.loads(p.read_text()), {"old": 1})
            self.assertEqual(list(Path(folder).iterdir()), [p])


if __name__ == "__main__":
    unittest.main()
