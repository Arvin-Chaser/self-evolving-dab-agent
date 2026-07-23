import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from adapters.feedback.common_trace_checks import (
    extract_execution_errors,
    extract_policy_errors,
    extract_trace_based_errors,
    extract_validation_errors,
    load_stage_trace,
    normalize_component,
    parse_strict_reason,
)
from adapters.feedback.dab_patents_checks import (
    extract_patents_code_errors,
    extract_patents_trace_errors,
)
from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report


CONCISE_TERMINAL = os.getenv("DAB_CONCISE_TERMINAL", "").lower() in {"1", "true", "yes"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


COUNT_KEYWORDS = (
    "count",
    "rows",
    "row_count",
    "total",
    "unique",
    "mapped",
    "unmapped",
    "coverage",
    "years",
    "codes",
)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def interesting_numeric_outputs(outputs: object) -> dict:
    if not isinstance(outputs, dict):
        return {}
    selected = {}
    for key, value in outputs.items():
        key_text = str(key).lower()
        if is_number(value) and any(token in key_text for token in COUNT_KEYWORDS):
            selected[key] = value
    return selected


def inspect_publication_schema(result: dict) -> dict:
    db_path_text = result.get("publication_db_path")
    if not db_path_text:
        return {"available": False, "reason": "publication_db_path missing"}

    db_path = Path(db_path_text)
    if not db_path.exists():
        return {"available": False, "path": str(db_path), "reason": "publication database missing"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        rows = cursor.execute("PRAGMA table_info(publicationinfo)").fetchall()
        conn.close()
    except sqlite3.Error as exc:
        return {"available": False, "path": str(db_path), "reason": str(exc)}

    columns = [row[1] for row in rows]
    return {
        "available": True,
        "path": str(db_path),
        "table": "publicationinfo",
        "columns": columns,
        "has_cpc": "cpc" in columns,
        "has_cpc_prefix": "cpc_prefix" in columns,
        "has_filing_date": "filing_date" in columns,
        "has_publication_year": "publication_year" in columns,
    }


def build_pipeline_diagnostics(
    result: dict,
    stage_trace_info: dict,
    final_answer: str,
    code: str,
    strict_info: dict,
) -> dict:
    trace = stage_trace_info.get("trace") if isinstance(stage_trace_info, dict) else []
    trace = trace if isinstance(trace, list) else []
    schema = inspect_publication_schema(result)
    final_answer_lines = [line for line in final_answer.splitlines() if line.strip()]

    count_events = []
    for event in trace:
        if not isinstance(event, dict):
            continue
        counts = interesting_numeric_outputs(event.get("outputs"))
        if not counts:
            continue
        count_events.append(
            {
                "event": event.get("event") or event.get("operation"),
                "severity": event.get("severity"),
                "trigger": event.get("trigger"),
                "purpose": event.get("purpose"),
                "outputs": counts,
            }
        )

    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    diagnostics = {
        "run_dir": result.get("run_dir"),
        "passed": bool(result.get("passed")),
        "execution_success": bool(execution.get("execution_success")),
        "returncode": execution.get("returncode"),
        "validation_reason": result.get("validation_reason"),
        "strict_info": strict_info,
        "final_answer_line_count": len(final_answer_lines),
        "final_answer_preview_lines": final_answer_lines[:30],
        "publication_schema": schema,
        "stage_trace_event_count": len(trace),
        "count_events": count_events,
        "code_markers": {
            "mentions_publicationinfo_cpc": "publicationinfo" in code and "cpc" in code,
            "mentions_cpc_prefix": "cpc_prefix" in code,
            "mentions_publication_year": "publication_year" in code,
            "mentions_parse_cpc_definition": "parse_cpc_definition" in code or "CPC_DEFINITION_SQL_PATH" in code,
        },
    }
    diagnostics["preserved_invariants"] = derive_preserved_invariants(diagnostics)
    return diagnostics


def derive_preserved_invariants(diagnostics: dict) -> list[dict]:
    invariants = []

    def add(name: str, evidence: str, protected_scope: list[str], repair_boundary: str) -> None:
        invariants.append(
            {
                "name": name,
                "evidence": evidence,
                "protected_scope": protected_scope,
                "repair_boundary": repair_boundary,
            }
        )

    schema = diagnostics.get("publication_schema") or {}
    if schema.get("available") and schema.get("has_cpc") and not schema.get("has_cpc_prefix"):
        add(
            "publicationinfo_uses_cpc_column",
            "SQLite publicationinfo table has column cpc and does not have cpc_prefix.",
            ["schema_grounding", "sql_column_selection"],
            "Do not introduce cpc_prefix or publication_year as required columns.",
        )

    if diagnostics.get("execution_success"):
        add(
            "generated_code_executes_successfully",
            "Parent generated_solve.py returned success.",
            ["runtime_execution", "runtime_observer_api"],
            "Do not change runtime observer usage or generated-code structure in ways that risk execution failure.",
        )

    final_count = diagnostics.get("final_answer_line_count") or 0
    if final_count > 0:
        add(
            "nonempty_final_answer",
            f"Parent wrote {final_count} non-empty final answer lines.",
            ["answer_file_contract", "final_answer_writing"],
            "A child candidate should not lose the non-empty answer unless it passes validation.",
        )

    for item in diagnostics.get("count_events") or []:
        outputs = item.get("outputs") or {}
        parsed_count = (
            outputs.get("symbols_parsed")
            or outputs.get("symbols_count")
            or outputs.get("total_symbols")
            or outputs.get("parsed_rows")
            or outputs.get("unique_symbols")
        )
        if is_number(parsed_count) and parsed_count > 0:
            add(
                "cpc_definition_parsed",
                f"Runtime event {item.get('event')} parsed CPC definition count {parsed_count}.",
                ["cpc_definition_parser", "metadata_schema_grounding"],
                "Do not rewrite CPC dump parsing unless the current failure is explicitly parser-related.",
            )
            break

    for item in diagnostics.get("count_events") or []:
        outputs = item.get("outputs") or {}
        coverage = outputs.get("mapping_coverage")
        mapped = outputs.get("total_mapped_to_level5") or outputs.get("valid_records")
        if (is_number(coverage) and coverage >= 0.5) or (is_number(mapped) and mapped > 0):
            evidence = f"Runtime event {item.get('event')} reported outputs {outputs}."
            add(
                "level5_mapping_has_coverage",
                evidence,
                ["cpc_level_mapping", "metadata_to_level5_mapping"],
                "Do not tighten or replace the working mapping path unless the candidate preserves comparable coverage.",
            )
            break

    strict = diagnostics.get("strict_info") or {}
    expected = strict.get("expected_unique")
    got = strict.get("got_unique")
    if is_number(expected) and is_number(got) and got > 0:
        add(
            "remaining_failure_is_answer_set_cardinality",
            f"Strict validator expected {expected} unique answers and got {got}.",
            ["answer_synthesis", "final_filtering", "counting_semantics"],
            "Prefer changing only counting, deduplication, EMA, best-year, or final filtering semantics.",
        )

    return invariants


def load_validate_function(validate_path: Path, dab_root: Path):
    sys.path.insert(0, str(dab_root))

    spec = importlib.util.spec_from_file_location(
        "dab_validate_module_for_analysis",
        validate_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "validate"):
        raise AttributeError(f"No validate() function found in {validate_path}")

    return module.validate


def analyze_run(run_dir: Path, revalidate: bool = False) -> dict:
    started_at = utc_now_iso()
    result_path = run_dir / "result.json"
    solve_path = run_dir / "generated_solve.py"
    final_answer_path = run_dir / "final_answer.txt"
    script_report_path = run_dir / "script_run_report.analyze_agent_error.json"

    if not result_path.exists():
        raise FileNotFoundError(f"Missing result.json: {result_path}")

    result = load_json(result_path)
    stage_trace_info = load_stage_trace(run_dir, result)
    stage_trace = stage_trace_info["trace"]

    code = solve_path.read_text(encoding="utf-8") if solve_path.exists() else ""
    final_answer = final_answer_path.read_text(encoding="utf-8") if final_answer_path.exists() else ""

    passed = bool(result.get("passed"))
    reason = str(result.get("validation_reason", ""))

    if revalidate:
        case_dir = Path(result["case_dir"])
        publication_db_path = Path(result["publication_db_path"])
        dab_root = publication_db_path.parents[2]
        validate_path = case_dir / "validate.py"

        validate = load_validate_function(validate_path, dab_root)
        passed, reason = validate(final_answer)

    strict_info = parse_strict_reason(reason)
    pipeline_diagnostics = build_pipeline_diagnostics(
        result=result,
        stage_trace_info=stage_trace_info,
        final_answer=final_answer,
        code=code,
        strict_info=strict_info,
    )

    execution_errors = extract_execution_errors(result)
    code_generation_failed = any(error.get("type") == "llm_api_error" for error in execution_errors)

    localized_errors = []
    if not code_generation_failed:
        localized_errors.extend(extract_trace_based_errors(stage_trace_info))
    localized_errors.extend(extract_patents_trace_errors(stage_trace_info))
    localized_errors.extend(extract_validation_errors(passed, reason, strict_info))
    localized_errors.extend(extract_patents_code_errors(result, code))
    localized_errors.extend(extract_policy_errors(code))
    localized_errors.extend(execution_errors)

    for err in localized_errors:
        component = normalize_component(err.get("stage"), fallback="unknown_component")
        err["stage"] = component
        err["component"] = component

    if not localized_errors and passed:
        localized_errors.append({
            "stage": "success",
            "component": "success",
            "type": "validated_success",
            "subtype": None,
            "confidence": "medium",
            "evidence": reason,
            "target_modules": [],
        })

    component_distribution = Counter()
    error_distribution = Counter()

    for err in localized_errors:
        if err["stage"] == "success":
            continue
        component_distribution[err["component"]] += 1
        error_distribution[f"{err['stage']}.{err['type']}"] += 1

    # Backward-compatible key: values are now component/runtime labels, not fixed reasoning-stage labels.
    stage_distribution = component_distribution

    summary = {
        "run_dir": str(run_dir),
        "source_result_path": str(result_path),
        "revalidated": revalidate,
        
        "stage_trace_info": stage_trace_info,

        "passed": bool(passed),
        "validation_reason": reason,
        "strict_info": strict_info,
        "pipeline_diagnostics": pipeline_diagnostics,
        "preserved_invariants": pipeline_diagnostics.get("preserved_invariants", []),

        "case_group": result.get("case_group"),
        "case_name": result.get("case_name"),
        "prompt_version": result.get("prompt_version"),
        "question": result.get("question"),

        "stage_distribution": dict(stage_distribution),
        "component_distribution": dict(component_distribution),
        "error_distribution": dict(error_distribution),
        "localized_errors": localized_errors,

        "failed_case": {
            "generated_solve_path": str(solve_path),
            "final_answer_path": str(final_answer_path),
            "final_answer_preview": final_answer[:1000],
        },
        "script_run_report_path": str(script_report_path),
    }

    out_path = run_dir / "agent_error_summary.json"
    diagnostics_path = run_dir / "pipeline_diagnostics.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    diagnostics_path.write_text(json.dumps(pipeline_diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
    write_script_run_report(
        output_dir=run_dir,
        script_name="experiments/analyze_agent_error.py",
        script_role="feedback_analyzer",
        started_at=started_at,
        status="success",
        inputs=[
            path_ref("run_dir", run_dir),
            path_ref("result", result_path),
            path_ref("generated_solve", solve_path),
            path_ref("final_answer", final_answer_path),
        ],
        operations=[
            {
                "name": "load_run_artifacts",
                "status": "completed",
                "outputs": {
                    "stage_trace_exists": stage_trace_info.get("exists"),
                    "stage_trace_error": stage_trace_info.get("error"),
                    "stage_trace_item_count": len(stage_trace),
                    "generated_code_chars": len(code),
                    "final_answer_chars": len(final_answer),
                    "pipeline_count_event_count": len(pipeline_diagnostics.get("count_events", [])),
                    "preserved_invariant_count": len(pipeline_diagnostics.get("preserved_invariants", [])),
                },
            },
            {
                "name": "extract_problem_candidates",
                "status": "completed",
                "outputs": {
                    "localized_error_count": len(localized_errors),
                    "component_distribution": dict(component_distribution),
                    "stage_distribution": dict(stage_distribution),
                    "error_distribution": dict(error_distribution),
                },
            },
        ],
        outputs=[
            path_ref("agent_error_summary", out_path),
            path_ref("pipeline_diagnostics", diagnostics_path),
        ],
        checks=[
            {
                "name": "has_structured_observations",
                "passed": bool(localized_errors),
                "message": "Analyzer produced at least one success marker or problem candidate.",
            },
            {
                "name": "operation_trace_available",
                "passed": bool(stage_trace_info.get("exists")) and not bool(stage_trace_info.get("error")),
                "message": str(stage_trace_info.get("path")),
            },
        ],
        self_feedback={
            "confidence": "medium",
            "uncertainties": [] if localized_errors else ["No localized errors or success marker was produced."],
            "evolution_hints": [
                "Do not collapse observations into one primary signal here; leave repair selection to the meta-agent."
            ],
            "suggested_target_modules": [
                "adapters/feedback/common_trace_checks.py",
                "adapters/feedback/dab_patents_checks.py",
                "prompts/dab",
            ],
        },
        report_stem="analyze_agent_error",
    )

    if CONCISE_TERMINAL:
        print(
            "[analyze] "
            f"passed={bool(passed)} "
            f"errors={len(localized_errors)} "
            f"summary={out_path}"
        )
    else:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\nSaved to: {out_path}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-run current validate.py on final_answer.txt instead of trusting result.json."
    )

    args = parser.parse_args()

    analyze_run(Path(args.run_dir), revalidate=args.revalidate)
