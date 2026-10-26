#!/usr/bin/env python3
"""Run and aggregate a small DAB multi-query baseline batch.

This is the bridge from single-query repair seeds to DAB-wide harness
evolution. It reads a query batch file, runs the current DataAgent on each
query, analyzes each run into fine-grained feedback, and writes a single
multi-query repair seed for the meta-agent.

Use `--prepare-only` for a cheap path/configuration smoke test that does not
call the LLM.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = ROOT / ".venv/bin/python"
DEFAULT_OUTPUT_ROOT = ROOT / "logs" / "multi_query_baseline"


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose_hint_description(family: Path) -> str:
    """Match official run_agent.py: full schema followed by official hints."""
    base = (family / "db_description.txt").read_text(encoding="utf-8").strip()
    hints = (family / "db_description_withhint.txt").read_text(encoding="utf-8").strip()
    return base + "\n\n" + hints


def absolute_python_executable(path: Path) -> Path:
    """Make an interpreter path absolute without dereferencing a venv symlink."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(expanded))


def validate_runner_module_binding(
    *, module: str, runner_path: Path, source_root: Path, python_executable: Path,
) -> Path:
    expected_path = source_root.joinpath(*module.split(".")).with_suffix(".py").resolve()
    if expected_path != runner_path:
        raise SystemExit(
            f"Tool-agent module/path mismatch: {module} does not map to {runner_path}"
        )
    probe = subprocess.run(
        [
            str(python_executable),
            "-c",
            (
                "import importlib.util, pathlib, sys; "
                "spec = importlib.util.find_spec(sys.argv[1])\n"
                "if spec is None or spec.origin is None: raise SystemExit(3)\n"
                "print(pathlib.Path(spec.origin).resolve())"
            ),
            module,
        ],
        cwd=str(source_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode != 0:
        raise SystemExit(f"Selected Python cannot resolve tool-agent module: {module}")
    lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise SystemExit(f"Selected Python returned an invalid module origin for: {module}")
    origin = Path(lines[0]).resolve()
    try:
        same_file = origin.samefile(runner_path)
    except OSError:
        same_file = False
    if not same_file:
        raise SystemExit(
            f"Selected Python module origin mismatch: expected {runner_path}, observed {origin}"
        )
    return origin


def resolve_query_dir(*, root: Path, dab_root: Path, case: dict[str, Any], query_id: str) -> Path:
    """Resolve registry entries against either their original or deployed DAB root."""
    configured = Path(str(case["query_dir"]))
    candidates = [configured] if configured.is_absolute() else [root / configured]
    domain, separator, query_name = query_id.partition("/")
    if separator:
        candidates.append(dab_root / f"query_{domain}" / query_name)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Cannot resolve query directory for {query_id}; tried: "
        + ", ".join(str(path) for path in candidates)
    )


def run_cmd(
    args: list[str], *, cwd: Path, env: dict[str, str], stdout_path: Path,
    stderr_path: Path, timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            args, cwd=str(cwd), env=env, text=True, stdout=out, stderr=err,
            start_new_session=os.name == "posix",
        )
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Stop tool subprocesses as well as the Python child before advancing.
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.kill()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except ProcessLookupError:
                    pass
                proc.wait()
            raise
        return subprocess.CompletedProcess(args, returncode)


def query_map_from_registry(registry_path: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(registry_path)
    rows = registry.get("queries") if isinstance(registry, dict) else []
    if not isinstance(rows, list):
        raise ValueError(f"registry queries must be a list: {registry_path}")
    return {str(row["query_id"]): row for row in rows if isinstance(row, dict) and row.get("query_id")}


def run_dynamic_query_queue(
    query_specs: list[tuple[int, str]],
    *,
    workers: int,
    run_query: Callable[[int, str], dict[str, Any]],
    on_progress: Callable[[dict[int, dict[str, Any]], int], None] | None = None,
    serialization_key: Callable[[str], str] | None = None,
) -> tuple[dict[int, dict[str, Any]], int]:
    """Fill worker slots with eligible jobs while preserving per-group order."""
    if workers < 1:
        raise ValueError("workers must be positive")
    if not query_specs:
        return {}, 0
    worker_count = min(workers, len(query_specs))
    results_by_index: dict[int, dict[str, Any]] = {}
    pending = [(index, query_id, serialization_key(query_id) if serialization_key else None)
               for index, query_id in query_specs]
    active_keys: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="dab-query") as executor:
        future_to_job: dict[concurrent.futures.Future[dict[str, Any]], tuple[int, str | None]] = {}

        def fill_workers() -> None:
            while pending and len(future_to_job) < worker_count:
                position = next((i for i, (_, _, key) in enumerate(pending)
                                 if serialization_key is None or key not in active_keys), None)
                if position is None:
                    break
                index, query_id, key = pending.pop(position)
                future = executor.submit(run_query, index, query_id)
                future_to_job[future] = (index, key)
                if serialization_key is not None:
                    active_keys.add(key)

        fill_workers()
        while future_to_job:
            done, _ = concurrent.futures.wait(future_to_job, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                index, key = future_to_job.pop(future)
                if serialization_key is not None:
                    active_keys.remove(key)
                results_by_index[index] = future.result()
                if on_progress is not None:
                    on_progress(dict(results_by_index), worker_count)
            fill_workers()
    return results_by_index, worker_count


def answer_quality_f1(feedback_summary: dict[str, Any]) -> float | None:
    quality = feedback_summary.get("answer_quality") if isinstance(feedback_summary.get("answer_quality"), dict) else {}
    value = quality.get("f1")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def query_error_reason(row: dict[str, Any], *, prepare_only: bool) -> str | None:
    """Return a content-blind stop reason for a child that did not finish cleanly."""
    if row.get("run_exit_code") != 0:
        return "child_exit_nonzero"
    expected_status = "prepared" if prepare_only else "completed"
    if row.get("status") != expected_status:
        return "child_status_not_" + expected_status
    if not prepare_only and row.get("analyze_exit_code") != 0:
        return "analyzer_exit_nonzero"
    observer_exit = row.get("observer_exit_code")
    if observer_exit not in (None, 0):
        return "observer_exit_nonzero"
    return None


def summarize_query(
    *,
    query_id: str,
    case: dict[str, Any],
    run_id: str,
    run_dir: Path,
    run_exit: int,
    analyze_exit: int | None,
    observer_exit: int | None = None,
) -> dict[str, Any]:
    summary = read_json(run_dir / "summary.json") if (run_dir / "summary.json").exists() else {}
    feedback = read_json(run_dir / "feedback_summary.json") if (run_dir / "feedback_summary.json").exists() else {}
    observations = read_json(run_dir / "observations.json") if (run_dir / "observations.json").exists() else []
    observer_feedback = read_json(run_dir / "observer_fine_grained_feedback.json") if (run_dir / "observer_fine_grained_feedback.json").exists() else {}
    f1 = answer_quality_f1(feedback) if isinstance(feedback, dict) else None
    answer_quality = feedback.get("answer_quality") if isinstance(feedback, dict) else None
    return {
        "query_id": query_id,
        "domain": case.get("domain"),
        "query_dir": case.get("query_dir"),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "run_exit_code": run_exit,
        "analyze_exit_code": analyze_exit,
        "observer_exit_code": observer_exit,
        "observer_feedback_path": str(run_dir / "observer_fine_grained_feedback.json") if (run_dir / "observer_fine_grained_feedback.json").exists() else None,
        "observer_generated_feedback": observer_feedback if isinstance(observer_feedback, dict) else {},
        "status": summary.get("status"),
        "terminate_reason": summary.get("terminate_reason"),
        "final_answer_nonempty": summary.get("final_answer_nonempty"),
        "llm_call_count": summary.get("llm_call_count"),
        "tool_call_count": summary.get("tool_call_count"),
        "run_error": summary.get("run_error"),
        "selected_stage": feedback.get("selected_stage") if isinstance(feedback, dict) else None,
        "selected_signal": feedback.get("selected_signal") if isinstance(feedback, dict) else None,
        "selected_problem_type": feedback.get("selected_problem_type") if isinstance(feedback, dict) else None,
        "answer_quality": feedback.get("answer_quality") if isinstance(feedback, dict) else None,
        "answer_f1": f1,
        "strict_match_passed": answer_quality.get("strict_match_passed") if isinstance(answer_quality, dict) else None,
        "helper_usage_summary": feedback.get("helper_usage_summary") if isinstance(feedback, dict) else None,
        "agent_self_observation_summary": feedback.get("agent_self_observation_summary") if isinstance(feedback, dict) else None,
        "top_observations": observations[:5] if isinstance(observations, list) else [],
    }


def build_multi_query_seed(
    *,
    batch: dict[str, Any],
    query_summaries: list[dict[str, Any]],
    output_dir: Path,
    execution_context: dict[str, Any],
) -> dict[str, Any]:
    successful_runs = [row for row in query_summaries if row.get("run_exit_code") == 0]
    answer_f1s = [row["answer_f1"] for row in query_summaries if isinstance(row.get("answer_f1"), float)]
    problem_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    helper_usage_status_counts: dict[str, int] = {}
    for row in query_summaries:
        problem = row.get("selected_problem_type") or "unknown"
        stage = row.get("selected_stage") or "unknown"
        helper_usage = row.get("helper_usage_summary") if isinstance(row.get("helper_usage_summary"), dict) else {}
        helper_status = helper_usage.get("status") or "unknown"
        problem_counts[str(problem)] = problem_counts.get(str(problem), 0) + 1
        stage_counts[str(stage)] = stage_counts.get(str(stage), 0) + 1
        helper_usage_status_counts[str(helper_status)] = helper_usage_status_counts.get(str(helper_status), 0) + 1

    return {
        "schema_version": "dab_multi_query_repair_seed_v001",
        "created_at": utc_now(),
        "feedback_type": "dab_multi_query_workflow_feedback",
        "repair_profile": "multi_query_architecture_evolution",
        "batch": batch,
        "batch_id": batch.get("batch_id"),
        "query_count": len(query_summaries),
        "successful_run_count": len(successful_runs),
        "max_iterations_count": sum(1 for row in query_summaries if row.get("terminate_reason") == "max_iterations"),
        "final_answer_nonempty_count": sum(1 for row in query_summaries if row.get("final_answer_nonempty")),
        "strict_pass_count": sum(1 for row in query_summaries if row.get("strict_match_passed") is True),
        "strict_evaluated_count": sum(1 for row in query_summaries if isinstance(row.get("strict_match_passed"), bool)),
        "average_f1": round(sum(answer_f1s) / len(answer_f1s), 6) if answer_f1s else None,
        "answer_f1_scored_count": len(answer_f1s),
        "selected_problem_type_counts": problem_counts,
        "selected_stage_counts": stage_counts,
        "helper_usage_status_counts": helper_usage_status_counts,
        "helper_registered_but_not_called_count": helper_usage_status_counts.get("helper_tool_registered_but_not_called", 0),
        "per_query_feedback": query_summaries,
        "execution_context": execution_context,
        "artifact_paths": {
            "output_dir": str(output_dir),
            "multi_query_summary": str(output_dir / "multi_query_summary.json"),
            "multi_query_repair_seed": str(output_dir / "multi_query_repair_seed.json"),
        },
        "meta_agent_instructions": [
            "Do not optimize a single query in isolation.",
            "Use per-query fine-grained feedback to identify cross-query workflow weaknesses.",
            "Prefer architecture-level reusable DataAgent structures when multiple queries share failure modes.",
            "Consider planner, tool-use controller, schema explorer, answer verifier, observer, memory/performance tracker, or near-miss refinement controller.",
            "If proposing only a query/domain helper, explain why it is not a shortcut and why the evidence supports that abstraction.",
            "Every candidate must declare candidate_structure_type.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "dab_corpus/batches/multi_query_arch_smoke_001.json")
    parser.add_argument("--all-queries", action="store_true", help="Run every query in --registry; this may incur substantial API usage.")
    parser.add_argument("--max-queries", type=int, help="Use only the first N selected queries, for a bounded smoke test.")
    parser.add_argument("--registry", type=Path, default=ROOT / "dab_corpus/registry.json")
    parser.add_argument("--dab-root", type=Path, default=ROOT / "external/DataAgentBench_sparse")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Bounded candidate source root containing experiments/run_dab_tool_agent.py; defaults to this repository.",
    )
    parser.add_argument(
        "--tool-agent-runner",
        type=Path,
        default=Path("experiments/run_dab_tool_agent.py"),
        help="Child tool-agent entry point; relative paths are resolved inside --source-root.",
    )
    parser.add_argument(
        "--tool-agent-runner-module",
        help="Execute the hash-bound child runner with python -m so package-relative imports are available.",
    )
    parser.add_argument(
        "--batch-launcher",
        type=Path,
        help="Optional outer launcher recorded by path and SHA-256; relative paths are resolved inside --source-root.",
    )
    parser.add_argument("--dab-upstream-root", type=Path, help="Upstream DataAgent source root; defaults to --dab-root.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=f"multi_query_baseline_{utc_slug()}")
    parser.add_argument(
        "--python",
        type=Path,
        help="Python executable used for child runner/analyzer processes; defaults to this interpreter when the source snapshot has no .venv.",
    )
    parser.add_argument("--max-iterations", type=int, default=0, help="Agent LLM turn limit; 0 means unbounded (default).")
    parser.add_argument("--llm-timeout", type=float, default=600.0, help="Seconds allowed per model request (default: 600).")
    parser.add_argument("--llm-retries", type=int, default=2, help="Maximum attempts per model turn (default: 2).")
    parser.add_argument("--deployment-name", help="Explicit model binding for each query runner.")
    parser.add_argument("--openai-compatible-base-url", help="Explicit provider /v1 endpoint for each query runner.")
    parser.add_argument("--openai-compatible-api-key-env", help="Name of the provider credential environment variable, not its value.")
    parser.add_argument("--llm-retry-sleep", type=float, default=20.0, help="Seconds between model attempts (default: 20).")
    parser.add_argument("--client-max-retries", type=int, default=0, help="SDK internal retries (default: 0).")
    parser.add_argument(
        "--tool-agent-policy",
        type=Path,
        help="Policy overlay passed to every query runner; relative paths are resolved inside --source-root.",
    )
    parser.add_argument(
        "--disable-self-observation-tool",
        action="store_true",
        help="Disable the optional self-observation tool for every query runner.",
    )
    parser.add_argument(
        "--disable-evolved-helper-tools",
        action="store_true",
        help="Disable evolved helper tools for every query runner.",
    )
    parser.add_argument(
        "--enable-g0132-task-workspace",
        action="store_true",
        help="Enable the task-facing G13 successor workspace for every query runner.",
    )
    parser.add_argument("--g0132-synthesis-reserve-turns", type=int, default=6)
    parser.add_argument("--g0132-final-verification-actions", type=int, default=1)
    parser.add_argument("--g0132-synthesis-deadline-reserve-sec", type=float, default=240.0)
    parser.add_argument("--g0132-workspace-max-view-chars", type=int, default=6000)
    parser.add_argument("--g0132-max-actions-per-requirement", type=int, default=3)
    parser.add_argument("--g0132-max-python-actions", type=int, default=3)
    parser.add_argument("--disable-g0132-message-compaction", action="store_true")
    parser.add_argument("--query-timeout-sec", type=float, default=1200.0, help="Wall-clock limit for each query, including analysis and observer (default: 1200).")
    parser.add_argument("--postgres-statement-timeout-ms", type=int, default=1080000, help="Server-side PostgreSQL statement timeout in milliseconds (default: 18 minutes).")
    parser.add_argument(
        "--bootstrap-databases",
        action="store_true",
        help="Preload each query's server-backed database before starting its agent wall clock.",
    )
    parser.add_argument(
        "--database-bootstrap-timeout-sec",
        type=float,
        default=2400.0,
        help="Wall-clock limit for one database preload process (default: 2400).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("DAB_MULTI_QUERY_WORKERS", "4")),
        help="Number of dynamic query workers. Each worker claims the next unfinished query; default: 4.",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse completed per-query runs from this --run-id.")
    parser.add_argument(
        "--operational-only",
        action="store_true",
        help="Write a restricted operational summary and suppress the research/meta-agent repair seed.",
    )
    parser.add_argument(
        "--stop-on-query-error",
        action="store_true",
        help="With one worker, stop before dispatching another query after any child/analyzer/observer error.",
    )
    parser.add_argument("--use-base-db-description", action="store_true", help="Compatibility flag; the full db_description.txt is now the default.")
    parser.add_argument("--use-hint-only-db-description", action="store_true", help="Explicitly use db_description_withhint.txt without the full database schema.")
    parser.add_argument("--use-hints", action="store_true", help="Append official hints to the full database description, matching the official harness.")
    parser.add_argument("--skip-docker-check", action="store_true")
    parser.add_argument("--skip-postgres-check", action="store_true")
    parser.add_argument("--skip-observer", action="store_true", help="Do not run the fine-grained ObserverAgent for each query.")
    parser.add_argument("--observer-no-llm", action="store_true", help="Use deterministic ObserverAgent fallback instead of calling the observer LLM.")
    args = parser.parse_args(argv)

    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.stop_on_query_error and args.workers != 1:
        parser.error("--stop-on-query-error requires --workers 1")
    if args.max_iterations < 0:
        parser.error("--max-iterations must be zero (unbounded) or positive")
    if args.llm_timeout <= 0:
        parser.error("--llm-timeout must be positive")
    if args.llm_retries < 1:
        parser.error("--llm-retries must be positive")
    if args.llm_retry_sleep < 0:
        parser.error("--llm-retry-sleep must be nonnegative")
    if args.client_max_retries < 0:
        parser.error("--client-max-retries must be nonnegative")
    if args.g0132_synthesis_reserve_turns < 1:
        parser.error("--g0132-synthesis-reserve-turns must be positive")
    if args.g0132_final_verification_actions < 0:
        parser.error("--g0132-final-verification-actions must be nonnegative")
    if args.g0132_synthesis_deadline_reserve_sec < 30:
        parser.error("--g0132-synthesis-deadline-reserve-sec must be at least 30")
    if args.g0132_workspace_max_view_chars < 1000:
        parser.error("--g0132-workspace-max-view-chars must be at least 1000")
    if args.query_timeout_sec <= 0:
        parser.error("--query-timeout-sec must be positive")
    if args.database_bootstrap_timeout_sec <= 0:
        parser.error("--database-bootstrap-timeout-sec must be positive")
    if args.postgres_statement_timeout_ms < 1 or args.postgres_statement_timeout_ms >= args.query_timeout_sec * 1000:
        parser.error("--postgres-statement-timeout-ms must be positive and below the query wall limit")
    if args.use_base_db_description and args.use_hint_only_db_description:
        parser.error("database description flags are mutually exclusive")
    if args.use_hints and args.use_hint_only_db_description:
        parser.error("--use-hints and --use-hint-only-db-description are mutually exclusive")

    source_root = args.source_root.resolve() if args.source_root else ROOT
    if not (source_root / "experiments/run_dab_tool_agent.py").is_file():
        raise SystemExit(f"Candidate source root is missing the active DAB runner: {source_root}")
    tool_agent_runner = args.tool_agent_runner
    if not tool_agent_runner.is_absolute():
        tool_agent_runner = source_root / tool_agent_runner
    tool_agent_runner = tool_agent_runner.resolve()
    if not tool_agent_runner.is_file():
        raise SystemExit(f"Tool-agent runner not found: {tool_agent_runner}")
    tool_agent_runner_module = args.tool_agent_runner_module
    if tool_agent_runner_module and not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", tool_agent_runner_module):
        parser.error("--tool-agent-runner-module must be a dotted Python module name")
    batch_launcher = args.batch_launcher
    if batch_launcher is not None:
        if not batch_launcher.is_absolute():
            batch_launcher = source_root / batch_launcher
        batch_launcher = batch_launcher.resolve()
        if not batch_launcher.is_file():
            raise SystemExit(f"Batch launcher not found: {batch_launcher}")
    tool_agent_policy = None
    if args.tool_agent_policy:
        tool_agent_policy = args.tool_agent_policy
        if not tool_agent_policy.is_absolute():
            tool_agent_policy = source_root / tool_agent_policy
        tool_agent_policy = tool_agent_policy.resolve()
        if not tool_agent_policy.is_file():
            raise SystemExit(f"Tool-agent policy not found: {tool_agent_policy}")
    requested_python = args.python or (DEFAULT_PYTHON if DEFAULT_PYTHON.is_file() else Path(sys.executable))
    python_executable = absolute_python_executable(requested_python)
    if not python_executable.is_file():
        raise SystemExit(f"Python executable not found: {python_executable}")
    tool_agent_runner_module_origin = None
    if tool_agent_runner_module:
        tool_agent_runner_module_origin = validate_runner_module_binding(
            module=tool_agent_runner_module,
            runner_path=tool_agent_runner,
            source_root=source_root,
            python_executable=python_executable,
        )

    registry = query_map_from_registry(args.registry.resolve())
    batch = (
        {"schema_version": "dab_query_batch_v001", "batch_id": "all_registry_queries", "query_ids": list(registry)}
        if args.all_queries
        else read_json(args.batch.resolve())
    )
    if args.max_queries is not None:
        if args.max_queries < 1:
            parser.error("--max-queries must be positive")
        batch = {**batch, "query_ids": batch.get("query_ids", [])[: args.max_queries]}
    output_dir = args.output_root.resolve() / args.run_id
    batch_path = output_dir / "batch.json"
    prior_progress_path = output_dir / "multi_query_progress.json"
    if prior_progress_path.exists() and not args.resume:
        raise SystemExit(f"Run ID already has progress; use --resume or a new --run-id: {output_dir}")
    if args.resume and batch_path.exists():
        prior_batch = read_json(batch_path)
        if prior_batch.get("query_ids") != batch.get("query_ids"):
            raise SystemExit("Cannot resume: selected query IDs differ from the saved batch")
    query_ids = batch.get("query_ids")
    if not isinstance(query_ids, list) or not query_ids:
        raise SystemExit(f"batch query_ids must be a non-empty list: {args.batch}")

    query_specs: list[tuple[int, str]] = []
    for index, query_id_raw in enumerate(query_ids, start=1):
        query_id = str(query_id_raw)
        if query_id not in registry:
            raise SystemExit(f"query_id missing from registry: {query_id}")
        query_specs.append((index, query_id))

    if not args.use_hint_only_db_description:
        for _, query_id in query_specs:
            query_dir = resolve_query_dir(root=source_root, dab_root=args.dab_root.resolve(), case=registry[query_id], query_id=query_id)
            description = query_dir.parent / "db_description.txt"
            if not description.is_file():
                raise FileNotFoundError(f"Full database description missing for {query_id}: {description}")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(batch_path, batch)
    description_inputs: dict[str, dict[str, Any]] = {}
    if args.use_hints:
        for _, query_id in query_specs:
            family = resolve_query_dir(root=source_root, dab_root=args.dab_root.resolve(),
                                       case=registry[query_id], query_id=query_id).parent
            target = output_dir / "description_inputs" / (query_id.replace("/", "_") + ".txt")
            composed = compose_hint_description(family)
            if target.exists() and target.read_text(encoding="utf-8") != composed:
                raise SystemExit(f"Cannot reuse changed frozen description: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text(composed, encoding="utf-8")
            description_inputs[query_id] = {
                "path": str(target), "sha256": sha256_file(target),
                "base_sha256": sha256_file(family / "db_description.txt"),
                "hint_sha256": sha256_file(family / "db_description_withhint.txt"),
            }
        write_json(output_dir / "description_input_manifest.json", description_inputs)
    env = os.environ.copy()
    env["PGOPTIONS"] = (env.get("PGOPTIONS", "") + f" -c statement_timeout={args.postgres_statement_timeout_ms}").strip()
    prior_progress = read_json(prior_progress_path) if args.resume and prior_progress_path.exists() else {}
    prior_by_run_id = {
        row.get("run_id"): row
        for row in prior_progress.get("queries", [])
        if isinstance(row, dict) and row.get("run_id")
    } if isinstance(prior_progress, dict) else {}

    def run_query(index: int, query_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + args.query_timeout_sec

        def remaining_time(command: list[str]) -> float:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, args.query_timeout_sec)
            return remaining

        case = registry[query_id]
        query_dir = resolve_query_dir(
            root=source_root,
            dab_root=args.dab_root.resolve(),
            case=case,
            query_id=query_id,
        )
        safe_query_id = query_id.replace("/", "_")
        run_id = f"{args.run_id}_q{index:02d}_{safe_query_id}"
        run_output_root = output_dir / "runs"
        run_dir = run_output_root / run_id

        prior_row = prior_by_run_id.get(run_id)
        if args.resume and prior_row and (run_dir / "summary.json").is_file():
            prior_status = read_json(run_dir / "summary.json").get("status")
            if prior_row.get("run_exit_code") == 0 and (
                (args.prepare_only and prior_status == "prepared")
                or (not args.prepare_only and prior_status == "completed")
            ):
                return prior_row
            raise SystemExit(f"Cannot safely resume incomplete or differently configured query run: {run_dir}")

        runner_command = [str(python_executable)]
        if tool_agent_runner_module:
            runner_command.extend(["-m", tool_agent_runner_module])
        else:
            runner_command.append(str(tool_agent_runner))
        cmd = [
            *runner_command,
            "--dab-data-root",
            str(args.dab_root.resolve()),
            "--dab-upstream-root",
            str((args.dab_upstream_root or args.dab_root).resolve()),
            "--query-dir",
            str(query_dir),
            "--output-root",
            str(run_output_root),
            "--run-id",
            run_id,
            "--max-iterations",
            str(args.max_iterations),
            "--llm-timeout",
            str(args.llm_timeout),
            "--llm-retries",
            str(args.llm_retries),
            "--llm-retry-sleep",
            str(args.llm_retry_sleep),
            "--client-max-retries",
            str(args.client_max_retries),
            "--postgres-statement-timeout-ms",
            str(args.postgres_statement_timeout_ms),
        ]
        for option, value in (
            ("--deployment-name", args.deployment_name),
            ("--openai-compatible-base-url", args.openai_compatible_base_url),
            ("--openai-compatible-api-key-env", args.openai_compatible_api_key_env),
            ("--tool-agent-policy", tool_agent_policy),
        ):
            if value:
                cmd.extend([option, str(value)])
        if args.disable_self_observation_tool:
            cmd.append("--disable-self-observation-tool")
        if args.disable_evolved_helper_tools:
            cmd.append("--disable-evolved-helper-tools")
        if args.enable_g0132_task_workspace:
            cmd.extend(
                [
                    "--enable-g0132-task-workspace",
                    "--g0132-synthesis-reserve-turns",
                    str(args.g0132_synthesis_reserve_turns),
                    "--g0132-final-verification-actions",
                    str(args.g0132_final_verification_actions),
                    "--g0132-synthesis-deadline-reserve-sec",
                    str(args.g0132_synthesis_deadline_reserve_sec),
                    "--g0132-workspace-max-view-chars",
                    str(args.g0132_workspace_max_view_chars),
                    "--g0132-max-actions-per-requirement",
                    str(args.g0132_max_actions_per_requirement),
                    "--g0132-max-python-actions",
                    str(args.g0132_max_python_actions),
                ]
            )
        if args.disable_g0132_message_compaction:
            cmd.append("--disable-g0132-message-compaction")
        if args.use_hints:
            description = description_inputs[query_id]
            if sha256_file(Path(description["path"])) != description["sha256"]:
                raise RuntimeError("Frozen composed description changed: " + query_id)
            cmd.extend(["--db-description", description["path"]])
        elif not args.use_hint_only_db_description:
            cmd.extend(["--db-description", str(query_dir.parent / "db_description.txt")])
        if args.prepare_only:
            cmd.append("--prepare-only")
        if args.skip_docker_check:
            cmd.append("--skip-docker-check")
        if args.skip_postgres_check:
            cmd.append("--skip-postgres-check")

        bootstrap_record: dict[str, Any] | None = None
        if args.bootstrap_databases and not args.prepare_only:
            bootstrap_run_id = run_id + "_database_preload"
            bootstrap_output_root = output_dir / "database_preloads"
            receipt_path = bootstrap_output_root / bootstrap_run_id / "preloaded_databases.json"
            bootstrap_cmd = [
                *cmd,
                "--output-root", str(bootstrap_output_root),
                "--run-id", bootstrap_run_id,
                "--preload-databases",
                "--database-bootstrap-timeout-sec", str(args.database_bootstrap_timeout_sec),
            ]
            bootstrap_started = time.monotonic()
            bootstrap_timed_out = False
            try:
                bootstrap_proc = run_cmd(
                    bootstrap_cmd,
                    cwd=source_root,
                    env=env,
                    stdout_path=output_dir / "logs" / f"{safe_query_id}.database_preload.stdout",
                    stderr_path=output_dir / "logs" / f"{safe_query_id}.database_preload.stderr",
                    timeout=args.database_bootstrap_timeout_sec,
                )
            except subprocess.TimeoutExpired:
                bootstrap_proc = subprocess.CompletedProcess(bootstrap_cmd, 124)
                bootstrap_timed_out = True
            bootstrap_record = {
                "enabled": True,
                "run_id": bootstrap_run_id,
                "exit_code": bootstrap_proc.returncode,
                "timed_out": bootstrap_timed_out,
                "elapsed_sec": round(time.monotonic() - bootstrap_started, 6),
                "receipt_path": str(receipt_path) if receipt_path.is_file() else None,
            }
            if bootstrap_proc.returncode != 0 or not receipt_path.is_file():
                result = summarize_query(
                    query_id=query_id,
                    case=case,
                    run_id=run_id,
                    run_dir=run_dir,
                    run_exit=bootstrap_proc.returncode or 1,
                    analyze_exit=None,
                )
                result.update({
                    "status": "database_bootstrap_failed",
                    "terminate_reason": "database_bootstrap_timeout" if bootstrap_timed_out else "database_bootstrap_failed",
                    "database_bootstrap": bootstrap_record,
                    "run_error": "database_bootstrap_timeout" if bootstrap_timed_out else "database_bootstrap_failed",
                    "final_answer_nonempty": False,
                })
                return result
            cmd.extend([
                "--reuse-preloaded-databases",
                "--preloaded-database-receipt", str(receipt_path),
            ])

        timeout_stage: str | None = None
        try:
            run_proc = run_cmd(
                cmd,
                cwd=source_root,
                env=env,
                stdout_path=output_dir / "logs" / f"{safe_query_id}.run.stdout",
                stderr_path=output_dir / "logs" / f"{safe_query_id}.run.stderr",
                timeout=remaining_time(cmd),
            )
        except subprocess.TimeoutExpired:
            run_proc = subprocess.CompletedProcess(cmd, 124)
            timeout_stage = "run"

        analyze_exit: int | None = None
        observer_exit: int | None = None
        if timeout_stage is None and not args.prepare_only and (run_dir / "summary.json").exists():
            analyze_cmd = [
                    str(python_executable),
                    str(source_root / "experiments/analyze_dab_tool_agent_trace.py"),
                    "--run-dir",
                    str(run_dir),
                    "--output-dir",
                    str(run_dir),
            ]
            try:
                analyze_proc = run_cmd(
                    analyze_cmd,
                    cwd=source_root,
                    env=env,
                    stdout_path=output_dir / "logs" / f"{safe_query_id}.analyze.stdout",
                    stderr_path=output_dir / "logs" / f"{safe_query_id}.analyze.stderr",
                    timeout=remaining_time(analyze_cmd),
                )
                analyze_exit = analyze_proc.returncode
            except subprocess.TimeoutExpired:
                analyze_exit = 124
                timeout_stage = "analyze"
            if timeout_stage is None and not args.skip_observer:
                observer_cmd = [
                    str(python_executable),
                    str(source_root / "experiments/run_fine_grained_observer_agent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--query-id",
                    query_id,
                    "--domain",
                    str(case.get("domain") or ""),
                    "--output",
                    str(run_dir / "observer_fine_grained_feedback.json"),
                    "--behavior-input-output",
                    str(run_dir / "observer_raw_behavior_input.json"),
                ]
                if args.observer_no_llm:
                    observer_cmd.append("--no-llm")
                try:
                    observer_proc = run_cmd(
                        observer_cmd,
                        cwd=source_root,
                        env=env,
                        stdout_path=output_dir / "logs" / f"{safe_query_id}.observer.stdout",
                        stderr_path=output_dir / "logs" / f"{safe_query_id}.observer.stderr",
                        timeout=remaining_time(observer_cmd),
                    )
                    observer_exit = observer_proc.returncode
                except subprocess.TimeoutExpired:
                    observer_exit = 124
                    timeout_stage = "observer"

        result = summarize_query(
            query_id=query_id,
            case=case,
            run_id=run_id,
            run_dir=run_dir,
            run_exit=run_proc.returncode,
            analyze_exit=analyze_exit,
            observer_exit=observer_exit,
        )
        if timeout_stage is not None:
            result.update({
                "status": "timeout",
                "terminate_reason": f"query_wall_timeout_{args.query_timeout_sec:g}s",
                "query_timeout_stage": timeout_stage,
                "query_timeout_sec": args.query_timeout_sec,
            })
            if timeout_stage == "run":
                result["run_error"] = result["terminate_reason"]
                result["final_answer_nonempty"] = False
        if bootstrap_record is not None:
            result["database_bootstrap"] = bootstrap_record
        return result

    # The scheduler skips pending same-domain work until its database is free.
    # Results are re-sorted by frozen batch index for deterministic artifacts.
    scheduling = "sequential_fail_fast" if args.stop_on_query_error else "dynamic_worker_queue"

    def write_progress(results: dict[int, dict[str, Any]], worker_count: int) -> None:
        completed = [results[key] for key in sorted(results)]
        write_json(
            output_dir / "multi_query_progress.json",
            {
                "created_at": utc_now(),
                "scheduling": scheduling,
                "workers": worker_count,
                "queries": completed,
            },
        )

    stop_reason: str | None = None
    if args.stop_on_query_error:
        worker_count = 1
        results_by_index: dict[int, dict[str, Any]] = {}
        for index, query_id in query_specs:
            result = run_query(index, query_id)
            results_by_index[index] = result
            write_progress(results_by_index, worker_count)
            stop_reason = query_error_reason(result, prepare_only=args.prepare_only)
            if stop_reason is not None:
                write_json(
                    output_dir / "operational_stop.json",
                    {
                        "schema_version": "dab_operational_batch_stop_v1",
                        "created_at": utc_now(),
                        "reason": stop_reason,
                        "stopped_after_batch_index": index,
                        "completed_row_count": len(results_by_index),
                        "remaining_row_count": len(query_specs) - len(results_by_index),
                    },
                )
                break
    else:
        results_by_index, worker_count = run_dynamic_query_queue(
            query_specs,
            workers=args.workers,
            run_query=run_query,
            on_progress=write_progress,
            serialization_key=lambda query_id: query_id.partition("/")[0],
        )

    query_summaries = [results_by_index[index] for index, _ in query_specs if index in results_by_index]

    execution_context = {
        "source_root": str(source_root),
        "runner_path": str(tool_agent_runner),
        "runner_sha256": sha256_file(tool_agent_runner),
        "runner_module": tool_agent_runner_module,
        "runner_module_origin": str(tool_agent_runner_module_origin) if tool_agent_runner_module_origin else None,
        "batch_launcher_path": str(batch_launcher) if batch_launcher else None,
        "batch_launcher_sha256": sha256_file(batch_launcher) if batch_launcher else None,
        "batch_runner_sha256": sha256_file(Path(__file__).resolve()),
        "python_executable": str(python_executable),
        "dab_root": str(args.dab_root.resolve()),
        "dab_upstream_root": str((args.dab_upstream_root or args.dab_root).resolve()),
        "max_iterations": args.max_iterations,
        "llm_timeout_sec": args.llm_timeout,
        "llm_retry_attempts": args.llm_retries,
        "llm_retry_sleep_sec": args.llm_retry_sleep,
        "client_max_retries": args.client_max_retries,
        "deployment_name": args.deployment_name,
        "openai_compatible_base_url": args.openai_compatible_base_url,
        "openai_compatible_api_key_env": args.openai_compatible_api_key_env,
        "tool_agent_policy": str(tool_agent_policy) if tool_agent_policy else None,
        "tool_agent_policy_sha256": sha256_file(tool_agent_policy) if tool_agent_policy else None,
        "self_observation_tool_disabled": args.disable_self_observation_tool,
        "evolved_helper_tools_disabled": args.disable_evolved_helper_tools,
        "query_timeout_sec": args.query_timeout_sec,
        "postgres_statement_timeout_ms": args.postgres_statement_timeout_ms,
        "database_bootstrap_enabled": args.bootstrap_databases,
        "database_bootstrap_timeout_sec": args.database_bootstrap_timeout_sec,
        "db_description_mode": "base_plus_official_hints" if args.use_hints else "hint_only" if args.use_hint_only_db_description else "base",
        "description_inputs": description_inputs,
        "same_domain_serialized": True,
        "workers": worker_count,
        "scheduling": scheduling,
        "operational_only": args.operational_only,
        "stop_on_query_error": args.stop_on_query_error,
    }
    if args.operational_only:
        operational_summary_path = output_dir / "operational_panel_summary.json"
        operational_summary = {
            "schema_version": "dab_operational_panel_summary_v1",
            "created_at": utc_now(),
            "status": "stopped" if stop_reason else "completed",
            "research_export_allowed": False,
            "contains_task_identifiers": True,
            "batch": batch,
            "completed_row_count": len(query_summaries),
            "planned_row_count": len(query_specs),
            "stop_reason": stop_reason,
            "queries": query_summaries,
            "execution_context": execution_context,
        }
        write_json(operational_summary_path, operational_summary)
        print(json.dumps({
            "status": operational_summary["status"],
            "output_dir": str(output_dir),
            "operational_summary": str(operational_summary_path),
        }, indent=2, ensure_ascii=False))
        return 2 if stop_reason else 0

    seed = build_multi_query_seed(
        batch=batch,
        query_summaries=query_summaries,
        output_dir=output_dir,
        execution_context=execution_context,
    )
    write_json(output_dir / "multi_query_summary.json", {"schema_version": "dab_multi_query_summary_v001", **seed})
    write_json(output_dir / "multi_query_repair_seed.json", seed)
    print(json.dumps({"status": "ok", "output_dir": str(output_dir), "seed": str(output_dir / "multi_query_repair_seed.json")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
