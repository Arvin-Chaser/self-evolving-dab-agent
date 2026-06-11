import argparse
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from llm_client import call_llm


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_query(query_path: Path) -> str:
    raw = load_text(query_path).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip('"')


def extract_python_code(raw_output: str) -> str:
    """
    Extract Python code from LLM output.

    Supports:
    ```python
    ...
    ```

    If no code fence exists, return raw text.
    """
    text = raw_output.strip()

    match = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"

    match = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip() + "\n"

    return text + "\n"


def get_sqlite_schema(db_path: Path, table_name: str = "publicationinfo") -> str:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return f"No schema found for table {table_name}."

    return row[0]


def get_sample_rows(db_path: Path, limit: int = 3) -> str:
    """
    Get compact sample rows from publicationinfo.

    We only include a few fields because cpc can be long.
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        """
        SELECT filing_date, publication_date, grant_date, substr(cpc, 1, 800)
        FROM publicationinfo
        WHERE cpc IS NOT NULL
        LIMIT ?
        """,
        (limit,),
    )

    rows = cur.fetchall()
    conn.close()

    formatted = []

    for row in rows:
        formatted.append(
            {
                "filing_date": row[0],
                "publication_date": row[1],
                "grant_date": row[2],
                "cpc_prefix": row[3],
            }
        )

    return json.dumps(formatted, indent=2, ensure_ascii=False)


def build_prompt(
    prompt_path: Path,
    question: str,
    db_description: str,
    sqlite_schema: str,
    sample_rows: str,
    dab_root: Path,
    case_dir: Path,
    publication_db_path: Path,
    cpc_definition_sql_path: Path,
    final_answer_path: Path,
    stage_trace_path: Path,
) -> str:
    """
    Build prompt by replacing only our known placeholders.

    Important:
    Do NOT use str.format() here, because evolved prompts may contain
    literal braces such as EMA_{t-1}, JSON examples, dictionaries, etc.
    str.format() would mistakenly treat them as template variables.
    """
    template = load_text(prompt_path)

    replacements = {
        "{question}": question,
        "{db_description}": db_description,
        "{sqlite_schema}": sqlite_schema,
        "{sample_rows}": sample_rows,
        "{dab_root}": str(dab_root),
        "{case_dir}": str(case_dir),
        "{publication_db_path}": str(publication_db_path),
        "{cpc_definition_sql_path}": str(cpc_definition_sql_path),
        "{final_answer_path}": str(final_answer_path),
        "{stage_trace_path}": str(stage_trace_path),
    }

    prompt = template

    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    return prompt


def load_validate_function(validate_path: Path, dab_root: Path):
    """
    Dynamically load DAB validate.py.
    """
    sys.path.insert(0, str(dab_root))

    spec = importlib.util.spec_from_file_location(
        "dab_validate_module",
        validate_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "validate"):
        raise AttributeError(f"No validate() function found in {validate_path}")

    return module.validate


def execute_generated_code(
    generated_code_path: Path,
    run_dir: Path,
    final_answer_path: Path,
    stage_trace_path: Path,
    dab_root: Path,
    case_dir: Path,
    publication_db_path: Path,
    cpc_definition_sql_path: Path,
    timeout_sec: int,
) -> dict:
    env = os.environ.copy()

    env["DAB_ROOT"] = str(dab_root)
    env["CASE_DIR"] = str(case_dir)
    env["PUBLICATION_DB_PATH"] = str(publication_db_path)
    env["CPC_DEFINITION_SQL_PATH"] = str(cpc_definition_sql_path)
    env["FINAL_ANSWER_PATH"] = str(final_answer_path)
    env["STAGE_TRACE_PATH"] = str(stage_trace_path)

    # Prevent local LLM/GitHub proxy pollution from affecting generated code unless needed.
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    env.setdefault("no_proxy", "localhost,127.0.0.1,::1")

    start = time.time()

    try:
        completed = subprocess.run(
            [sys.executable, str(generated_code_path)],
            cwd=str(run_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )

        end = time.time()

        return {
            "execution_success": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "latency_sec": end - start,
            "timeout": False,
        }

    except subprocess.TimeoutExpired as e:
        end = time.time()

        return {
            "execution_success": False,
            "returncode": None,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "latency_sec": end - start,
            "timeout": True,
            "error": f"timeout after {timeout_sec} seconds",
        }

    except Exception as e:
        end = time.time()

        return {
            "execution_success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "latency_sec": end - start,
            "timeout": False,
            "error": f"{type(e).__name__}: {str(e)}",
        }


def run_dab_agent(
    case_dir: Path,
    prompt_path: Path,
    version: str,
    dab_root: Path,
    timeout_sec: int,
):
    case_dir = case_dir.resolve()
    prompt_path = prompt_path.resolve()
    dab_root = dab_root.resolve()

    query_path = case_dir / "query.json"
    validate_path = case_dir / "validate.py"

    case_group_dir = case_dir.parent
    db_description_path = case_group_dir / "db_description_withhint.txt"

    if not db_description_path.exists():
        db_description_path = case_group_dir / "db_description.txt"

    dataset_dir = case_group_dir / "query_dataset"
    publication_db_path = dataset_dir / "patent_publication.db"
    cpc_definition_sql_path = dataset_dir / "patent_CPCDefinition.sql"

    required_paths = [
        query_path,
        validate_path,
        db_description_path,
        publication_db_path,
        cpc_definition_sql_path,
        prompt_path,
    ]

    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"Required path not found: {path}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = (
        BASE_DIR
        / "logs"
        / "dab_agent"
        / f"run_{version}_{case_group_dir.name}_{case_dir.name}_{timestamp}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    final_answer_path = run_dir / "final_answer.txt"
    stage_trace_path = run_dir / "stage_trace.json"
    generated_solve_path = run_dir / "generated_solve.py"

    question = load_query(query_path)
    db_description = load_text(db_description_path)
    sqlite_schema = get_sqlite_schema(publication_db_path)
    sample_rows = get_sample_rows(publication_db_path)

    prompt = build_prompt(
        prompt_path=prompt_path,
        question=question,
        db_description=db_description,
        sqlite_schema=sqlite_schema,
        sample_rows=sample_rows,
        dab_root=dab_root,
        case_dir=case_dir,
        publication_db_path=publication_db_path,
        cpc_definition_sql_path=cpc_definition_sql_path,
        final_answer_path=final_answer_path,
        stage_trace_path=stage_trace_path,
    )

    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    print(f"Running DAB agent case: {case_dir}")
    print(f"Prompt version: {version}")
    print(f"Run dir: {run_dir}")
    print("Calling LLM to generate solve.py...")

    llm_start = time.time()

    try:
        raw_llm_output = call_llm(prompt)
        llm_error = None
    except Exception as e:
        raw_llm_output = ""
        llm_error = f"{type(e).__name__}: {str(e)}"

    llm_end = time.time()

    (run_dir / "raw_llm_output.txt").write_text(raw_llm_output, encoding="utf-8")

    if llm_error:
        result = {
            "source": "DAB",
            "mode": "agent_generated_code",
            "case_group": case_group_dir.name,
            "case_name": case_dir.name,
            "case_dir": str(case_dir),
            "prompt_version": version,
            "prompt_path": str(prompt_path),
            "question": question,
            "passed": False,
            "validation_reason": f"llm_api_error: {llm_error}",
            "llm_latency_sec": llm_end - llm_start,
            "execution": None,
            "final_answer": "",
            "run_dir": str(run_dir),
        }

        save_result(run_dir, result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    generated_code = extract_python_code(raw_llm_output)
    generated_solve_path.write_text(generated_code, encoding="utf-8")

    print("Generated solve.py saved.")
    print("Executing generated code...")

    execution = execute_generated_code(
        generated_code_path=generated_solve_path,
        run_dir=run_dir,
        final_answer_path=final_answer_path,
        stage_trace_path=stage_trace_path,
        dab_root=dab_root,
        case_dir=case_dir,
        publication_db_path=publication_db_path,
        cpc_definition_sql_path=cpc_definition_sql_path,
        timeout_sec=timeout_sec,
    )

    (run_dir / "execution_stdout.txt").write_text(
        execution.get("stdout", "") or "",
        encoding="utf-8",
    )
    (run_dir / "execution_stderr.txt").write_text(
        execution.get("stderr", "") or "",
        encoding="utf-8",
    )

    if final_answer_path.exists():
        final_answer = final_answer_path.read_text(encoding="utf-8")
    else:
        final_answer = ""

    validate = load_validate_function(validate_path, dab_root)

    if not execution["execution_success"]:
        passed = False
        reason = (
            "agent_code_execution_error: "
            + (execution.get("error") or execution.get("stderr") or "unknown execution error")
        )

    elif not final_answer.strip():
        passed = False
        reason = "missing_final_answer_file_or_empty_answer"

    else:
        try:
            passed, reason = validate(final_answer)
            passed = bool(passed)
            reason = str(reason)
        except Exception as e:
            passed = False
            reason = f"validator_runtime_error: {type(e).__name__}: {str(e)}"

    result = {
        "source": "DAB",
        "mode": "agent_generated_code",
        "case_group": case_group_dir.name,
        "case_name": case_dir.name,
        "case_dir": str(case_dir),

        "prompt_version": version,
        "prompt_path": str(prompt_path),
        "question": question,

        "db_description_path": str(db_description_path),
        "publication_db_path": str(publication_db_path),
        "cpc_definition_sql_path": str(cpc_definition_sql_path),

        "generated_solve_path": str(generated_solve_path),
        "final_answer_path": str(final_answer_path),
        "stage_trace_path": str(stage_trace_path),

        "passed": passed,
        "validation_reason": reason,
        "final_answer": final_answer,

        "llm_latency_sec": llm_end - llm_start,
        "execution": execution,

        "run_dir": str(run_dir),
    }

    save_result(run_dir, result)

    print("\n=== DAB Agent Run Finished ===")
    print(json.dumps({
        "passed": result["passed"],
        "validation_reason": result["validation_reason"],
        "final_answer_preview": result["final_answer"][:500],
        "run_dir": result["run_dir"],
    }, indent=2, ensure_ascii=False))

    return result


def save_result(run_dir: Path, result: dict):
    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    summary = {
        "prompt_version": result["prompt_version"],
        "mode": result["mode"],
        "total": 1,
        "correct": 1 if result["passed"] else 0,
        "accuracy": 1.0 if result["passed"] else 0.0,
        "validation_reason": result["validation_reason"],
        "run_dir": result["run_dir"],
    }

    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--dab-root",
        default=str(Path.home() / "research" / "DataAgentBench"),
    )
    parser.add_argument("--timeout-sec", type=int, default=300)

    args = parser.parse_args()

    run_dab_agent(
        case_dir=Path(args.case_dir),
        prompt_path=Path(args.prompt),
        version=args.version,
        dab_root=Path(args.dab_root),
        timeout_sec=args.timeout_sec,
    )