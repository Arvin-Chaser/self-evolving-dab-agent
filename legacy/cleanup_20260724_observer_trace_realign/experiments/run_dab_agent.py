import argparse
import ast
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from llm_client import call_llm
from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report

RUNTIME_OBSERVER_SOURCE = BASE_DIR / "adapters" / "runtime_observer.py"
CONCISE_TERMINAL = os.getenv("DAB_CONCISE_TERMINAL", "").lower() in {"1", "true", "yes"}


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


def get_table_columns(db_path: Path, table_name: str = "publicationinfo") -> list[str]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    try:
        rows = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    finally:
        conn.close()
    return [str(row[1]) for row in rows]


def line_numbers_for_token(text: str, token: str) -> list[int]:
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    return [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def lint_generated_code_schema(
    generated_code: str,
    available_columns: list[str],
    table_name: str = "publicationinfo",
) -> dict:
    """Catch generated-code references to nonexistent high-risk DB columns before execution."""
    available = set(available_columns)
    protected_missing_columns = [
        "cpc_prefix",
        "publication_year",
    ]
    findings = []

    for column in protected_missing_columns:
        if column in available:
            continue
        lines = line_numbers_for_token(generated_code, column)
        if not lines:
            continue
        findings.append(
            {
                "rule": "forbid_missing_publicationinfo_column",
                "table": table_name,
                "column": column,
                "line_numbers": lines[:20],
                "message": (
                    f"Generated code references `{column}`, but `{table_name}` "
                    "does not expose that column."
                ),
            }
        )

    result = {
        "status": "passed" if not findings else "failed",
        "passed": not findings,
        "table": table_name,
        "available_columns": available_columns,
        "findings": findings,
    }
    return result


def write_preexecution_lint_trace(stage_trace_path: Path, lint_result: dict) -> None:
    event = {
        "event": "generated_code_schema_lint_failed",
        "stage": "schema_grounding",
        "trigger": "pre_execution_check_failed",
        "severity": "error",
        "status": "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context": {
            "task": "pre_execution_generated_code_schema_lint",
            "table": lint_result.get("table"),
        },
        "purpose": "Prevent generated code from executing with known nonexistent SQLite columns.",
        "inputs": {
            "available_columns": lint_result.get("available_columns", []),
        },
        "outputs": {},
        "checks": [
            {
                "name": "generated_code_schema_lint",
                "passed": bool(lint_result.get("passed")),
                "message": "Generated code must not require nonexistent publicationinfo columns.",
                "observed": lint_result.get("findings", []),
                "expected": {
                    "missing_column_references": 0,
                },
            }
        ],
        "evidence": {
            "findings": lint_result.get("findings", []),
        },
        "assumptions": [],
        "warnings": [],
        "error": None,
        "hypothesis": "The generated code regressed schema grounding before local execution.",
        "suggested_target": "schema_grounding",
        "tags": ["pre_execution_schema_lint", "generated_code_guard"],
    }
    stage_trace_path.write_text(json.dumps([event], indent=2, ensure_ascii=False), encoding="utf-8")


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
                "cpc_sample": row[3],
            }
        )

    return json.dumps(formatted, indent=2, ensure_ascii=False)


def format_helper_arg(arg: ast.arg) -> str:
    if arg.annotation is None:
        return arg.arg
    return f"{arg.arg}: {ast.unparse(arg.annotation)}"


def describe_helper_function(node: ast.FunctionDef) -> dict[str, object]:
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    parts: list[str] = []
    accepted_keywords: set[str] = set()

    for arg, default in zip(positional, defaults):
        text = format_helper_arg(arg)
        if default is not None:
            text += "=..."
        parts.append(text)
        if arg not in args.posonlyargs:
            accepted_keywords.add(arg.arg)

    if args.vararg is not None:
        parts.append("*" + format_helper_arg(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        text = format_helper_arg(arg)
        if default is not None:
            text += "=..."
        parts.append(text)
        accepted_keywords.add(arg.arg)

    accepts_kwargs = args.kwarg is not None
    if args.kwarg is not None:
        parts.append("**" + format_helper_arg(args.kwarg))

    return {
        "name": node.name,
        "signature": f"{node.name}({', '.join(parts)})",
        "accepted_keywords": sorted(accepted_keywords),
        "accepts_kwargs": accepts_kwargs,
    }


def discover_patents_helper_api(root: Path) -> list[dict[str, object]]:
    helper_dir = root / "adapters" / "patents"
    if not helper_dir.exists():
        return []
    helpers: list[dict[str, object]] = []
    for path in sorted(helper_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        function_details = [
            describe_helper_function(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]
        functions = [str(item["name"]) for item in function_details]
        if functions:
            module = f"adapters.patents.{path.stem}"
            helpers.append(
                {
                    "path": str(path.relative_to(root)),
                    "module": module,
                    "functions": functions,
                    "function_details": function_details,
                }
            )
    return helpers


def build_patents_helper_contract(root: Path) -> str:
    helpers = discover_patents_helper_api(root)
    if not helpers:
        return ""
    lines = [
        "",
        "Additional project helper API contract:",
        "- The repository provides reusable PATENTS helper modules. For matching tasks, generated_solve.py MUST import and use these helpers instead of reimplementing the same helper logic inline.",
        "- If you use CPC hierarchy, metadata parsing, level mapping, EMA, or answer diagnostics covered by a helper below, import the helper explicitly from its adapters.patents module.",
        "- Do not copy the helper implementation into generated_solve.py; call the helper and log whether it was used.",
        "- Use the exact helper signatures and parameter names shown below; do not invent aliases unless they appear in the signature.",
        "Available helpers:",
    ]
    for helper in helpers:
        lines.append(f"- module {helper['module']}:")
        for detail in helper.get("function_details", []):
            lines.append(f"  - from {helper['module']} import {detail['name']}  # {detail['signature']}")
    lines.append("")
    return "\n".join(lines)


def lint_generated_code_helper_api_calls(generated_code: str, helpers: list[dict[str, object]]) -> list[dict[str, object]]:
    try:
        tree = ast.parse(generated_code)
    except SyntaxError:
        return []

    helper_by_module = {str(helper["module"]): helper for helper in helpers}
    helper_by_stem = {str(helper["module"]).rsplit(".", 1)[-1]: helper for helper in helpers}
    function_imports: dict[str, dict[str, object]] = {}
    module_aliases: dict[str, dict[str, object]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in helper_by_module:
                helper = helper_by_module[node.module]
                details = {
                    str(detail["name"]): detail
                    for detail in helper.get("function_details", [])
                    if isinstance(detail, dict)
                }
                for alias in node.names:
                    if alias.name in details:
                        function_imports[alias.asname or alias.name] = {
                            "helper": helper,
                            "detail": details[alias.name],
                        }
            elif node.module == "adapters.patents":
                for alias in node.names:
                    helper = helper_by_stem.get(alias.name)
                    if helper:
                        module_aliases[alias.asname or alias.name] = helper
        elif isinstance(node, ast.Import):
            for alias in node.names:
                helper = helper_by_module.get(alias.name)
                if helper:
                    module_aliases[alias.asname or alias.name.rsplit(".", 1)[-1]] = helper

    findings: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        detail: dict[str, object] | None = None
        helper_module: str | None = None
        if isinstance(node.func, ast.Name) and node.func.id in function_imports:
            imported = function_imports[node.func.id]
            detail = imported["detail"]  # type: ignore[assignment]
            helper_module = str(imported["helper"]["module"])  # type: ignore[index]
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            helper = module_aliases.get(node.func.value.id)
            if helper:
                details = {
                    str(item["name"]): item
                    for item in helper.get("function_details", [])
                    if isinstance(item, dict)
                }
                detail = details.get(node.func.attr)
                helper_module = str(helper["module"])

        if not detail or bool(detail.get("accepts_kwargs")):
            continue
        accepted_keywords = set(str(item) for item in detail.get("accepted_keywords", []))
        unknown_keywords = [
            keyword.arg
            for keyword in node.keywords
            if keyword.arg is not None and keyword.arg not in accepted_keywords
        ]
        if unknown_keywords:
            findings.append(
                {
                    "type": "helper_call_unknown_keyword",
                    "message": "Generated code calls a PATENTS helper with keyword arguments not present in the helper signature.",
                    "module": helper_module,
                    "function": detail.get("name"),
                    "signature": detail.get("signature"),
                    "unknown_keywords": unknown_keywords,
                    "line_number": node.lineno,
                }
            )

    return findings


def lint_generated_code_helper_contract(generated_code: str, prompt: str, root: Path) -> dict:
    helpers = discover_patents_helper_api(root)
    if not helpers or "adapters.patents" not in prompt:
        return {"status": "not_required", "passed": True, "findings": [], "helpers": helpers}
    code_low = generated_code.lower()
    observed = []
    missing = []
    for helper in helpers:
        module = str(helper["module"]).lower()
        stem = module.rsplit(".", 1)[-1]
        used = (
            module in code_low
            or f"from adapters.patents import {stem}" in code_low
            or f"import adapters.patents.{stem}" in code_low
        )
        if used:
            observed.append(helper["module"])
        else:
            missing.append(helper["module"])
    api_findings = lint_generated_code_helper_api_calls(generated_code, helpers)
    if api_findings:
        return {
            "status": "failed",
            "passed": False,
            "helpers": helpers,
            "observed_modules": observed,
            "missing_modules": missing,
            "findings": api_findings,
        }
    if observed:
        return {"status": "passed", "passed": True, "findings": [], "helpers": helpers, "observed_modules": observed, "missing_modules": missing}
    return {
        "status": "failed",
        "passed": False,
        "helpers": helpers,
        "observed_modules": observed,
        "missing_modules": missing,
        "findings": [
            {
                "type": "helper_not_used_by_generated_code",
                "message": "Prompt required adapters.patents helper usage, but generated_solve.py did not import any discovered helper module.",
                "required_modules": [helper["module"] for helper in helpers],
            }
        ],
    }

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
    runtime_observer_path: Path,
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
        "{runtime_observer_path}": str(runtime_observer_path),
    }

    prompt = template

    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    helper_contract = build_patents_helper_contract(BASE_DIR)
    if helper_contract and "Additional project helper API contract:" not in prompt:
        prompt = prompt.rstrip() + "\n" + helper_contract

    return prompt


def inject_runtime_observer(run_dir: Path) -> Path:
    if not RUNTIME_OBSERVER_SOURCE.exists():
        raise FileNotFoundError(f"Runtime observer source not found: {RUNTIME_OBSERVER_SOURCE}")

    target_path = run_dir / "runtime_observer.py"
    shutil.copy2(RUNTIME_OBSERVER_SOURCE, target_path)
    return target_path


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
    env["RUNTIME_LOG_PATH"] = str(stage_trace_path)
    env["PYTHONPATH"] = str(run_dir) + os.pathsep + str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

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
    started_at = utc_now_iso()
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
    script_report_path = run_dir / "script_run_report.run_dab_agent.json"
    runtime_observer_path = inject_runtime_observer(run_dir)

    question = load_query(query_path)
    db_description = load_text(db_description_path)
    sqlite_schema = get_sqlite_schema(publication_db_path)
    publication_columns = get_table_columns(publication_db_path)
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
        runtime_observer_path=runtime_observer_path,
    )

    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    operations = [
        {
            "name": "inject_runtime_observer",
            "status": "completed",
            "outputs": {
                "runtime_observer_source": str(RUNTIME_OBSERVER_SOURCE),
                "runtime_observer_path": str(runtime_observer_path),
            },
            "checks": [
                {
                    "name": "runtime_observer_injected",
                    "passed": runtime_observer_path.exists(),
                    "message": "The generated agent can import runtime_observer from its run directory.",
                }
            ],
        },
        {
            "name": "load_case_context",
            "status": "completed",
            "outputs": {
                "question_loaded": bool(question),
                "schema_chars": len(sqlite_schema),
                "publication_column_count": len(publication_columns),
                "sample_rows_chars": len(sample_rows),
            },
            "checks": [
                {
                    "name": "required_paths_exist",
                    "passed": all(path.exists() for path in required_paths),
                    "message": "All required DAB case, prompt, and data paths are present.",
                }
            ],
        },
        {
            "name": "build_object_agent_prompt",
            "status": "completed",
            "outputs": {
                "prompt_path": str(run_dir / "prompt.txt"),
                "prompt_chars": len(prompt),
            },
        },
    ]

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
    operations.append(
        {
            "name": "call_llm_for_generated_code",
            "status": "failed" if llm_error else "completed",
            "outputs": {
                "raw_llm_output_path": str(run_dir / "raw_llm_output.txt"),
                "raw_llm_output_chars": len(raw_llm_output),
                "llm_latency_sec": llm_end - llm_start,
            },
            "error": llm_error,
        }
    )

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
            "runtime_observer_path": str(runtime_observer_path),
            "script_run_report_path": str(script_report_path),
        }

        save_result(run_dir, result)
        write_script_run_report(
            output_dir=run_dir,
            script_name="experiments/run_dab_agent.py",
            script_role="object_agent_runner",
            started_at=started_at,
            status="partial",
            inputs=[
                path_ref("case_dir", case_dir),
                path_ref("prompt", prompt_path),
                path_ref("dab_root", dab_root),
            ],
            operations=operations,
            outputs=[
                path_ref("result", run_dir / "result.json"),
                path_ref("summary", run_dir / "summary.json"),
                path_ref("prompt", run_dir / "prompt.txt"),
                path_ref("raw_llm_output", run_dir / "raw_llm_output.txt"),
                path_ref("runtime_observer", runtime_observer_path),
            ],
            checks=[
                {
                    "name": "object_agent_run_passed",
                    "passed": False,
                    "message": result["validation_reason"],
                }
            ],
            self_feedback={
                "confidence": "high",
                "uncertainties": ["The object agent did not produce executable code because the LLM call failed."],
                "evolution_hints": ["Separate infrastructure/API failures from prompt or analyzer quality."],
                "suggested_target_modules": ["llm_infrastructure", "run_dab_agent.py"],
            },
            report_stem="run_dab_agent",
        )
        if CONCISE_TERMINAL:
            print(f"[data-agent] llm_failed run_dir={run_dir} reason={result['validation_reason']}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    generated_code = extract_python_code(raw_llm_output)
    generated_solve_path.write_text(generated_code, encoding="utf-8")
    operations.append(
        {
            "name": "extract_generated_python",
            "status": "completed",
            "outputs": {
                "generated_solve_path": str(generated_solve_path),
                "generated_code_chars": len(generated_code),
            },
        }
    )

    schema_lint = lint_generated_code_schema(
        generated_code=generated_code,
        available_columns=publication_columns,
    )
    helper_lint = lint_generated_code_helper_contract(
        generated_code=generated_code,
        prompt=prompt,
        root=BASE_DIR,
    )
    schema_lint["helper_contract_lint"] = helper_lint
    if not helper_lint.get("passed", True):
        schema_lint["passed"] = False
        schema_lint.setdefault("findings", []).extend(helper_lint.get("findings", []))
    schema_lint_path = run_dir / "generated_code_schema_lint.json"
    schema_lint_path.write_text(json.dumps(schema_lint, indent=2, ensure_ascii=False), encoding="utf-8")
    operations.append(
        {
            "name": "lint_generated_code_schema",
            "status": "completed" if schema_lint.get("passed") else "failed",
            "outputs": {
                "schema_lint_path": str(schema_lint_path),
                "passed": schema_lint.get("passed"),
                "finding_count": len(schema_lint.get("findings", [])),
            },
            "error": None if schema_lint.get("passed") else json.dumps(schema_lint.get("findings", []), ensure_ascii=False),
        }
    )

    if not schema_lint.get("passed"):
        write_preexecution_lint_trace(stage_trace_path, schema_lint)
        execution = {
            "execution_success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "latency_sec": 0.0,
            "timeout": False,
            "skipped": True,
            "skip_reason": "generated_code_schema_lint_failed",
            "error": "generated_code_schema_lint_failed: " + json.dumps(schema_lint.get("findings", []), ensure_ascii=False),
        }
        (run_dir / "execution_stdout.txt").write_text("", encoding="utf-8")
        (run_dir / "execution_stderr.txt").write_text(execution["error"], encoding="utf-8")
        reason = execution["error"]
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
            "runtime_observer_path": str(runtime_observer_path),
            "generated_code_schema_lint_path": str(schema_lint_path),
            "generated_code_schema_lint": schema_lint,

            "passed": False,
            "validation_reason": reason,
            "final_answer": "",

            "llm_latency_sec": llm_end - llm_start,
            "execution": execution,

            "run_dir": str(run_dir),
            "script_run_report_path": str(script_report_path),
        }

        save_result(run_dir, result)
        write_script_run_report(
            output_dir=run_dir,
            script_name="experiments/run_dab_agent.py",
            script_role="object_agent_runner",
            started_at=started_at,
            status="partial",
            inputs=[
                path_ref("case_dir", case_dir),
                path_ref("prompt", prompt_path),
                path_ref("dab_root", dab_root),
            ],
            operations=operations,
            outputs=[
                path_ref("result", run_dir / "result.json"),
                path_ref("summary", run_dir / "summary.json"),
                path_ref("prompt", run_dir / "prompt.txt"),
                path_ref("raw_llm_output", run_dir / "raw_llm_output.txt"),
                path_ref("generated_solve", generated_solve_path),
                path_ref("stage_trace", stage_trace_path),
                path_ref("runtime_observer", runtime_observer_path),
                path_ref("generated_code_schema_lint", schema_lint_path),
            ],
            checks=[
                {
                    "name": "object_agent_run_passed",
                    "passed": False,
                    "message": reason,
                },
                {
                    "name": "generated_code_schema_lint_passed",
                    "passed": False,
                    "message": str(schema_lint_path),
                },
                {
                    "name": "runtime_log_written",
                    "passed": stage_trace_path.exists(),
                    "message": str(stage_trace_path),
                },
            ],
            self_feedback={
                "confidence": "high",
                "uncertainties": [],
                "evolution_hints": [
                    "Treat generated-code schema lint failures as schema-grounding regressions before runtime execution."
                ],
                "suggested_target_modules": [
                    "prompts/dab",
                    "schema_grounding",
                    "experiments/run_dab_agent.py",
                ],
            },
            report_stem="run_dab_agent",
        )

        if CONCISE_TERMINAL:
            print(f"[data-agent] finished passed={result['passed']} run_dir={result['run_dir']}")
        else:
            print("\n=== DAB Agent Run Finished ===")
            print(json.dumps({
                "passed": result["passed"],
                "validation_reason": result["validation_reason"],
                "final_answer_preview": "",
                "run_dir": result["run_dir"],
            }, indent=2, ensure_ascii=False))

        return result

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
    operations.append(
        {
            "name": "execute_generated_code",
            "status": "completed" if execution.get("execution_success") else "failed",
            "outputs": {
                "execution_success": execution.get("execution_success"),
                "returncode": execution.get("returncode"),
                "timeout": execution.get("timeout"),
                "latency_sec": execution.get("latency_sec"),
                "stdout_path": str(run_dir / "execution_stdout.txt"),
                "stderr_path": str(run_dir / "execution_stderr.txt"),
            },
            "error": execution.get("error") or execution.get("stderr"),
        }
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
    operations.append(
        {
            "name": "validate_final_answer",
            "status": "completed" if passed else "failed",
            "outputs": {
                "passed": passed,
                "validation_reason": reason,
                "final_answer_chars": len(final_answer),
            },
        }
    )

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
        "runtime_observer_path": str(runtime_observer_path),
        "generated_code_schema_lint_path": str(schema_lint_path),
        "generated_code_schema_lint": schema_lint,

        "passed": passed,
        "validation_reason": reason,
        "final_answer": final_answer,

        "llm_latency_sec": llm_end - llm_start,
        "execution": execution,

        "run_dir": str(run_dir),
        "script_run_report_path": str(script_report_path),
    }

    save_result(run_dir, result)
    write_script_run_report(
        output_dir=run_dir,
        script_name="experiments/run_dab_agent.py",
        script_role="object_agent_runner",
        started_at=started_at,
        status="success" if passed else "partial",
        inputs=[
            path_ref("case_dir", case_dir),
            path_ref("prompt", prompt_path),
            path_ref("dab_root", dab_root),
        ],
        operations=operations,
        outputs=[
            path_ref("result", run_dir / "result.json"),
            path_ref("summary", run_dir / "summary.json"),
            path_ref("prompt", run_dir / "prompt.txt"),
            path_ref("raw_llm_output", run_dir / "raw_llm_output.txt"),
            path_ref("generated_solve", generated_solve_path),
            path_ref("final_answer", final_answer_path),
            path_ref("stage_trace", stage_trace_path),
            path_ref("runtime_observer", runtime_observer_path),
            path_ref("generated_code_schema_lint", schema_lint_path),
        ],
        checks=[
            {
                "name": "object_agent_run_passed",
                "passed": bool(passed),
                "message": reason,
            },
            {
                "name": "generated_code_schema_lint_passed",
                "passed": bool(schema_lint.get("passed")),
                "message": str(schema_lint_path),
            },
            {
                "name": "runtime_log_written",
                "passed": stage_trace_path.exists(),
                "message": str(stage_trace_path),
            },
            {
                "name": "runtime_observer_injected",
                "passed": runtime_observer_path.exists(),
                "message": str(runtime_observer_path),
            },
        ],
        self_feedback={
            "confidence": "medium",
            "uncertainties": [] if stage_trace_path.exists() else ["Generated code did not write a runtime log."],
            "evolution_hints": [
                "Use generated_solve.py, runtime_observer.py, stage_trace.json, validation_reason, and analyzer output together."
            ],
            "suggested_target_modules": [
                "prompts/dab",
                "adapters/runtime_observer.py",
                "generated_code_runtime_logging",
                "experiments/analyze_agent_error.py",
            ],
        },
        report_stem="run_dab_agent",
    )

    if CONCISE_TERMINAL:
        print(
            "[data-agent] "
            f"finished passed={result['passed']} "
            f"answer_lines={len([line for line in result['final_answer'].splitlines() if line.strip()])} "
            f"run_dir={result['run_dir']}"
        )
    else:
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
