#!/usr/bin/env python3
"""Translate fine-grained feedback into a concrete helper-repair plan.

The planner is intentionally deterministic: it turns selected stage/signal,
runtime trace events, ranked feedback, and answer-delta evidence into a small
API-level plan for data_agent_tool_repair.  This keeps Codex-Qwen from merely
"writing a helper" and instead constrains helper synthesis to the active
fine-grained failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _lower_blob(*items: Any) -> str:
    parts: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            parts.append(item)
        else:
            try:
                parts.append(json.dumps(item, ensure_ascii=False))
            except TypeError:
                parts.append(str(item))
    return "\n".join(parts).lower()


def _trace_events(feedback: dict[str, Any]) -> list[dict[str, Any]]:
    events = feedback.get("runtime_trace_evidence")
    return events if isinstance(events, list) else []


def _event_names(feedback: dict[str, Any]) -> set[str]:
    return {str(item.get("event") or "") for item in _trace_events(feedback) if isinstance(item, dict)}


def _matched_feedback(feedback: dict[str, Any], markers: tuple[str, ...]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for item in _trace_events(feedback):
        text = _lower_blob(item)
        if any(marker in text for marker in markers):
            matched.append(item)
    for item in feedback.get("ranked_feedback_signals") or []:
        text = _lower_blob(item)
        if any(marker in text for marker in markers):
            matched.append(item)
    return matched[:6]


def _base_plan(feedback: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "status": "planned",
        "planner": "helper_repair_planner_v1",
        "reason": reason,
        "source_selected_stage": feedback.get("selected_stage"),
        "source_selected_signal": feedback.get("selected_signal"),
        "risk_scope": "minimal/local/data_agent_tool_repair",
        "forbidden_actions": [
            "do not hardcode expected CPC answers or exact answer counts",
            "do not edit benchmark data, logs, candidates, archive, or trajectories",
            "do not replace generated_solve.py directly",
            "do not use CPC string shape as a substitute for CPCDefinition metadata when metadata is available",
        ],
    }


def cpc_definition_parser_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = _base_plan(feedback, reason="Fine-grained feedback points to CPCDefinition COPY/block/field parsing failure.")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/cpc_definition_parser.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create a reusable CPCDefinition SQL COPY block parser and require generated_solve.py to import/use it instead of re-parsing the SQL dump inline.",
            "required_functions": [
                {
                    "name": "parse_cpc_definition_sql",
                    "signature": "parse_cpc_definition_sql(sql_path: str | Path) -> tuple[dict[str, int | None], dict[str, list[str]]]",
                    "purpose": "Return symbol_to_level and symbol_to_parents from the CPCDefinition SQL COPY block.",
                    "must_handle": [
                        "COPY public.cpc_definition (...) FROM stdin; header on one line",
                        "quoted and unquoted column names",
                        "tab-delimited data rows after FROM stdin",
                        "exact backslash-dot COPY terminator",
                        "escaped newlines in parents fields",
                        "malformed/header lines should be skipped or surfaced without corrupting mappings",
                    ],
                }
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/cpc_definition_parser.py",
                "import adapters.patents.cpc_definition_parser",
                "parse real CPC_DEFINITION_SQL_PATH and assert symbol_to_level has many rows",
                "assert at least one parsed level == 5",
                "assert symbol_to_parents is non-empty for metadata rows with parents",
                "child generated_solve.py must import adapters.patents.cpc_definition_parser",
            ],
            "success_criteria": [
                "no cpc_definition_field_count_mismatch trace caused by header/data-boundary confusion",
                "generated code no longer contains a bespoke fragile COPY parser for CPCDefinition",
                "child eval progresses from parser failure to mapping/EMA/answer-delta evaluation",
            ],
            "matched_feedback": _matched_feedback(feedback, ("cpc_definition", "field_count", "copy", "from stdin", "metadata_parser")),
        }
    )
    return plan


def cpc_mapping_plan(feedback: dict[str, Any], *, reason: str | None = None, runtime_type_repair: bool = False) -> dict[str, Any]:
    plan = _base_plan(feedback, reason=reason or "Fine-grained feedback points to CPC level/granularity mapping or string-shape inference.")
    must_handle = [
        "exact metadata lookup before normalization",
        "parent traversal using symbol_to_parents",
        "no slash-count/prefix-length/string-shape level inference",
        "return None when metadata cannot confirm a level-5 symbol",
    ]
    focused_tests = [
        "py_compile adapters/patents/cpc_mapping.py",
        "import adapters.patents.cpc_mapping",
        "synthetic metadata test: level > 5 child maps to level 5 parent",
        "synthetic metadata test: missing symbol returns None, not raw fallback",
        "child generated_solve.py must import adapters.patents.cpc_mapping",
    ]
    success_criteria = [
        "no helper string-shape fallback",
        "child trace logs mapping coverage instead of silently accepting unmapped codes",
    ]
    if runtime_type_repair:
        must_handle.extend(
            [
                "symbol_to_level values may be int, numeric strings such as '5', empty strings, or malformed strings",
                "coerce numeric-like level values to int before comparing with target level",
                "treat invalid or missing level values as unknown instead of raising TypeError",
                "preserve get_level5_symbol public API used by existing generated_solve.py imports",
            ]
        )
        focused_tests.extend(
            [
                "synthetic metadata test: level string '5' is accepted as level 5",
                "synthetic metadata test: child level string '6' can traverse to parent level string '5'",
                "synthetic metadata test: malformed level string returns None without TypeError",
            ]
        )
        success_criteria.insert(0, "child no longer fails with TypeError comparing int and str in get_level5_symbol")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/cpc_mapping.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create or update a metadata-grounded CPC level mapping helper and require generated_solve.py to call it for raw publication CPC codes.",
            "required_functions": [
                {
                    "name": "get_level5_symbol",
                    "signature": "get_level5_symbol(raw_code: str, symbol_to_level: dict[str, int | str | None], symbol_to_parents: dict[str, list[str]]) -> str | None",
                    "purpose": "Map a raw CPC symbol to a metadata-confirmed level-5 symbol or return None.",
                    "must_handle": must_handle,
                }
            ],
            "focused_validation_tests": focused_tests,
            "success_criteria": success_criteria,
            "matched_feedback": _matched_feedback(
                feedback,
                (
                    "granularity",
                    "mapping",
                    "level",
                    "fallback",
                    "string shape",
                    "missing",
                    "extra",
                    "cpc_mapping.py",
                    "get_level5_symbol",
                    "typeerror",
                    "not supported between instances",
                ),
            ),
        }
    )
    return plan


def cpc_mapping_runtime_type_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    return cpc_mapping_plan(
        feedback,
        reason="Runtime traceback points to adapters/patents/cpc_mapping.py get_level5_symbol comparing non-normalized level values.",
        runtime_type_repair=True,
    )


def metadata_year_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = _base_plan(feedback, reason="Fine-grained feedback points to missing filing years or empty EMA inputs.")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/patent_query_utils.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create reusable filing-year extraction and publication CPC row normalization helpers.",
            "required_functions": [
                {
                    "name": "extract_filing_year",
                    "signature": "extract_filing_year(value: str | None) -> int | None",
                    "purpose": "Parse valid filing years from database date strings without inventing missing dates.",
                    "must_handle": ["YYYY-MM-DD", "empty/null values", "invalid dates return None"],
                }
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/patent_query_utils.py",
                "import adapters.patents.patent_query_utils",
                "synthetic date parsing tests for valid/invalid filing dates",
                "child trace should not emit no_years_found when data contains filing years",
            ],
            "success_criteria": ["year extraction produces non-empty yearly counts when publication rows contain filing_date"],
            "matched_feedback": _matched_feedback(feedback, ("no_years", "filing", "year", "metadata_parser")),
        }
    )
    return plan


def ema_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = _base_plan(feedback, reason="Fine-grained feedback points to EMA or best-year calculation.")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/ema.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create reusable EMA/best-year helpers with exact parameter names exposed to generated_solve.py.",
            "required_functions": [
                {
                    "name": "compute_ema_per_code",
                    "signature": "compute_ema_per_code(yearly_counts: dict[str, dict[int, int]], smoothing_factor: float = 0.2) -> dict[str, dict[int, float]]",
                    "purpose": "Compute an EMA time series per CPC code over filing years.",
                    "must_handle": ["sorted year axis", "missing years as zero or documented policy", "smoothing_factor parameter name"],
                },
                {
                    "name": "best_years_by_code",
                    "signature": "best_years_by_code(ema_by_code: dict[str, dict[int, float]]) -> dict[str, int]",
                    "purpose": "Select the best EMA year per CPC code.",
                    "must_handle": ["deterministic tie policy", "empty series"],
                },
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/ema.py",
                "import adapters.patents.ema",
                "synthetic EMA test with smoothing_factor=0.2",
                "pre-execution lint should reject unknown helper keyword aliases",
            ],
            "success_criteria": ["child uses helper API without TypeError", "answer delta improves or selected signal moves beyond EMA calculation"],
            "matched_feedback": _matched_feedback(feedback, ("ema", "best year", "year_axis", "smoothing")),
        }
    )
    return plan


def answer_delta_action_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = _base_plan(
        feedback,
        reason="Trace already contains candidate_decision_summary diagnostics but answer metrics did not improve; next helper must change ranking/filtering behavior, not add more observation-only logging.",
    )
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/candidate_filtering.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create a reusable candidate ranking/filtering helper that consumes the full unfiltered candidate_rows and returns the final CPC symbols to write; do not pass pre-filtered candidates_2022 and do not merely sort/log a summary.",
            "required_functions": [
                {
                    "name": "rank_or_filter_candidates",
                    "signature": "rank_or_filter_candidates(candidate_rows: list[dict], *, target_year: int = 2022) -> list[str]",
                    "purpose": "Return the candidate CPC symbols selected for the final answer using generated evidence such as best_year, counts, EMA values, and exclusion reasons.",
                    "must_handle": [
                        "no ground-truth answer lists or exact expected counts",
                        "deterministic ranking/tie policy",
                        "uses best_year/EMA/count evidence rather than simply echoing all candidates",
                        "returns a concrete list of symbols for final_answer.txt",
                    ],
                }
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/candidate_filtering.py",
                "import adapters.patents.candidate_filtering",
                "synthetic rank_or_filter_candidates test filters at least one excluded candidate",
                "child generated_solve.py must use rank_or_filter_candidates to construct final_answer.txt",
                "child answer delta must improve relative to parent or candidate is not parent-eligible",
            ],
            "success_criteria": [
                "generated_solve.py passes full candidate_rows to the helper and uses the helper output as final CPC symbols, not merely for logging",
                "child F1 improves relative to archive parent",
                "candidate_decision_summary remains available as supporting trace evidence",
            ],
            "matched_feedback": _matched_feedback(feedback, ("candidate_decision_summary", "answer_delta", "missing", "extra", "precision", "recall", "f1")),
        }
    )
    return plan

def answer_delta_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = _base_plan(feedback, reason="Fine-grained feedback shows non-empty but wrong answer; helper should diagnose missing/extra candidates rather than rewrite parser bootstrapping.")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/answer_diagnostics.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create reusable candidate diagnostics that logs per-code counts, best-year decisions, and exclusion reasons without using ground truth answers.",
            "required_functions": [
                {
                    "name": "summarize_candidate_decisions",
                    "signature": "summarize_candidate_decisions(candidate_rows: list[dict]) -> dict[str, object]",
                    "purpose": "Summarize why each CPC candidate was included/excluded using generated evidence only.",
                    "must_handle": ["no ground-truth answer lists", "per-code best year", "candidate count and exclusion reason samples", "report missing/extra pressure from answer_delta without using expected answer values"],
                }
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/answer_diagnostics.py",
                "import adapters.patents.answer_diagnostics",
                "synthetic candidate decision summary test",
                "child trace should include candidate diagnostics before final_answer_written",
            ],
            "success_criteria": ["selected signal becomes concrete mapping/EMA/exclusion reason rather than broad answer_delta"],
            "matched_feedback": _matched_feedback(feedback, ("missing", "extra", "answer_delta", "precision", "recall", "f1")),
        }
    )
    return plan


def plan_helper_repair(feedback: dict[str, Any], repair_profile: str | None = None) -> dict[str, Any]:
    if repair_profile and repair_profile != "data_agent_tool_repair":
        return {"status": "not_applicable", "reason": f"repair_profile={repair_profile} is not data_agent_tool_repair"}

    combined = _lower_blob(
        feedback.get("selected_stage"),
        feedback.get("selected_signal"),
        feedback.get("repair_routing"),
        feedback.get("answer_delta"),
        feedback.get("runtime_trace_evidence"),
        feedback.get("ranked_feedback_signals"),
    )
    event_names = _event_names(feedback)

    cpc_mapping_traceback = (
        "adapters/patents/cpc_mapping.py" in combined
        or "adapters.patents.cpc_mapping" in combined
        or "get_level5_symbol" in combined
    )
    level_type_error = (
        "not supported between instances of 'int' and 'str'" in combined
        or "not supported between instances of \"int\" and \"str\"" in combined
        or ("typeerror" in combined and "level > 5" in combined)
        or ("typeerror" in combined and "get_level5_symbol" in combined and "level" in combined)
    )
    if cpc_mapping_traceback and level_type_error:
        return cpc_mapping_runtime_type_plan(feedback)
    if "cpc_definition_field_count_mismatch" in combined or ("cpc_definition" in combined and "field_count" in combined):
        return cpc_definition_parser_plan(feedback)
    if "no_years_found" in combined or "no_yearly_data" in combined or "no_years_with_level5_data" in combined:
        return metadata_year_plan(feedback)
    answer_delta = feedback.get("answer_delta") if isinstance(feedback.get("answer_delta"), dict) else {}
    if (
        answer_delta.get("missing_count") is not None
        or answer_delta.get("extra_count") is not None
        or answer_delta.get("expected_count") is not None
        or answer_delta.get("predicted_count") is not None
    ):
        if "candidate_decision_summary" in event_names:
            return answer_delta_action_plan(feedback)
        return answer_delta_plan(feedback)
    if "ema" in combined or "best year" in combined or "year_axis" in combined or "smoothing" in combined:
        return ema_plan(feedback)
    if "granularity" in combined or "string shape" in combined or "slash" in combined or "level" in combined or "granularity_mapping" in event_names:
        return cpc_mapping_plan(feedback)

    plan = _base_plan(feedback, reason="No precise helper target matched; default to safe reusable PATENTS utilities.")
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/patent_query_utils.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create a minimal reusable PATENTS helper only if it directly addresses the selected fine-grained feedback; otherwise no_op_failed.",
            "required_functions": [],
            "focused_validation_tests": ["py_compile changed helper", "import changed helper", "child generated_solve.py must import changed helper"],
            "success_criteria": ["candidate rationale explicitly links helper API to selected_stage/selected_signal"],
            "matched_feedback": _matched_feedback(feedback, ("patents", "cpc", "runtime", "answer")),
        }
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feedback_json")
    parser.add_argument("--repair-profile", default="data_agent_tool_repair")
    args = parser.parse_args()
    feedback = json.loads(Path(args.feedback_json).read_text(encoding="utf-8"))
    print(json.dumps(plan_helper_repair(feedback, args.repair_profile), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
