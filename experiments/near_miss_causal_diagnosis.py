#!/usr/bin/env python3
"""Build generic near-miss causal diagnosis evidence for DAB tool-agent runs.

This module deliberately does not decide the repair.  It converts answer-level
missing/extra samples plus local workflow artifacts into open hypotheses that a
meta-agent can inspect.  The goal is to make near-miss boundary refinement a
query-agnostic feedback capability, not a PATENTS/CPC-specific rule.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


COMMON_ARTIFACT_NAMES = (
    "final_answer.txt",
    "workflow_trace.jsonl",
    "tool_calls.jsonl",
    "llm_calls.jsonl",
    "agent_self_observations.jsonl",
    "summary.json",
)


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_answer_quality(value: Any) -> dict[str, Any]:
    quality = _dict(value)
    if not quality:
        return {}
    out = dict(quality)
    if "missing_count" not in out and "false_negative" in out:
        out["missing_count"] = out.get("false_negative")
    if "extra_count" not in out and "false_positive" in out:
        out["extra_count"] = out.get("false_positive")
    if "true_positive_count" not in out and "true_positive" in out:
        out["true_positive_count"] = out.get("true_positive")
    return out


def answer_quality_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("answer_quality", "child_answer_quality", "child_answer_metrics", "answer_metrics"):
        quality = normalize_answer_quality(payload.get(key))
        if quality:
            return quality
    for key in ("feedback_summary", "workflow_feedback_summary", "fine_grained_feedback", "meta_agent_seed"):
        nested = _dict(payload.get(key))
        quality = answer_quality_from_payload(nested) if nested else {}
        if quality:
            return quality
    return {}


def _sample_items(quality: dict[str, Any], primary: str, fallback: str) -> list[str]:
    values = _list(quality.get(primary)) or _list(quality.get(fallback))
    return [str(item) for item in values if str(item).strip()]


def _read_text(path: Path, *, max_chars: int = 250_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def _artifact_paths_from_payload(payload: dict[str, Any], run_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if run_dir:
        for name in COMMON_ARTIFACT_NAMES:
            paths.append(run_dir / name)
    artifact_maps = []
    for key in ("artifact_paths", "full_evidence_pack_paths"):
        value = payload.get(key)
        if isinstance(value, dict):
            artifact_maps.append(value)
    fine = _dict(payload.get("fine_grained_feedback"))
    if isinstance(fine.get("full_evidence_pack_paths"), dict):
        artifact_maps.append(fine["full_evidence_pack_paths"])
    for mapping in artifact_maps:
        for value in mapping.values():
            if isinstance(value, str) and value.strip():
                paths.append(Path(value))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except Exception:
            key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _source_name(path: Path) -> str:
    name = path.name
    if name.endswith(".jsonl"):
        return name[:-6]
    if name.endswith(".json"):
        return name[:-5]
    if name.endswith(".txt"):
        return name[:-4]
    return name


def _load_sources(payload: dict[str, Any], run_dir: Path | None) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in _artifact_paths_from_payload(payload, run_dir):
        if not path.exists() or not path.is_file():
            continue
        text = _read_text(path)
        if not text:
            continue
        sources.append({"name": _source_name(path), "path": str(path), "text": text})
    return sources


def _contains(text: str, item: str) -> bool:
    if not item:
        return False
    return item.lower() in text.lower()


def _diagnose_item(item: str, direction: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    presence = {str(src["name"]): _contains(str(src.get("text") or ""), item) for src in sources}
    final_has = bool(presence.get("final_answer"))
    seen_before_final = any(value for name, value in presence.items() if name != "final_answer")
    source_hits = [name for name, value in presence.items() if value]

    if direction == "missing":
        if final_has:
            hypothesis = "present_in_final_answer_but_validator_still_marks_missing"
            repair_surface = ["answer_format", "normalization", "validator_interface", "final_answer_serialization"]
            question = "The item appears in the final answer text, so inspect formatting, normalization, or validator extraction mismatch."
        elif seen_before_final:
            hypothesis = "observed_before_final_answer_but_dropped_or_not_selected"
            repair_surface = ["candidate_filter", "ranking", "tie_breaker", "final_answer_assembly", "tool_policy"]
            question = "The item appeared in intermediate artifacts but not in the final answer; inspect where it was filtered, ranked out, or omitted."
        else:
            hypothesis = "not_observed_in_available_workflow_artifacts"
            repair_surface = ["data_retrieval", "query_logic", "candidate_generation", "schema_grounding", "tool_selection"]
            question = "The item never appears in available artifacts; inspect retrieval/query coverage and whether the workflow generated this candidate at all."
    else:
        if final_has and seen_before_final:
            hypothesis = "extra_item_survived_to_final_answer"
            repair_surface = ["candidate_filter", "ranking", "negative_filter", "final_answer_assembly"]
            question = "The extra item appears before and in the final answer; inspect why filters/ranking accepted it."
        elif final_has:
            hypothesis = "extra_item_introduced_at_final_answer_assembly"
            repair_surface = ["final_answer_assembly", "formatting", "llm_answer_synthesis"]
            question = "The extra item is only visible in final output; inspect answer assembly or LLM synthesis."
        else:
            hypothesis = "extra_item_reported_but_not_found_in_scanned_artifacts"
            repair_surface = ["validator_interface", "artifact_truncation", "answer_extraction"]
            question = "The extra item was reported by metrics but not found in scanned artifacts; inspect extraction/truncation."

    return {
        "item": item,
        "direction": direction,
        "hypothesis": hypothesis,
        "presence_by_artifact": presence,
        "source_hits": source_hits,
        "suggested_repair_surfaces": repair_surface,
        "meta_agent_question": question,
        "confidence": "medium" if source_hits else "low",
        "policy": "diagnostic_only_do_not_hardcode_item_as_answer_rule",
    }


def build_near_miss_causal_diagnosis(
    payload: dict[str, Any],
    *,
    run_dir: Path | str | None = None,
    max_items: int = 12,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    inferred_run_dir = run_dir or payload.get("run_dir") or payload.get("child_run_dir") or payload.get("parent_run_dir")
    run_dir_path = Path(str(inferred_run_dir)) if inferred_run_dir else None
    quality = answer_quality_from_payload(payload)
    missing_items = _sample_items(quality, "missing_codes_sample", "missing_items_sample")[:max_items]
    extra_items = _sample_items(quality, "extra_codes_sample", "extra_items_sample")[:max_items]
    f1 = _float_or_none(quality.get("f1"))
    missing_count = _int_or_none(quality.get("missing_count"))
    extra_count = _int_or_none(quality.get("extra_count"))
    strict_match_passed = quality.get("strict_match_passed")
    active = bool(
        strict_match_passed is False
        and f1 is not None
        and f1 >= 0.90
        and missing_count is not None
        and extra_count is not None
        and missing_count <= 5
        and extra_count <= 5
        and (missing_items or extra_items)
    )
    sources = _load_sources(payload, run_dir_path)
    item_diagnoses = [
        *[_diagnose_item(item, "missing", sources) for item in missing_items],
        *[_diagnose_item(item, "extra", sources) for item in extra_items],
    ]
    hypothesis_counts = dict(Counter(row["hypothesis"] for row in item_diagnoses))
    return {
        "schema_version": "near_miss_causal_diagnosis_v001",
        "available": bool(quality),
        "active": active,
        "mode": "near_miss_boundary_causal_diagnosis" if active else "available_for_non_near_miss_context",
        "activation_criteria": {
            "strict_match_passed": False,
            "f1_min": 0.90,
            "missing_count_max": 5,
            "extra_count_max": 5,
            "requires_missing_or_extra_samples": True,
        },
        "observed_quality": {
            "strict_match_passed": strict_match_passed,
            "f1": f1,
            "precision": _float_or_none(quality.get("precision")),
            "recall": _float_or_none(quality.get("recall")),
            "expected_count": _int_or_none(quality.get("expected_count")),
            "predicted_count": _int_or_none(quality.get("predicted_count")),
            "missing_count": missing_count,
            "extra_count": extra_count,
        },
        "boundary_items": {
            "missing_sample": missing_items,
            "extra_sample": extra_items,
        },
        "artifact_sources_scanned": [
            {"name": str(src["name"]), "path": str(src["path"])} for src in sources
        ],
        "item_diagnoses": item_diagnoses,
        "aggregate_hypotheses": hypothesis_counts,
        "meta_agent_use": {
            "role": "open_causal_hypotheses_not_fixed_repair_decision",
            "recommended_next_step": "For each boundary item, inspect whether it was never generated, generated but dropped, or present but malformed; then choose the repair surface yourself.",
            "forbidden_use": "Do not hardcode missing/extra samples, expected counts, or validator-only answer lists as DataAgent rules.",
        },
    }