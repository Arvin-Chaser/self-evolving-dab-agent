"""Credential-safe runtime and persistent output checks using synthetic inputs."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from experiments import dab_meta_runtime as runtime


class MetaRuntimeTests(unittest.TestCase):
    def test_configured_same_endpoint_hook_is_used_only_in_child_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                '[model_providers.school]\nbase_url="http://example.test/v1"\nenv_key="TEST_DAB_KEY"\n',
                encoding="utf-8")
            (root / "test.config.toml").write_text(
                'model_provider="school"\nmodel="test-model"\n'
                '[model_providers.previous]\nbase_url="http://example.test/v1"\n'
                '[model_providers.previous.auth]\ncommand="existing-hook"\nargs=[]\n', encoding="utf-8")
            response = io.BytesIO(json.dumps({"data": [{"id": "test-model"}]}).encode())
            opener = mock.Mock()
            opener.open.return_value = response
            with mock.patch.dict(os.environ, {"CODEX_HOME": directory}, clear=True), \
                 mock.patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "synthetic-token", "")) as hook, \
                 mock.patch.object(runtime.urllib.request, "build_opener", return_value=opener):
                env = runtime.meta_environment("test")
                self.assertEqual(env["TEST_DAB_KEY"], "synthetic-token")
                self.assertNotIn("TEST_DAB_KEY", os.environ)
                self.assertEqual(hook.call_args.args[0], ["existing-hook"])

    def test_missing_key_does_not_search_credential_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                'model_provider="school"\n[model_providers.school]\n'
                'base_url="http://example.test/v1"\nenv_key="TEST_DAB_KEY"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": directory}, clear=True), \
                 mock.patch.object(runtime.subprocess, "run") as hook:
                with self.assertRaisesRegex(RuntimeError, "Missing provider credential"):
                    runtime.meta_environment(None)
                hook.assert_not_called()

    def test_model_output_is_written_to_files_without_a_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, err = root / "stdout", root / "stderr"
            proc = runtime.run_logged_command(
                [sys.executable, "-c", "import sys; print(sys.stdin.read()); print('diagnostic', file=sys.stderr)"],
                cwd=root, prompt="synthetic prompt", stdout_path=out, stderr_path=err,
                env=os.environ.copy(), timeout=None)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("synthetic prompt", out.read_text(encoding="utf-8"))
            self.assertIn("diagnostic", proc.stderr)


if __name__ == "__main__":
    unittest.main()
