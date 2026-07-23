import argparse
import json
import sys
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from adapters.feedback.common_trace_checks import normalize_component


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
    Convert raw DAB validation feedback into a component/runtime error localization record.

    Important:
    - surface_error is relatively certain because it comes from validator feedback.
    - root_cause_hypothesis is often uncertain unless we have execution traces.
    """

    if result["passed"]:
        return {
            "surface_error": {
                "component": "correct",
                "stage": "correct",
                "type": "correct",
                "subtype": None,
                "evidence": None,
            },
            "root_cause_hypothesis": {
                "component": None,
                "stage": None,
                "type": None,
                "confidence": None,
                "reason": None,
            },
            "possible_upstream_components": [],
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
                "component": "answer_synthesis",
                "stage": "answer_synthesis",
                "type": "output_completeness_error",
                "subtype": "missing_required_item",
                "evidence": reason,
                "domain_object": domain_object,
            },
            "root_cause_hypothesis": {
                "component": "unknown_component",
                "stage": "unknown_component",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The validator only reports that a required item is missing. "
                    "Without intermediate execution traces, this cannot be uniquely "
                    "attributed to retrieval, grounding, calculation, or final answer synthesis."
                ),
            },
            "possible_upstream_components": [
                "schema_grounding",
                "planning_decomposition",
                "runtime_execution",
                "transformation_calculation",
                "answer_synthesis",
            ],
            "possible_upstream_stages": [
                "schema_grounding",
                "planning_decomposition",
                "runtime_execution",
                "transformation_calculation",
                "answer_synthesis",
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
                "component": "answer_synthesis",
                "stage": "answer_synthesis",
                "type": "output_format_alignment_error",
                "subtype": "field_proximity_mismatch",
                "evidence": reason,
                "domain_object": "code-year-title group",
            },
            "root_cause_hypothesis": {
                "component": "answer_synthesis",
                "stage": "answer_synthesis",
                "type": "answer_formatting_error",
                "confidence": "medium",
                "reason": (
                    "The validator found a likely entity/title but could not find the "
                    "associated code/year nearby. This suggests an answer formatting "
                    "or alignment problem."
                ),
            },
            "possible_upstream_components": [
                "answer_synthesis",
            ],
            "possible_upstream_stages": [
                "answer_synthesis",
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
                "component": "answer_synthesis",
                "stage": "answer_synthesis",
                "type": "output_completeness_error",
                "subtype": "missing_or_incorrect_text_item",
                "evidence": reason,
                "domain_object": "name/title",
            },
            "root_cause_hypothesis": {
                "component": "unknown_component",
                "stage": "unknown_component",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The final output does not contain a required textual item. "
                    "The upstream cause may be entity grounding, retrieval, mapping, "
                    "or final answer synthesis."
                ),
            },
            "possible_upstream_components": [
                "schema_grounding",
                "code_generation",
                "transformation_calculation",
                "answer_synthesis",
            ],
            "possible_upstream_stages": [
                "schema_grounding",
                "code_generation",
                "transformation_calculation",
                "answer_synthesis",
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
                "component": "answer_synthesis",
                "stage": "answer_synthesis",
                "type": "output_format_alignment_error",
                "subtype": "missing_required_pair",
                "evidence": reason,
                "domain_object": "entity-title pair",
            },
            "root_cause_hypothesis": {
                "component": "unknown_component",
                "stage": "unknown_component",
                "type": "unknown_without_execution_trace",
                "confidence": "low",
                "reason": (
                    "The validator requires a paired output. The failure may come from "
                    "cross-database linking, entity mapping, or final output pairing."
                ),
            },
            "possible_upstream_components": [
                "schema_grounding",
                "tool_dependency_policy",
                "transformation_calculation",
                "answer_synthesis",
            ],
            "possible_upstream_stages": [
                "schema_grounding",
                "tool_dependency_policy",
                "transformation_calculation",
                "answer_synthesis",
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
                "component": "runtime_execution",
                "stage": "runtime_execution",
                "type": "tool_execution_error",
                "subtype": "validator_runtime_error",
                "evidence": reason,
                "domain_object": "validator",
            },
            "root_cause_hypothesis": {
                "component": "runtime_execution",
                "stage": "runtime_execution",
                "type": "environment_or_dependency_error",
                "confidence": "high",
                "reason": "The validation tool failed during execution.",
            },
            "possible_upstream_components": [
                "runtime_execution",
            ],
            "possible_upstream_stages": [
                "runtime_execution",
            ],
            "target_modules": [
                "evaluation_environment",
            ],
        }

    # Default fallback.
    return {
        "surface_error": {
            "component": "answer_synthesis",
            "stage": "answer_synthesis",
            "type": "validation_failure",
            "subtype": "unknown_validation_failure",
            "evidence": reason,
            "domain_object": None,
        },
        "root_cause_hypothesis": {
            "component": "unknown_component",
            "stage": "unknown_component",
            "type": "unknown_without_execution_trace",
            "confidence": "low",
            "reason": "The validator reported a failure, but the reason does not match known patterns.",
        },
        "possible_upstream_components": [
            "task_understanding",
            "schema_grounding",
            "planning_decomposition",
            "tool_dependency_policy",
            "code_generation",
            "runtime_execution",
            "transformation_calculation",
            "answer_synthesis",
        ],
        "possible_upstream_stages": [
            "task_understanding",
            "schema_grounding",
            "planning_decomposition",
            "tool_dependency_policy",
            "code_generation",
            "runtime_execution",
            "transformation_calculation",
            "answer_synthesis",
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
    component_distribution = Counter()

    if not passed:
        surface = localization["surface_error"]
        component = normalize_component(surface.get("component") or surface.get("stage"), fallback="unknown_component")
        surface["component"] = component
        surface["stage"] = component
        error_type = surface["type"]

        component_distribution[component] += 1
        error_distribution[f"{component}.{error_type}"] += 1

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

        "component_distribution": dict(component_distribution),
        "stage_distribution": dict(component_distribution),
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
