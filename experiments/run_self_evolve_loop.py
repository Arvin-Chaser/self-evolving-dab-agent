import argparse
import json
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str]):
    print("\n" + "=" * 80)
    print("Running command:")
    print(" ".join(cmd))
    print("=" * 80)

    completed = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        text=True,
    )

    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with return code {completed.returncode}: {' '.join(cmd)}")


def find_latest_run_dir(version: str, case_dir: Path) -> Path:
    case_group = case_dir.parent.name
    case_name = case_dir.name

    pattern = f"run_{version}_{case_group}_{case_name}_*"
    candidates = sorted(
        (BASE_DIR / "logs" / "dab_agent").glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(f"No run dir found with pattern: {pattern}")

    return candidates[0]


def load_result(run_dir: Path) -> dict:
    result_path = run_dir / "result.json"

    if not result_path.exists():
        raise FileNotFoundError(f"Missing result.json: {result_path}")

    return json.loads(result_path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--initial-prompt", required=True)
    parser.add_argument("--initial-version", required=True)

    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument("--timeout-sec", type=int, default=600)

    parser.add_argument(
        "--prompt-out-dir",
        default="prompts/dab/evolved",
    )

    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    current_prompt = Path(args.initial_prompt)
    current_version = args.initial_version

    prompt_out_dir = BASE_DIR / args.prompt_out_dir
    prompt_out_dir.mkdir(parents=True, exist_ok=True)

    history = []

    for i in range(1, args.max_iters + 1):
        print("\n" + "#" * 100)
        print(f"SELF-EVOLVE ITERATION {i}/{args.max_iters}")
        print(f"Prompt: {current_prompt}")
        print(f"Version: {current_version}")
        print("#" * 100)

        # 1. Run agent-generated code
        run_cmd([
            sys.executable,
            "experiments/run_dab_agent.py",
            "--case-dir", str(case_dir),
            "--prompt", str(current_prompt),
            "--version", current_version,
            "--timeout-sec", str(args.timeout_sec),
        ])

        run_dir = find_latest_run_dir(current_version, case_dir)
        print(f"\nLatest run dir: {run_dir}")

        result = load_result(run_dir)
        passed = bool(result.get("passed"))
        validation_reason = result.get("validation_reason", "")

        print("\nRun result:")
        print(json.dumps({
            "passed": passed,
            "validation_reason": validation_reason,
            "run_dir": str(run_dir),
        }, indent=2, ensure_ascii=False))

        # 2. Analyze error into 8-stage summary
        run_cmd([
            sys.executable,
            "experiments/analyze_agent_error.py",
            "--run-dir", str(run_dir),
        ])

        summary_path = run_dir / "agent_error_summary.json"

        if not summary_path.exists():
            raise FileNotFoundError(f"Missing agent_error_summary.json: {summary_path}")

        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        history.append({
            "iteration": i,
            "version": current_version,
            "prompt": str(current_prompt),
            "run_dir": str(run_dir),
            "passed": passed,
            "validation_reason": validation_reason,
            "stage_distribution": summary.get("stage_distribution", {}),
            "error_distribution": summary.get("error_distribution", {}),
        })

        # 3. Stop if passed
        if passed:
            print("\n✅ Passed. Stop self-evolution loop.")
            break

        # 4. If not passed and still have budget, evolve prompt
        if i == args.max_iters:
            print("\nReached max iterations. Stop.")
            break

        next_version = f"{args.initial_version}_iter{i + 1}"
        next_prompt = prompt_out_dir / f"{next_version}.txt"

        run_cmd([
            sys.executable,
            "experiments/evolve_code_agent_prompt.py",
            "--parent", str(current_prompt),
            "--summary", str(summary_path),
            "--out", str(next_prompt),
        ])

        current_prompt = next_prompt
        current_version = next_version

    # Save loop history
    loop_history_path = BASE_DIR / "logs" / "dab_agent" / "self_evolve_loop_history.json"
    loop_history_path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print("SELF-EVOLVE LOOP FINISHED")
    print(f"History saved to: {loop_history_path}")
    print("=" * 80)

    print(json.dumps(history, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()