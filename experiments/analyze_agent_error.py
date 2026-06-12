import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_stage_trace(run_dir: Path, result: dict):
    trace_path = result.get("stage_trace_path")

    if trace_path:
        trace_path = Path(trace_path)
    else:
        trace_path = run_dir / "stage_trace.json"

    if not trace_path.exists():
        return {
            "exists": False,
            "path": str(trace_path),
            "trace": [],
            "error": "stage_trace.json not found",
        }

    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if not isinstance(trace, list):
            return {
                "exists": True,
                "path": str(trace_path),
                "trace": [],
                "error": "stage_trace.json exists but is not a list",
            }

        return {
            "exists": True,
            "path": str(trace_path),
            "trace": trace,
            "error": None,
        }

    except Exception as e:
        return {
            "exists": True,
            "path": str(trace_path),
            "trace": [],
            "error": f"failed to parse stage_trace.json: {e}",
        }


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


def parse_strict_reason(reason: str) -> dict:
    info = {
        "expected_unique": None,
        "got_unique": None,
        "missing_count": None,
        "extra_count": None,
        "duplicate_count": None,
    }

    m = re.search(r"expected\s+(\d+)\s+unique.*?got\s+(\d+)\s+unique", reason, re.I | re.S)
    if m:
        info["expected_unique"] = int(m.group(1))
        info["got_unique"] = int(m.group(2))

    m = re.search(r"Missing .*?\((\d+)\)", reason, re.I)
    if m:
        info["missing_count"] = int(m.group(1))

    m = re.search(r"Extra .*?\((\d+)\)", reason, re.I)
    if m:
        info["extra_count"] = int(m.group(1))

    m = re.search(r"Duplicate .*?\((\d+)\)", reason, re.I)
    if m:
        info["duplicate_count"] = int(m.group(1))

    return info


def reads_path_variable(code: str, var_name: str) -> bool:
    patterns = [
        rf"open\s*\(\s*{var_name}",
        rf"with\s+open\s*\(\s*{var_name}",
        rf"Path\s*\(\s*{var_name}\s*\)\.read_text",
        rf"{var_name}.*?read_text\s*\(",
        rf"sqlite3\.connect\s*\(\s*{var_name}",
        rf"pd\.read_\w+\s*\(\s*{var_name}",
    ]

    return any(re.search(p, code, re.S) for p in patterns)


def detects_string_shape_level_heuristic(code: str) -> bool:
    suspicious_patterns = [
        r"containing\s+a\s+slash",
        r"contains\s+a\s+slash",
        r"codes?\s+with\s+a\s+slash",
        r"['\"]\/['\"]\s+in\s+\w+",
        r"level\s*5.*?slash",
        r"slash.*?level\s*5",
        r"string\s+shape",
    ]

    return any(re.search(p, code, re.I | re.S) for p in suspicious_patterns)


def detects_ground_truth_leak(code: str) -> bool:
    bad_patterns = [
        "ground_truth",
        "validate.py",
        "from validate import",
        "import validate",
        "expected answer",
        "standard answer",
    ]

    lower = code.lower()
    return any(p.lower() in lower for p in bad_patterns)

def extract_trace_based_errors(stage_trace_info: dict) -> list[dict]:
    errors = []

    if not stage_trace_info["exists"]:
        errors.append({
            "stage": "S6_execution",
            "type": "stage_trace_missing",
            "subtype": "required_trace_artifact_not_written",
            "confidence": "medium",
            "evidence": stage_trace_info["error"],
            "target_modules": ["runtime_trace_protocol", "generated_code_instrumentation"],
        })
        return errors

    if stage_trace_info["error"]:
        errors.append({
            "stage": "S6_execution",
            "type": "stage_trace_invalid",
            "subtype": "trace_json_parse_error",
            "confidence": "medium",
            "evidence": stage_trace_info["error"],
            "target_modules": ["runtime_trace_protocol", "generated_code_instrumentation"],
        })
        return errors

    trace = stage_trace_info["trace"]

    for item in trace:
        stage = item.get("stage")
        status = item.get("status")
        summary = str(item.get("summary", ""))
        error = item.get("error")
        assumptions = item.get("assumptions", [])
        outputs = item.get("outputs", {})
        evidence_used = item.get("evidence_used", [])

        joined = json.dumps({
            "summary": summary,
            "error": error,
            "assumptions": assumptions,
            "outputs": outputs,
            "evidence_used": evidence_used,
        }, ensure_ascii=False).lower()

        if status == "failed":
            errors.append({
                "stage": stage or "unknown_stage",
                "type": "stage_reported_failure",
                "subtype": "agent_trace_declared_stage_failure",
                "confidence": "high",
                "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                "target_modules": ["stage_trace_analysis"],
            })

        if stage == "S2_data_schema_grounding":
            if "metadata" in joined and ("not found" in joined or "unavailable" in joined or "could not parse" in joined):
                errors.append({
                    "stage": "S2_data_schema_grounding",
                    "type": "metadata_grounding_failure",
                    "subtype": "metadata_source_not_understood_or_not_parsed",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["data_source_grounding", "metadata_grounding"],
                })

        if stage == "S7_transformation_calculation":
            if "slash" in joined or "string shape" in joined or "character length" in joined:
                errors.append({
                    "stage": "S7_transformation_calculation",
                    "type": "granularity_level_error",
                    "subtype": "level_inferred_from_surface_pattern_in_trace",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["granularity_mapping", "transformation_logic"],
                })

        if stage == "S8_answer_synthesis_validation":
            if "extra" in joined or "duplicate" in joined or "missing" in joined or "count" in joined:
                errors.append({
                    "stage": "S8_answer_synthesis_validation",
                    "type": "answer_set_quality_check",
                    "subtype": "trace_reports_output_count_or_set_issue",
                    "confidence": "medium",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["answer_synthesis", "final_answer_filtering"],
                })

    return errors

def analyze_run(run_dir: Path, revalidate: bool = False) -> dict:
    result_path = run_dir / "result.json"
    solve_path = run_dir / "generated_solve.py"
    final_answer_path = run_dir / "final_answer.txt"

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

    localized_errors = []
    localized_errors.extend(extract_trace_based_errors(stage_trace_info))

    if not passed and "strict_match_failed" in reason:
        extra_count = strict_info.get("extra_count") or 0
        missing_count = strict_info.get("missing_count") or 0

        if extra_count > 0 and missing_count > 0:
            subtype = "missing_and_extra_items"
        elif extra_count > 0:
            subtype = "over_broad_output"
        elif missing_count > 0:
            subtype = "incomplete_output"
        else:
            subtype = "output_set_mismatch"

        localized_errors.append({
            "stage": "S8_answer_synthesis_validation",
            "type": "output_set_mismatch",
            "subtype": subtype,
            "confidence": "high",
            "evidence": reason,
            "target_modules": ["answer_synthesis", "final_answer_filtering"],
        })

    expected = strict_info.get("expected_unique")
    got = strict_info.get("got_unique")

    if expected and got and got > expected * 2:
        localized_errors.append({
            "stage": "S7_transformation_calculation",
            "type": "over_broad_filtering_or_granularity_error",
            "subtype": "output_cardinality_explosion",
            "confidence": "medium",
            "evidence": f"Expected {expected} unique items, but generated {got}.",
            "target_modules": ["transformation_logic", "filtering_logic", "granularity_control"],
        })

    question = str(result.get("question", ""))
    has_level_requirement = bool(re.search(r"\blevel\s*\d+\b", question, re.I))
    has_definition_source = bool(result.get("cpc_definition_sql_path"))

    definition_used = reads_path_variable(code, "CPC_DEFINITION_SQL_PATH")

    if has_level_requirement and has_definition_source and not definition_used:
        localized_errors.append({
            "stage": "S2_data_schema_grounding",
            "type": "missing_required_metadata_source",
            "subtype": "hierarchy_level_not_grounded_in_definition_data",
            "confidence": "high",
            "evidence": (
                "The task has a hierarchy/level requirement and a definition/metadata source is provided, "
                "but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH."
            ),
            "target_modules": ["data_source_grounding", "schema_grounding"],
        })

    if has_level_requirement and detects_string_shape_level_heuristic(code):
        localized_errors.append({
            "stage": "S7_transformation_calculation",
            "type": "granularity_level_error",
            "subtype": "level_inferred_from_string_shape",
            "confidence": "high",
            "evidence": (
                "Generated code appears to infer hierarchy level from string shape, "
                "for example slash/pattern matching, instead of grounding the level in metadata."
            ),
            "target_modules": ["granularity_mapping", "transformation_logic"],
        })

    if detects_ground_truth_leak(code):
        localized_errors.append({
            "stage": "S4_tool_dependency_planning",
            "type": "evaluation_leakage",
            "subtype": "ground_truth_or_validator_used_by_agent",
            "confidence": "high",
            "evidence": "Generated code appears to reference ground_truth or validate.py.",
            "target_modules": ["tool_access_policy", "sandbox_policy"],
        })

    execution = result.get("execution") or {}

    if execution and not execution.get("execution_success", True):
        localized_errors.append({
            "stage": "S6_execution",
            "type": "agent_code_execution_error",
            "subtype": "runtime_or_timeout_error",
            "confidence": "high",
            "evidence": execution.get("stderr") or execution.get("error") or "unknown execution error",
            "target_modules": ["code_execution", "runtime_environment"],
        })

    if not localized_errors and passed:
        localized_errors.append({
            "stage": "success",
            "type": "validated_success",
            "subtype": None,
            "confidence": "medium",
            "evidence": reason,
            "target_modules": [],
        })

    stage_distribution = Counter()
    error_distribution = Counter()

    for err in localized_errors:
        if err["stage"] == "success":
            continue
        stage_distribution[err["stage"]] += 1
        error_distribution[f"{err['stage']}.{err['type']}"] += 1

    summary = {
        "run_dir": str(run_dir),
        "source_result_path": str(result_path),
        "revalidated": revalidate,
        
        "stage_trace_info": stage_trace_info,

        "passed": bool(passed),
        "validation_reason": reason,
        "strict_info": strict_info,

        "case_group": result.get("case_group"),
        "case_name": result.get("case_name"),
        "prompt_version": result.get("prompt_version"),
        "question": result.get("question"),

        "stage_distribution": dict(stage_distribution),
        "error_distribution": dict(error_distribution),
        "localized_errors": localized_errors,

        "failed_case": {
            "generated_solve_path": str(solve_path),
            "final_answer_path": str(final_answer_path),
            "final_answer_preview": final_answer[:1000],
        }
    }

    out_path = run_dir / "agent_error_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

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