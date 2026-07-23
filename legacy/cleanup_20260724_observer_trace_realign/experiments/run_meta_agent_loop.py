"""Coordinate the minimal project-level DAB meta-agent loop.

This script plays the Planner/Executor role. It can run parent data-agent
cases, analyze them, build a meta-agent task package, and leave a clean handoff
for a human/Codex/Claude Code meta-agent to produce a bounded project patch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from experiments.analyze_agent_error import analyze_run
from experiments.apply_candidate_patch import apply_candidate_patch
from experiments.build_evolution_task import build_evolution_task
from experiments.call_meta_agent import DEFAULT_SCHEMA as DEFAULT_META_AGENT_RESPONSE_SCHEMA
from experiments.call_meta_agent import call_meta_agent
from experiments.run_dab_agent import run_dab_agent
from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report


DEFAULT_PROMPT = BASE_DIR / "prompts" / "dab" / "dab_code_agent_prompt_v005_runtime_observer.txt"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def candidate_dir(candidate_id: str) -> Path:
    return BASE_DIR / "candidates" / "dab" / candidate_id


def write_candidate_manifest(
    candidate_id: str,
    role: str,
    parent_id: str | None,
    search_cases: list[str],
    trajectory_refs: list[str] | None = None,
    meta_agent_log_refs: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> Path:
    out_dir = candidate_dir(candidate_id)
    manifest_path = out_dir / "manifest.json"
    manifest = {
        "candidate_id": candidate_id,
        "parent_id": parent_id,
        "created_at": utc_now_iso(),
        "role": role,
        "changed_files": changed_files or [],
        "patch_path": str(out_dir / "patch.diff"),
        "change_summary_path": str(out_dir / "change_summary.md"),
        "trajectory_refs": trajectory_refs or [],
        "search_cases": search_cases,
        "heldout_cases": [],
        "scores_path": str(out_dir / "scores.json"),
        "meta_agent_log_refs": meta_agent_log_refs or [],
    }
    write_json(manifest_path, manifest)
    return manifest_path


def resolve_cases(case_args: list[str], cases_args: list[str], max_cases: int | None) -> list[Path]:
    paths = [Path(path).resolve() for path in case_args + cases_args]
    if max_cases is not None:
        paths = paths[:max_cases]
    return paths


def validate_paths(paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "name": path.name,
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
        }
        for path in paths
    ]


def run_and_analyze_parent_cases(
    cases: list[Path],
    prompt_path: Path,
    version: str,
    dab_root: Path,
    timeout_sec: int,
) -> tuple[list[Path], list[dict[str, Any]], list[dict[str, Any]]]:
    run_dirs: list[Path] = []
    run_results: list[dict[str, Any]] = []
    analyses: list[dict[str, Any]] = []

    for index, case_dir in enumerate(cases, start=1):
        case_version = f"{version}_case{index:03d}"
        result = run_dab_agent(
            case_dir=case_dir,
            prompt_path=prompt_path,
            version=case_version,
            dab_root=dab_root,
            timeout_sec=timeout_sec,
        )
        run_dir = Path(result["run_dir"])
        analysis = analyze_run(run_dir)

        run_dirs.append(run_dir)
        run_results.append(result)
        analyses.append(analysis)

    return run_dirs, run_results, analyses


def analyze_existing_runs(run_dirs: list[Path]) -> list[dict[str, Any]]:
    analyses = []
    for run_dir in run_dirs:
        analyses.append(analyze_run(run_dir))
    return analyses


def load_run_outcome(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "result.json"
    result = load_json(result_path) if result_path.exists() else {}
    return {
        "run_dir": str(run_dir),
        "case_group": result.get("case_group"),
        "case_name": result.get("case_name"),
        "case_id": f"{result.get('case_group')}/{result.get('case_name')}",
        "prompt_version": result.get("prompt_version"),
        "passed": bool(result.get("passed")),
        "validation_reason": result.get("validation_reason"),
    }


def compare_parent_child_runs(parent_run_dirs: list[Path], child_run_dirs: list[Path]) -> dict[str, Any]:
    parent_outcomes = [load_run_outcome(path) for path in parent_run_dirs]
    child_outcomes = [load_run_outcome(path) for path in child_run_dirs]

    parent_by_case = {item["case_id"]: item for item in parent_outcomes}
    child_by_case = {item["case_id"]: item for item in child_outcomes}
    all_case_ids = sorted(set(parent_by_case) | set(child_by_case))

    improved_cases = []
    regressed_cases = []
    unchanged_passed_cases = []
    unchanged_failed_cases = []
    unmatched_cases = []

    for case_id in all_case_ids:
        parent = parent_by_case.get(case_id)
        child = child_by_case.get(case_id)
        if not parent or not child:
            unmatched_cases.append({"case_id": case_id, "parent": parent, "child": child})
            continue

        if not parent["passed"] and child["passed"]:
            improved_cases.append({"case_id": case_id, "parent": parent, "child": child})
        elif parent["passed"] and not child["passed"]:
            regressed_cases.append({"case_id": case_id, "parent": parent, "child": child})
        elif parent["passed"] and child["passed"]:
            unchanged_passed_cases.append({"case_id": case_id, "parent": parent, "child": child})
        else:
            unchanged_failed_cases.append({"case_id": case_id, "parent": parent, "child": child})

    child_total = len(child_outcomes)
    child_passed = sum(1 for item in child_outcomes if item["passed"])

    return {
        "parent": {
            "total": len(parent_outcomes),
            "passed": sum(1 for item in parent_outcomes if item["passed"]),
            "accuracy": (
                sum(1 for item in parent_outcomes if item["passed"]) / len(parent_outcomes)
                if parent_outcomes
                else None
            ),
            "case_results": parent_outcomes,
        },
        "child": {
            "total": child_total,
            "passed": child_passed,
            "accuracy": child_passed / child_total if child_total else None,
            "case_results": child_outcomes,
        },
        "comparison_to_parent": {
            "improved_cases": improved_cases,
            "regressed_cases": regressed_cases,
            "unchanged_passed_cases": unchanged_passed_cases,
            "unchanged_failed_cases": unchanged_failed_cases,
            "unmatched_cases": unmatched_cases,
        },
    }


def write_handoff(loop_dir: Path, task_manifest: dict[str, Any], child_candidate_id: str) -> Path:
    path = loop_dir / "meta_agent_handoff.md"
    text = "\n".join(
        [
            f"# Meta-Agent Handoff: {task_manifest['task_id']}",
            "",
            "Use the task package below as the coding/meta-agent context.",
            "",
            f"- Task markdown: `{task_manifest['task_markdown_path']}`",
            f"- Context manifest: `{task_manifest['context_manifest_path']}`",
            f"- Child candidate id: `{child_candidate_id}`",
            "",
            "Expected outputs:",
            "",
            f"- `candidates/dab/{child_candidate_id}/patch.diff`",
            f"- `candidates/dab/{child_candidate_id}/change_summary.md`",
            f"- `candidates/dab/{child_candidate_id}/manifest.json`",
            f"- `candidates/dab/{child_candidate_id}/scores.json` after evaluation",
            "",
            "中文说明：",
            "",
            "下一步由 coding/meta-agent 阅读 task package 和 source refs，基于证据做一个小的项目级修改。",
            "这个脚本不会自动修改项目代码；它只负责把 parent run、分析结果和任务上下文准备好。",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")
    return path


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now_iso()
    loop_id = args.loop_id or f"loop_{time.strftime('%Y%m%d_%H%M%S')}"
    loop_dir = Path(args.output_dir).resolve() / loop_id
    loop_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = Path(args.prompt).resolve()
    dab_root = Path(args.dab_root).resolve()
    cases = resolve_cases(args.case_dir, args.cases, args.max_cases)
    existing_run_dirs = [Path(path).resolve() for path in args.parent_run_dir]
    child_run_dirs = [Path(path).resolve() for path in args.child_run_dir]
    parent_candidate_id = args.parent_candidate_id
    child_candidate_id = args.child_candidate_id

    search_cases = [str(path) for path in cases]
    parent_manifest_path = write_candidate_manifest(
        candidate_id=parent_candidate_id,
        role="parent",
        parent_id=None,
        search_cases=search_cases,
    )

    validations = validate_paths([prompt_path, dab_root, *cases, *existing_run_dirs, *child_run_dirs])
    checks = [
        {
            "name": "required_paths_exist",
            "passed": all(item["exists"] for item in validations),
            "message": "Prompt, DAB root, case dirs, and existing run dirs must exist.",
            "details": validations,
        }
    ]

    run_plan = {
        "loop_id": loop_id,
        "created_at": utc_now_iso(),
        "dry_run": args.dry_run,
        "prompt_path": str(prompt_path),
        "dab_root": str(dab_root),
        "cases": search_cases,
        "parent_run_dirs": [str(path) for path in existing_run_dirs],
        "child_run_dirs": [str(path) for path in child_run_dirs],
        "parent_candidate_manifest": str(parent_manifest_path),
        "child_candidate_id": child_candidate_id,
        "auto_meta_agent": args.auto_meta_agent,
        "meta_agent_dry_run": args.meta_agent_dry_run,
        "apply_meta_agent_patch": args.apply_meta_agent_patch,
    }
    write_json(loop_dir / "run_plan.json", run_plan)

    if args.dry_run:
        report_path, _ = write_script_run_report(
            output_dir=loop_dir,
            script_name="experiments/run_meta_agent_loop.py",
            script_role="planner_executor",
            started_at=started_at,
            status="success" if checks[0]["passed"] else "failed",
        inputs=[path_ref("prompt", prompt_path), path_ref("dab_root", dab_root)]
            + [path_ref("case_dir", path) for path in cases]
            + [path_ref("child_run_dir", path) for path in child_run_dirs],
            operations=[
                {
                    "name": "dry_run_validate_pipeline_inputs",
                    "status": "completed",
                    "outputs": {
                        "loop_dir": str(loop_dir),
                        "case_count": len(cases),
                        "existing_run_dir_count": len(existing_run_dirs),
                    },
                    "checks": checks,
                }
            ],
            outputs=[path_ref("run_plan", loop_dir / "run_plan.json")],
            checks=checks,
            self_feedback={
                "confidence": "high",
                "uncertainties": [],
                "evolution_hints": ["Dry run validates wiring only; no LLM call or benchmark execution happened."],
                "suggested_target_modules": ["experiments/run_meta_agent_loop.py"],
            },
            report_stem="run_meta_agent_loop",
        )
        return {
            "loop_id": loop_id,
            "status": "dry_run_finished",
            "loop_dir": str(loop_dir),
            "run_plan_path": str(loop_dir / "run_plan.json"),
            "script_run_report_path": str(report_path),
            "checks": checks,
        }

    if not existing_run_dirs and not cases:
        raise ValueError("Provide --case-dir/--cases or --parent-run-dir.")

    if existing_run_dirs:
        parent_run_dirs = existing_run_dirs
        analyses = analyze_existing_runs(parent_run_dirs)
        run_results = [load_json(path / "result.json") for path in parent_run_dirs if (path / "result.json").exists()]
    else:
        parent_run_dirs, run_results, analyses = run_and_analyze_parent_cases(
            cases=cases,
            prompt_path=prompt_path,
            version=args.version,
            dab_root=dab_root,
            timeout_sec=args.timeout_sec,
        )

    task_manifest = build_evolution_task(
        run_dirs=parent_run_dirs,
        output_dir=loop_dir / "tasks",
        parent_candidate=parent_manifest_path,
        filtered_analyzer_refs=[
            Path(path).resolve()
            for path in getattr(args, "filtered_analyzer_refs", []) or []
        ],
        notes=args.notes,
    )

    child_manifest_path = write_candidate_manifest(
        candidate_id=child_candidate_id,
        role="child",
        parent_id=parent_candidate_id,
        search_cases=search_cases,
        trajectory_refs=[task_manifest["context_manifest_path"]],
        meta_agent_log_refs=[task_manifest["task_markdown_path"]],
    )
    handoff_path = write_handoff(loop_dir, task_manifest, child_candidate_id)

    meta_agent_result = None
    apply_patch_result = None
    if args.auto_meta_agent:
        meta_agent_result = call_meta_agent(
            task_md=Path(task_manifest["task_markdown_path"]),
            context_manifest=Path(task_manifest["context_manifest_path"]),
            candidate_dir=candidate_dir(child_candidate_id),
            response_schema=Path(args.meta_agent_response_schema).resolve(),
            max_source_chars=args.meta_agent_max_source_chars,
            max_total_source_chars=args.meta_agent_max_total_source_chars,
            patch_repair_attempts=args.meta_agent_patch_repair_attempts,
            dry_run=args.meta_agent_dry_run,
        )
        if args.apply_meta_agent_patch:
            apply_patch_result = apply_candidate_patch(
                candidate_dir=candidate_dir(child_candidate_id),
                repo_root=BASE_DIR,
                dry_run=args.apply_patch_dry_run,
            )

    child_analyses: list[dict[str, Any]] = []
    comparison_summary = None
    comparison_path = None
    scores_path = None

    if child_run_dirs:
        child_analyses = analyze_existing_runs(child_run_dirs)
        comparison_summary = compare_parent_child_runs(parent_run_dirs, child_run_dirs)
        comparison_path = loop_dir / "comparison_summary.json"
        scores_path = candidate_dir(child_candidate_id) / "scores.json"
        write_json(comparison_path, comparison_summary)
        write_json(scores_path, comparison_summary)

    if comparison_summary:
        loop_status = "comparison_finished"
    elif apply_patch_result and apply_patch_result.get("applied"):
        loop_status = "awaiting_child_run"
    elif apply_patch_result and apply_patch_result.get("status") == "success":
        loop_status = "candidate_patch_checked"
    elif meta_agent_result and meta_agent_result.get("dry_run"):
        loop_status = "meta_agent_dry_run_finished"
    elif meta_agent_result and meta_agent_result.get("patch_apply_check_passed"):
        loop_status = "awaiting_patch_apply"
    elif meta_agent_result and meta_agent_result.get("patch_found"):
        loop_status = "meta_agent_patch_invalid"
    elif meta_agent_result:
        loop_status = "meta_agent_patch_failed"
    else:
        loop_status = "awaiting_meta_agent_patch"

    loop_state = {
        "loop_id": loop_id,
        "status": loop_status,
        "loop_dir": str(loop_dir),
        "parent_candidate_manifest": str(parent_manifest_path),
        "child_candidate_manifest": str(child_manifest_path),
        "parent_run_dirs": [str(path) for path in parent_run_dirs],
        "child_run_dirs": [str(path) for path in child_run_dirs],
        "analysis_count": len(analyses),
        "child_analysis_count": len(child_analyses),
        "run_result_count": len(run_results),
        "task_manifest_path": task_manifest["context_manifest_path"],
        "task_markdown_path": task_manifest["task_markdown_path"],
        "handoff_path": str(handoff_path),
        "meta_agent_result": meta_agent_result,
        "apply_patch_result": apply_patch_result,
        "comparison_summary_path": str(comparison_path) if comparison_path else None,
        "scores_path": str(scores_path) if scores_path else None,
    }
    write_json(loop_dir / "loop_state.json", loop_state)

    meta_agent_operation = {
        "name": "call_coding_meta_agent",
        "status": "skipped",
        "outputs": {
            "auto_meta_agent": args.auto_meta_agent,
        },
    }
    if meta_agent_result:
        meta_agent_operation = {
            "name": "call_coding_meta_agent",
            "status": meta_agent_result.get("status"),
            "outputs": {
                "candidate_dir": meta_agent_result.get("candidate_dir"),
                "patch_path": meta_agent_result.get("patch_path"),
                "patch_found": meta_agent_result.get("patch_found"),
                "patch_apply_check_passed": meta_agent_result.get("patch_apply_check_passed"),
                "dry_run": meta_agent_result.get("dry_run"),
            },
        }

    apply_patch_operation = {
        "name": "apply_candidate_patch",
        "status": "skipped",
        "outputs": {
            "apply_meta_agent_patch": args.apply_meta_agent_patch,
        },
    }
    if apply_patch_result:
        apply_patch_operation = {
            "name": "apply_candidate_patch",
            "status": apply_patch_result.get("status"),
            "outputs": {
                "patch_path": apply_patch_result.get("patch_path"),
                "applied": apply_patch_result.get("applied"),
                "dry_run": apply_patch_result.get("dry_run"),
                "apply_report_path": str(candidate_dir(child_candidate_id) / "apply_report.json"),
            },
        }

    report_path, _ = write_script_run_report(
        output_dir=loop_dir,
        script_name="experiments/run_meta_agent_loop.py",
        script_role="planner_executor",
        started_at=started_at,
        status="partial",
        inputs=[path_ref("prompt", prompt_path), path_ref("dab_root", dab_root)]
        + [path_ref("case_dir", path) for path in cases]
        + [path_ref("parent_run_dir", path) for path in existing_run_dirs],
        operations=[
            {
                "name": "prepare_parent_candidate",
                "status": "completed",
                "outputs": {"manifest_path": str(parent_manifest_path)},
                "checks": checks,
            },
            {
                "name": "collect_parent_evidence",
                "status": "completed",
                "outputs": {
                    "parent_run_dir_count": len(parent_run_dirs),
                    "analysis_count": len(analyses),
                },
            },
            {
                "name": "build_meta_agent_task",
                "status": "completed",
                "outputs": {
                    "task_manifest_path": task_manifest["context_manifest_path"],
                    "task_markdown_path": task_manifest["task_markdown_path"],
                },
            },
            {
                "name": "handoff_to_coding_meta_agent",
                "status": "completed" if meta_agent_result or comparison_summary else "awaiting_external_patch",
                "outputs": {"handoff_path": str(handoff_path)},
            },
            meta_agent_operation,
            apply_patch_operation,
            {
                "name": "compare_parent_child_runs",
                "status": "completed" if comparison_summary else "skipped",
                "outputs": {
                    "child_run_dir_count": len(child_run_dirs),
                    "comparison_summary_path": str(comparison_path) if comparison_path else None,
                    "scores_path": str(scores_path) if scores_path else None,
                },
            },
        ],
        outputs=[
            path_ref("run_plan", loop_dir / "run_plan.json"),
            path_ref("loop_state", loop_dir / "loop_state.json"),
            path_ref("handoff", handoff_path),
            path_ref("task_manifest", task_manifest["context_manifest_path"]),
            path_ref("comparison_summary", comparison_path) if comparison_path else {
                "name": "comparison_summary",
                "path": None,
                "exists": False,
            },
        ],
        checks=checks,
        self_feedback={
            "confidence": "high",
            "uncertainties": [
                "Child candidate quality still requires a separate child run unless --child-run-dir is supplied."
            ],
            "evolution_hints": [
                "Use --auto-meta-agent to generate a patch candidate from the task package.",
                "Use --apply-meta-agent-patch only after accepting the patch safety gate behavior.",
            ],
            "suggested_target_modules": [
                "prompts/dab",
                "experiments/analyze_agent_error.py",
                "adapters/feedback",
                "experiments/build_evolution_task.py",
            ],
        },
        report_stem="run_meta_agent_loop",
    )

    loop_state["script_run_report_path"] = str(report_path)
    write_json(loop_dir / "loop_state.json", loop_state)
    return loop_state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", action="append", default=[])
    parser.add_argument("--cases", nargs="*", default=[])
    parser.add_argument("--parent-run-dir", action="append", default=[])
    parser.add_argument("--child-run-dir", action="append", default=[])
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--version", default="v005_runtime_observer")
    parser.add_argument("--dab-root", default=str(Path.home() / "research" / "DataAgentBench"))
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--output-dir", default=str(BASE_DIR / "logs" / "meta_agent"))
    parser.add_argument("--loop-id")
    parser.add_argument("--parent-candidate-id", default="iter_000_parent")
    parser.add_argument("--child-candidate-id", default="iter_001_child")
    parser.add_argument("--notes")
    parser.add_argument(
        "--auto-meta-agent",
        action="store_true",
        help="Call the coding meta-agent to generate candidates/dab/<child>/patch.diff.",
    )
    parser.add_argument(
        "--meta-agent-dry-run",
        action="store_true",
        help="Build the meta-agent prompt and candidate files without calling the LLM.",
    )
    parser.add_argument(
        "--apply-meta-agent-patch",
        action="store_true",
        help="Run the local patch safety gate after generating the meta-agent patch.",
    )
    parser.add_argument(
        "--apply-patch-dry-run",
        action="store_true",
        help="Run git apply --check but do not apply the candidate patch.",
    )
    parser.add_argument("--meta-agent-response-schema", default=str(DEFAULT_META_AGENT_RESPONSE_SCHEMA))
    parser.add_argument("--meta-agent-max-source-chars", type=int, default=12000)
    parser.add_argument("--meta-agent-max-total-source-chars", type=int, default=60000)
    parser.add_argument("--meta-agent-patch-repair-attempts", type=int, default=1)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate paths and write run_plan only. Does not call LLM or run benchmark cases.",
    )

    args = parser.parse_args()
    state = run_loop(args)
    print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
