"""Build a meta-agent task package from DAB run artifacts.

This script plays the Navigator role in the project-level loop. It does not
decide repairs. It gathers raw evidence, analyzer output, script reports, and
source references into a compact task package for a coding/meta-agent.
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

from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report


KNOWN_RUN_ARTIFACTS = [
    "result.json",
    "summary.json",
    "prompt.txt",
    "raw_llm_output.txt",
    "generated_solve.py",
    "final_answer.txt",
    "stage_trace.json",
    "execution_stdout.txt",
    "execution_stderr.txt",
]


DEFAULT_SOURCE_REFS = [
    "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
    "prompts/dab/dab_code_agent_prompt_v004_operation_trace.txt",
    "prompts/dab/meta_agent/project_evolve_prompt.txt",
    "experiments/run_dab_agent.py",
    "experiments/analyze_agent_error.py",
    "experiments/build_evolution_task.py",
    "experiments/run_meta_agent_loop.py",
    "experiments/script_run_report.py",
    "adapters/runtime_observer.py",
    "adapters/feedback/common_trace_checks.py",
    "adapters/feedback/dab_patents_checks.py",
]


DEFAULT_SCOPE_REFS = [
    "meta_agent/agent_scope.md",
    "meta_agent/loop_design.md",
    "meta_agent/component_map.md",
    "meta_agent/evolution_targets.md",
    "meta_agent/feedback_schema.md",
    "meta_agent/script_run_report_schema.md",
    "meta_agent/meta_agent_io.md",
    "meta_agent/candidate_schema.md",
]


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def as_ref(name: str, path: Path | str, role: str | None = None) -> dict[str, Any]:
    path = repo_path(path)
    ref = path_ref(name, path, role=role)
    try:
        ref["repo_relative_path"] = str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        ref["repo_relative_path"] = None
    return ref


def collect_run_artifact_refs(run_dir: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for filename in KNOWN_RUN_ARTIFACTS:
        path = run_dir / filename
        if path.exists():
            refs.append(as_ref(filename, path, role="run_artifact"))
    return refs


def collect_script_report_refs(run_dir: Path) -> list[dict[str, Any]]:
    refs = []
    for path in sorted(run_dir.glob("script_run_report*.json")):
        refs.append(as_ref(path.name, path, role="script_run_report"))
    return refs


def collect_analyzer_refs(run_dir: Path) -> list[dict[str, Any]]:
    refs = []
    path = run_dir / "agent_error_summary.json"
    if path.exists():
        refs.append(as_ref("agent_error_summary", path, role="analyzer_output"))
    return refs


def summarize_run(run_dir: Path, filtered_context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = load_json_if_exists(run_dir / "result.json") or {}
    analysis = load_json_if_exists(run_dir / "agent_error_summary.json") or {}
    localized_errors = analysis.get("localized_errors") or []

    if filtered_context:
        candidates = filtered_context.get("top_problem_candidates") or []
        return {
            "run_dir": str(run_dir),
            "case_group": result.get("case_group") or analysis.get("case_group"),
            "case_name": result.get("case_name") or analysis.get("case_name"),
            "prompt_version": result.get("prompt_version") or analysis.get("prompt_version"),
            "passed": result.get("passed") if "passed" in result else analysis.get("passed"),
            "validation_reason": result.get("validation_reason") or analysis.get("validation_reason"),
            "localized_error_count": len(candidates),
            "top_problem_candidates": candidates,
            "filtered_analyzer_context": True,
            "suppressed_evidence_count": len(filtered_context.get("suppressed_evidence") or []),
        }

    return {
        "run_dir": str(run_dir),
        "case_group": result.get("case_group") or analysis.get("case_group"),
        "case_name": result.get("case_name") or analysis.get("case_name"),
        "prompt_version": result.get("prompt_version") or analysis.get("prompt_version"),
        "passed": result.get("passed") if "passed" in result else analysis.get("passed"),
        "validation_reason": result.get("validation_reason") or analysis.get("validation_reason"),
        "localized_error_count": len(localized_errors),
        "top_problem_candidates": localized_errors[:8],
    }


def filtered_context_by_run_dir(filtered_analyzer_refs: list[Path] | None) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for path in filtered_analyzer_refs or []:
        context = load_json_if_exists(repo_path(path)) or {}
        run_dir = context.get("run_dir")
        if run_dir:
            contexts[str(Path(run_dir).resolve())] = context
    return contexts


def build_task_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        f"# Meta-Agent Evolution Task: {manifest['task_id']}",
        "",
        "## Goal",
        "",
        "Inspect the referenced run artifacts and source files, then propose a small project-level change to improve the DAB data-agent system.",
        "",
        "## 中文目标",
        "",
        "阅读下面引用的运行证据和源码文件，提出一个小而清晰的项目级修改，用来改进 DAB data-agent 系统。",
        "",
        "## Parent Candidate",
        "",
        f"- `{manifest.get('parent_candidate') or 'none'}`",
        "",
        "## Run Summaries",
        "",
    ]

    for item in manifest["run_summaries"]:
        lines.extend(
            [
                f"### {item.get('case_group')}/{item.get('case_name')}",
                "",
                f"- Run dir: `{item['run_dir']}`",
                f"- Prompt version: `{item.get('prompt_version')}`",
                f"- Passed: `{item.get('passed')}`",
                f"- Validation reason: `{item.get('validation_reason')}`",
                f"- Problem candidates: `{item.get('localized_error_count')}`",
                "",
            ]
        )

        for index, problem in enumerate(item.get("top_problem_candidates") or [], start=1):
            lines.append(
                f"{index}. `{problem.get('stage')}.{problem.get('type')}` "
                f"({problem.get('confidence')}): {problem.get('subtype')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Evidence Files",
            "",
            "Read raw artifacts before editing source files.",
            "",
        ]
    )

    if manifest.get("filtered_analyzer_context"):
        lines.extend(
            [
                "## Filtered Analyzer Context",
                "",
                "The analyzer refs below are authoritative filtered failure context for this task.",
                "Do not revive suppressed analyzer evidence from raw run artifacts or older summaries.",
                "If raw artifacts seem to conflict with filtered analyzer context, preserve the filtered invariants and target only the allowed repair areas.",
                "",
            ]
        )

    for section in ("run_artifact_refs", "analyzer_refs", "script_report_refs", "source_refs", "scope_refs"):
        lines.extend([f"### {section}", ""])
        for ref in manifest.get(section) or []:
            exists = "exists" if ref.get("exists") else "missing"
            lines.append(f"- `{ref['path']}` ({exists})")
        lines.append("")

    lines.extend(
        [
            "## Expected Meta-Agent Output",
            "",
            "- `patch.diff` with a bounded project-level change.",
            "- `change_summary.md` explaining evidence, modified component, expected transfer, risks, and validation.",
            "- `manifest.json` for the child candidate.",
            "- `scores.json` after child evaluation, when available.",
            "",
            "## Constraints",
            "",
            "- Do not edit validators, ground truth, old logs, or `legacy/`.",
            "- Do not choose a hard-coded benchmark answer.",
            "- Prefer evolving prompts, analyzer logic, feedback adapters, task packaging, or loop orchestration.",
            "- Do not default to object-level prompt edits. First decide whether the failure is a data-agent behavior problem or a feedback/runner/analyzer/task-packaging problem.",
            "- If evidence is coarse, contradictory, missing, or repeatedly causes prompt regressions, improve feedback, runtime checks, analyzer classification, filtered context, or loop guards before adding more data-agent prompt constraints.",
            "- If a child regresses by using nonexistent schema columns, leaking validator-only counts, losing runtime logs, or losing a non-empty answer, prefer a local lint/analyzer/packaging repair over another prompt-only repair.",
            "- Runner changes are allowed only when evidence points to runner/context/artifact issues.",
            "",
        ]
    )

    return "\n".join(lines)


def build_evolution_task(
    run_dirs: list[Path],
    output_dir: Path,
    task_id: str | None = None,
    parent_candidate: Path | None = None,
    source_refs: list[Path] | None = None,
    filtered_analyzer_refs: list[Path] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    task_id = task_id or f"task_{time.strftime('%Y%m%d_%H%M%S')}"
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    normalized_run_dirs = [Path(path).resolve() for path in run_dirs]
    all_source_refs = [repo_path(path) for path in DEFAULT_SOURCE_REFS]
    if source_refs:
        all_source_refs.extend(repo_path(path) for path in source_refs)

    scope_refs = [repo_path(path) for path in DEFAULT_SCOPE_REFS]

    run_artifact_refs: list[dict[str, Any]] = []
    analyzer_refs: list[dict[str, Any]] = []
    script_report_refs: list[dict[str, Any]] = []
    run_summaries: list[dict[str, Any]] = []
    filtered_contexts = filtered_context_by_run_dir(filtered_analyzer_refs)

    operations = []
    checks = []

    for run_dir in normalized_run_dirs:
        run_exists = run_dir.exists()
        checks.append(
            {
                "name": "run_dir_exists",
                "passed": run_exists,
                "message": str(run_dir),
            }
        )
        if not run_exists:
            continue

        run_artifact_refs.extend(collect_run_artifact_refs(run_dir))
        if filtered_analyzer_refs:
            analyzer_refs.extend(
                as_ref(path.name, path, role="filtered_analyzer_output")
                for path in filtered_analyzer_refs
            )
        else:
            analyzer_refs.extend(collect_analyzer_refs(run_dir))
        script_report_refs.extend(collect_script_report_refs(run_dir))
        run_summaries.append(summarize_run(run_dir, filtered_contexts.get(str(run_dir.resolve()))))

    operations.append(
        {
            "name": "collect_evidence_refs",
            "status": "completed",
            "outputs": {
                "run_dir_count": len(normalized_run_dirs),
                "run_artifact_ref_count": len(run_artifact_refs),
                "analyzer_ref_count": len(analyzer_refs),
                "filtered_analyzer_ref_count": len(filtered_analyzer_refs or []),
                "script_report_ref_count": len(script_report_refs),
            },
            "checks": checks,
        }
    )

    source_ref_items = [as_ref(path.name, path, role="source_ref") for path in all_source_refs]
    scope_ref_items = [as_ref(path.name, path, role="scope_ref") for path in scope_refs]

    manifest: dict[str, Any] = {
        "task_id": task_id,
        "created_at": utc_now_iso(),
        "task_dir": str(task_dir),
        "parent_candidate": str(parent_candidate) if parent_candidate else None,
        "notes": notes,
        "run_dirs": [str(path) for path in normalized_run_dirs],
        "run_summaries": run_summaries,
        "run_artifact_refs": run_artifact_refs,
        "analyzer_refs": analyzer_refs,
        "filtered_analyzer_context": bool(filtered_analyzer_refs),
        "script_report_refs": script_report_refs,
        "source_refs": source_ref_items,
        "scope_refs": scope_ref_items,
    }

    manifest_path = task_dir / "context_manifest.json"
    task_md_path = task_dir / "task.md"
    manifest["context_manifest_path"] = str(manifest_path)
    manifest["task_markdown_path"] = str(task_md_path)

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    task_md_path.write_text(build_task_markdown(manifest), encoding="utf-8")

    report_path, _ = write_script_run_report(
        output_dir=task_dir,
        script_name="experiments/build_evolution_task.py",
        script_role="navigator_task_builder",
        started_at=started_at,
        status="success" if all(check["passed"] for check in checks) else "partial",
        inputs=[
            {"name": "run_dir", "path": str(path), "exists": path.exists()}
            for path in normalized_run_dirs
        ],
        operations=operations,
        outputs=[
            path_ref("context_manifest", manifest_path, role="task_package"),
            path_ref("task_markdown", task_md_path, role="task_package"),
        ],
        checks=checks,
        self_feedback={
            "confidence": "high" if analyzer_refs else "medium",
            "uncertainties": [] if analyzer_refs else ["No analyzer output was found for at least one run."],
            "evolution_hints": [
                "Use runtime-log, analyzer, comparison, and script-level evidence before editing agent components."
            ],
            "suggested_target_modules": [
                "prompts/dab",
                "adapters/runtime_observer.py",
                "experiments/analyze_agent_error.py",
                "adapters/feedback",
                "experiments/build_evolution_task.py",
            ],
        },
        report_stem="build_evolution_task",
    )

    manifest["script_run_report_path"] = str(report_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", action="append", required=True)
    parser.add_argument("--output-dir", default=str(BASE_DIR / "logs" / "meta_agent"))
    parser.add_argument("--task-id")
    parser.add_argument("--parent-candidate")
    parser.add_argument("--source-ref", action="append", default=[])
    parser.add_argument("--notes")

    args = parser.parse_args()

    manifest = build_evolution_task(
        run_dirs=[Path(path) for path in args.run_dir],
        output_dir=Path(args.output_dir),
        task_id=args.task_id,
        parent_candidate=Path(args.parent_candidate) if args.parent_candidate else None,
        source_refs=[Path(path) for path in args.source_ref],
        notes=args.notes,
    )

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nSaved task package to: {manifest['task_dir']}")


if __name__ == "__main__":
    main()
