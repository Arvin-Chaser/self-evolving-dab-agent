#!/usr/bin/env python3
"""Analyze DAB tool-agent workflow artifacts into generic feedback observations.

This analyzer is the first zero-start bridge from DAB workflow logs to the
meta-agent evidence layer.  It intentionally avoids PATENTS/CPC-specific rules.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "path": str(path)}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            value = {"_parse_error": str(exc), "line_no": line_no, "raw": line}
        rows.append(value if isinstance(value, dict) else {"value": value})
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_query_validator(query_dir: Path) -> Any | None:
    validate_path = query_dir / "validate.py"
    if not validate_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(f"dab_validate_{abs(hash(validate_path))}", validate_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def compute_answer_quality(summary: dict[str, Any], final_answer: str) -> dict[str, Any]:
    """Compute answer-level quality metrics when the query validator exposes a set extractor.

    This is analyzer-only feedback. It may read ground truth/validator artifacts because the
    DataAgent itself never receives this object; the metrics are for post-run meta-agent repair.
    """

    query_dir_raw = summary.get("query_dir")
    if not query_dir_raw:
        return {"available": False, "reason": "summary_missing_query_dir"}

    query_dir = Path(str(query_dir_raw))
    validator = _load_query_validator(query_dir)
    if validator is None:
        return {"available": False, "reason": "validator_not_found_or_unloadable", "query_dir": str(query_dir)}

    required = ("extract_cpc_codes", "load_ground_truth_codes")
    if not all(hasattr(validator, name) for name in required):
        return {
            "available": False,
            "reason": "validator_missing_supported_code_set_interface",
            "query_dir": str(query_dir),
        }

    try:
        expected_codes = list(validator.load_ground_truth_codes())
        predicted_codes = list(validator.extract_cpc_codes(final_answer))
        strict_passed = None
        strict_reason = None
        if hasattr(validator, "validate"):
            strict_passed, strict_reason = validator.validate(final_answer)
    except Exception as exc:
        return {
            "available": False,
            "reason": "answer_quality_runtime_error",
            "query_dir": str(query_dir),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    expected_set = set(expected_codes)
    predicted_set = set(predicted_codes)
    missing = sorted(expected_set - predicted_set)
    extra = sorted(predicted_set - expected_set)
    true_positive = len(expected_set & predicted_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(expected_set) if expected_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    duplicates = sorted(code for code, count in Counter(predicted_codes).items() if count > 1)

    return {
        "available": True,
        "metric_type": "cpc_code_set_overlap",
        "strict_match_passed": strict_passed,
        "strict_match_reason": strict_reason,
        "expected_count": len(expected_set),
        "predicted_count": len(predicted_set),
        "true_positive_count": true_positive,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_count": len(duplicates),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "missing_codes_sample": missing[:20],
        "extra_codes_sample": extra[:20],
        "predicted_codes_sample": sorted(predicted_set)[:20],
        "query_dir": str(query_dir),
    }


def observation(
    problem_id: str,
    *,
    stage: str,
    problem_type: str,
    severity: str,
    evidence: dict[str, Any],
    confidence: float,
    uncertainty: str,
    suggested_targets: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "problem_id": problem_id,
        "stage": stage,
        "problem_type": problem_type,
        "severity": severity,
        "evidence": evidence,
        "confidence": confidence,
        "uncertainty": uncertainty,
        "suggested_targets": suggested_targets,
        "rationale": rationale,
    }


def result_is_empty(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, dict):
        if result.get("success") is False:
            return False
        values = [result[key] for key in ("result", "preview") if key in result]
        if not values:
            return False
        return all(value in (None, "", [], {}, "[]") for value in values)
    if result in ("", [], {}, "[]"):
        return True
    return False


def compute_helper_usage_summary(summary: dict[str, Any], tool_calls: list[dict[str, Any]], final_answer: str) -> dict[str, Any]:
    specs = summary.get("evolved_helper_specs") if isinstance(summary.get("evolved_helper_specs"), list) else []
    helper_names = [str(spec.get("name")) for spec in specs if isinstance(spec, dict) and spec.get("name")]
    helper_tool_name = str(summary.get("evolved_helper_tool_name") or "run_evolved_helper")
    helper_tool_enabled = bool(summary.get("evolved_helper_tool_enabled") or specs)

    helper_call_indexes: list[int] = []
    return_answer_indexes: list[int] = []
    helper_call_samples: list[dict[str, Any]] = []
    for idx, row in enumerate(tool_calls, start=1):
        tool_name = row.get("tool_name")
        if tool_name == helper_tool_name:
            helper_call_indexes.append(idx)
            helper_call_samples.append({
                "index": idx,
                "tool_name": tool_name,
                "result_preview": str(row.get("result"))[:500],
            })
        if tool_name == "return_answer":
            return_answer_indexes.append(idx)

    helper_called = bool(helper_call_indexes)
    return_answer_after_helper = bool(
        helper_call_indexes
        and return_answer_indexes
        and min(return_answer_indexes) > min(helper_call_indexes)
    )

    if not helper_tool_enabled:
        status = "no_evolved_helper_registered"
        dependency_status = "not_applicable"
    elif not helper_called:
        status = "helper_tool_registered_but_not_called"
        dependency_status = "helper_output_not_available_for_final_answer"
    elif return_answer_after_helper and str(final_answer).strip():
        status = "helper_tool_called_before_final_answer"
        dependency_status = "helper_output_available_before_final_answer_unverified"
    elif helper_called:
        status = "helper_tool_called_but_no_later_final_answer"
        dependency_status = "helper_output_not_used_for_final_answer"
    else:
        status = "unknown"
        dependency_status = "unknown"

    return {
        "schema_version": "dab_tool_agent_helper_usage_summary_v001",
        "helper_tool_enabled": helper_tool_enabled,
        "helper_tool_name": helper_tool_name,
        "registered_helper_count": len(helper_names),
        "registered_helper_names": helper_names,
        "helper_tool_called": helper_called,
        "helper_call_count": len(helper_call_indexes),
        "helper_call_indexes": helper_call_indexes,
        "return_answer_indexes": return_answer_indexes,
        "return_answer_after_helper": return_answer_after_helper,
        "final_answer_nonempty": bool(str(final_answer).strip()),
        "status": status,
        "final_answer_dependency_status": dependency_status,
        "helper_call_samples": helper_call_samples[:3],
    }


def compact_agent_self_observations(rows: list[dict[str, Any]], max_items: int = 8) -> dict[str, Any]:
    """Compact DataAgent-authored freeform observations without judging them.

    These observations are intentionally open-ended. The analyzer exposes them as
    evidence for the meta-agent to interpret, rather than converting them into a
    fixed failure-stage taxonomy.
    """
    compact_items: list[dict[str, Any]] = []
    claims: list[str] = []
    uncertainties: list[str] = []
    intended_next_steps: list[str] = []
    evidence_refs: list[str] = []

    for idx, row in enumerate(rows, start=1):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if not isinstance(payload, dict):
            payload = {"freeform": str(payload)}
        item = {
            "index": idx,
            "timestamp": row.get("timestamp"),
            "freeform": str(payload.get("freeform") or "")[:1200],
            "current_goal": payload.get("current_goal"),
            "intended_next_step": payload.get("intended_next_step"),
            "failure_if_stopped_now": payload.get("failure_if_stopped_now"),
            "evidence_refs": payload.get("evidence_refs") if isinstance(payload.get("evidence_refs"), list) else [],
        }
        compact_items.append(item)
        for key, target in (("claims", claims), ("uncertainties", uncertainties), ("evidence_refs", evidence_refs)):
            values = payload.get(key)
            if isinstance(values, list):
                target.extend(str(value) for value in values if str(value).strip())
        if payload.get("intended_next_step"):
            intended_next_steps.append(str(payload.get("intended_next_step")))

    return {
        "schema_version": "agent_self_observation_summary_v001",
        "available": bool(rows),
        "count": len(rows),
        "tool_name": "record_self_observation",
        "interpretation_policy": "open_observations_for_meta_agent_inference_not_fixed_failure_taxonomy",
        "items": compact_items[:max_items],
        "claims_sample": claims[:max_items],
        "uncertainties_sample": uncertainties[:max_items],
        "intended_next_steps_sample": intended_next_steps[:max_items],
        "evidence_refs_sample": evidence_refs[:max_items],
    }


def select_primary_workflow_signal(
    observations: list[dict[str, Any]],
    answer_quality: dict[str, Any],
    helper_usage_summary: dict[str, Any],
    summary: dict[str, Any],
    final_answer: str,
) -> dict[str, Any]:
    def candidate_layers_for(problem_type: str, stage: str) -> list[str]:
        mapping = {
            "tool_runtime_unavailable": ["runner_or_environment", "tool_environment"],
            "helper_tool_registered_but_not_called": ["tool_schema", "prompt_policy", "helper_registry", "workflow_logging"],
            "answer_quality_mismatch": ["answer_logic", "helper_tool", "tool_call_strategy", "workflow_logging"],
            "tool_failure": ["tool_call_strategy", "schema_grounding", "tool_schema", "helper_tool"],
            "empty_result": ["query_logic", "schema_grounding", "tool_call_strategy"],
            "missing_final_answer": ["workflow_control", "answer_submission", "prompt_policy"],
            "budget_exhausted": ["workflow_control", "tool_call_strategy", "prompt_policy"],
            "llm_did_not_call_tool": ["tool_selection_policy", "tool_schema", "prompt_policy"],
            "no_tool_call_recorded": ["tool_selection_policy", "model_tool_protocol", "runner"],
            "missing_data_query": ["tool_selection_policy", "query_logic", "prompt_policy"],
            "missing_local_computation": ["tool_selection_policy", "helper_tool", "prompt_policy"],
            "answer_validation_failed": ["answer_logic", "validation_interface", "helper_tool"],
        }
        candidates = list(mapping.get(problem_type, []))
        if stage and stage != "unknown" and stage not in candidates:
            candidates.append(stage)
        return candidates

    def score(obs: dict[str, Any]) -> tuple[int, float]:
        severity_score = {"error": 300, "warning": 200, "info": 100}.get(str(obs.get("severity")), 0)
        problem_type = str(obs.get("problem_type") or "")
        final_answer_nonempty = bool(str(final_answer).strip())
        bonus = {
            "tool_runtime_unavailable": 80,
            "missing_final_answer": 75 if not final_answer_nonempty else 20,
            "answer_quality_mismatch": 85 if final_answer_nonempty else 35,
            "helper_tool_registered_but_not_called": 70,
            "tool_failure": 60,
            "empty_result": 50,
            "budget_exhausted": 40,
            "llm_did_not_call_tool": 35,
            "no_tool_call_recorded": 35,
            "missing_data_query": 25,
            "missing_local_computation": 20,
        }.get(problem_type, 0)
        return (severity_score + bonus, float(obs.get("confidence") or 0.0))

    routing_policy = {
        "source": "deterministic_observation_extractor_v002",
        "role": "weak_context_only",
        "meta_agent_must_decide_repair_layer": True,
        "meta_agent_may_override": True,
        "note": "The analyzer selects failure evidence and candidate layers only; it does not decide the repair target.",
    }

    if not observations:
        selected_stage = "answer_validation" if answer_quality.get("available") else "workflow"
        selected_signal = "no_structured_observation"
        candidate_layers = candidate_layers_for("", selected_stage)
        return {
            "selected_stage": selected_stage,
            "selected_signal": selected_signal,
            "selected_problem_type": None,
            "selected_observation_id": None,
            "candidate_repair_layers": candidate_layers,
            "routing_policy": routing_policy,
            "meta_agent_decision_required": True,
            "selection_reason": "No structured observations were emitted.",
        }

    best = max(observations, key=score)
    stage = str(best.get("stage") or "unknown")
    problem_type = str(best.get("problem_type") or "unknown")
    evidence = best.get("evidence") if isinstance(best.get("evidence"), dict) else {}
    signal_bits = [problem_type]
    for key in ("f1", "precision", "recall", "missing_count", "extra_count", "count"):
        if key in evidence and evidence.get(key) is not None:
            signal_bits.append(f"{key}={evidence.get(key)}")
    if problem_type == "helper_tool_registered_but_not_called":
        signal_bits.append(str(helper_usage_summary.get("status")))
    selected_signal = ";".join(signal_bits)
    return {
        "selected_stage": stage,
        "selected_signal": selected_signal,
        "selected_problem_type": problem_type,
        "selected_observation_id": best.get("problem_id"),
        "candidate_repair_layers": candidate_layers_for(problem_type, stage),
        "routing_policy": routing_policy,
        "meta_agent_decision_required": True,
        "selection_reason": best.get("rationale"),
    }

def analyze_run(run_dir: Path) -> dict[str, Any]:
    summary = read_json(run_dir / "summary.json", {})
    workflow_trace = read_jsonl(run_dir / "workflow_trace.jsonl")
    llm_calls = read_jsonl(run_dir / "llm_calls.jsonl")
    tool_calls = read_jsonl(run_dir / "tool_calls.jsonl")
    final_agent = read_json(run_dir / "final_agent.json", {})
    validation_rows = read_jsonl(run_dir / "validation.jsonl")
    final_answer = read_text(run_dir / "final_answer.txt")
    self_observation_rows = read_jsonl(run_dir / "agent_self_observations.jsonl")
    answer_quality = compute_answer_quality(summary, final_answer)
    helper_usage_summary = compute_helper_usage_summary(summary, tool_calls, final_answer)
    agent_self_observation_summary = compact_agent_self_observations(self_observation_rows)

    observations: list[dict[str, Any]] = []
    tool_names = [row.get("tool_name") for row in tool_calls if row.get("tool_name")]
    tool_counter = Counter(tool_names)
    failed_tool_calls = []
    empty_tool_calls = []

    for idx, row in enumerate(tool_calls, start=1):
        result = row.get("result")
        success = result.get("success") if isinstance(result, dict) else row.get("success")
        if success is False:
            failed_tool_calls.append({"index": idx, "tool_name": row.get("tool_name"), "result": result})
        elif result_is_empty(result):
            empty_tool_calls.append({"index": idx, "tool_name": row.get("tool_name"), "result": result})

    if summary.get("run_error"):
        observations.append(observation(
            "run_error",
            stage="run_execution",
            problem_type="run_error",
            severity="error",
            evidence={"run_error": summary.get("run_error")},
            confidence=0.95,
            uncertainty="The wrapper captured an exception, but downstream cause may require log inspection.",
            suggested_targets=["runner", "tool_environment", "data_agent_wrapper"],
            rationale="The run terminated with an explicit wrapper-level error.",
        ))

    run_error_text = str(summary.get("run_error") or "")
    startup_environment_blocked = bool(
        summary.get("startup_failure")
        and ("docker" in run_error_text.lower() or summary.get("docker_diagnostics"))
    )
    if startup_environment_blocked:
        observations.append(observation(
            "docker_environment_unavailable",
            stage="environment_setup",
            problem_type="tool_runtime_unavailable",
            severity="error",
            evidence={
                "run_error": summary.get("run_error"),
                "docker_status": summary.get("docker_status"),
                "docker_diagnostics": summary.get("docker_diagnostics"),
            },
            confidence=0.95,
            uncertainty="This is a local execution environment blocker, not evidence that the data-agent reasoning or prompt failed.",
            suggested_targets=["runner", "docker_wsl_integration", "tool_environment"],
            rationale="The wrapper failed before LLM/tool workflow startup because Docker was unavailable from WSL.",
        ))

    if startup_environment_blocked:
        primary_signal = select_primary_workflow_signal(observations, answer_quality, helper_usage_summary, summary, final_answer)
        feedback_summary = {
            "schema_version": "dab_tool_agent_feedback_summary_v002",
            "created_at": utc_now(),
            "run_dir": str(run_dir),
            "status": summary.get("status"),
            "terminate_reason": summary.get("terminate_reason"),
            "final_answer_nonempty": False,
            "answer_quality": answer_quality,
            "helper_usage_summary": helper_usage_summary,
            "agent_self_observation_summary": agent_self_observation_summary,
            "selected_stage": primary_signal.get("selected_stage"),
            "selected_signal": primary_signal.get("selected_signal"),
            "selected_problem_type": primary_signal.get("selected_problem_type"),
            "recommended_repair_layer": None,
            "candidate_repair_layers": primary_signal.get("candidate_repair_layers") or [],
            "routing_policy": primary_signal.get("routing_policy") or {},
            "meta_agent_decision_required": primary_signal.get("meta_agent_decision_required"),
            "primary_signal": primary_signal,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "tool_counts": {},
            "observation_count": len(observations),
            "problem_types": dict(Counter(row["problem_type"] for row in observations)),
            "severities": dict(Counter(row["severity"] for row in observations)),
        }
        meta_agent_seed = {
            "schema_version": "dab_tool_agent_meta_agent_seed_v001",
            "created_at": utc_now(),
            "run_dir": str(run_dir),
            "zero_start_profile": "meta_agent/zero_start_data_agent_profile.md",
            "allowed_initial_tools": ["list_db", "query_db", "execute_python", "return_answer"],
            "forbidden_initial_domain_helpers": ["cpc_level_helper", "ema_helper", "patents_schema_helper", "metadata_parser_helper"],
            "feedback_summary": feedback_summary,
            "selected_stage": primary_signal.get("selected_stage"),
            "selected_signal": primary_signal.get("selected_signal"),
            "recommended_repair_layer": None,
            "candidate_repair_layers": primary_signal.get("candidate_repair_layers") or [],
            "routing_policy": primary_signal.get("routing_policy") or {},
            "meta_agent_decision_required": primary_signal.get("meta_agent_decision_required"),
            "helper_usage_summary": helper_usage_summary,
            "agent_self_observation_summary": agent_self_observation_summary,
            "answer_quality": answer_quality,
            "top_observations": observations[:8],
            "instruction": (
                "Use these observations as evidence for DataAgent evolution. Do not treat them as fixed repair decisions. "
                "Prefer generic prompt/tool/logging/analyzer improvements unless repeated evidence justifies a domain helper."
            ),
        }
        return {
            "summary": summary,
            "final_agent": final_agent,
            "feedback_summary": feedback_summary,
            "observations": observations,
            "meta_agent_seed": meta_agent_seed,
        }

    if not str(final_answer).strip():
        observations.append(observation(
            "no_final_answer",
            stage="answer_submission",
            problem_type="missing_final_answer",
            severity="warning",
            evidence={"final_answer_path": str(run_dir / "final_answer.txt"), "terminate_reason": summary.get("terminate_reason")},
            confidence=0.9,
            uncertainty="A short smoke run may intentionally stop before answer generation.",
            suggested_targets=["prompt", "tool_policy", "iteration_budget"],
            rationale="The normalized final answer is empty.",
        ))


    if answer_quality.get("available") and answer_quality.get("strict_match_passed") is False:
        observations.append(observation(
            "answer_quality_mismatch",
            stage="answer_validation",
            problem_type="answer_quality_mismatch",
            severity="error" if str(final_answer).strip() else "warning",
            evidence={
                "metric_type": answer_quality.get("metric_type"),
                "expected_count": answer_quality.get("expected_count"),
                "predicted_count": answer_quality.get("predicted_count"),
                "true_positive_count": answer_quality.get("true_positive_count"),
                "missing_count": answer_quality.get("missing_count"),
                "extra_count": answer_quality.get("extra_count"),
                "duplicate_count": answer_quality.get("duplicate_count"),
                "precision": answer_quality.get("precision"),
                "recall": answer_quality.get("recall"),
                "f1": answer_quality.get("f1"),
                "missing_codes_sample": answer_quality.get("missing_codes_sample"),
                "extra_codes_sample": answer_quality.get("extra_codes_sample"),
                "predicted_codes_sample": answer_quality.get("predicted_codes_sample"),
                "strict_match_reason": answer_quality.get("strict_match_reason"),
            },
            confidence=0.95,
            uncertainty="This compares the normalized final answer against query ground truth after the run; it is feedback for meta-agent repair, not data-agent-visible evidence.",
            suggested_targets=["answer_logic", "tool_policy", "helper_tools", "workflow_logging"],
            rationale="The final answer does not match the validator ground truth; precision/recall/F1 provide a continuous improvement signal.",
        ))

    if helper_usage_summary.get("status") == "helper_tool_registered_but_not_called":
        observations.append(observation(
            "helper_tool_registered_but_not_called",
            stage="helper_tool_usage",
            problem_type="helper_tool_registered_but_not_called",
            severity="warning",
            evidence={
                "helper_tool_name": helper_usage_summary.get("helper_tool_name"),
                "registered_helper_names": helper_usage_summary.get("registered_helper_names"),
                "tool_counts": dict(tool_counter),
                "final_answer_dependency_status": helper_usage_summary.get("final_answer_dependency_status"),
            },
            confidence=0.9,
            uncertainty="The helper was available as a workflow tool, but this does not prove the helper would have fixed the answer if called.",
            suggested_targets=["tool_schema", "prompt_policy", "helper_registry", "workflow_logging"],
            rationale="An evolved helper was registered for the DataAgent workflow but the LLM never selected the helper tool.",
        ))

    if summary.get("terminate_reason") == "max_iterations" or "max_iterations" in str(summary.get("terminate_reason")):
        observations.append(observation(
            "max_iterations_reached",
            stage="workflow_control",
            problem_type="budget_exhausted",
            severity="info",
            evidence={"llm_call_count": summary.get("llm_call_count"), "terminate_reason": summary.get("terminate_reason")},
            confidence=0.9,
            uncertainty="May be expected for smoke tests with intentionally low max_iterations.",
            suggested_targets=["iteration_budget", "prompt", "tool_policy"],
            rationale="The agent stopped because the iteration limit was reached.",
        ))

    if not llm_calls and not workflow_trace:
        observations.append(observation(
            "no_llm_activity",
            stage="llm_call",
            problem_type="no_llm_call_recorded",
            severity="error" if not summary.get("run_error") else "warning",
            evidence={"llm_calls_path": str(run_dir / "llm_calls.jsonl"), "workflow_trace_count": len(workflow_trace)},
            confidence=0.85,
            uncertainty="The run may have failed before DataAgent startup or logs may be missing.",
            suggested_targets=["runner", "model_client", "logging"],
            rationale="No LLM activity was recorded.",
        ))

    llm_without_tool = []
    for idx, row in enumerate(workflow_trace, start=1):
        if row.get("event") == "llm_call" and int(row.get("tool_call_count") or 0) == 0:
            llm_without_tool.append({"index": row.get("index", idx), "has_content": row.get("has_content")})
    if llm_without_tool:
        observations.append(observation(
            "llm_no_tool_call",
            stage="tool_selection",
            problem_type="llm_did_not_call_tool",
            severity="warning",
            evidence={"llm_without_tool": llm_without_tool[:5], "count": len(llm_without_tool)},
            confidence=0.8,
            uncertainty="Some providers may encode tool calls differently; inspect raw llm_calls if needed.",
            suggested_targets=["prompt", "model_tool_protocol", "tool_schema"],
            rationale="At least one LLM turn did not produce a tool call in the normalized workflow trace.",
        ))

    if not tool_calls:
        observations.append(observation(
            "no_tool_calls",
            stage="tool_execution",
            problem_type="no_tool_call_recorded",
            severity="warning",
            evidence={"tool_calls_path": str(run_dir / "tool_calls.jsonl")},
            confidence=0.85,
            uncertainty="May be expected if the run failed before the first tool execution.",
            suggested_targets=["prompt", "model_tool_protocol", "runner"],
            rationale="No tool calls were recorded.",
        ))

    if tool_counter and set(tool_counter) <= {"list_db"}:
        observations.append(observation(
            "only_list_db_no_query_db",
            stage="tool_selection",
            problem_type="insufficient_data_retrieval",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.75,
            uncertainty="A short exploratory run may only inspect schema; longer runs may query later.",
            suggested_targets=["prompt", "tool_policy", "iteration_budget"],
            rationale="The agent inspected databases but did not retrieve data rows.",
        ))

    if tool_counter.get("query_db", 0) == 0:
        observations.append(observation(
            "query_db_never_called",
            stage="tool_selection",
            problem_type="missing_data_query",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.7,
            uncertainty="Some tasks may be answerable without query_db, but DAB data tasks usually need evidence retrieval.",
            suggested_targets=["prompt", "tool_policy"],
            rationale="No query_db call was observed.",
        ))

    if tool_counter.get("execute_python", 0) == 0:
        observations.append(observation(
            "execute_python_never_called",
            stage="tool_selection",
            problem_type="missing_local_computation",
            severity="info",
            evidence={"tool_counts": dict(tool_counter)},
            confidence=0.65,
            uncertainty="Some simple tasks may not need Python, but complex benchmark queries often do.",
            suggested_targets=["prompt", "tool_policy", "helper_tools"],
            rationale="No execute_python call was observed.",
        ))

    if failed_tool_calls:
        observations.append(observation(
            "tool_call_failed",
            stage="tool_execution",
            problem_type="tool_failure",
            severity="error",
            evidence={"failed_tool_calls": failed_tool_calls[:5], "count": len(failed_tool_calls)},
            confidence=0.95,
            uncertainty="Failure may be caused by tool args, environment, database, or generated code.",
            suggested_targets=["tool_args", "tool_environment", "prompt", "helper_tools"],
            rationale="One or more tool calls returned success=false.",
        ))

    if empty_tool_calls:
        observations.append(observation(
            "empty_tool_result",
            stage="tool_execution",
            problem_type="empty_result",
            severity="warning",
            evidence={"empty_tool_calls": empty_tool_calls[:5], "count": len(empty_tool_calls)},
            confidence=0.75,
            uncertainty="An empty result can be correct for some queries; compare with query intent and later tool usage.",
            suggested_targets=["query_logic", "schema_grounding", "prompt"],
            rationale="One or more successful tool calls produced an empty-looking result.",
        ))

    if validation_rows:
        failed_validation = [row for row in validation_rows if row.get("success") is False or row.get("status") in {"failed", "error"}]
        if failed_validation:
            observations.append(observation(
                "validation_failed",
                stage="validation",
                problem_type="answer_validation_failed",
                severity="error",
                evidence={"failed_validation": failed_validation[:3], "count": len(failed_validation)},
                confidence=0.9,
                uncertainty="Validator output should be inspected for answer-level details.",
                suggested_targets=["answer_logic", "prompt", "helper_tools"],
                rationale="Validation artifacts indicate failure.",
            ))

    primary_signal = select_primary_workflow_signal(observations, answer_quality, helper_usage_summary, summary, final_answer)
    feedback_summary = {
        "schema_version": "dab_tool_agent_feedback_summary_v002",
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "status": summary.get("status"),
        "terminate_reason": summary.get("terminate_reason"),
        "final_answer_nonempty": bool(str(final_answer).strip()),
        "answer_quality": answer_quality,
        "helper_usage_summary": helper_usage_summary,
        "agent_self_observation_summary": agent_self_observation_summary,
        "selected_stage": primary_signal.get("selected_stage"),
        "selected_signal": primary_signal.get("selected_signal"),
        "selected_problem_type": primary_signal.get("selected_problem_type"),
        "recommended_repair_layer": None,
        "candidate_repair_layers": primary_signal.get("candidate_repair_layers") or [],
        "routing_policy": primary_signal.get("routing_policy") or {},
        "meta_agent_decision_required": primary_signal.get("meta_agent_decision_required"),
        "primary_signal": primary_signal,
        "llm_call_count": summary.get("llm_call_count") or len(llm_calls),
        "tool_call_count": summary.get("tool_call_count") or len(tool_calls),
        "tool_counts": dict(tool_counter),
        "observation_count": len(observations),
        "problem_types": dict(Counter(row["problem_type"] for row in observations)),
        "severities": dict(Counter(row["severity"] for row in observations)),
    }

    meta_agent_seed = {
        "schema_version": "dab_tool_agent_meta_agent_seed_v001",
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "zero_start_profile": "meta_agent/zero_start_data_agent_profile.md",
        "allowed_initial_tools": ["list_db", "query_db", "execute_python", "return_answer"],
        "forbidden_initial_domain_helpers": ["cpc_level_helper", "ema_helper", "patents_schema_helper", "metadata_parser_helper"],
        "feedback_summary": feedback_summary,
        "selected_stage": primary_signal.get("selected_stage"),
        "selected_signal": primary_signal.get("selected_signal"),
        "recommended_repair_layer": None,
        "candidate_repair_layers": primary_signal.get("candidate_repair_layers") or [],
        "routing_policy": primary_signal.get("routing_policy") or {},
        "meta_agent_decision_required": primary_signal.get("meta_agent_decision_required"),
        "helper_usage_summary": helper_usage_summary,
        "agent_self_observation_summary": agent_self_observation_summary,
        "answer_quality": answer_quality,
        "top_observations": observations[:8],
        "instruction": (
            "Use these observations as evidence for DataAgent evolution. Do not treat them as fixed repair decisions. "
            "Prefer generic prompt/tool/logging/analyzer improvements unless repeated evidence justifies a domain helper."
        ),
    }

    return {
        "summary": summary,
        "final_agent": final_agent,
        "feedback_summary": feedback_summary,
        "observations": observations,
        "meta_agent_seed": meta_agent_seed,
        "agent_self_observations": self_observation_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Path to logs/dab_tool_agent/<run_id>.")
    parser.add_argument("--output-dir", help="Defaults to --run-dir.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_dir
    result = analyze_run(run_dir)
    write_json(output_dir / "observations.json", result["observations"])
    write_json(output_dir / "feedback_summary.json", result["feedback_summary"])
    write_json(output_dir / "meta_agent_seed.json", result["meta_agent_seed"])
    print(json.dumps(result["feedback_summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
