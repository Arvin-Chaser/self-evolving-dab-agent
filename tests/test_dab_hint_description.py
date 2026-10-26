import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import run_multi_query_baseline as baseline
from experiments.run_multi_query_baseline import compose_hint_description


class HintDescriptionTests(unittest.TestCase):
    def test_matches_official_append_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "db_description.txt").write_text(" schema \n", encoding="utf-8")
            (root / "db_description_withhint.txt").write_text(" hint \n", encoding="utf-8")
            self.assertEqual(compose_hint_description(root), "schema\n\nhint")

    def test_missing_hint_fails_instead_of_silently_running_no_hint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "db_description.txt").write_text("schema", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                compose_hint_description(root)

    def test_dispatch_uses_composed_input_and_no_hint_keeps_base(self):
        for use_hints in (False, True):
            with self.subTest(use_hints=use_hints), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / "source"
                (source / "experiments").mkdir(parents=True)
                (source / "experiments/run_dab_tool_agent.py").write_text("# stub\n", encoding="utf-8")
                family = root / "dab/query_a"
                query_dir = family / "query1"
                query_dir.mkdir(parents=True)
                (family / "db_description.txt").write_text("schema", encoding="utf-8")
                (family / "db_description_withhint.txt").write_text("hint", encoding="utf-8")
                batch = root / "batch.json"
                batch.write_text(json.dumps({"batch_id": "hint_test", "query_ids": ["a/query1"]}), encoding="utf-8")
                registry = root / "registry.json"
                registry.write_text(json.dumps({"queries": [{"query_id": "a/query1", "domain": "a", "query_dir": str(query_dir)}]}), encoding="utf-8")

                def fake_run(args, **kwargs):
                    description = Path(args[args.index("--db-description") + 1])
                    self.assertEqual(description.read_text(encoding="utf-8"), "schema\n\nhint" if use_hints else "schema")
                    if not use_hints:
                        self.assertEqual(description, family / "db_description.txt")
                    run_dir = Path(args[args.index("--output-root") + 1]) / args[args.index("--run-id") + 1]
                    run_dir.mkdir(parents=True)
                    (run_dir / "summary.json").write_text(json.dumps({"status": "prepared"}), encoding="utf-8")
                    return subprocess.CompletedProcess(args, 0)

                argv = ["baseline", "--batch", str(batch), "--registry", str(registry),
                        "--source-root", str(source), "--dab-root", str(family.parent),
                        "--output-root", str(root / "output"), "--run-id", "test", "--python", sys.executable,
                        "--prepare-only", "--skip-observer"] + (["--use-hints"] if use_hints else [])
                with patch.object(sys, "argv", argv), patch.object(baseline, "run_cmd", side_effect=fake_run):
                    self.assertEqual(baseline.main(), 0)
                manifest_path = root / "output/test/description_input_manifest.json"
                self.assertEqual(manifest_path.exists(), use_hints)
                if use_hints:
                    description = json.loads(manifest_path.read_text(encoding="utf-8"))["a/query1"]
                    self.assertEqual(description["sha256"], baseline.sha256_file(Path(description["path"])))
