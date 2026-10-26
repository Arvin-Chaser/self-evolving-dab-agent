"""Open-ended post-child-eval diagnosis evidence for the meta-agent loop.

This module intentionally does not classify failures into a fixed enum.  It
builds a compact evidence object and an open diagnostic task.  The meta-agent is
expected to produce its own free-form diagnosis label, causal hypothesis, and
next repair strategy from this evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _metric_delta(child: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    keys = ("precision", "recall", "f1", "jaccard")
    delta: dict[str, Any] = {}
    for key in keys:
        child_v = _safe_float(child.get(key))
        parent_v = _safe_float(parent.get(key))
        if child_v is not None or parent_v is not None:
            delta[key] = {
                "parent": parent_v,
                "child": child_v,
                "delta": None if child_v is None or parent_v is None else round(child_v - parent_v, 6),
            }
    count_keys = ("expected_count", "predicted_count", "true_positive", "false_positive", "false_negative")
    for key in count_keys:
        child_v = _safe_int(child.get(key))
        parent_v = _safe_int(parent.get(key))
        if child_v is not None or parent_v is not None:
            delta[key] = {
                "parent": parent_v,
                "child": child_v,
                "delta": None if child_v is None or parent_v is None else child_v - parent_v,
            }
    return delta


def _sample_list(value: Any, limit: int = 24) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def build_open_diagnosis_evidence(
    *,
    candidate_dir: Path | None = None,
    parent_candidate_dir: Path | None = None,
    child_run_dir: Path | None = None,
    child_analysis: dict[str, Any] | None = None,
    child_signal: dict[str, Any] | None = None,
    child_feedback: dict[str, Any] | None = None,
    child_answer_metrics: dict[str, Any] | None = None,
    parent_answer_metrics: dict[str, Any] | None = None,
    helper_usage: dict[str, Any] | None = None,
    child_failure_gates: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Build neutral evidence for a meta-agent open diagnosis.

    The returned object is deliberately descriptive, not prescriptive: no closed
    failure class or forced target helper is emitted here.
    """
    child_analysis = child_analysis or {}
    child_signal = child_signal or {}
    child_feedback = child_feedback or {}
    child_answer_metrics = child_answer_metrics or {}
    parent_answer_metrics = parent_answer_metrics or {}
    helper_usage = helper_usage or {}
    child_failure_gates = child_failure_gates or []
    changed_files = changed_files or []

    diagnosis_questions = [
        "What failure mechanism best explains the child result, in your own open-vocabulary label?",
        "Which evidence supports that causal hypothesis, and which tempting hypotheses are ruled out?",
        "Did the candidate remove an earlier blocker while introducing or revealing a later-stage issue?",
        "What should the next repair target and expected child-observable behavior be?",
        "What should the next iteration avoid repeating?",
    ]
    parent_f1 = _safe_float(parent_answer_metrics.get("f1"))
    child_f1 = _safe_float(child_answer_metrics.get("f1"))
    return {
        "schema_version": "open_diagnosis_evidence_v001",
        "purpose": "Evidence for meta-agent self-diagnosis after child eval. Labels and repair strategy are intentionally open-ended, not enum constrained.",
        "open_diagnosis_required_output": {
            "diagnosis_label": "free-form concise label invented by the meta-agent",
            "causal_hypothesis": "why the child behaved this way",
            "supporting_evidence": "specific evidence references, not generic impressions",
            "ruled_out_or_deprioritized_hypotheses": "what no longer seems causal",
            "next_repair_strategy": "target layer/files and expected child-observable behavior",
            "not_to_repeat": "patch shapes or assumptions to avoid next round",
            "uncertainties": "what remains unknown and how validation should check it",
        },
        "diagnosis_questions": diagnosis_questions,
        "candidate": {
            "candidate_dir": str(candidate_dir) if candidate_dir else None,
            "parent_candidate_dir": str(parent_candidate_dir) if parent_candidate_dir else None,
            "changed_files": changed_files,
        },
        "child_run": {
            "child_run_dir": str(child_run_dir) if child_run_dir else None,
            "passed_original_dab_validation": child_analysis.get("passed"),
            "validation_reason": child_analysis.get("validation_reason"),
            "selected_stage": child_feedback.get("selected_stage") or child_signal.get("selected_component"),
            "selected_signal": child_feedback.get("selected_signal") or child_signal.get("selected_signal"),
            "failure_gates": child_failure_gates,
        },
        "parent_child_metrics": {
            "parent_answer_metrics": parent_answer_metrics,
            "child_answer_metrics": child_answer_metrics,
            "metric_delta": _metric_delta(child_answer_metrics, parent_answer_metrics),
            "improved_f1": None if parent_f1 is None or child_f1 is None else child_f1 > parent_f1,
        },
        "answer_delta_details": {
            "missing_codes_sample": _sample_list(child_answer_metrics.get("missing_codes")),
            "extra_codes_sample": _sample_list(child_answer_metrics.get("extra_codes")),
            "predicted_codes_sample": _sample_list(child_answer_metrics.get("predicted_codes_sample")),
        },
        "helper_usage": helper_usage,
        "fine_grained_feedback_summary": {
            "selected_stage": child_feedback.get("selected_stage"),
            "selected_signal": child_feedback.get("selected_signal"),
            "answer_delta": child_feedback.get("answer_delta"),
            "runtime_trace_evidence_sample": _sample_list(child_feedback.get("runtime_trace_evidence"), 8),
            "ranked_feedback_signals_sample": _sample_list(child_feedback.get("ranked_feedback_signals"), 5),
        },
        "script_boundary": {
            "script_should_not_decide_fixed_failure_type": True,
            "meta_agent_should_choose_open_diagnosis": True,
            "deterministic_planner_role": "advisory_fallback_and_safety_validation, not a closed taxonomy",
        },
    }


def compact_open_diagnosis_evidence(evidence: dict[str, Any], *, max_items: int = 12) -> dict[str, Any]:
    """Compact open diagnosis evidence for prompt context."""
    if not isinstance(evidence, dict):
        return {}
    metric_delta = evidence.get("parent_child_metrics", {}).get("metric_delta") if isinstance(evidence.get("parent_child_metrics"), dict) else {}
    child_run = evidence.get("child_run") if isinstance(evidence.get("child_run"), dict) else {}
    answer_delta = evidence.get("answer_delta_details") if isinstance(evidence.get("answer_delta_details"), dict) else {}
    helper_usage = evidence.get("helper_usage") if isinstance(evidence.get("helper_usage"), dict) else {}
    fine = evidence.get("fine_grained_feedback_summary") if isinstance(evidence.get("fine_grained_feedback_summary"), dict) else {}
    return {
        "schema_version": evidence.get("schema_version"),
        "purpose": evidence.get("purpose"),
        "open_diagnosis_required_output": evidence.get("open_diagnosis_required_output"),
        "diagnosis_questions": evidence.get("diagnosis_questions"),
        "child_run": child_run,
        "metric_delta": metric_delta,
        "answer_delta_details": {
            "missing_codes_sample": _sample_list(answer_delta.get("missing_codes_sample"), max_items),
            "extra_codes_sample": _sample_list(answer_delta.get("extra_codes_sample"), max_items),
            "predicted_codes_sample": _sample_list(answer_delta.get("predicted_codes_sample"), max_items),
        },
        "helper_usage_status": helper_usage.get("status"),
        "helper_usage_details": helper_usage.get("details"),
        "fine_grained_feedback_summary": {
            "selected_stage": fine.get("selected_stage"),
            "selected_signal": fine.get("selected_signal"),
            "answer_delta": fine.get("answer_delta"),
            "runtime_trace_evidence_sample": _sample_list(fine.get("runtime_trace_evidence_sample"), 5),
            "ranked_feedback_signals_sample": _sample_list(fine.get("ranked_feedback_signals_sample"), 3),
        },
        "script_boundary": evidence.get("script_boundary"),
    }