import argparse
import json
from collections import Counter
from pathlib import Path


def classify_failure(result: dict) -> str:
    if result["result_match"]:
        return "correct"

    if not result["pred_exec_success"]:
        error = result.get("pred_error") or ""

        if "no such table" in error or "no such column" in error:
            return "schema_grounding_error"

        if "syntax error" in error:
            return "sql_syntax_error"

        return "sql_execution_error"

    gold = result.get("gold_result")
    pred = result.get("pred_result")

    if gold is None or pred is None:
        return "unknown_error"

    if len(gold) == len(pred) and len(gold) > 0 and len(pred) > 0:
        gold_width = len(gold[0])
        pred_width = len(pred[0])

        if gold_width != pred_width:
            return "projection_error"

    if len(gold) != len(pred):
        return "filter_or_join_error"

    return "result_mismatch"


def analyze_run(run_dir: Path) -> dict:
    results_path = run_dir / "results.jsonl"
    summary_path = run_dir / "summary.json"

    if not results_path.exists():
        raise FileNotFoundError(f"results.jsonl not found: {results_path}")

    if not summary_path.exists():
        raise FileNotFoundError(f"summary.json not found: {summary_path}")

    results = []

    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                results.append(json.loads(line))

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    failed_cases = []
    counter = Counter()

    for result in results:
        if result["result_match"]:
            continue

        error_type = classify_failure(result)
        counter[error_type] += 1

        failed_cases.append({
            "id": result["id"],
            "question": result["question"],
            "error_type": error_type,
            "gold_sql": result["gold_sql"],
            "pred_sql": result["pred_sql"],
            "gold_result": result["gold_result"],
            "pred_result": result["pred_result"],
            "pred_error": result["pred_error"],
        })

    error_summary = {
        "run_dir": str(run_dir),
        "prompt_version": summary.get("prompt_version"),
        "prompt_path": summary.get("prompt_path"),

        "total": summary["total"],
        "correct": summary["correct"],
        "accuracy": summary["accuracy"],

        "error_distribution": dict(counter),
        "failed_cases": failed_cases,
    }

    out_path = run_dir / "error_summary.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(error_summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(error_summary, indent=2, ensure_ascii=False))
    print(f"\nSaved error summary to: {out_path}")

    return error_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)

    args = parser.parse_args()

    analyze_run(Path(args.run_dir))