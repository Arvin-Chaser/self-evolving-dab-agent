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
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
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


def run_cmd(args: list[str], *, cwd: Path, env: dict[str, str], stdout_path: Path, stderr_path: Path) -> subprocess.CompletedProcess[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        return subprocess.run(args, cwd=str(cwd), env=env, text=True, stdout=out, stderr=err, check=False)


def query_map_from_registry(registry_path: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(registry_path)
    rows = registry.get("queries") if isinstance(registry, dict) else []
    if not isinstance(rows, list):
        raise ValueError(f"registry queries must be a list: {registry_path}")
    return {str(row["query_id"]): row for row in rows if isinstance(row, dict) and row.get("query_id")}


def answer_quality_f1(feedback_summary: dict[str, Any]) -> float | None:
    quality = feedback_summary.get("answer_quality") if isinstance(feedback_summary.get("answer_quality"), dict) else {}
    value = quality.get("f1")
    try:
        return float(value)
    except (TypeError, ValueError):
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
        "helper_usage_summary": feedback.get("helper_usage_summary") if isinstance(feedback, dict) else None,
        "agent_self_observation_summary": feedback.get("agent_self_observation_summary") if isinstance(feedback, dict) else None,
        "top_observations": observations[:5] if isinstance(observations, list) else [],
    }


def build_multi_query_seed(*, batch: dict[str, Any], query_summaries: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
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
        "final_answer_nonempty_count": sum(1 for row in query_summaries if row.get("final_answer_nonempty")),
        "average_f1": round(sum(answer_f1s) / len(answer_f1s), 6) if answer_f1s else None,
        "selected_problem_type_counts": problem_counts,
        "selected_stage_counts": stage_counts,
        "helper_usage_status_counts": helper_usage_status_counts,
        "helper_registered_but_not_called_count": helper_usage_status_counts.get("helper_tool_registered_but_not_called", 0),
        "per_query_feedback": query_summaries,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "dab_corpus/batches/multi_query_arch_smoke_001.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "dab_corpus/registry.json")
    parser.add_argument("--dab-root", type=Path, default=ROOT / "external/DataAgentBench_sparse")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=f"multi_query_baseline_{utc_slug()}")
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("DAB_MULTI_QUERY_MAX_ITERATIONS", "6")))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-docker-check", action="store_true")
    parser.add_argument("--skip-postgres-check", action="store_true")
    parser.add_argument("--skip-observer", action="store_true", help="Do not run the fine-grained ObserverAgent for each query.")
    parser.add_argument("--observer-no-llm", action="store_true", help="Use deterministic ObserverAgent fallback instead of calling the observer LLM.")
    args = parser.parse_args()

    batch = read_json(args.batch.resolve())
    registry = query_map_from_registry(args.registry.resolve())
    output_dir = args.output_root.resolve() / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "batch.json", batch)

    env = os.environ.copy()
    query_summaries: list[dict[str, Any]] = []
    query_ids = batch.get("query_ids")
    if not isinstance(query_ids, list) or not query_ids:
        raise SystemExit(f"batch query_ids must be a non-empty list: {args.batch}")

    for index, query_id_raw in enumerate(query_ids, start=1):
        query_id = str(query_id_raw)
        if query_id not in registry:
            raise SystemExit(f"query_id missing from registry: {query_id}")
        case = registry[query_id]
        query_dir = ROOT / str(case["query_dir"])
        safe_query_id = query_id.replace("/", "_")
        run_id = f"{args.run_id}_q{index:02d}_{safe_query_id}"
        run_output_root = output_dir / "runs"
        run_dir = run_output_root / run_id

        cmd = [
            str(PYTHON),
            str(ROOT / "experiments/run_dab_tool_agent.py"),
            "--dab-data-root",
            str(args.dab_root.resolve()),
            "--query-dir",
            str(query_dir),
            "--output-root",
            str(run_output_root),
            "--run-id",
            run_id,
            "--max-iterations",
            str(args.max_iterations),
        ]
        if args.prepare_only:
            cmd.append("--prepare-only")
        if args.skip_docker_check:
            cmd.append("--skip-docker-check")
        if args.skip_postgres_check:
            cmd.append("--skip-postgres-check")

        run_proc = run_cmd(
            cmd,
            cwd=ROOT,
            env=env,
            stdout_path=output_dir / "logs" / f"{safe_query_id}.run.stdout",
            stderr_path=output_dir / "logs" / f"{safe_query_id}.run.stderr",
        )

        analyze_exit: int | None = None
        observer_exit: int | None = None
        if run_dir.exists() and (run_dir / "summary.json").exists():
            analyze_proc = run_cmd(
                [
                    str(PYTHON),
                    str(ROOT / "experiments/analyze_dab_tool_agent_trace.py"),
                    "--run-dir",
                    str(run_dir),
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=env,
                stdout_path=output_dir / "logs" / f"{safe_query_id}.analyze.stdout",
                stderr_path=output_dir / "logs" / f"{safe_query_id}.analyze.stderr",
            )
            analyze_exit = analyze_proc.returncode
            if not args.skip_observer:
                observer_cmd = [
                    str(PYTHON),
                    str(ROOT / "experiments/run_fine_grained_observer_agent.py"),
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
                observer_proc = run_cmd(
                    observer_cmd,
                    cwd=ROOT,
                    env=env,
                    stdout_path=output_dir / "logs" / f"{safe_query_id}.observer.stdout",
                    stderr_path=output_dir / "logs" / f"{safe_query_id}.observer.stderr",
                )
                observer_exit = observer_proc.returncode

        query_summaries.append(
            summarize_query(
                query_id=query_id,
                case=case,
                run_id=run_id,
                run_dir=run_dir,
                run_exit=run_proc.returncode,
                analyze_exit=analyze_exit,
                observer_exit=observer_exit,
            )
        )
        write_json(output_dir / "multi_query_progress.json", {"created_at": utc_now(), "queries": query_summaries})

    seed = build_multi_query_seed(batch=batch, query_summaries=query_summaries, output_dir=output_dir)
    write_json(output_dir / "multi_query_summary.json", {"schema_version": "dab_multi_query_summary_v001", **seed})
    write_json(output_dir / "multi_query_repair_seed.json", seed)
    print(json.dumps({"status": "ok", "output_dir": str(output_dir), "seed": str(output_dir / "multi_query_repair_seed.json")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
