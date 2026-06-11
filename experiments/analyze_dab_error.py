import argparse
import json
from pathlib import Path
from collections import Counter


def infer_domain_object(reason: str) -> str:
    reason_lower = reason.lower()

    if "cpc code" in reason_lower:
        return "CPC code"

    if "code/year" in reason_lower:
        return "code-year pair"

    if "assignee" in reason_lower and "title" in reason_lower:
        return "assignee-title pair"

    if "title" in reason_lower:
        return "title"

    if "year" in reason_lower:
        return "year"

    if "code" in reason_lower:
        return "code"

    return "required item"


def classify_dab_failure(result: dict) -> dict:
    """
    Convert raw DAB validation feedback into an 8-stage error localization record.

    Important:
    - surface_error is relatively certain because it comes from validator feedback.
    - root_cause_hypothesis is often uncertain unless we have execution traces.
    """

    if result["passed"]:
        return {
            "surface_error": {
                "stage": "correct",
                "type": "correct",
                "subtype": None,
                "evidence": None,
            },
            "root_cause_hypothesis": {
                "stage": None,
                "type": None,
                "confidence": None,
                "reason": None,
            },
            "possible_upstream_stages": [],
            "target_modules": [],
        }

    reason = result.get("validation_reason", "")

    # Case 1: validator says a required item is missing.
    # Example: "Missing CPC code: A22B"
    if "Missing" in reason:
        domain_object = infer_domain_object(reason)

        return {
            "surface_error": {
                "stage": "S8_answer_synthesis_validation",
                "type": "output_completeness_error",
                "subtype": "missing_required_item",
                "evidence": reason,
                "domain_object": domain_object,
            },
            "root_cause_hypothesis": {
                "stage": "unknown",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The validator only reports that a required item is missing. "
                    "Without intermediate execution traces, this cannot be uniquely "
                    "attributed to retrieval, grounding, calculation, or final answer synthesis."
                ),
            },
            "possible_upstream_stages": [
                "S2_data_schema_grounding",
                "S3_planning_decomposition",
                "S6_execution",
                "S7_transformation_calculation",
                "S8_answer_synthesis_validation",
            ],
            "target_modules": [
                "answer_synthesis",
                "completeness_checking",
                "execution_trace_logging",
            ],
        }

    # Case 2: output has items, but fields are not aligned closely enough.
    # Example from query3 validator: "Code/year not found near ..."
    if "Code/year not found" in reason:
        return {
            "surface_error": {
                "stage": "S8_answer_synthesis_validation",
                "type": "output_format_alignment_error",
                "subtype": "field_proximity_mismatch",
                "evidence": reason,
                "domain_object": "code-year-title group",
            },
            "root_cause_hypothesis": {
                "stage": "S8_answer_synthesis_validation",
                "type": "answer_formatting_error",
                "confidence": "medium",
                "reason": (
                    "The validator found a likely entity/title but could not find the "
                    "associated code/year nearby. This suggests an answer formatting "
                    "or alignment problem."
                ),
            },
            "possible_upstream_stages": [
                "S8_answer_synthesis_validation",
            ],
            "target_modules": [
                "answer_formatting",
                "validator_oriented_output",
            ],
        }

    # Case 3: fuzzy matching cannot find a required entity/title.
    if "Name fuzzy match failed" in reason:
        return {
            "surface_error": {
                "stage": "S8_answer_synthesis_validation",
                "type": "output_completeness_error",
                "subtype": "missing_or_incorrect_text_item",
                "evidence": reason,
                "domain_object": "name/title",
            },
            "root_cause_hypothesis": {
                "stage": "unknown",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The final output does not contain a required textual item. "
                    "The upstream cause may be entity grounding, retrieval, mapping, "
                    "or final answer synthesis."
                ),
            },
            "possible_upstream_stages": [
                "S2_data_schema_grounding",
                "S5_query_code_generation",
                "S7_transformation_calculation",
                "S8_answer_synthesis_validation",
            ],
            "target_modules": [
                "entity_grounding",
                "answer_synthesis",
                "execution_trace_logging",
            ],
        }

    # Case 4: required pair cannot be matched.
    # Example from query2 validator: "No match for: assignee + title"
    if "No match for" in reason:
        return {
            "surface_error": {
                "stage": "S8_answer_synthesis_validation",
                "type": "output_format_alignment_error",
                "subtype": "missing_required_pair",
                "evidence": reason,
                "domain_object": "entity-title pair",
            },
            "root_cause_hypothesis": {
                "stage": "unknown",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The validator requires a paired output. The failure may come from "
                    "cross-database linking, entity mapping, or final output pairing."
                ),
            },
            "possible_upstream_stages": [
                "S2_data_schema_grounding",
                "S4_tool_dependency_planning",
                "S7_transformation_calculation",
                "S8_answer_synthesis_validation",
            ],
            "target_modules": [
                "cross_database_linking",
                "answer_pairing",
                "execution_trace_logging",
            ],
        }

    # Case 5: validator itself crashes.
    if "validator_runtime_error" in reason:
        return {
            "surface_error": {
                "stage": "S6_execution",
                "type": "tool_execution_error",
                "subtype": "validator_runtime_error",
                "evidence": reason,
                "domain_object": "validator",
            },
            "root_cause_hypothesis": {
                "stage": "S6_execution",
                "type": "environment_or_dependency_error",
                "confidence": "high",
                "reason": "The validation tool failed during execution.",
            },
            "possible_upstream_stages": [
                "S6_execution",
            ],
            "target_modules": [
                "evaluation_environment",
            ],
        }

    # Default fallback.
    return {
        "surface_error": {
            "stage": "S8_answer_synthesis_validation",
            "type": "validation_failure",
            "subtype": "unknown_validation_failure",
            "evidence": reason,
            "domain_object": None,
        },
        "root_cause_hypothesis": {
            "stage": "unknown",
            "type": "unknown_without_execution_trace",
            "confidence": "low",
            "reason": "The validator reported a failure, but the reason does not match known patterns.",
        },
        "possible_upstream_stages": [
            "S1_task_understanding",
            "S2_data_schema_grounding",
            "S3_planning_decomposition",
            "S4_tool_dependency_planning",
            "S5_query_code_generation",
            "S6_execution",
            "S7_transformation_calculation",
            "S8_answer_synthesis_validation",
        ],
        "target_modules": [
            "error_analysis",
            "execution_trace_logging",
        ],
    }


def analyze_dab_run(run_dir: Path):
    result_path = run_dir / "result.json"

    if not result_path.exists():
        raise FileNotFoundError(f"result.json not found: {result_path}")

    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    localization = classify_dab_failure(result)

    passed = result["passed"]

    error_distribution = Counter()
    stage_distribution = Counter()

    if not passed:
        surface = localization["surface_error"]
        stage = surface["stage"]
        error_type = surface["type"]

        stage_distribution[stage] += 1
        error_distribution[f"{stage}.{error_type}"] += 1

    failed_cases = []

    if not passed:
        failed_cases.append({
            "case_group": result["case_group"],
            "case_name": result["case_name"],
            "question": result["question"],
            "validation_reason": result["validation_reason"],
            "llm_output": result["llm_output"],
            "error_localization": localization,
        })

    error_summary = {
        "run_dir": str(run_dir),
        "prompt_version": result["prompt_version"],

        "total": 1,
        "correct": 1 if passed else 0,
        "accuracy": 1.0 if passed else 0.0,

        "stage_distribution": dict(stage_distribution),
        "error_distribution": dict(error_distribution),

        "failed_cases": failed_cases,
    }

    out_path = run_dir / "error_summary.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(error_summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(error_summary, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {out_path}")

    return error_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)

    args = parser.parse_args()

    analyze_dab_run(Path(args.run_dir))