#!/usr/bin/env python3
"""Run the minimal DAB code-agent signal-evolve loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from extract_primary_signal import extract_primary_signal
from evolve_dab_prompt import evolve_prompt


DEFAULT_OUTPUT_DIR = Path("logs/dab_agent/min_loop_demo")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_dab_agent(
    *,
    cases: list[Path],
    prompt: Path,
    output_dir: Path,
    max_cases: int | None,
    dry_run: bool,
    label: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        result = {
            "label": label,
            "dry_run": True,
            "cases": [str(path) for path in cases],
            "prompt": str(prompt),
            "output_dir": str(output_dir),
            "max_cases": max_cases,
            "success": False,
            "stage": "pipeline_wiring",
            "message": "Dry run placeholder: DAB agent execution was skipped.",
        }
        write_json(output_dir / "run_result.json", result)
        write_json(
            output_dir / "stage_failures.json",
            {
                "success": False,
                "stage": "pipeline_wiring",
                "observation": "Dry run verified wiring through run, signal extraction, prompt evolution, and comparison.",
            },
        )
        return result

    cmd = [
        sys.executable,
        "experiments/run_dab_agent.py",
        "--prompt",
        str(prompt),
        "--output-dir",
        str(output_dir),
    ]
    for case in cases:
        cmd.extend(["--cases", str(case)])
    if max_cases is not None:
        cmd.extend(["--max-cases", str(max_cases)])

    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    result = {
        "label": label,
        "dry_run": False,
        "command": cmd,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "success": completed.returncode == 0,
    }
    write_json(output_dir / "run_self_evolve_invocation.json", result)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} DAB run failed with exit code {completed.returncode}. See {output_dir}.")
    return result


def compare_runs(parent_result: dict[str, Any], child_result: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    parent_success = bool(parent_result.get("success"))
    child_success = bool(child_result.get("success"))
    if child_success and not parent_success:
        verdict = "child_improved"
    elif child_success == parent_success:
        verdict = "tie"
    else:
        verdict = "child_regressed"
    return {
        "verdict": verdict,
        "parent_success": parent_success,
        "child_success": child_success,
        "primary_signal": signal,
        "parent_result": parent_result,
        "child_result": child_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", required=True, type=Path)
    parser.add_argument("--parent-prompt", required=True, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir: Path = args.output_dir
    parent_run_dir = output_dir / "parent_run"
    child_run_dir = output_dir / "child_run"
    artifacts_dir = output_dir / "artifacts"
    child_prompt_path = artifacts_dir / "child_prompt.txt"
    signal_path = artifacts_dir / "primary_signal.json"
    evolution_summary_path = artifacts_dir / "evolution_summary.json"
    comparison_path = output_dir / "comparison_summary.json"
    selected_cases = args.cases[: args.max_cases] if args.max_cases is not None else args.cases

    write_json(
        output_dir / "run_plan.json",
        {
            "dry_run": args.dry_run,
            "parent_prompt": str(args.parent_prompt),
            "child_prompt": str(child_prompt_path),
            "cases": [str(path) for path in selected_cases],
            "case_count": len(selected_cases),
            "output_dir": str(output_dir),
        },
    )

    parent_result = run_dab_agent(
        cases=selected_cases,
        prompt=args.parent_prompt,
        output_dir=parent_run_dir,
        max_cases=args.max_cases,
        dry_run=args.dry_run,
        label="parent",
    )
    signal = extract_primary_signal(parent_run_dir)
    write_json(signal_path, signal)

    evolution_summary = evolve_prompt(args.parent_prompt, signal_path, child_prompt_path, dry_run=args.dry_run)
    write_json(evolution_summary_path, evolution_summary)

    child_result = run_dab_agent(
        cases=selected_cases,
        prompt=child_prompt_path,
        output_dir=child_run_dir,
        max_cases=args.max_cases,
        dry_run=args.dry_run,
        label="child",
    )

    comparison = compare_runs(parent_result, child_result, signal)
    write_json(comparison_path, comparison)
    print(json.dumps({"comparison_summary": str(comparison_path), "verdict": comparison["verdict"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
