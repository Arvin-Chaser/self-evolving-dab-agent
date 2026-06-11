import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DAB_ROOT = BASE_DIR / "benchmarks" / "DataAgentBench"
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(DAB_ROOT))

from llm_client import call_llm
from adapters.dab_validator import run_dab_validation


LOGS_DIR = BASE_DIR / "logs" / "dab"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_query(query_path: Path) -> str:
    raw = load_text(query_path).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip('"')


def build_prompt(prompt_path: Path, question: str, db_description: str) -> str:
    template = load_text(prompt_path)

    return template.format(
        question=question,
        db_description=db_description,
    )


def run_dab_eval(
    case_dir: Path,
    prompt_path: Path,
    version: str,
    db_description_path: Path | None = None,
):
    case_dir = case_dir.resolve()
    prompt_path = prompt_path.resolve()

    query_path = case_dir / "query.json"
    validate_path = case_dir / "validate.py"

    if db_description_path is None:
        db_description_path = case_dir.parent / "db_description_withhint.txt"

        if not db_description_path.exists():
            db_description_path = case_dir.parent / "db_description.txt"

    db_description_path = db_description_path.resolve()

    if not query_path.exists():
        raise FileNotFoundError(f"query.json not found: {query_path}")

    if not validate_path.exists():
        raise FileNotFoundError(f"validate.py not found: {validate_path}")

    if not db_description_path.exists():
        raise FileNotFoundError(f"db description not found: {db_description_path}")

    question = load_query(query_path)
    db_description = load_text(db_description_path)

    prompt = build_prompt(
        prompt_path=prompt_path,
        question=question,
        db_description=db_description,
    )

    print(f"Running DAB case: {case_dir}")
    print(f"Prompt version: {version}")
    print(f"Question: {question}")

    start_time = time.time()
    raw_output = call_llm(prompt)
    end_time = time.time()

    validation = run_dab_validation(
        validate_path=validate_path,
        llm_output=raw_output,
    )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = LOGS_DIR / f"run_{version}_{case_dir.parent.name}_{case_dir.name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "source": "DAB",
        "case_group": case_dir.parent.name,
        "case_name": case_dir.name,
        "case_dir": str(case_dir),

        "prompt_version": version,
        "prompt_path": str(prompt_path),

        "question": question,
        "db_description_path": str(db_description_path),

        "llm_output": raw_output,

        "passed": validation["passed"],
        "validation_reason": validation["reason"],

        "latency_sec": end_time - start_time,
        "num_llm_calls": 1,
    }

    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    with open(run_dir / "llm_output.txt", "w", encoding="utf-8") as f:
        f.write(raw_output)

    summary = {
        "prompt_version": version,
        "total": 1,
        "correct": 1 if validation["passed"] else 0,
        "accuracy": 1.0 if validation["passed"] else 0.0,
        "validation_reason": validation["reason"],
        "run_dir": str(run_dir),
    }

    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n=== DAB Evaluation Finished ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {run_dir}")

    return {
        "run_dir": str(run_dir),
        "result": result,
        "summary": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--db-description", default=None)

    args = parser.parse_args()

    run_dab_eval(
        case_dir=Path(args.case_dir),
        prompt_path=Path(args.prompt),
        version=args.version,
        db_description_path=Path(args.db_description) if args.db_description else None,
    )

