"""Common feedback checks for data-agent run artifacts.

These checks avoid benchmark-specific assumptions. They operate on generic
artifacts such as result.json, generated code, execution metadata, validator
messages, and runtime logs. The log file may still be named stage_trace.json for
compatibility.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

def legacy_component_key(index: int, label: str) -> str:
    return f"S{index}_{label}"


COMPONENT_ALIASES = {
    legacy_component_key(1, "task_understanding"): "task_understanding",
    legacy_component_key(2, "data_schema_grounding"): "schema_grounding",
    legacy_component_key(3, "planning_decomposition"): "planning_decomposition",
    legacy_component_key(4, "tool_dependency_planning"): "tool_dependency_policy",
    legacy_component_key(5, "query_code_generation"): "code_generation",
    legacy_component_key(5, "code_generation"): "code_generation",
    legacy_component_key(6, "execution"): "runtime_execution",
    legacy_component_key(7, "transformation_calculation"): "transformation_calculation",
    legacy_component_key(8, "answer_synthesis_validation"): "answer_synthesis",
}


def normalize_component(value: Any, fallback: str = "unknown_component") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return COMPONENT_ALIASES.get(text, text)


def load_stage_trace(run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    trace_path = result.get("stage_trace_path")

    if trace_path:
        trace_path = Path(trace_path)
    else:
        trace_path = run_dir / "stage_trace.json"

    if not trace_path.exists() and (run_dir / "stage_trace.json").exists():
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

    except Exception as exc:
        return {
            "exists": True,
            "path": str(trace_path),
            "trace": [],
            "error": f"failed to parse stage_trace.json: {exc}",
        }


def parse_strict_reason(reason: str) -> dict[str, int | None]:
    info: dict[str, int | None] = {
        "expected_unique": None,
        "got_unique": None,
        "missing_count": None,
        "extra_count": None,
        "duplicate_count": None,
    }

    match = re.search(r"expected\s+(\d+)\s+unique.*?got\s+(\d+)\s+unique", reason, re.I | re.S)
    if match:
        info["expected_unique"] = int(match.group(1))
        info["got_unique"] = int(match.group(2))

    match = re.search(r"Missing .*?\((\d+)\)", reason, re.I)
    if match:
        info["missing_count"] = int(match.group(1))

    match = re.search(r"Extra .*?\((\d+)\)", reason, re.I)
    if match:
        info["extra_count"] = int(match.group(1))

    match = re.search(r"Duplicate .*?\((\d+)\)", reason, re.I)
    if match:
        info["duplicate_count"] = int(match.group(1))

    return info


def detects_ground_truth_leak(code: str) -> bool:
    bad_patterns = [
        r"\bfrom\s+validate\s+import\b",
        r"\bimport\s+validate\b",
        r"open\s*\([^)]*(ground_truth|validate\.py)",
        r"Path\s*\([^)]*(ground_truth|validate\.py)",
        r"read_\w+\s*\([^)]*ground_truth",
        r"spec_from_file_location\s*\([^)]*validate",
        r"(expected answer|standard answer).{0,80}(open|read|load|parse)",
    ]

    lower = code.lower()
    return any(re.search(pattern, lower, re.S) for pattern in bad_patterns)


def iter_operation_events(stage_item: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    if stage_item.get("event") or stage_item.get("trigger") or stage_item.get("operation"):
        event = dict(stage_item)
        event.setdefault(
            "stage",
            normalize_component(
                stage_item.get("stage")
                or stage_item.get("optional_label")
                or stage_item.get("suggested_target")
                or stage_item.get("event"),
                fallback="runtime_event",
            ),
        )
        event.setdefault("operation", stage_item.get("operation") or stage_item.get("event"))
        events.append(event)

    operation_events = stage_item.get("operation_events") or []
    if isinstance(operation_events, dict):
        operation_events = [operation_events]

    if isinstance(operation_events, list):
        for event in operation_events:
            if not isinstance(event, dict):
                continue
            item = dict(event)
            item.setdefault(
                "stage",
                normalize_component(stage_item.get("stage") or item.get("optional_label"), fallback="runtime_event"),
            )
            events.append(item)

    return events


def numeric_values(value: Any) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []

    def visit(prefix: str, item: Any) -> None:
        if isinstance(item, bool):
            return
        if isinstance(item, (int, float)):
            values.append((prefix, float(item)))
            return
        if isinstance(item, dict):
            for key, child in item.items():
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                visit(child_prefix, child)
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
                visit(child_prefix, child)

    visit("", value)
    return values


def count_like_key(key: str) -> bool:
    lower = key.lower()
    return any(
        token in lower
        for token in (
            "count",
            "rows",
            "records",
            "items",
            "symbols",
            "levels",
            "mapped",
            "unmapped",
            "candidates",
            "outputs",
            "parsed",
            "pairs",
        )
    )


def zero_count_warnings(event: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    outputs = event.get("outputs") or {}
    for key, value in numeric_values(outputs):
        if value == 0 and count_like_key(key):
            warnings.append(f"{key}=0")
    return warnings


def operation_summary(event: dict[str, Any]) -> str:
    return json.dumps(
        {
            "event": event.get("event"),
            "trigger": event.get("trigger"),
            "severity": event.get("severity"),
            "function": event.get("function"),
            "operation": event.get("operation"),
            "stage": event.get("stage"),
            "status": event.get("status"),
            "purpose": event.get("purpose"),
            "inputs": event.get("inputs"),
            "outputs": event.get("outputs"),
            "checks": event.get("checks"),
            "evidence": event.get("evidence"),
            "warnings": event.get("warnings"),
            "hypothesis": event.get("hypothesis"),
            "suggested_target": event.get("suggested_target"),
            "error": event.get("error"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )[:1200]


def target_modules_for_event(event: dict[str, Any], fallback: list[str]) -> list[str]:
    target = event.get("suggested_target")
    if isinstance(target, str) and target:
        return [target, "adapters/runtime_observer.py", "adapters/feedback/common_trace_checks.py"]
    if isinstance(target, list) and target:
        return [str(item) for item in target] + [
            "adapters/runtime_observer.py",
            "adapters/feedback/common_trace_checks.py",
        ]
    return fallback


def extract_operation_event_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if stage_trace_info.get("error"):
        return errors

    for stage_item in stage_trace_info.get("trace") or []:
        for event in iter_operation_events(stage_item):
            stage = (
                event.get("stage")
                or event.get("optional_label")
                or stage_item.get("stage")
                or stage_item.get("optional_label")
                or event.get("suggested_target")
                or event.get("event")
                or event.get("operation")
                or event.get("function")
                or "unknown_operation"
            )
            stage = normalize_component(stage, fallback="unknown_operation")
            operation = str(event.get("operation") or event.get("event") or event.get("function") or "unknown_operation")
            status = str(event.get("status") or "").lower()
            trigger = str(event.get("trigger") or "").lower()
            severity = str(event.get("severity") or "").lower()
            handled_runtime_signal = False

            if trigger == "exception" or severity == "error":
                errors.append(
                    {
                        "stage": stage,
                        "type": "runtime_log_exception_or_error",
                        "subtype": operation,
                        "confidence": "high",
                        "evidence": operation_summary(event),
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_execution", "adapters/runtime_observer.py"],
                        ),
                    }
                )
                continue

            if trigger in {"runtime_anomaly", "fallback_used"}:
                handled_runtime_signal = True
                errors.append(
                    {
                        "stage": stage,
                        "type": "runtime_log_anomaly",
                        "subtype": operation,
                        "confidence": "medium",
                        "evidence": operation_summary(event),
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_observer_policy", "data_flow_checks"],
                        ),
                    }
                )

            if trigger == "runtime_check_failed":
                handled_runtime_signal = True
                errors.append(
                    {
                        "stage": stage,
                        "type": "runtime_check_failed",
                        "subtype": operation,
                        "confidence": "high",
                        "evidence": operation_summary(event),
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_observer_policy", "data_validation_checks"],
                        ),
                    }
                )

            if status in {"failed", "failure", "error", "exception"}:
                errors.append(
                    {
                        "stage": stage,
                        "type": "operation_reported_failure",
                        "subtype": operation,
                        "confidence": "high",
                        "evidence": operation_summary(event),
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_log_analysis", "generated_code_runtime_logging"],
                        ),
                    }
                )
            elif (status == "warning" or event.get("warnings")) and not handled_runtime_signal:
                errors.append(
                    {
                        "stage": stage,
                        "type": "operation_reported_warning",
                        "subtype": operation,
                        "confidence": "medium",
                        "evidence": operation_summary(event),
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_log_analysis", "generated_code_runtime_logging"],
                        ),
                    }
                )

            checks = event.get("checks") or []
            if isinstance(checks, dict):
                checks = [checks]
            if isinstance(checks, list):
                for check in checks:
                    if not isinstance(check, dict) or check.get("passed", True):
                        continue
                    errors.append(
                        {
                            "stage": stage,
                            "type": "operation_check_failed",
                            "subtype": str(check.get("name") or operation),
                            "confidence": "high",
                            "evidence": operation_summary(event),
                            "target_modules": target_modules_for_event(
                                event,
                                ["runtime_log_analysis", "data_validation_checks"],
                            ),
                        }
                    )

            zero_warnings = zero_count_warnings(event)
            if zero_warnings:
                errors.append(
                    {
                        "stage": stage,
                        "type": "operation_zero_output_signal",
                        "subtype": operation,
                        "confidence": "low",
                        "evidence": f"Zero count-like outputs observed: {', '.join(zero_warnings)}. Event: {operation_summary(event)}",
                        "target_modules": target_modules_for_event(
                            event,
                            ["runtime_log_analysis", "data_flow_checks"],
                        ),
                    }
                )

    return errors


def extract_trace_based_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    if not stage_trace_info["exists"]:
        errors.append(
            {
                "stage": "runtime_execution",
                "type": "runtime_log_missing",
                "subtype": "required_runtime_log_artifact_not_written",
                "confidence": "medium",
                "evidence": stage_trace_info["error"],
                "target_modules": [
                    "adapters/runtime_observer.py",
                    "generated_code_runtime_logging",
                    "prompts/dab",
                ],
            }
        )
        return errors

    if stage_trace_info["error"]:
        errors.append(
            {
                "stage": "runtime_execution",
                "type": "runtime_log_invalid",
                "subtype": "runtime_log_json_parse_error",
                "confidence": "medium",
                "evidence": stage_trace_info["error"],
                "target_modules": [
                    "adapters/runtime_observer.py",
                    "generated_code_runtime_logging",
                    "prompts/dab",
                ],
            }
        )
        return errors

    if not stage_trace_info["trace"]:
        errors.append(
            {
                "stage": "runtime_execution",
                "type": "insufficient_runtime_evidence",
                "subtype": "runtime_log_empty",
                "confidence": "medium",
                "evidence": "Runtime log exists but contains no events.",
                "target_modules": [
                    "adapters/runtime_observer.py",
                    "prompts/dab",
                    "adapters/feedback/common_trace_checks.py",
                ],
            }
        )
        return errors

    for item in stage_trace_info["trace"]:
        raw_stage = item.get("stage")
        stage = normalize_component(raw_stage, fallback="")
        status = item.get("status")
        summary = str(item.get("summary", ""))
        error = item.get("error")
        assumptions = item.get("assumptions", [])
        outputs = item.get("outputs", {})
        evidence_used = item.get("evidence_used", [])

        joined = json.dumps(
            {
                "summary": summary,
                "error": error,
                "assumptions": assumptions,
                "outputs": outputs,
                "evidence_used": evidence_used,
            },
            ensure_ascii=False,
        ).lower()

        if status == "failed":
            errors.append(
                {
                    "stage": stage or "unknown_component",
                    "type": "stage_reported_failure",
                    "subtype": "agent_trace_declared_stage_failure",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["stage_trace_analysis"],
                }
            )

        if stage == "schema_grounding":
            if "metadata" in joined and ("not found" in joined or "unavailable" in joined or "could not parse" in joined):
                errors.append(
                    {
                        "stage": "schema_grounding",
                        "type": "metadata_grounding_failure",
                        "subtype": "metadata_source_not_understood_or_not_parsed",
                        "confidence": "high",
                        "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                        "target_modules": ["data_source_grounding", "metadata_grounding"],
                    }
                )

        if stage == "answer_synthesis":
            if "extra" in joined or "duplicate" in joined or "missing" in joined or "count" in joined:
                errors.append(
                    {
                        "stage": "answer_synthesis",
                        "type": "answer_set_quality_check",
                        "subtype": "trace_reports_output_count_or_set_issue",
                        "confidence": "medium",
                        "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                        "target_modules": ["answer_synthesis", "final_answer_filtering"],
                    }
                )

    errors.extend(extract_operation_event_errors(stage_trace_info))
    return errors




def extract_zero_mapping_and_year_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract focused zero-output signals used by PATENTS feedback adapters."""
    errors: list[dict[str, Any]] = []
    if stage_trace_info.get("error"):
        return errors

    for item in stage_trace_info.get("trace") or []:
        event = str(item.get("event") or item.get("operation") or "").lower()
        reason = str(item.get("reason") or item.get("status") or item.get("summary") or "").lower()
        outputs = item.get("outputs") or {}
        joined = json.dumps(
            {
                "event": item.get("event"),
                "reason": item.get("reason"),
                "summary": item.get("summary"),
                "outputs": outputs,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).lower()

        if "no_years_found" in reason or "no_years_found" in joined:
            errors.append(
                {
                    "stage": "metadata_parser",
                    "type": "operation_zero_output_signal",
                    "subtype": "no_years_found",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["metadata_parser", "year_extraction"],
                }
            )

        if ("mapping" in event or "year" in event or "extraction" in event) and any(
            value == 0 for _, value in numeric_values(outputs)
        ):
            errors.append(
                {
                    "stage": normalize_component(item.get("stage"), fallback="transformation_calculation"),
                    "type": "operation_zero_output_signal",
                    "subtype": "zero_mapping_or_year_extraction_output",
                    "confidence": "medium",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["metadata_parser", "granularity_mapping", "transformation_logic"],
                }
            )

    return errors

def extract_validation_errors(passed: bool, reason: str, strict_info: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

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

        errors.append(
            {
                "stage": "answer_synthesis",
                "type": "output_set_mismatch",
                "subtype": subtype,
                "confidence": "high",
                "evidence": reason,
                "target_modules": ["answer_synthesis", "final_answer_filtering"],
            }
        )

    expected = strict_info.get("expected_unique")
    got = strict_info.get("got_unique")

    if expected and got and got > expected * 2:
        errors.append(
            {
                "stage": "transformation_calculation",
                "type": "over_broad_filtering_or_granularity_error",
                "subtype": "output_cardinality_explosion",
                "confidence": "medium",
                "evidence": f"Expected {expected} unique items, but generated {got}.",
                "target_modules": ["transformation_logic", "filtering_logic", "granularity_control"],
            }
        )

    return errors


def extract_policy_errors(code: str) -> list[dict[str, Any]]:
    if not detects_ground_truth_leak(code):
        return []

    return [
        {
            "stage": "tool_dependency_policy",
            "type": "evaluation_leakage",
            "subtype": "ground_truth_or_validator_used_by_agent",
            "confidence": "high",
            "evidence": "Generated code appears to reference ground_truth or validate.py.",
            "target_modules": ["tool_access_policy", "sandbox_policy"],
        }
    ]


def extract_execution_errors(result: dict[str, Any]) -> list[dict[str, Any]]:
    reason = str(result.get("validation_reason") or "")
    if reason.startswith("llm_api_error:"):
        return [
            {
                "stage": "code_generation",
                "type": "llm_api_error",
                "subtype": "object_agent_code_generation_failed",
                "confidence": "high",
                "evidence": reason,
                "target_modules": ["llm_infrastructure", "run_dab_agent.py"],
            }
        ]

    if reason.startswith("generated_code_schema_lint_failed:"):
        return [
            {
                "stage": "schema_grounding",
                "type": "generated_code_schema_lint_failed",
                "subtype": "nonexistent_publicationinfo_column_reference",
                "confidence": "high",
                "evidence": reason,
                "target_modules": ["schema_grounding", "sql_column_selection", "run_dab_agent.py"],
            }
        ]

    execution = result.get("execution") or {}
    if not execution or execution.get("execution_success", True):
        return []

    return [
        {
            "stage": "runtime_execution",
            "type": "agent_code_execution_error",
            "subtype": "runtime_or_timeout_error",
            "confidence": "high",
            "evidence": execution.get("stderr") or execution.get("error") or "unknown execution error",
            "target_modules": ["code_execution", "runtime_environment"],
        }
    ]
