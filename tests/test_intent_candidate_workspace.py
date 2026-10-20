"""Local, synthetic checks for the intent-to-candidate source workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments import intent_candidate_workspace as workspace


class IntentCandidateWorkspaceTests(unittest.TestCase):
    def test_source_tree_hash_ignores_workspace_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            runner = source / "experiments/run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("print('ok')\n", encoding="utf-8")
            agents = source / "AGENTS.md"
            agents.write_text("first\n", encoding="utf-8")
            first = workspace.source_tree_hash(source)
            agents.write_text("second\n", encoding="utf-8")
            self.assertEqual(first, workspace.source_tree_hash(source))
            runner.write_text("print('changed')\n", encoding="utf-8")
            self.assertNotEqual(first, workspace.source_tree_hash(source))

    def test_generate_does_not_retry_a_failed_model_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("import argparse\nargparse.ArgumentParser().parse_args()\n", encoding="utf-8")
            parent = root / "parent.py"
            parent.write_text("# parent\n", encoding="utf-8")
            intent = {"proposed_mechanism": "A synthetic frame", "code_parent_hash": workspace.sha256(parent.read_bytes())}
            intent_path = root / "intent.json"
            workspace.write_json(intent_path, intent)
            output = root / "candidate"
            workspace.prepare(argparse.Namespace(
                source_root=source, output=output, intent=intent_path,
                parent_source=parent, mechanism_contract=None,
            ))
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                self.assertIn("A synthetic frame", kwargs["prompt"])
                self.assertIsNone(kwargs["timeout"])
                return subprocess.CompletedProcess(command, 1, "", "model route unavailable")

            with mock.patch("experiments.dab_meta_runtime.resolve_codex", return_value="fake-codex"), \
                 mock.patch("experiments.dab_meta_runtime.meta_environment", return_value={}), \
                 mock.patch("experiments.dab_meta_runtime.run_logged_command", side_effect=fake_run):
                result = workspace.generate(argparse.Namespace(
                    workspace=output, codex="fake-codex", model=None, profile=None,
                    python=None, timeout=0, max_repairs=2,
                ))
            self.assertEqual(result, 1)
            self.assertEqual(len(calls), 1)
            status = json.loads((output / "generation_status.json").read_text(encoding="utf-8"))
            self.assertEqual(len(status["attempts"]), 1)
            self.assertFalse(status["attempts"][0]["changed_files"])

    def test_prepare_and_audit_without_benchmark_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("import argparse\nargparse.ArgumentParser().parse_args()\n", encoding="utf-8")
            (source / "AGENTS.md").write_text("# Synthetic guidance\n", encoding="utf-8")
            excluded = source / "experiments" / "dab_fixed_signal_feedback" / "old.py"
            excluded.parent.mkdir()
            excluded.write_text("raise RuntimeError('must not copy')\n", encoding="utf-8")
            upstream = source / "external" / "DataAgentBench_official" / "common_scaffold" / "DataAgent.py"
            upstream.parent.mkdir(parents=True)
            upstream.write_text("class DataAgent:\n    def _handle_tool_call(self, call):\n        return call\n", encoding="utf-8")
            parent = root / "parent.py"
            parent.write_text("# parent\n", encoding="utf-8")
            intent = {
                "proposed_mechanism": "Inject a frame on the real dispatch path.",
                "code_parent_hash": workspace.sha256(parent.read_bytes()),
                "irrelevant_history": "not needed in the implementation brief",
            }
            intent["canonical_json_sha256"] = workspace.canonical_hash(intent)
            intent_path = root / "intent.json"
            workspace.write_json(intent_path, intent)
            output = root / "candidate"
            args = argparse.Namespace(
                source_root=source,
                output=output,
                intent=intent_path,
                parent_source=parent,
                mechanism_contract=None,
            )
            self.assertEqual(workspace.prepare(args), 0)
            self.assertFalse((output / "repo" / excluded.relative_to(source)).exists())
            task = (output / "implementation_task.md").read_text(encoding="utf-8")
            self.assertIn("Inject a frame", task)
            self.assertNotIn("irrelevant_history", task)
            self.assertIn("codex --codex-run-as-apply-patch $patchText", task)
            self.assertIn("*** Begin Patch\n*** Add File: experiments/example_module.py\n+def example():", task)
            self.assertIn("For `*** Add File`, do not put `@@`", task)
            self.assertIn("Do not invoke `apply_patch.bat`", task)
            self.assertIn("../context/upstream_DataAgent.py", task)
            self.assertEqual((output / "context/upstream_DataAgent.py").read_bytes(), upstream.read_bytes())
            manifest = json.loads((output / "workspace_manifest.json").read_text(encoding="utf-8"))
            agents = output / "repo" / "AGENTS.md"
            agents_hash = next(item["sha256"] for item in manifest["files"] if item["path"] == "AGENTS.md")
            self.assertEqual(agents_hash, workspace.sha256(agents.read_bytes()))

            audit_args = argparse.Namespace(workspace=output, python=None)
            self.assertEqual(workspace.audit(audit_args), 1)
            self.assertTrue((output / "repair_task.md").exists())
            test_file = output / "repo" / "tests" / "test_mechanism.py"
            test_file.parent.mkdir()
            test_file.write_text("def test_frame():\n    assert True\n", encoding="utf-8")
            implementation_file = output / "repo" / "experiments" / "mechanism.py"
            implementation_file.write_text("def frame():\n    return '阶段：探索'\n", encoding="utf-8")
            workspace.write_json(
                output / "repo" / "candidate_workspace_report.json",
                {"claim_to_source": [{
                    "claim": "An implementation source exists",
                    "path": "experiments/mechanism.py",
                    "symbol": "frame",
                    "evidence": "The function is present; this is only a preflight fixture.",
                }]},
            )
            staged = workspace.run(["git", "add", "experiments/mechanism.py"], cwd=output / "repo")
            self.assertEqual(staged.returncode, 0)
            self.assertEqual(workspace.audit(audit_args), 0)
            admission = json.loads((output / "candidate_admission.json").read_text(encoding="utf-8"))
            self.assertEqual(admission["status"], "source_preflight_passed")
            self.assertFalse(admission["formal_dab_evaluation_run"])
            self.assertIn("experiments/mechanism.py", (output / "candidate.patch").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
