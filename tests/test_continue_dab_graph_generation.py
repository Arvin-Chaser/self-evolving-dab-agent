"""Synthetic deployment checks: frozen inputs, six workers, no duplicate run."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments import continue_dab_graph_generation as continuation
from experiments import verify_dab_source_deployment as verifier


class ContinuationTests(unittest.TestCase):
    def test_deployment_uses_exact_candidate_and_batch_with_six_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generation = root / "generations/gen_004"
            repo = generation / "repo"
            (repo / "experiments").mkdir(parents=True)
            (repo / "experiments/run_dab_tool_agent.py").write_text("# synthetic\n", encoding="utf-8")
            batch = root / "batch.json"
            batch.write_text('{"query_ids":["alpha/query1"]}', encoding="utf-8")
            candidate_path = generation / "candidate_ref.json"
            candidate_path.write_text(json.dumps({
                "repo": str(repo), "patch_sha256": "a" * 64,
                "source_tree_sha256": continuation.source_tree_hash(repo)}), encoding="utf-8")
            state = {"next_generation": 4, "active_candidate_ref": str(candidate_path)}
            campaign = {"evolution_batch": str(batch),
                "evolution_batch_sha256": hashlib.sha256(batch.read_bytes()).hexdigest(),
                "query_ids": ["alpha/query1"]}
            args = argparse.Namespace(campaign_root=root, workers=6,
                ssh_key=root / "test-key", server="test-server")
            commands = []

            def fake_infrastructure(command):
                commands.append(command)
                if "printf existing" in command[-1]:
                    return "existing"
                return "12345" if "nohup" in command[-1] else "OK"

            with mock.patch.object(continuation, "infrastructure", side_effect=fake_infrastructure):
                spec = continuation.deploy_evaluation(args, state, campaign)
                count = len(commands)
                again = continuation.deploy_evaluation(args, state, campaign)
            self.assertEqual(len(commands), count)
            self.assertEqual(again, spec)
            self.assertEqual(spec["workers"], 6)
            self.assertEqual(spec["query_ids"], ["alpha/query1"])
            launcher = (generation / "remote_eval_launcher.sh").read_text(encoding="utf-8")
            self.assertIn("--max-iterations 0 --workers 6", launcher)
            self.assertIn("gen004_aaaaaaaa/repo", launcher)
            self.assertIn("evolution_domain17_v1_20260929.json", launcher)
            self.assertFalse(any("tar -xzf" in command[-1] for command in commands))
            self.assertTrue(any("verify_source.py --repo" in command[-1] for command in commands))
            self.assertEqual(verifier.digest(repo), continuation.source_tree_hash(repo))
            batch.write_text("modified", encoding="utf-8")
            (generation / "remote_evaluation.json").unlink()
            with mock.patch.object(continuation, "infrastructure") as transport:
                with self.assertRaisesRegex(RuntimeError, "Frozen evolution batch changed"):
                    continuation.deploy_evaluation(args, state, campaign)
                transport.assert_not_called()

    def test_trusted_verifier_matches_canonical_order_not_platform_path_order(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "tests").mkdir()
            for name in ("Alpha.py", "beta.py", "Zeta.md"):
                (repo / "tests" / name).write_text(name, encoding="utf-8")
            (repo / "AGENTS.md").write_text("not part of source identity", encoding="utf-8")
            self.assertEqual(verifier.digest(repo), continuation.source_tree_hash(repo))
            original = verifier.digest(repo)
            (repo / "tests/Alpha.py").write_text("changed", encoding="utf-8")
            self.assertNotEqual(original, verifier.digest(repo))


if __name__ == "__main__":
    unittest.main()
