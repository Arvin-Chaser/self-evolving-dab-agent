import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import run_multi_query_baseline as baseline
from experiments.run_multi_query_baseline import run_dynamic_query_queue


class DynamicWorkerQueueTests(unittest.TestCase):
    def test_run_command_stops_after_wall_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(subprocess.TimeoutExpired):
                baseline.run_cmd(
                    [sys.executable, "-c", "import time; time.sleep(2)"],
                    cwd=root, env={}, stdout_path=root / "stdout.log",
                    stderr_path=root / "stderr.log", timeout=0.05,
                )

    def test_workers_claim_shared_queue_and_results_keep_frozen_indexes(self) -> None:
        lock = threading.Lock()
        release = threading.Event()
        active = 0
        peak_active = 0
        first_wave_started = 0
        progress_sizes: list[int] = []

        def run_query(index: int, query_id: str) -> dict[str, object]:
            nonlocal active, peak_active, first_wave_started
            with lock:
                active += 1
                peak_active = max(peak_active, active)
                first_wave_started += 1
                if first_wave_started >= 2:
                    release.set()
            self.assertTrue(release.wait(timeout=1))
            try:
                return {"query_id": query_id, "index": index}
            finally:
                with lock:
                    active -= 1

        results, workers = run_dynamic_query_queue(
            [(1, "a/query1"), (2, "b/query1"), (3, "c/query1"), (4, "d/query1")],
            workers=2,
            run_query=run_query,
            on_progress=lambda current, _workers: progress_sizes.append(len(current)),
        )

        self.assertEqual(workers, 2)
        self.assertEqual(peak_active, 2)
        self.assertEqual(sorted(results), [1, 2, 3, 4])
        self.assertEqual([results[index]["query_id"] for index in sorted(results)], [
            "a/query1",
            "b/query1",
            "c/query1",
            "d/query1",
        ])
        self.assertEqual(progress_sizes, [1, 2, 3, 4])

    def test_same_dataset_runs_do_not_overlap(self) -> None:
        lock = threading.Lock()
        first_a = threading.Event()
        first_b = threading.Event()
        active_by_domain = {"a": 0, "b": 0}
        peak_by_domain = {"a": 0, "b": 0}
        peak_total = 0

        def run_query(index: int, query_id: str) -> dict[str, object]:
            nonlocal peak_total
            domain = query_id.split("/", 1)[0]
            with lock:
                active_by_domain[domain] += 1
                peak_by_domain[domain] = max(peak_by_domain[domain], active_by_domain[domain])
                peak_total = max(peak_total, sum(active_by_domain.values()))
            if domain == "a":
                first_a.set()
            else:
                first_b.set()
            self.assertTrue(first_a.wait(timeout=2))
            self.assertTrue(first_b.wait(timeout=2))
            with lock:
                active_by_domain[domain] -= 1
            return {"query_id": query_id, "index": index}

        results, workers = run_dynamic_query_queue(
            [(1, "a/query1"), (2, "a/query3"), (3, "b/query1"), (4, "b/query3")],
            workers=3,
            run_query=run_query,
            serialization_key=lambda query_id: query_id.split("/", 1)[0],
        )

        self.assertEqual(workers, 3)
        self.assertEqual(len(results), 4)
        self.assertEqual(peak_by_domain, {"a": 1, "b": 1})
        self.assertEqual(peak_total, 2)

    def test_waiting_same_dataset_does_not_occupy_a_worker(self) -> None:
        other_dataset_started = threading.Event()
        seen: list[str] = []

        def run_query(index: int, query_id: str) -> dict[str, object]:
            seen.append(query_id)
            if query_id == "a/query1":
                self.assertTrue(other_dataset_started.wait(timeout=2))
            elif query_id == "b/query1":
                other_dataset_started.set()
            return {"query_id": query_id, "index": index}

        results, workers = run_dynamic_query_queue(
            [(1, "a/query1"), (2, "a/query3"), (3, "b/query1")],
            workers=2,
            run_query=run_query,
            serialization_key=lambda query_id: query_id.split("/", 1)[0],
        )

        self.assertEqual(workers, 2)
        self.assertEqual(set(seen[:2]), {"a/query1", "b/query1"})
        self.assertEqual(sorted(results), [1, 2, 3])

    def test_baseline_defaults_to_unbounded_turns_and_full_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "experiments").mkdir(parents=True)
            (source / "experiments/run_dab_tool_agent.py").write_text("# stub\n", encoding="utf-8")
            dab_root = root / "dab"
            query_dir = dab_root / "query_crmarenapro/query1"
            query_dir.mkdir(parents=True)
            description = query_dir.parent / "db_description.txt"
            description.write_text("core_crm: Account table\n", encoding="utf-8")
            (query_dir.parent / "db_description_withhint.txt").write_text("HINTS only\n", encoding="utf-8")
            batch = root / "batch.json"
            batch.write_text(json.dumps({"batch_id": "one", "query_ids": ["crmarenapro/query1"]}), encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"queries": [{"query_id": "crmarenapro/query1", "domain": "crmarenapro", "query_dir": str(query_dir)}]}), encoding="utf-8")
            output = root / "output"
            commands: list[list[str]] = []
            child_envs: list[dict[str, str]] = []

            def fake_run_cmd(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                child_envs.append(kwargs["env"])
                if Path(args[1]).name == "run_dab_tool_agent.py":
                    run_dir = Path(args[args.index("--output-root") + 1]) / args[args.index("--run-id") + 1]
                    run_dir.mkdir(parents=True)
                    (run_dir / "summary.json").write_text(json.dumps({"status": "prepared"}), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0)

            argv = ["baseline", "--batch", str(batch), "--registry", str(registry),
                    "--source-root", str(source), "--dab-root", str(dab_root),
                    "--output-root", str(output), "--run-id", "one", "--python", sys.executable,
                    "--prepare-only", "--skip-observer", "--workers", "1",
                    "--deployment-name", "deepseek-flash",
                    "--openai-compatible-base-url", "https://api.deepseek.com/v1",
                    "--openai-compatible-api-key-env", "DEEPSEEK_API_KEY"]
            with patch.object(sys, "argv", argv), patch.object(baseline, "run_cmd", side_effect=fake_run_cmd):
                self.assertEqual(baseline.main(), 0)

            command = commands[0]
            self.assertEqual(command[command.index("--max-iterations") + 1], "0")
            self.assertEqual(command[command.index("--llm-timeout") + 1], "600.0")
            self.assertEqual(command[command.index("--llm-retries") + 1], "2")
            self.assertEqual(command[command.index("--llm-retry-sleep") + 1], "20.0")
            self.assertEqual(command[command.index("--client-max-retries") + 1], "0")
            self.assertEqual(command[command.index("--deployment-name") + 1], "deepseek-flash")
            self.assertEqual(command[command.index("--openai-compatible-base-url") + 1], "https://api.deepseek.com/v1")
            self.assertEqual(command[command.index("--openai-compatible-api-key-env") + 1], "DEEPSEEK_API_KEY")
            self.assertEqual(command[command.index("--db-description") + 1], str(description))
            self.assertIn("statement_timeout=1080000", child_envs[0]["PGOPTIONS"])
            summary = json.loads((output / "one/multi_query_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["execution_context"]["db_description_mode"], "base")
            self.assertEqual(summary["execution_context"]["llm_timeout_sec"], 600.0)
            self.assertEqual(summary["execution_context"]["llm_retry_attempts"], 2)
            self.assertEqual(summary["execution_context"]["llm_retry_sleep_sec"], 20.0)
            self.assertEqual(summary["execution_context"]["client_max_retries"], 0)
            self.assertEqual(summary["execution_context"]["deployment_name"], "deepseek-flash")
            self.assertEqual(summary["execution_context"]["query_timeout_sec"], 1200.0)
            self.assertEqual(summary["execution_context"]["postgres_statement_timeout_ms"], 1080000)
            self.assertTrue(summary["execution_context"]["same_domain_serialized"])
            self.assertEqual(summary["answer_f1_scored_count"], 0)

    def test_query_wall_timeout_is_recorded_and_next_query_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "experiments").mkdir(parents=True)
            (source / "experiments/run_dab_tool_agent.py").write_text("# stub\n", encoding="utf-8")
            dab_root = root / "dab"
            for name in ("query1", "query3"):
                (dab_root / "query_a" / name).mkdir(parents=True)
            (dab_root / "query_a/db_description.txt").write_text("schema\n", encoding="utf-8")
            batch = root / "batch.json"
            batch.write_text(json.dumps({"batch_id": "two", "query_ids": ["a/query1", "a/query3"]}), encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"queries": [
                {"query_id": f"a/{name}", "domain": "a", "query_dir": str(dab_root / "query_a" / name)}
                for name in ("query1", "query3")
            ]}), encoding="utf-8")
            output = root / "output"
            started: list[str] = []

            def fake_run_cmd(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                run_id = args[args.index("--run-id") + 1]
                started.append(run_id)
                if "query1" in run_id:
                    raise subprocess.TimeoutExpired(args, 0.01)
                run_dir = Path(args[args.index("--output-root") + 1]) / run_id
                run_dir.mkdir(parents=True)
                (run_dir / "summary.json").write_text(json.dumps({"status": "prepared"}), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0)

            argv = ["baseline", "--batch", str(batch), "--registry", str(registry),
                    "--source-root", str(source), "--dab-root", str(dab_root),
                    "--output-root", str(output), "--run-id", "two", "--python", sys.executable,
                    "--prepare-only", "--skip-observer", "--workers", "2", "--query-timeout-sec", "0.01",
                    "--postgres-statement-timeout-ms", "1"]
            # The stub raises timeout explicitly; host scheduling must not consume
            # the synthetic 10 ms budget before the second stub is dispatched.
            with patch.object(sys, "argv", argv), patch.object(baseline, "run_cmd", side_effect=fake_run_cmd), \
                    patch.object(baseline.time, "monotonic", return_value=100.0):
                self.assertEqual(baseline.main(), 0)

            progress = json.loads((output / "two/multi_query_progress.json").read_text(encoding="utf-8"))
            self.assertEqual(len(started), 2)
            self.assertEqual([row["status"] for row in progress["queries"]], ["timeout", "prepared"])
            self.assertEqual(progress["queries"][0]["query_timeout_stage"], "run")
            self.assertEqual(progress["queries"][0]["run_exit_code"], 124)


if __name__ == "__main__":
    unittest.main()
