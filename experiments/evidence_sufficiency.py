#!/usr/bin/env python3
"""Assess whether current evidence is sufficient for the next meta-agent repair.

This module does not decide the concrete repair.  It only records whether the
available parent/child behavior evidence can support a DataAgent repair, or
whether the next candidate should consider evolving observer/trace/feedback
plumbing first.
"""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _truthy_count(items: list[bool]) -> int:
    return sum(1 for item in items if item)



def _diagnostic_task_for_missing_evidence(name: str) -> dict[str, Any]:
    """Describe the producer-path reasoning the meta-agent should perform."""
    catalog: dict[str, dict[str, Any]] = {
        "full_child_rerun_stderr_or_traceback": {
            "evidence_layer": "runtime_evidence_acquisition",
            "producer_path_to_find": "the child-eval subprocess launcher that runs the full child rerun",
            "preservation_path_to_find": "where stdout/stderr/exit-code/traceback should be written into child_eval artifacts",
            "consumer_path_to_find": "child_eval_report, failure observer, and next repair seed readers",
            "verification_goal": "a failing full child rerun leaves a stderr or traceback artifact path in child_eval_report.json",
        },
        "pre_query_failure_traceback": {
            "evidence_layer": "runtime_evidence_acquisition",
            "producer_path_to_find": "the earliest DataAgent/batch initialization path before first query dispatch",
            "preservation_path_to_find": "the exception handler around setup/import/tool initialization and batch runner startup",
            "consumer_path_to_find": "observer raw behavior input and evidence_sufficiency",
            "verification_goal": "a startup failure records the exception type/message before query_count remains zero",
        },
        "raw_action_trace_or_behavior_input": {
            "evidence_layer": "runtime_evidence_acquisition",
            "producer_path_to_find": "the DataAgent action loop that records LLM/tool/return_answer events",
            "preservation_path_to_find": "run directory artifacts consumed by direct/fine-grained observer agents",
            "consumer_path_to_find": "run_fine_grained_observer_agent and run_direct_failure_observer_agent behavior-input builders",
            "verification_goal": "a real or failing run directory contains raw behavior events or an explicit no-events startup failure artifact",
        },
        "runtime_helper_tool_list_or_call_trace": {
            "evidence_layer": "runtime_evidence_acquisition",
            "producer_path_to_find": "helper registry installation and run_evolved_helper wrapper in the DataAgent runtime",
            "preservation_path_to_find": "tool-list exposure records plus helper payload/result/exception trace records",
            "consumer_path_to_find": "helper_usage_summary and observer feedback generation",
            "verification_goal": "the run artifacts show whether helpers were registered, exposed to the LLM, called, and with what outcome",
        },
        "parent_child_delta": {
            "evidence_layer": "artifact_comparison_preservation",
            "producer_path_to_find": "child-eval parent/child comparison code",
            "preservation_path_to_find": "parent_child_delta fields in child_eval_report and next repair seed",
            "consumer_path_to_find": "archive selection, failure observer, and meta-agent seed packaging",
            "verification_goal": "candidate reports include a non-empty comparison or an explicit reason comparison is impossible",
        },
        "answer_quality_or_failure_mechanism": {
            "evidence_layer": "observer_interpretation",
            "producer_path_to_find": "answer validator and direct failure observer",
            "preservation_path_to_find": "answer quality metrics or LLM-observed failure mechanism in seed artifacts",
            "consumer_path_to_find": "meta-agent prompt/context pack and archive reward",
            "verification_goal": "a run produces either measurable answer quality or an explicit non-answer failure mechanism",
        },
        "selected_stage_or_signal": {
            "evidence_layer": "observer_interpretation",
            "producer_path_to_find": "trace analyzer and observer agent stage/signal selection",
            "preservation_path_to_find": "feedback_summary, observer feedback, and repair seed fields",
            "consumer_path_to_find": "archive selector and meta-agent context pack",
            "verification_goal": "seed contains a concrete stage/signal or an explicit explanation of ambiguity",
        },
        "closed_answers_to_observer_open_questions": {
            "evidence_layer": "meta_feedback_loop",
            "producer_path_to_find": "the next meta-agent task that should inspect artifacts named by observer open questions",
            "preservation_path_to_find": "candidate final message, validation logs, or next seed evidence answers",
            "consumer_path_to_find": "future failure observer and archive observation",
            "verification_goal": "the next candidate explicitly resolves or narrows observer open questions using real artifacts",
        },
    }
    return {
        "missing_evidence": name,
        **catalog.get(name, {
            "evidence_layer": "unknown",
            "producer_path_to_find": "identify which code path should produce this missing artifact",
            "preservation_path_to_find": "identify where the artifact should be saved",
            "consumer_path_to_find": "identify who reads the artifact in the next loop",
            "verification_goal": "prove the real pipeline now emits or explicitly explains this evidence",
        }),
        "meta_agent_rule": "Do not patch only the consumer/analyzer if the missing evidence is not produced or preserved upstream.",
    }

def assess_evidence_sufficiency(
    *,
    seed: dict[str, Any] | None = None,
    observer_feedback: dict[str, Any] | None = None,
    child_eval: dict[str, Any] | None = None,
    failure_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, archive-friendly evidence sufficiency assessment."""
    seed = _as_dict(seed)
    observer_feedback = _as_dict(observer_feedback)
    child_eval = _as_dict(child_eval)
    failure_observation = _as_dict(failure_observation)

    fine = _as_dict(seed.get("fine_grained_feedback"))
    answer_quality = _as_dict(seed.get("answer_quality") or fine.get("answer_quality"))
    child_summary = _as_dict(
        child_eval.get("child_multi_query_summary")
        or child_eval.get("child_summary")
        or child_eval.get("child_status")
    )
    full_child = _as_dict(child_eval.get("full_child_rerun"))
    parent_child_delta = _as_dict(child_eval.get("parent_child_delta"))
    full_child_artifacts = _as_dict(full_child.get("artifact_paths"))
    helper_status = _as_dict(
        child_eval.get("helper_usage_status_counts")
        or child_summary.get("helper_usage_status_counts")
        or seed.get("helper_usage_status_counts")
    )

    selected_stage = (
        child_eval.get("child_selected_stage")
        or _as_dict(child_eval.get("child_status")).get("selected_stage")
        or seed.get("selected_stage")
        or fine.get("selected_stage")
    )
    selected_signal = (
        child_eval.get("child_selected_signal")
        or _as_dict(child_eval.get("child_status")).get("selected_signal")
        or seed.get("selected_signal")
        or fine.get("selected_signal")
    )

    query_count = child_eval.get("query_count")
    if query_count is None:
        query_count = child_summary.get("query_count") or seed.get("query_count")
    final_answer_count = child_eval.get("final_answer_nonempty_count")
    if final_answer_count is None:
        final_answer_count = child_summary.get("final_answer_nonempty_count") or seed.get("final_answer_nonempty_count")

    evidence_chain = _as_list(failure_observation.get("evidence_chain"))
    open_questions = _as_list(failure_observation.get("open_questions_for_meta_agent"))
    observer_mechanism = (
        failure_observation.get("primary_failure_mechanism")
        or observer_feedback.get("primary_failure_mechanism")
        or full_child.get("failure_mechanism")
    )
    observer_confidence = failure_observation.get("confidence") or observer_feedback.get("confidence")
    raw_behavior_input = (
        failure_observation.get("direct_behavior_input")
        or seed.get("observer_raw_behavior_input_path")
        or fine.get("observer_raw_behavior_input_path")
        or full_child.get("stderr_path")
        or full_child_artifacts.get("stderr")
    )

    has_action_trace = bool(
        raw_behavior_input
        or _as_dict(fine.get("full_evidence_pack_paths")).get("json")
        or _as_dict(seed.get("full_evidence_pack_paths")).get("json")
    )
    has_answer_metric = any(answer_quality.get(k) is not None for k in ("f1", "precision", "recall", "missing_count", "extra_count"))
    has_parent_child_delta = bool(parent_child_delta)
    has_failure_mechanism = bool(observer_mechanism)
    has_evidence_chain = bool(evidence_chain)
    has_stage_signal = bool(selected_stage or selected_signal)
    has_tool_runtime_evidence = bool(helper_status) or "helper" in str(observer_mechanism or "").lower()
    has_full_child_traceback = bool(
        full_child.get("stderr")
        or full_child.get("stderr_path")
        or full_child.get("stderr_tail")
        or full_child_artifacts.get("stderr")
        or child_eval.get("stderr_path")
        or child_eval.get("traceback")
    )

    missing: list[str] = []
    if not has_stage_signal:
        missing.append("selected_stage_or_signal")
    if not has_action_trace:
        missing.append("raw_action_trace_or_behavior_input")
    if not has_answer_metric and not has_failure_mechanism:
        missing.append("answer_quality_or_failure_mechanism")
    if child_eval and not has_parent_child_delta:
        missing.append("parent_child_delta")
    if full_child.get("status") == "failed" and not has_full_child_traceback:
        missing.append("full_child_rerun_stderr_or_traceback")
    if (query_count == 0 or query_count == "0") and not has_full_child_traceback:
        missing.append("pre_query_failure_traceback")
    if "helper" in str(observer_mechanism or "").lower() and not helper_status:
        missing.append("runtime_helper_tool_list_or_call_trace")
    if open_questions:
        missing.append("closed_answers_to_observer_open_questions")

    sufficient_signals = _truthy_count(
        [
            has_stage_signal,
            has_action_trace,
            has_answer_metric,
            has_failure_mechanism,
            has_evidence_chain or has_full_child_traceback,
            has_parent_child_delta or not child_eval,
            has_tool_runtime_evidence or "helper" not in str(observer_mechanism or "").lower(),
        ]
    )
    max_signals = 7
    score = round(sufficient_signals / max_signals, 3)

    hard_insufficient = bool(
        full_child.get("status") == "failed" and not has_full_child_traceback
        or (query_count == 0 or query_count == "0") and not has_full_child_traceback
        or ("helper" in str(observer_mechanism or "").lower() and not helper_status)
    )
    status = "insufficient" if hard_insufficient or score < 0.72 else "sufficient"
    opportunity = status == "insufficient"

    if opportunity:
        target = "observer_feedback_pipeline"
    elif has_answer_metric or has_failure_mechanism:
        target = "data_agent_repair"
    else:
        target = "meta_agent_decide"

    missing_unique = sorted(set(missing))
    diagnostic_tasks = [_diagnostic_task_for_missing_evidence(item) for item in missing_unique]
    layer_order = [
        "runtime_evidence_acquisition",
        "artifact_comparison_preservation",
        "observer_interpretation",
        "meta_feedback_loop",
        "unknown",
    ]
    layer_counts = {layer: 0 for layer in layer_order}
    for task in diagnostic_tasks:
        layer = str(task.get("evidence_layer") or "unknown")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
    recommended_observer_subtarget = next((layer for layer in layer_order if layer_counts.get(layer)), None)

    return {
        "schema_version": "evidence_sufficiency_v002",
        "status": status,
        "score": score,
        "feedback_evolution_opportunity": opportunity,
        "recommended_evolution_target": target,
        "rationale": (
            "Evidence cannot yet distinguish competing failure explanations; evolve observer/trace/feedback plumbing first."
            if opportunity
            else "Evidence appears sufficient for a direct DataAgent repair attempt."
        ),
        "missing_evidence": missing_unique,
        "recommended_observer_subtarget": recommended_observer_subtarget,
        "missing_evidence_diagnostic_tasks": diagnostic_tasks,
        "meta_agent_required_reasoning": [
            "For each missing evidence item, identify its producer path, preservation path, and consumer path before choosing a patch target.",
            "Patch the producer or preservation path when evidence is absent; patch analyzer interpretation only when the artifact is already produced.",
            "Verify against the real child/eval pipeline, not only synthetic analyzer inputs.",
            "If the real pipeline still cannot run because of an external environment issue, preserve command/stdout/stderr/traceback artifacts that prove that boundary.",
        ],
        "available_evidence": {
            "has_stage_signal": has_stage_signal,
            "has_action_trace_or_behavior_input": has_action_trace,
            "has_answer_quality_metric": has_answer_metric,
            "has_failure_mechanism": has_failure_mechanism,
            "has_failure_evidence_chain": has_evidence_chain,
            "has_parent_child_delta": has_parent_child_delta,
            "has_tool_runtime_evidence": has_tool_runtime_evidence,
            "has_full_child_traceback": has_full_child_traceback,
        },
        "observed_failure_context": {
            "selected_stage": selected_stage,
            "selected_signal": selected_signal,
            "primary_failure_mechanism": observer_mechanism,
            "observer_confidence": observer_confidence,
            "query_count": query_count,
            "final_answer_nonempty_count": final_answer_count,
            "full_child_rerun_status": full_child.get("status"),
        },
        "meta_agent_instruction": (
            "Before another answer/helper repair, perform missing-evidence producer-path diagnosis and consider evolving runtime trace, stderr preservation, tool-list, or helper-call evidence so future patches are diagnosable."
            if opportunity
            else "Proceed with a DataAgent repair if the patch can be verified against the available evidence."
        ),
    }
