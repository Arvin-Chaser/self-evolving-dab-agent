import json
import time
from pathlib import Path

from llm_client import call_llm
from sql_runner import run_sql

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_EVAL_CASES_PATH = DATA_DIR / "eval_cases.jsonl"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def resolve_path(path):
    """
    Convert a relative path into an absolute path based on the project root.
    """
    path = Path(path)

    if path.is_absolute():
        return path

    return BASE_DIR / path


def load_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_cases(cases_path=None):
    if cases_path is None:
        cases_path = DEFAULT_EVAL_CASES_PATH
    else:
        cases_path = resolve_path(cases_path)

    cases = []

    with open(cases_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            cases.append(json.loads(line))

    return cases


def build_prompt(question: str, prompt_path: Path) -> str:
    prompt_template = load_text(prompt_path)
    schema = load_text(SCHEMA_PATH)

    return prompt_template.format(
        schema=schema,
        question=question,
    )


def clean_sql(raw_output: str) -> str:
    """
    Remove common LLM formatting artifacts.
    """
    sql = raw_output.strip()

    if sql.startswith("```sql"):
        sql = sql.removeprefix("```sql").strip()

    if sql.startswith("```"):
        sql = sql.removeprefix("```").strip()

    if sql.endswith("```"):
        sql = sql.removesuffix("```").strip()

    if sql.lower().startswith("sql:"):
        sql = sql[4:].strip()

    return sql


def evaluate_case(case: dict, prompt_path: Path, prompt_version: str) -> dict:
    question = case["question"]
    gold_sql = case["gold_sql"]

    prompt = build_prompt(question, prompt_path)

    start_time = time.time()

    raw_output = call_llm(prompt)
    pred_sql = clean_sql(raw_output)

    llm_end_time = time.time()

    pred_exec = run_sql(pred_sql)
    gold_exec = run_sql(gold_sql)

    end_time = time.time()

    result_match = (
        pred_exec["success"]
        and gold_exec["success"]
        and pred_exec["result"] == gold_exec["result"]
    )

    return {
        "id": case["id"],
        "prompt_version": prompt_version,
        "prompt_path": str(prompt_path),

        "question": question,

        "gold_sql": gold_sql,
        "pred_sql": pred_sql,
        "raw_llm_output": raw_output,

        "gold_exec_success": gold_exec["success"],
        "pred_exec_success": pred_exec["success"],

        "gold_result": gold_exec["result"],
        "pred_result": pred_exec["result"],

        "result_match": result_match,

        "gold_error": gold_exec["error"],
        "pred_error": pred_exec["error"],

        "latency_llm_sec": llm_end_time - start_time,
        "latency_total_sec": end_time - start_time,

        "num_llm_calls": 1,
    }


def summarize_results(results: list[dict], prompt_version: str, prompt_path: Path) -> dict:
    total = len(results)

    if total == 0:
        return {
            "prompt_version": prompt_version,
            "prompt_path": str(prompt_path),
            "total": 0,
            "correct": 0,
            "accuracy": 0,
            "exec_success_count": 0,
            "exec_success_rate": 0,
            "avg_llm_latency_sec": 0,
            "avg_total_latency_sec": 0,
            "total_llm_calls": 0,
        }

    correct = sum(1 for r in results if r["result_match"])
    exec_success_count = sum(1 for r in results if r["pred_exec_success"])

    return {
        "prompt_version": prompt_version,
        "prompt_path": str(prompt_path),

        "total": total,
        "correct": correct,
        "accuracy": correct / total,

        "exec_success_count": exec_success_count,
        "exec_success_rate": exec_success_count / total,

        "avg_llm_latency_sec": sum(r["latency_llm_sec"] for r in results) / total,
        "avg_total_latency_sec": sum(r["latency_total_sec"] for r in results) / total,

        "total_llm_calls": sum(r["num_llm_calls"] for r in results),
    }


def run_eval(prompt_path, prompt_version, cases_path=None):
    LOGS_DIR.mkdir(exist_ok=True)

    prompt_path = resolve_path(prompt_path)

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    cases = load_cases(cases_path)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = LOGS_DIR / f"run_{prompt_version}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for case in cases:
        print(f"Evaluating {case['id']}...")

        result = evaluate_case(
            case=case,
            prompt_path=prompt_path,
            prompt_version=prompt_version,
        )

        results.append(result)

        status = "PASS" if result["result_match"] else "FAIL"
        print(f"  [{status}] {case['question']}")

        if not result["result_match"]:
            print(f"  pred_sql: {result['pred_sql']}")
            print(f"  pred_error: {result['pred_error']}")

    summary = summarize_results(
        results=results,
        prompt_version=prompt_version,
        prompt_path=prompt_path,
    )

    results_path = run_dir / "results.jsonl"
    results_pretty_path = run_dir / "results_pretty.json"
    results_readable_path = run_dir / "results_readable.txt"
    summary_path = run_dir / "summary.json"

    with open(results_path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    with open(results_pretty_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    with open(results_readable_path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, indent=2, ensure_ascii=False))
            f.write("\n\n")

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nEvaluation finished.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {run_dir}")

    return {
        "run_dir": str(run_dir),
        "summary": summary,
        "results_path": str(results_path),
        "summary_path": str(summary_path),
    }


if __name__ == "__main__":
    run_eval(
        prompt_path="prompts/text2sql_prompt.txt",
        prompt_version="baseline",
    )