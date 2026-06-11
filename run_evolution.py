import argparse
import json
from pathlib import Path

from evaluator import run_eval
from analyze_errors import analyze_run
from evolve_prompt import evolve_prompt


BASE_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = BASE_DIR / "archive"
VERSIONS_PATH = ARCHIVE_DIR / "versions.jsonl"


def append_archive(record: dict):
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    with open(VERSIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_one_generation(parent_prompt, parent_version, child_prompt, child_version):
    print("\n=== Step 1: Evaluate parent prompt ===")
    parent_eval = run_eval(
        prompt_path=parent_prompt,
        prompt_version=parent_version,
    )

    parent_run_dir = Path(parent_eval["run_dir"])

    print("\n=== Step 2: Analyze parent failures ===")
    error_summary = analyze_run(parent_run_dir)

    print("\n=== Step 3: Evolve prompt ===")
    evolution_metadata = evolve_prompt(
        parent_prompt_path=Path(parent_prompt),
        error_summary_path=parent_run_dir / "error_summary.json",
        output_prompt_path=Path(child_prompt),
    )

    print("\n=== Step 4: Evaluate child prompt ===")
    child_eval = run_eval(
        prompt_path=child_prompt,
        prompt_version=child_version,
    )

    archive_record = {
        "child_version": child_version,
        "parent_version": parent_version,

        "parent_prompt": str(parent_prompt),
        "child_prompt": str(child_prompt),

        "parent_run_dir": parent_eval["run_dir"],
        "child_run_dir": child_eval["run_dir"],

        "parent_summary": parent_eval["summary"],
        "child_summary": child_eval["summary"],

        "error_distribution": error_summary["error_distribution"],
        "modification_summary": evolution_metadata["modification_summary"],
    }

    append_archive(archive_record)

    print("\n=== Evolution finished ===")
    print(json.dumps(archive_record, indent=2, ensure_ascii=False))
    print(f"\nArchive saved to: {VERSIONS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parent-prompt", required=True)
    parser.add_argument("--parent-version", required=True)
    parser.add_argument("--child-prompt", required=True)
    parser.add_argument("--child-version", required=True)

    args = parser.parse_args()

    run_one_generation(
        parent_prompt=args.parent_prompt,
        parent_version=args.parent_version,
        child_prompt=args.child_prompt,
        child_version=args.child_version,
    )