"""PATENTS/CPC-specific feedback checks for DAB runs.

These checks are intentionally separated from common feedback logic. They are
useful for the current PATENTS experiments, but should remain optional adapters
rather than assumptions baked into the generic analyzer.
"""

from __future__ import annotations

import json
import re
from typing import Any

from adapters.feedback.common_trace_checks import normalize_component


def reads_path_variable(code: str, var_name: str) -> bool:
    patterns = [
        rf"open\s*\(\s*{var_name}",
        rf"with\s+open\s*\(\s*{var_name}",
        rf"Path\s*\(\s*{var_name}\s*\)\.read_text",
        rf"{var_name}.*?read_text\s*\(",
        rf"sqlite3\.connect\s*\(\s*{var_name}",
        rf"pd\.read_\w+\s*\(\s*{var_name}",
    ]

    return any(re.search(pattern, code, re.S) for pattern in patterns)


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

    return any(re.search(pattern, code, re.I | re.S) for pattern in suspicious_patterns)


def extract_patents_trace_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if stage_trace_info.get("error"):
        return errors

    # Detect zero-parsed-patents signal from patent_aggregation_summary event
    for item in stage_trace_info.get("trace") or []:
        if item.get("event") == "patent_aggregation_summary":
            outputs = item.get("outputs") or {}
            parsed_patents = outputs.get("parsed_patents", 0)
            if parsed_patents == 0:
                errors.append(
                    {
                        "stage": "granularity_mapping",
                        "type": "operation_zero_output_signal",
                        "subtype": "patent_aggregation_zero_parsed_patents",
                        "confidence": "high",
                        "evidence": f"patent_aggregation_summary reported parsed_patents=0: {json.dumps(outputs, ensure_ascii=False)[:500]}",
                        "target_modules": ["granularity_mapping", "level5_mapping_logic"],
                    }
                )
                break


    # Detect zero-parsed-symbols signal from cpc_definition_parsed event
    for item in stage_trace_info.get("trace") or []:
        if item.get("event") == "cpc_definition_parsed":
            outputs = item.get("outputs") or {}
            parsed_symbols = outputs.get("parsed_symbols", outputs.get("symbols_parsed", 0))
            if parsed_symbols == 0:
                errors.append(
                    {
                        "stage": "metadata_parser",
                        "type": "operation_zero_output_signal",
                        "subtype": "cpc_definition_parsed_zero_symbols",
                        "confidence": "high",
                        "evidence": f"cpc_definition_parsed reported parsed_symbols=0: {json.dumps(outputs, ensure_ascii=False)[:500]}",
                        "target_modules": ["metadata_parser", "cpc_definition_parser"],
                    }
                )
                break

    for item in stage_trace_info.get("trace") or []:
        stage = normalize_component(item.get("stage"), fallback="")
        if stage != "transformation_calculation":
            continue

        joined = json.dumps(
            {
                "summary": str(item.get("summary", "")),
                "error": item.get("error"),
                "assumptions": item.get("assumptions", []),
                "outputs": item.get("outputs", {}),
                "evidence_used": item.get("evidence_used", []),
            },
            ensure_ascii=False,
        ).lower()

        if "slash" in joined or "string shape" in joined or "character length" in joined:
            errors.append(
                {
                    "stage": "granularity_mapping",
                    "type": "granularity_level_error",
                    "subtype": "level_inferred_from_surface_pattern_in_trace",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["granularity_mapping", "transformation_logic"],
                }
            )

    # Add zero-mapping and zero-year extraction errors
    from adapters.feedback.common_trace_checks import extract_zero_mapping_and_year_errors
    errors.extend(extract_zero_mapping_and_year_errors(stage_trace_info))

    return errors


def extract_patents_code_errors(result: dict[str, Any], code: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    question = str(result.get("question", ""))
    has_level_requirement = bool(re.search(r"\blevel\s*\d+\b", question, re.I))
    has_definition_source = bool(result.get("cpc_definition_sql_path"))

    if not has_level_requirement:
        return errors

    definition_used = reads_path_variable(code, "CPC_DEFINITION_SQL_PATH")

    if has_definition_source and not definition_used:
        errors.append(
            {
                "stage": "schema_grounding",
                "type": "missing_required_metadata_source",
                "subtype": "hierarchy_level_not_grounded_in_definition_data",
                "confidence": "high",
                "evidence": (
                    "The task has a hierarchy/level requirement and a definition/metadata source is provided, "
                    "but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH."
                ),
                "target_modules": ["data_source_grounding", "schema_grounding"],
            }
        )

    if detects_string_shape_level_heuristic(code):
        errors.append(
            {
                "stage": "granularity_mapping",
                "type": "granularity_level_error",
                "subtype": "level_inferred_from_string_shape",
                "confidence": "high",
                "evidence": (
                    "Generated code appears to infer hierarchy level from string shape, "
                    "for example slash/pattern matching, instead of grounding the level in metadata."
                ),
                "target_modules": ["granularity_mapping", "transformation_logic"],
            }
        )

    return errors
