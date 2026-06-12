#!/usr/bin/env python3
"""Run the minimal DAB code-agent signal-evolve loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extract_primary_signal import extract_primary_signal
from evolve_dab_prompt import evolve_prompt


DEFAULT_OUTPUT_DIR = Path("logs/dab_agent/min_loop_demo")
DEFAULT_TIMEOUT_SEC = 120


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_result_json(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "result.json"
    if not result_path.exists():
        return {
            "passed": False,
            "validation_reason": f"Missing result.json at {result_path}.",
            "run_dir": str(run_dir),
        }
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.setdefault("run_dir", str(run_dir))
    result.setdefault("passed", False)
    result.setdefault("validation_reason", "")
    return result


def case_name(case_dir: Path) -> str:
    return case_dir.name or str(abs(hash(str(case_dir))))


def planned_run_dir(output_dir: Path, label: str, index: int, case_dir: Path) -> Path:
    return output_dir / f"{label}_runs" / f"{index:03d}_{case_name(case_dir)}"


def find_real_run_dir(version: str) -> Path:
    candidates = [
        Path("logs/dab_agent") / version,
        Path("logs/dab") / version,
        Path(version),
    ]
    for candidate in candidates:
        if (candidate / "result.json").exists():
            return candidate
    return candidates[0]


def run_one_case(
    *,
    case_dir: Path,
    prompt: Path,
    run_dir: Path,
    version: str,
    dab_root: Path,
    timeout_sec: int,
    dry_run: bool,
    label: str,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        result = {
            "case_dir": str(case_dir),
            "label": label,
            "passed": False,
            "prompt": str(prompt),
            "run_dir": str(run_dir),
            "validation_reason": "Dry run placeholder: DAB agent execution was skipped.",
            "version": version,
        }
        write_json(run_dir / "result.json", result)
        return result

    cmd = [
        sys.executable,
        "experiments/run_dab_agent.py",
        "--case-dir",
        str(case_dir),
        "--prompt",
        str(prompt),
        "--version",
        version,
        "--dab-root",
        str(dab_root),
        "--timeout-sec",
        str(timeout_sec),
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    real_run_dir = find_real_run_dir(version)
    invocation = {
        "case_dir": str(case_dir),
        "command": cmd,
        "expected_run_dir": str(real_run_dir),
        "label": label,
        "returncode": completed.returncode,
        "stderr_tail": completed.stderr[-4000:],
        "stdout_tail": completed.stdout[-4000:],
    }
    write_json(run_dir / "run_self_evolve_invocation.json", invocation)
    result = read_result_json(real_run_dir)
    result["case_dir"] = str(case_dir)
    result["label"] = label
    result["subprocess_returncode"] = completed.returncode
    return result


def run_cases(
    *,
    cases: list[Path],
    prompt: Path,
    output_dir: Path,
    version_prefix: str,
    dab_root: Path,
    timeout_sec: int,
    dry_run: bool,
    label: str,
) -> list[dict[str, Any]]:
    results = []
    for index, case_dir in enumerate(cases, start=1):
        version = f"{version_prefix}_{index:03d}_{case_name(case_dir)}"
        run_dir = planned_run_dir(output_dir, label, index, case_dir)
        results.append(
            run_one_case(
                case_dir=case_dir,
                prompt=prompt,
                run_dir=run_dir,
                version=version,
                dab_root=dab_root,
                timeout_sec=timeout_sec,
                dry_run=dry_run,
                label=label,
            )
        )
    return results


def analyze_one_run(run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    try:
        from analyze_agent_error import analyze_run

        analysis = analyze_run(run_dir)
        if isinstance(analysis, dict):
            return analysis
    except Exception as exc:
        return {
            "stage": "analysis",
            "error": type(exc).__name__,
            "message": str(exc),
            "run_dir": str(run_dir),
            "validation_reason": result.get("validation_reason", ""),
        }
    return {
        "stage": "unknown",
        "message": str(result.get("validation_reason", "")),
        "run_dir": str(run_dir),
        "validation_reason": result.get("validation_reason", ""),
    }


def summarize_parent_errors(parent_results: list[dict[str, Any]]) -> dict[str, Any]:
    stage_distribution: Counter[str] = Counter()
    error_distribution: Counter[str] = Counter()
    localized_errors: list[dict[str, Any]] = []

    for result in parent_results:
        if bool(result.get("passed")):
            continue
        run_dir = Path(str(result.get("run_dir", "")))
        analysis = analyze_one_run(run_dir, result)
        stage = str(analysis.get("stage") or analysis.get("failed_stage") or "unknown")
        message = str(
            analysis.get("message")
            or analysis.get("error")
            or analysis.get("validation_reason")
            or result.get("validation_reason")
            or "No validation reason was provided."
        )
        stage_distribution[stage] += 1
        error_distribution[message[:200]] += 1
        localized_errors.append(
            {
                "case_dir": result.get("case_dir", ""),
                "message": message,
                "run_dir": str(run_dir),
                "stage": stage,
                "validation_reason": result.get("validation_reason", ""),
            }
        )

    return {
        "stage_distribution": dict(stage_distribution),
        "error_distribution": dict(error_distribution),
        "localized_errors": localized_errors,
    }


def score(results: list[dict[str, Any]]) -> tuple[int, int, float]:
    total = len(results)
    passed = sum(1 for result in results if bool(result.get("passed")))
    return total, passed, (passed / total if total else 0.0)


def compare_cases(parent_results: list[dict[str, Any]], child_results: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    parent_by_case = {str(result.get("case_dir")): bool(result.get("passed")) for result in parent_results}
    child_by_case = {str(result.get("case_dir")): bool(result.get("passed")) for result in child_results}
    improved = []
    regressed = []
    unchanged_failed = []
    for case_dir, parent_passed in parent_by_case.items():
        child_passed = child_by_case.get(case_dir, False)
        if child_passed and not parent_passed:
            improved.append(case_dir)
        elif parent_passed and not child_passed:
            regressed.append(case_dir)
        elif not parent_passed and not child_passed:
            unchanged_failed.append(case_dir)
    return improved, regressed, unchanged_failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", required=True, type=Path)
    parser.add_argument("--parent-prompt", required=True, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--dab-root", default=Path("/home/m0st1ma/research/DataAgentBench"), type=Path)
    parser.add_argument("--timeout-sec", default=DEFAULT_TIMEOUT_SEC, type=int)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-llm-evolver", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_cases = args.cases[: args.max_cases] if args.max_cases is not None else args.cases
    output_dir: Path = args.output_dir
    artifacts_dir = output_dir / "artifacts"
    child_prompt_path = artifacts_dir / "child_prompt.txt"
    parent_error_summary_path = output_dir / "parent_error_summary.json"
    primary_signal_path = artifacts_dir / "primary_signal.json"
    comparison_path = output_dir / "comparison_summary.json"

    planned_steps = [
        "validate paths and parameters",
        "run parent prompt on selected DAB cases",
        "analyze parent stage-level failures",
        "extract primary signal",
        "evolve child prompt with rule-based mutation",
        "run child prompt on the same DAB cases",
        "compare validator passed scores",
    ]
    write_json(
        output_dir / "run_plan.json",
        {
            "cases": [str(path) for path in selected_cases],
            "dab_root": str(args.dab_root),
            "dry_run": args.dry_run,
            "output_dir": str(output_dir),
            "parent_prompt": str(args.parent_prompt),
            "planned_steps": planned_steps,
            "timeout_sec": args.timeout_sec,
            "use_llm_evolver": args.use_llm_evolver,
        },
    )
    if args.dry_run:
        print(json.dumps({"dry_run": True, "planned_steps": planned_steps}, indent=2))

    parent_results = run_cases(
        cases=selected_cases,
        prompt=args.parent_prompt,
        output_dir=output_dir,
        version_prefix="parent_min_loop",
        dab_root=args.dab_root,
        timeout_sec=args.timeout_sec,
        dry_run=args.dry_run,
        label="parent",
    )
    parent_error_summary = summarize_parent_errors(parent_results)
    write_json(parent_error_summary_path, parent_error_summary)

    primary_signal = extract_primary_signal(parent_error_summary_path)
    write_json(primary_signal_path, primary_signal)
    evolve_prompt(
        args.parent_prompt,
        primary_signal_path,
        child_prompt_path,
        use_llm_evolver=args.use_llm_evolver,
    )

    child_results = run_cases(
        cases=selected_cases,
        prompt=child_prompt_path,
        output_dir=output_dir,
        version_prefix="child_min_loop",
        dab_root=args.dab_root,
        timeout_sec=args.timeout_sec,
        dry_run=args.dry_run,
        label="child",
    )

    parent_total, parent_passed, parent_score = score(parent_results)
    child_total, child_passed, child_score = score(child_results)
    improved_cases, regressed_cases, unchanged_failed_cases = compare_cases(parent_results, child_results)
    comparison = {
        "parent_prompt": str(args.parent_prompt),
        "child_prompt": str(child_prompt_path),
        "selected_signal": primary_signal.get("selected_signal") or primary_signal.get("message", ""),
        "selected_stage": primary_signal.get("selected_stage") or primary_signal.get("stage", "unknown"),
        "parent_total": parent_total,
        "parent_passed": parent_passed,
        "parent_score": parent_score,
        "child_total": child_total,
        "child_passed": child_passed,
        "child_score": child_score,
        "improved_cases": improved_cases,
        "regressed_cases": regressed_cases,
        "unchanged_failed_cases": unchanged_failed_cases,
        "parent_run_dirs": [str(result.get("run_dir", "")) for result in parent_results],
        "child_run_dirs": [str(result.get("run_dir", "")) for result in child_results],
        "primary_signal_path": str(primary_signal_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    write_json(comparison_path, comparison)
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
