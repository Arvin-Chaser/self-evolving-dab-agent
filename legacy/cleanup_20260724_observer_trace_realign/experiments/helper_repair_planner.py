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
                    "signature": "parse_cpc_definition_sql(sql_path: str | Path) -> dict[str, dict]",
                    "purpose": "Return a dict with symbol_to_level and symbol_to_parents from the CPCDefinition SQL COPY block.",
                    "must_handle": [
                        "COPY public.cpc_definition (...) FROM stdin; header on one line",
                        "quoted and unquoted column names",
                        "tab-delimited data rows after FROM stdin",
                        "exact backslash-dot COPY terminator",
                        "escaped newlines in parents fields",
                        "column list should be sliced between COPY public.cpc_definition ( and ) FROM stdin; instead of using a first-parenthesis regex",
                        "malformed/header lines should be skipped or surfaced without corrupting mappings",
                        "return {'symbol_to_level': ..., 'symbol_to_parents': ...}; do not return a bare tuple",
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


def cpc_definition_schema_grounding_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = cpc_definition_parser_plan(feedback)
    plan["reason"] = (
        "Fine-grained schema_grounding feedback says generated_solve.py did not read "
        "CPC_DEFINITION_SQL_PATH; create a reusable CPCDefinition metadata reader and require "
        "generated_solve.py to call it before CPC level mapping."
    )
    plan["helper_focus"] = (
        "Create or update a reusable CPCDefinition metadata reader/parser. Prompt glue must require "
        "generated_solve.py to call metadata = parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH) before mapping raw CPC codes, "
        "extract symbol_to_level = metadata.get('symbol_to_level', {}) and symbol_to_parents = metadata.get('symbol_to_parents', {}), "
        "then use those dictionaries in get_level5_symbol/raw-code mapping, "
        "and fail/log explicitly if metadata is empty instead of producing an empty final_answer.txt."
    )
    plan["focused_validation_tests"] = [
        "py_compile adapters/patents/cpc_definition_parser.py",
        "import adapters.patents.cpc_definition_parser",
        "parse real CPC_DEFINITION_SQL_PATH and assert symbol_to_level has many rows",
        "child generated_solve.py must call metadata = parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH)",
        "child generated_solve.py must use metadata.get('symbol_to_level', {}) and metadata.get('symbol_to_parents', {}) before final answer construction",
        "child selected_signal should move beyond schema_grounding/not_read_cpc_definition",
    ]
    plan["success_criteria"] = [
        "generated_solve.py reads CPC_DEFINITION_SQL_PATH through the helper before CPC mapping",
        "symbol_to_level and symbol_to_parents are non-empty in runtime trace or generated code flow",
        "child final_answer.txt is not empty solely because CPCDefinition metadata was never read",
        "child eval progresses to mapping/EMA/answer-delta rather than schema_grounding",
    ]
    plan["matched_feedback"] = _matched_feedback(
        feedback,
        ("schema_grounding", "cpc_definition_sql_path", "does not actually read", "metadata source", "cpcdefinition"),
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


def cpc_mapping_missing_module_plan(feedback: dict[str, Any]) -> dict[str, Any]:
    plan = cpc_mapping_plan(
        feedback,
        reason="Generated code imports adapters.patents.cpc_mapping/get_level5_symbol but the helper module is missing from the materialized parent source; create or materialize the missing helper instead of adding answer diagnostics.",
        runtime_type_repair=False,
    )
    plan["focused_validation_tests"] = [
        "py_compile adapters/patents/cpc_mapping.py",
        "import adapters.patents.cpc_mapping",
        "synthetic get_level5_symbol test for exact level-5 metadata match",
        "synthetic get_level5_symbol test returns None when metadata cannot confirm mapping",
        "parent/child generated_solve.py import should not fail with ModuleNotFoundError",
    ]
    plan["success_criteria"] = [
        "generated_solve.py no longer fails with ModuleNotFoundError for adapters.patents.cpc_mapping",
        "helper remains metadata-grounded and does not fallback to raw CPC strings when metadata is missing",
    ]
    return plan


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
        reason="Fine-grained answer_delta shows a non-empty but wrong answer; the next helper must change ranking/filtering behavior, not add more observation-only logging.",
    )
    plan.update(
        {
            "recommended_helper_file": "adapters/patents/candidate_filtering.py",
            "recommended_prompt_glue_file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "helper_focus": "Create a reusable candidate ranking/filtering helper that consumes the full unfiltered candidate_rows and returns the final CPC symbols to write; do not pass pre-filtered candidates_2022; do not implement only best_year == target_year filtering; add an evidence-based exclusion/ranking policy beyond best-year equality.",
            "required_functions": [
                {
                    "name": "rank_or_filter_candidates",
                    "signature": "rank_or_filter_candidates(candidate_rows: list[dict], *, target_year: int = 2022) -> list[str]",
                    "purpose": "Return the candidate CPC symbols selected for the final answer using generated evidence such as best_year, counts, EMA values, and exclusion reasons.",
                    "must_handle": [
                        "no ground-truth answer lists or exact expected counts",
                        "deterministic ranking/tie policy",
                        "uses best_year/EMA/count evidence rather than simply echoing all candidates",
                        "must not be equivalent to filtering only row.get(\'best_year\') == target_year",
                        "must add an evidence-based exclusion/ranking policy beyond best-year equality",
                        "returns a concrete list of symbols for final_answer.txt",
                    ],
                }
            ],
            "focused_validation_tests": [
                "py_compile adapters/patents/candidate_filtering.py",
                "import adapters.patents.candidate_filtering",
                "synthetic rank_or_filter_candidates test proves behavior is not equivalent to best_year == target_year only",
                "child generated_solve.py must call rank_or_filter_candidates on full unfiltered candidate_rows to construct final_answer.txt",
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



def attach_patch_generation_contract(plan: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    """Attach an action contract that the patch-spec proposer can follow."""
    if plan.get("status") != "planned":
        return plan
    patch_feedback = feedback.get("patch_generation_feedback") if isinstance(feedback.get("patch_generation_feedback"), dict) else {}
    required_functions = plan.get("required_functions") if isinstance(plan.get("required_functions"), list) else []
    helper_file = str(plan.get("recommended_helper_file") or "")
    required_names = {str(func.get("name") or "") for func in required_functions if isinstance(func, dict)}
    behavior_required = helper_file.endswith("candidate_filtering.py") or "rank_or_filter_candidates" in required_names
    behavior_contract: dict[str, Any] = {
        "required": behavior_required,
        "why": (
            "Fine-grained feedback already contains candidate diagnostics or measurable answer_delta; the next patch must change final answer selection/ranking/filtering, not add observation-only diagnostics."
            if behavior_required
            else "This helper may be diagnostic or infrastructural, but patch_spec should still explain the expected child behavior difference."
        ),
        "before": "Parent generated_solve.py selects final CPC symbols through generated heuristic code and the observed selected_signal remains unresolved.",
        "after": (
            "Child generated_solve.py calls the planned helper on full unfiltered runtime evidence and uses the helper output to construct final_answer.txt."
            if behavior_required
            else "Child generated_solve.py has more concrete reusable evidence or safer helper behavior for the selected signal."
        ),
        "must_change_decision_path": behavior_required,
        "patch_spec_required_fields": [
            "behavior_change_contract.before",
            "behavior_change_contract.after",
            "behavior_change_contract.decision_path_change",
            "behavior_change_contract.child_observable_effect",
            "behavior_change_contract.why_not_diagnostics_only",
        ],
        "insufficient_patch_shapes": [
            "diagnostics-only helper that only summarizes/logs candidate decisions",
            "helper that is imported but not used to construct final_answer.txt",
            "prompt glue that asks generated_solve.py to call helper only after pre-filtering candidates",
            "ranking/filtering equivalent to best_year == target_year or top-k expected-count truncation",
        ],
    }
    contract: dict[str, Any] = {
        "schema_version": "helper_patch_generation_contract_v002",
        "recommended_helper_file": helper_file,
        "recommended_prompt_glue_file": plan.get("recommended_prompt_glue_file"),
        "helper_focus": plan.get("helper_focus"),
        "required_functions": required_functions,
        "must_use_feedback_fields": [
            "patch_generation_feedback.selected_stage",
            "patch_generation_feedback.selected_signal",
            "patch_generation_feedback.evidence_to_use.relevant_trace_events",
            "patch_generation_feedback.diagnosis_summary.answer_delta_metrics",
        ],
        "patch_spec_rationale_must_include": [
            "the selected_stage/selected_signal being repaired",
            "which trace/ranked feedback event supports the target file",
            "why the change is not prompt-only advice when a helper is recommended",
            "how the child behavior should differ from the parent behavior",
            "the explicit behavior_change_contract fields when behavior_change_contract.required is true",
        ],
        "behavior_change_contract": behavior_contract,
        "helper_io_contract": {
            "inputs": [],
            "outputs": [],
            "reason_metadata_required": True,
        },
        "forbidden_shortcuts": list((patch_feedback.get("forbidden_patch_shortcuts") if isinstance(patch_feedback, dict) else []) or [])
        or [
            "hardcode expected answers or answer counts",
            "top-k truncate to expected answer cardinality",
            "generate diagnostics-only helper when action helper is required",
        ],
        "focused_validation_tests": plan.get("focused_validation_tests") or [],
        "success_criteria": plan.get("success_criteria") or [],
    }
    for func in required_functions:
        if not isinstance(func, dict):
            continue
        name = str(func.get("name") or "")
        signature = str(func.get("signature") or "")
        if "candidate_rows" in signature:
            contract["helper_io_contract"]["inputs"].append("full unfiltered candidate_rows")
            if name == "rank_or_filter_candidates":
                contract["helper_io_contract"]["inputs"].append("target_year")
                contract["helper_io_contract"]["outputs"].extend(["selected_symbols", "rank/exclusion reasons"])
            elif name == "summarize_candidate_decisions":
                contract["helper_io_contract"]["outputs"].extend(["candidate decision summary", "per-symbol reason samples"])
            else:
                contract["helper_io_contract"]["outputs"].append("structured helper result with reasons")
        if name == "parse_cpc_definition_sql" or "cpc_definition" in signature.lower() or "sql_path" in signature.lower():
            contract["helper_io_contract"]["inputs"].append("CPC_DEFINITION_SQL_PATH")
            contract["helper_io_contract"]["outputs"].extend(["metadata dict", "symbol_to_level", "symbol_to_parents"])
        if "raw_code" in signature or "symbol_to_level" in signature:
            contract["helper_io_contract"]["inputs"].extend(["raw CPC code", "symbol_to_level", "symbol_to_parents"])
            contract["helper_io_contract"]["outputs"].extend(["metadata-confirmed mapped symbol or None", "failure reason if logged"])
        if "year" in signature.lower() or "filing" in signature.lower():
            contract["helper_io_contract"]["inputs"].append("raw filing/date value")
            contract["helper_io_contract"]["outputs"].append("int year or None")
        if "ema" in signature.lower():
            contract["helper_io_contract"]["inputs"].append("yearly_counts over filing years")
            contract["helper_io_contract"]["outputs"].append("EMA series or best-year mapping")
    # Stable de-duplication for readability.
    for key in ("inputs", "outputs"):
        seen: list[str] = []
        for item in contract["helper_io_contract"][key]:
            if item and item not in seen:
                seen.append(item)
        contract["helper_io_contract"][key] = seen
    plan["patch_generation_contract"] = contract
    return plan


def plan_helper_repair(feedback: dict[str, Any], repair_profile: str | None = None) -> dict[str, Any]:
    if repair_profile and repair_profile != "data_agent_tool_repair":
        return {"status": "not_applicable", "reason": f"repair_profile={repair_profile} is not data_agent_tool_repair"}

    combined = _lower_blob(
        feedback.get("selected_stage"),
        feedback.get("selected_signal"),
        feedback.get("repair_routing"),
        feedback.get("answer_delta"),
        feedback.get("analysis_summary"),
        feedback.get("runtime_trace_evidence"),
        feedback.get("ranked_feedback_signals"),
    )
    event_names = _event_names(feedback)
    active_selected_stage = str(feedback.get("selected_stage") or "").lower()
    active_selected_signal = str(feedback.get("selected_signal") or "").lower()
    active_schema_grounding_signal = (
        "schema_grounding" in active_selected_stage
        or "does not actually read" in active_selected_signal
        or "does not read" in active_selected_signal
        or "did not read" in active_selected_signal
        or "cpc_definition_sql_path" in active_selected_signal
    )

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
    missing_cpc_mapping_module = (
        cpc_mapping_traceback
        and (
            "modulenotfounderror" in combined
            or "no module named 'adapters.patents'" in combined
            or 'no module named "adapters.patents"' in combined
            or "no module named 'adapters.patents.cpc_mapping'" in combined
            or 'no module named "adapters.patents.cpc_mapping"' in combined
        )
    )
    if missing_cpc_mapping_module:
        return attach_patch_generation_contract(cpc_mapping_missing_module_plan(feedback), feedback)
    if cpc_mapping_traceback and level_type_error:
        return attach_patch_generation_contract(cpc_mapping_runtime_type_plan(feedback), feedback)
    cpc_definition_parser_context = (
        "parse_cpc_definition_sql" in combined
        or "cpc_definition_parser" in combined
        or "symbol_to_level" in combined
        or "symbol_to_parents" in combined
        or "cpcdefinition" in combined
        or "cpc definition" in combined
    )
    tuple_get_api_error = (
        "tuple object has no attribute get" in combined
        or "'tuple' object has no attribute 'get'" in combined
        or ("tuple" in combined and "has no attribute" in combined and "get" in combined)
        or ("attributeerror" in combined and ".get" in combined and "tuple" in combined)
    )
    cpc_definition_parser_api_mismatch = cpc_definition_parser_context and tuple_get_api_error
    if cpc_definition_parser_api_mismatch:
        plan = cpc_definition_schema_grounding_plan(feedback)
        plan["reason"] = (
            "Runtime evidence shows parse_cpc_definition_sql return-value API mismatch: generated_solve.py expects a metadata dict with .get('symbol_to_level')/.get('symbol_to_parents'), "
            "so repair the CPCDefinition parser contract instead of switching to answer filtering."
        )
        return attach_patch_generation_contract(plan, feedback)
    cpc_definition_header_parse_failure = cpc_definition_parser_context and (
        "failed to extract columns from copy header" in combined
        or "failed to parse column names" in combined
        or "missing required columns" in combined
        or ("copy header" in combined and "column" in combined and ("valueerror" in combined or "parse" in combined))
    )
    if cpc_definition_header_parse_failure:
        plan = cpc_definition_parser_plan(feedback)
        plan["reason"] = (
            "Runtime evidence shows parse_cpc_definition_sql is called, but the helper fails on the real CPCDefinition COPY header; "
            "repair the parser's header/column extraction instead of treating this as a not-read or candidate-filtering issue."
        )
        plan["helper_focus"] = (
            "Repair the CPCDefinition SQL parser so it handles the real header form "
            "`COPY public.cpc_definition (\"applicationReferences\", ..., symbol, ...) FROM stdin;`. "
            "Extract columns by slicing between `COPY public.cpc_definition (` and `) FROM stdin;`, preserving quoted column names after stripping quotes, "
            "then parse the tab-delimited rows and return {'symbol_to_level': ..., 'symbol_to_parents': ...}."
        )
        plan["focused_validation_tests"] = [
            "py_compile adapters/patents/cpc_definition_parser.py",
            "import adapters.patents.cpc_definition_parser",
            "parse real patent_CPCDefinition.sql and assert symbol_to_level is non-empty",
            "parse real patent_CPCDefinition.sql and assert symbol_to_parents is non-empty",
            "assert known real columns include symbol, level, parents after quote stripping",
        ]
        plan["success_criteria"] = [
            "parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH) does not raise Failed to extract columns from COPY header",
            "metadata['symbol_to_level'] and metadata['symbol_to_parents'] are non-empty for the real PATENTS CPCDefinition SQL file",
            "child eval progresses past CPCDefinition parser initialization into CPC mapping/EMA/answer-delta behavior",
        ]
        return attach_patch_generation_contract(plan, feedback)
    schema_grounding_not_read_cpc_definition = (
        active_schema_grounding_signal
        and ("cpc_definition_sql_path" in combined or "cpcdefinition" in combined or "cpc definition" in combined)
        and (
            "does not actually read" in combined
            or "did not read" in combined
            or "does not read" in combined
            or "not read" in combined
            or "metadata source is provided" in combined
        )
    )
    if schema_grounding_not_read_cpc_definition:
        return attach_patch_generation_contract(cpc_definition_schema_grounding_plan(feedback), feedback)
    if "cpc_definition_field_count_mismatch" in combined or ("cpc_definition" in combined and "field_count" in combined):
        return attach_patch_generation_contract(cpc_definition_parser_plan(feedback), feedback)
    if "no_years_found" in combined or "no_yearly_data" in combined or "no_years_with_level5_data" in combined:
        return attach_patch_generation_contract(metadata_year_plan(feedback), feedback)
    answer_delta = feedback.get("answer_delta") if isinstance(feedback.get("answer_delta"), dict) else {}
    if (
        answer_delta.get("missing_count") is not None
        or answer_delta.get("extra_count") is not None
        or answer_delta.get("expected_count") is not None
        or answer_delta.get("predicted_count") is not None
    ):
        return attach_patch_generation_contract(answer_delta_action_plan(feedback), feedback)
    if "ema" in combined or "best year" in combined or "year_axis" in combined or "smoothing" in combined:
        return attach_patch_generation_contract(ema_plan(feedback), feedback)
    if "granularity" in combined or "string shape" in combined or "slash" in combined or "level" in combined or "granularity_mapping" in event_names:
        return attach_patch_generation_contract(cpc_mapping_plan(feedback), feedback)

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
    return attach_patch_generation_contract(plan, feedback)


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
