import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import run_g011_g013_integrated_small_panel as launcher


class IntegratedSmallPanelLauncherTests(unittest.TestCase):
    def launcher_args(self, *extra: str) -> list[str]:
        return [
            "--registry", "registry.json",
            "--dab-root", "dab",
            "--dab-upstream-root", "upstream",
            "--output-root", "output",
            "--run-id", "panel_test",
            "--python", "python",
            *extra,
        ]

    def test_current_frozen_inputs_match_protocol_bindings(self) -> None:
        observed = launcher.validate_frozen_inputs(launcher.ROOT)

        self.assertEqual(len(observed), len(launcher.FROZEN_SHA256))
        self.assertEqual(
            observed[launcher.INTEGRATED_RUNNER_RELATIVE.as_posix()],
            launcher.FROZEN_SHA256[launcher.INTEGRATED_RUNNER_RELATIVE],
        )
        batch = json.loads(
            (launcher.ROOT / launcher.PANEL_RELATIVE / "operational_batch.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(batch["query_ids"]), 6)
        self.assertEqual(len(set(batch["query_ids"])), 6)

    def test_frozen_input_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "bound.txt"
            target.write_text("changed\n", encoding="utf-8")
            with patch.object(launcher, "FROZEN_SHA256", {Path("bound.txt"): "0" * 64}):
                with self.assertRaisesRegex(SystemExit, "Frozen panel input changed"):
                    launcher.validate_frozen_inputs(root)

    def test_baseline_arguments_lock_frozen_execution_contract(self) -> None:
        args = launcher.build_parser().parse_args(self.launcher_args("--prepare-only"))
        argv = launcher.build_baseline_argv(args, launcher.ROOT)

        def value(option: str) -> str:
            return argv[argv.index(option) + 1]

        self.assertEqual(value("--batch"), str(launcher.ROOT / launcher.PANEL_RELATIVE / "operational_batch.json"))
        self.assertEqual(value("--tool-agent-runner"), str(launcher.INTEGRATED_RUNNER_RELATIVE))
        self.assertEqual(
            value("--tool-agent-runner-module"),
            "experiments.run_dab_tool_agent_g011_g013_integrated",
        )
        self.assertEqual(Path(value("--batch-launcher")), Path(launcher.__file__).resolve())
        self.assertEqual(value("--max-iterations"), "0")
        self.assertEqual(value("--llm-retries"), "1")
        self.assertEqual(value("--client-max-retries"), "0")
        self.assertEqual(value("--workers"), "1")
        self.assertEqual(value("--query-timeout-sec"), "1200")
        self.assertEqual(value("--postgres-statement-timeout-ms"), "300000")
        self.assertEqual(value("--database-bootstrap-timeout-sec"), "2400")
        self.assertEqual(value("--deployment-name"), "deepseek-flash")
        self.assertEqual(value("--openai-compatible-base-url"), "https://api.deepseek.com/v1")
        self.assertEqual(value("--openai-compatible-api-key-env"), "DEEPSEEK_API_KEY")
        self.assertIn("--skip-observer", argv)
        self.assertIn("--operational-only", argv)
        self.assertIn("--stop-on-query-error", argv)
        self.assertIn("--bootstrap-databases", argv)
        self.assertIn("--prepare-only", argv)
        self.assertNotIn("--use-hints", argv)
        self.assertNotIn("--use-hint-only-db-description", argv)
        self.assertNotIn("--tool-agent-policy", argv)
        self.assertNotIn("--enable-g0132-task-workspace", argv)
        self.assertNotIn("--resume", argv)

    def test_runtime_checks_cannot_be_skipped_for_a_real_panel(self) -> None:
        with self.assertRaises(SystemExit):
            launcher.main(self.launcher_args("--skip-postgres-check"))

    def test_source_root_cannot_attest_a_different_launcher_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                launcher.main([
                    "--source-root", directory,
                    *self.launcher_args("--prepare-only"),
                ])

    def test_frozen_integrated_entry_runs_as_a_module(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "experiments.run_dab_tool_agent_g011_g013_integrated", "--help"],
            cwd=launcher.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_main_validates_bindings_before_forwarding(self) -> None:
        with patch.object(launcher, "validate_frozen_inputs") as validate, \
                patch.object(launcher.run_multi_query_baseline, "main", return_value=17) as baseline_main:
            result = launcher.main([
                "--source-root", str(launcher.ROOT),
                *self.launcher_args("--prepare-only"),
            ])

        self.assertEqual(result, 17)
        validate.assert_called_once_with(launcher.ROOT.resolve())
        forwarded = baseline_main.call_args.args[0]
        self.assertIn("--prepare-only", forwarded)
        self.assertEqual(
            forwarded[forwarded.index("--tool-agent-runner") + 1],
            str(launcher.INTEGRATED_RUNNER_RELATIVE),
        )


if __name__ == "__main__":
    unittest.main()
