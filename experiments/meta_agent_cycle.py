#!/usr/bin/env python3
"""Postprocess a meta-agent candidate into review, seed, and archive artifacts.

This script captures the glue work that previously happened in conversation:

- infer candidate lifecycle state;
- generate a human merge review package;
- generate the next repair seed;
- write/update archive candidate cards and indexes.

It deliberately does not run Qwen, apply patches, merge to main, or modify
candidate patches. Human approval remains the boundary before merge/promotion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.archive_observation import build_archive_observation
from experiments.evidence_sufficiency import assess_evidence_sufficiency


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def compact_failure_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact = {
        "schema_version": value.get("schema_version"),
        "observer_mode": value.get("observer_mode"),
        "input_policy": value.get("input_policy"),
        "primary_failure_mechanism": value.get("primary_failure_mechanism"),
        "confidence": value.get("confidence"),
        "affected_queries": value.get("affected_queries"),
        "not_to_repeat": (value.get("not_to_repeat") or [])[:8],
        "open_questions_for_meta_agent": (value.get("open_questions_for_meta_agent") or [])[:8],
        "repair_decision_policy": value.get("repair_decision_policy"),
        "source_pack": value.get("source_pack"),
        "direct_behavior_input": value.get("direct_behavior_input"),
    }
    evidence = value.get("evidence_chain")
    if isinstance(evidence, list):
        compact["evidence_chain"] = evidence[:8]
    effects = value.get("fine_grained_effect")
    if isinstance(effects, dict):
        compact["fine_grained_effect"] = effects
    return {k: v for k, v in compact.items() if v not in (None, [], {})}


def ensure_failure_observation(candidate_dir: Path, *, use_llm: bool = True, parent_agent_id: str | None = None, archive_root: Path | None = None) -> dict[str, Any]:
    """Generate candidate failure-observation artifacts if possible.

    This is observer-only evidence. It must not gate, repair, or mutate the
    candidate patch. LLM observer failures fall back to deterministic evidence
    extraction so postprocess remains robust.
    """
    child_eval = candidate_dir / "child_eval/child_eval_report.json"
    generic_child_eval = candidate_dir / "child_eval/generic_child_eval_report.json"
    if not child_eval.exists() and not generic_child_eval.exists():
        return {}
    output = candidate_dir / "failure_observation.json"
    direct_input = candidate_dir / "direct_behavior_observation_input.json"
    cmd = [
        sys.executable,
        str(ROOT / "experiments/run_direct_failure_observer_agent.py"),
        "--candidate-dir",
        str(candidate_dir),
        "--archive-root",
        str(archive_root or (ROOT / "archive")),
    ]
    parent_agent_id = parent_agent_id or os.getenv("FAILURE_OBSERVER_PARENT_AGENT_ID")
    if parent_agent_id:
        cmd.extend(["--parent-agent-id", parent_agent_id])
    if not use_llm:
        cmd.append("--no-llm")
    try:
        subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=True)
    except Exception:
        fallback_cmd = [
            sys.executable,
            str(ROOT / "experiments/run_direct_failure_observer_agent.py"),
            "--candidate-dir",
            str(candidate_dir),
            "--archive-root",
            str(ROOT / "archive"),
            "--no-llm",
        ]
        if parent_agent_id:
            fallback_cmd.extend(["--parent-agent-id", parent_agent_id])
        try:
            subprocess.run(fallback_cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
        except Exception:
            return {}
    observation = load_json(output) or {}
    if observation:
        observation.setdefault("direct_behavior_input", str(direct_input))
    return observation


def parse_numstat(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        rows.append({"path": path, "added": int(added), "deleted": int(deleted)})
    return rows


def diff_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            files.append(line.split(" b/", 1)[1])
    return sorted(set(files))


def compact_signal(signal: Any) -> dict[str, Any]:
    if isinstance(signal, dict):
        return signal
    if not isinstance(signal, str):
        return {"raw": signal}
    text = signal.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"raw": text}

def parse_code_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def compute_answer_metrics(validation_reason: str | None) -> dict[str, Any]:
    reason = validation_reason or ""
    metrics: dict[str, Any] = {
        "status": "unavailable",
        "expected_count": None,
        "predicted_count": None,
        "true_positive": None,
        "false_positive": None,
        "false_negative": None,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "jaccard": 0.0,
    }
    match = re.search(
        r"expected\s+(\d+)\s+unique\s+CPC\s+codes,\s+got\s+(\d+)\s+unique\s+CPC\s+codes",
        reason,
        flags=re.IGNORECASE,
    )
    if not match:
        return metrics

    expected_count = int(match.group(1))
    predicted_count = int(match.group(2))
    missing_match = re.search(r"Missing CPC codes \((\d+)\):\s*([^\n]*)", reason)
    extra_match = re.search(r"Extra CPC codes \((\d+)\):\s*([^\n]*)", reason)
    false_negative = int(missing_match.group(1)) if missing_match else 0
    false_positive = int(extra_match.group(1)) if extra_match else max(predicted_count - expected_count, 0)
    true_positive = max(expected_count - false_negative, 0)
    precision = true_positive / predicted_count if predicted_count else 0.0
    recall = true_positive / expected_count if expected_count else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    denom = true_positive + false_positive + false_negative
    jaccard = true_positive / denom if denom else 0.0
    return {
        "status": "computed",
        "expected_count": expected_count,
        "predicted_count": predicted_count,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "jaccard": round(jaccard, 6),
        "missing_codes": parse_code_list(missing_match.group(2) if missing_match else None),
        "extra_codes": parse_code_list(extra_match.group(2) if extra_match else None),
    }



def normalize_answer_quality_metrics(value: Any) -> dict[str, Any]:
    """Normalize analyzer-native answer_quality into archive answer_metrics keys."""
    if not isinstance(value, dict):
        return {}
    if value.get("available") is False and not any(key in value for key in ("f1", "precision", "recall")):
        return {}
    metrics = dict(value)
    if "true_positive" not in metrics and "true_positive_count" in metrics:
        metrics["true_positive"] = metrics.get("true_positive_count")
    if "false_positive" not in metrics and "extra_count" in metrics:
        metrics["false_positive"] = metrics.get("extra_count")
    if "false_negative" not in metrics and "missing_count" in metrics:
        metrics["false_negative"] = metrics.get("missing_count")
    if "status" not in metrics:
        metrics["status"] = "computed"
    return metrics


def first_answer_metrics_from_child_eval(child_eval: dict[str, Any], *, role: str) -> tuple[dict[str, Any], str | None]:
    """Extract child/parent metrics from the materialized child-eval report.

    The new DAB tool-agent loop evaluates a materialized parent workspace and
    writes both parent_answer_quality and child_answer_quality into the child
    eval report. Those metrics are the correct local baseline for this
    candidate. Archive parent-card metrics are only a fallback for legacy
    generated-solve reports that do not contain materialized-parent quality.
    """
    if not isinstance(child_eval, dict):
        return {}, None
    if role == "child":
        direct_keys = ("child_answer_metrics", "child_answer_quality", "answer_metrics", "answer_quality")
    elif role == "parent":
        direct_keys = ("parent_answer_metrics", "parent_answer_quality")
    else:
        direct_keys = ()
    for key in direct_keys:
        metrics = normalize_answer_quality_metrics(child_eval.get(key))
        if metrics:
            return metrics, f"child_eval.{key}"
    child_status = child_eval.get("child_status") if isinstance(child_eval.get("child_status"), dict) else {}
    if role == "child":
        for source_name, source in (("child_status", child_status), ("child_eval", child_eval)):
            metrics = normalize_answer_quality_metrics(source.get("answer_quality") if isinstance(source, dict) else None)
            if metrics:
                return metrics, f"{source_name}.answer_quality"
    return {}, None

def parent_answer_metrics(archive_root: Path | None, parent_agent_id: str | None, case_id: str = "PATENTS_query1") -> dict[str, Any]:
    if not archive_root or not parent_agent_id:
        return {}
    card = find_agent_card(archive_root, parent_agent_id)
    if not isinstance(card, dict):
        return {}
    evals = card.get("evals") if isinstance(card.get("evals"), dict) else {}
    case_eval = evals.get(case_id) if isinstance(evals.get(case_id), dict) else None
    if case_eval is None and evals:
        case_eval = next((item for item in evals.values() if isinstance(item, dict) and isinstance(item.get("answer_metrics"), dict)), None)
    metrics = (case_eval or {}).get("answer_metrics") if isinstance(case_eval, dict) else None
    return metrics if isinstance(metrics, dict) else {}


def _int_metric(mapping: dict[str, Any], key: str, default: int = 0) -> int:
    value = mapping.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_multi_query_child_eval(child_eval: dict[str, Any]) -> dict[str, Any]:
    """Extract non-template multi-query improvement evidence from child eval.

    The archive selector should not only reward final all-query success. For
    multi-query evolution, a candidate can be a useful next parent when it turns
    empty answers into concrete answers, removes tool failures, or makes
    registered helper tools actually participate in answer generation, even if
    one strict validator still reports a near miss. This keeps the gate from
    rejecting genuine answer-path progress while still leaving merge eligibility
    tied to strict validation.
    """
    summary = child_eval.get("child_multi_query_summary")
    if not isinstance(summary, dict):
        summary = {}
    delta = child_eval.get("parent_child_delta")
    if not isinstance(delta, dict):
        delta = {}

    per_query = summary.get("per_query_feedback")
    if not isinstance(per_query, list):
        per_query = []

    strict_total = 0
    strict_pass_count = 0
    strict_failures: list[dict[str, Any]] = []
    near_miss_count = 0
    for item in per_query:
        if not isinstance(item, dict):
            continue
        aq = item.get("answer_quality")
        if not isinstance(aq, dict):
            continue
        if "strict_match_passed" not in aq:
            continue
        strict_total += 1
        passed = bool(aq.get("strict_match_passed"))
        if passed:
            strict_pass_count += 1
            continue
        reason = str(aq.get("strict_match_reason") or aq.get("reason") or "")
        strict_failures.append(
            {
                "query_id": item.get("query_id"),
                "domain": item.get("domain"),
                "selected_stage": item.get("selected_stage"),
                "selected_signal": item.get("selected_signal"),
                "reason": reason,
            }
        )
        missing_count = aq.get("missing_count")
        extra_count = aq.get("extra_count")
        f1_value = aq.get("f1")
        has_full_delta = isinstance(missing_count, (int, float)) and isinstance(extra_count, (int, float))
        full_delta_near_miss = bool(
            has_full_delta
            and bool(item.get("final_answer_nonempty"))
            and (
                int(missing_count) + int(extra_count) <= 5
                or (isinstance(f1_value, (int, float)) and float(f1_value) >= 0.90 and int(missing_count) <= 5)
            )
        )
        lowered = reason.lower()
        strict_reason_near_miss = bool(
            not has_full_delta
            and "missing" in lowered
            and "," not in reason
            and ";" not in reason
            and _int_metric(item, "tool_call_count", 0) > 0
            and bool(item.get("final_answer_nonempty"))
        )
        if full_delta_near_miss or strict_reason_near_miss:
            near_miss_count += 1

    child_failure_gates = child_eval.get("child_failure_gates")
    if not isinstance(child_failure_gates, list):
        child_failure_gates = []

    query_count = _int_metric(child_eval, "query_count", _int_metric(summary, "query_count", 0))
    child_final_answer_nonempty_count = _int_metric(
        delta, "child_final_answer_nonempty_count", _int_metric(child_eval, "final_answer_nonempty_count", 0)
    )
    answer_parent_gate_blocked_empty_child_answer = bool(
        query_count > 0
        and child_final_answer_nonempty_count <= 0
        and strict_pass_count <= 0
    )

    metrics = {
        "available": bool(summary or delta),
        "query_count": query_count,
        "strict_validation_total": strict_total,
        "strict_validation_pass_count": strict_pass_count,
        "strict_validation_failed_count": max(0, strict_total - strict_pass_count),
        "strict_validation_pass_ratio": round(strict_pass_count / strict_total, 6) if strict_total else None,
        "strict_validation_failures": strict_failures,
        "strict_near_miss_count": near_miss_count,
        "child_final_answer_nonempty_count": child_final_answer_nonempty_count,
        "child_has_nonempty_answer": child_final_answer_nonempty_count > 0,
        "answer_parent_gate_blocked_empty_child_answer": answer_parent_gate_blocked_empty_child_answer,
        "delta_final_answer_nonempty_count": _int_metric(delta, "delta_final_answer_nonempty_count", 0),
        "delta_successful_run_count": _int_metric(delta, "delta_successful_run_count", 0),
        "delta_tool_failure_count": _int_metric(delta, "delta_tool_failure_count", 0),
        "delta_helper_registered_but_not_called_count": _int_metric(
            delta, "delta_helper_registered_but_not_called_count", 0
        ),
        "reduced_tool_failures": bool(delta.get("reduced_tool_failures")),
        "reduced_helper_registered_but_not_called": bool(delta.get("reduced_helper_registered_but_not_called")),
        "improved_answer_count": bool(delta.get("improved_answer_count")),
        "improved_success_count": bool(delta.get("improved_success_count")),
        "severe_regression": bool(delta.get("severe_regression")),
        "child_failure_gates": child_failure_gates,
    }
    return metrics


def score_multi_query_progress(metrics: dict[str, Any]) -> tuple[float, list[str]]:
    if not metrics.get("available") or metrics.get("severe_regression"):
        return 0.0, []
    reasons: list[str] = []
    if metrics.get("answer_parent_gate_blocked_empty_child_answer"):
        return 0.0, ["blocked_empty_child_answers_no_parent_reward"]
    reward = 0.0
    if _int_metric(metrics, "delta_final_answer_nonempty_count", 0) > 0:
        reward += 0.22
        reasons.append("increased_final_answer_nonempty_count")
    if _int_metric(metrics, "delta_successful_run_count", 0) > 0:
        reward += 0.12
        reasons.append("increased_successful_run_count")
    if _int_metric(metrics, "delta_tool_failure_count", 0) < 0:
        reward += 0.18
        reasons.append("reduced_tool_failures")
    if _int_metric(metrics, "delta_helper_registered_but_not_called_count", 0) < 0:
        reward += 0.18
        reasons.append("converted_registered_helpers_into_called_helpers")
    pass_ratio = metrics.get("strict_validation_pass_ratio")
    if isinstance(pass_ratio, (int, float)) and pass_ratio > 0:
        reward += min(0.25, 0.25 * float(pass_ratio))
        reasons.append("some_strict_validators_passed")
    if _int_metric(metrics, "strict_near_miss_count", 0) > 0:
        reward += 0.08
        reasons.append("strict_validator_near_miss_with_nonempty_answer")
    if metrics.get("child_failure_gates"):
        reward = min(reward, 0.30)
        reasons.append("capped_due_to_child_failure_gates")
    return round(min(0.90, reward), 6), reasons


def compute_evolution_assessment(
    candidate_type: str,
    child_eval: dict[str, Any],
    *,
    archive_root: Path | None = None,
    parent_agent_id: str | None = None,
    case_id: str = "PATENTS_query1",
) -> dict[str, Any]:
    child_final_status = child_eval.get("final_status") or child_eval.get("status")
    if child_final_status == "infra_failed_llm_connection":
        return {
            "evolution_status": "infra_failed_llm_connection",
            "evolution_parent_eligible": False,
            "reward": 0.0,
            "answer_metrics": {"status": "unavailable_infra_failed_llm_connection"},
            "parent_comparison_metrics": {
                "parent_agent_id": parent_agent_id,
                "parent_answer_metrics": parent_answer_metrics(archive_root, parent_agent_id, case_id),
                "parent_metrics_source": "archive_parent_card",
                "child_answer_metrics_source": "unavailable_infra_failed_llm_connection",
                "comparison_baseline": "not_comparable_infra_failure",
                "child_f1": None,
                "parent_f1": None,
                "delta_f1": None,
                "relative_improved": False,
                "severe_regression": False,
            },
            "execution_metrics": {
                "child_exit_code": child_eval.get("child_run_exit_code"),
                "child_execution_success": False,
                "child_has_answer_like_output": False,
            },
            "signal_metrics": {
                "useful_new_signal": False,
                "child_selected_stage": child_eval.get("child_selected_stage"),
                "child_selected_signal": child_eval.get("child_selected_signal"),
            },
            "merge_eligible": False,
            "selection_rationale": "Child eval was skipped because the DataAgent LLM preflight failed; candidate answer quality is not comparable and should not be treated as a semantic regression.",
        }
    child_status = child_eval.get("child_status") or {}
    validation_reason = child_status.get("validation_reason") or child_eval.get("child_validation_reason")
    answer_metrics, child_metrics_source = first_answer_metrics_from_child_eval(child_eval, role="child")
    if not answer_metrics:
        answer_metrics = compute_answer_metrics(validation_reason)
        child_metrics_source = "parsed_child_validation_reason"
    child_passed = bool(child_status.get("passed_original_dab_validation") or child_eval.get("child_passed"))
    child_exit_code = child_eval.get("child_run_exit_code")
    predicted_count = answer_metrics.get("predicted_count") or 0
    execution_success = child_exit_code == 0
    has_answer_like_output = predicted_count > 0
    useful_new_signal = bool(child_status.get("selected_stage") or child_eval.get("child_selected_stage"))
    multi_query_metrics = summarize_multi_query_child_eval(child_eval)
    multi_query_reward, multi_query_reward_reasons = score_multi_query_progress(multi_query_metrics)
    all_strict_validators_passed = bool(
        multi_query_metrics.get("strict_validation_total")
        and multi_query_metrics.get("strict_validation_pass_count") == multi_query_metrics.get("strict_validation_total")
    )

    answer_f1 = float(answer_metrics.get("f1") or 0.0)
    materialized_parent_metrics, materialized_parent_metrics_source = first_answer_metrics_from_child_eval(child_eval, role="parent")
    archive_parent_metrics = parent_answer_metrics(archive_root, parent_agent_id, case_id)
    archive_parent_metrics_source = "archive_parent_card" if archive_parent_metrics else None

    parent_metrics = materialized_parent_metrics or archive_parent_metrics
    parent_metrics_source = materialized_parent_metrics_source or archive_parent_metrics_source
    has_parent_answer_metrics = parent_metrics.get("f1") is not None
    parent_f1 = float(parent_metrics.get("f1") or 0.0) if has_parent_answer_metrics else None
    delta_f1 = round(answer_f1 - parent_f1, 6) if parent_f1 is not None else None

    has_archive_parent_metrics = archive_parent_metrics.get("f1") is not None
    archive_parent_f1 = float(archive_parent_metrics.get("f1") or 0.0) if has_archive_parent_metrics else None
    delta_f1_vs_archive_parent = round(answer_f1 - archive_parent_f1, 6) if archive_parent_f1 is not None else None
    materialized_parent_f1 = (
        float(materialized_parent_metrics.get("f1") or 0.0)
        if materialized_parent_metrics.get("f1") is not None
        else None
    )
    delta_f1_vs_materialized_parent = (
        round(answer_f1 - materialized_parent_f1, 6)
        if materialized_parent_f1 is not None
        else None
    )
    archive_parent_tolerance = 1e-6
    archive_parent_regression = bool(
        candidate_type == "data_agent_repair"
        and archive_parent_f1 is not None
        and not multi_query_metrics.get("available")
        and answer_f1 < archive_parent_f1 - archive_parent_tolerance
    )
    materialized_parent_reproduction_gap = bool(
        archive_parent_f1 is not None
        and materialized_parent_f1 is not None
        and materialized_parent_f1 < archive_parent_f1 - archive_parent_tolerance
    )
    restored_to_archive_parent_level = bool(
        candidate_type == "data_agent_repair"
        and materialized_parent_reproduction_gap
        and answer_f1 >= archive_parent_f1 - archive_parent_tolerance
        and answer_f1 <= archive_parent_f1 + archive_parent_tolerance
    )

    relative_improved = bool(child_passed or parent_f1 is None or answer_f1 > parent_f1 + 1e-6)
    parent_predicted_count = int(parent_metrics.get("predicted_count") or 0) if parent_metrics else 0
    severe_regression = bool(
        candidate_type == "data_agent_repair"
        and parent_f1 is not None
        and parent_f1 > 0
        and not multi_query_metrics.get("available")
        and (
            answer_f1 <= 0
            or (parent_predicted_count > 0 and predicted_count > max(parent_predicted_count * 5, parent_predicted_count + 100))
        )
    )
    severe_regression = bool(severe_regression or multi_query_metrics.get("severe_regression"))

    if child_passed or all_strict_validators_passed:
        evolution_status = "passed"
        eligible = True
    elif severe_regression:
        evolution_status = "failed_severe_child_regression"
        eligible = False
    elif archive_parent_regression:
        evolution_status = "failed_archive_parent_regression"
        eligible = False
    elif multi_query_metrics.get("answer_parent_gate_blocked_empty_child_answer"):
        evolution_status = "failed_empty_child_answers_not_parent_eligible"
        eligible = False
    elif (
        candidate_type == "data_agent_repair"
        and multi_query_reward > 0
        and not multi_query_metrics.get("child_failure_gates")
    ):
        evolution_status = "partial_multi_query_improvement"
        eligible = True
    elif candidate_type == "data_agent_repair" and multi_query_reward > 0:
        evolution_status = "failed_multi_query_improvement_capped_by_child_gates"
        eligible = False
    elif restored_to_archive_parent_level:
        evolution_status = "stabilization_or_reproduction_repair"
        eligible = False
    elif candidate_type == "data_agent_repair" and answer_f1 > 0 and relative_improved:
        evolution_status = "improved_but_failed"
        eligible = True
    elif candidate_type == "data_agent_repair" and answer_f1 > 0 and delta_f1 is not None and delta_f1 < -1e-6:
        evolution_status = "failed_negative_delta"
        eligible = False
    elif candidate_type == "data_agent_repair" and answer_f1 > 0 and not relative_improved:
        evolution_status = "failed_no_relative_answer_improvement"
        eligible = False
    else:
        evolution_status = "failed_no_measured_answer_improvement"
        eligible = False

    reward = 1.0 if child_passed else 0.0
    if evolution_status == "improved_but_failed":
        reward = round(min(0.85, 0.20 + 0.70 * answer_f1 + (0.05 if execution_success else 0.0)), 6)
    elif evolution_status == "stabilization_or_reproduction_repair":
        reward = round(min(0.35, 0.10 + 0.20 * answer_f1 + (0.05 if execution_success else 0.0)), 6)
    elif evolution_status == "partial_multi_query_improvement":
        reward = multi_query_reward
    elif evolution_status == "failed_multi_query_improvement_capped_by_child_gates":
        reward = multi_query_reward

    if child_passed or all_strict_validators_passed:
        rationale = "Strict validation passed."
    elif evolution_status == "stabilization_or_reproduction_repair":
        rationale = "Candidate recovered a degraded materialized-parent run back to the selected archive parent's recorded quality, but did not exceed the archive parent best; keep as evidence/stability repair, not as a new answer parent."
    elif evolution_status == "partial_multi_query_improvement":
        rationale = "Candidate remains non-mergeable, but multi-query child eval shows answer-path progress: " + ", ".join(multi_query_reward_reasons)
    elif evolution_status == "failed_multi_query_improvement_capped_by_child_gates":
        rationale = "Candidate has some multi-query improvement evidence, but child failure gates prevent it from becoming a parent."
    elif evolution_status == "failed_empty_child_answers_not_parent_eligible":
        rationale = "Candidate executed multi-query child runs but produced no non-empty final answers and no strict validation pass; keep it as failure evidence, not as an answer parent."
    elif eligible:
        rationale = "Candidate remains non-mergeable, but child answer improved relative to both the materialized parent baseline and the selected archive parent baseline."
    elif evolution_status == "failed_severe_child_regression":
        rationale = "Candidate caused a severe child answer regression relative to the selected parent baseline, so it is not parent-eligible."
    elif evolution_status == "failed_archive_parent_regression":
        rationale = "Candidate improved or recovered relative to the materialized parent run but is below the selected archive parent's recorded best F1, so it must not replace the archive parent."
    elif evolution_status == "failed_negative_delta":
        rationale = "Candidate reduced answer F1 relative to the selected parent baseline, so it is not parent-eligible."
    elif evolution_status == "failed_no_relative_answer_improvement":
        rationale = "Candidate has non-zero answer overlap but did not improve relative to the selected parent baseline, so it is not parent-eligible."
    else:
        rationale = "Candidate did not produce measurable answer overlap."

    return {
        "evolution_status": evolution_status,
        "evolution_parent_eligible": eligible,
        "reward": reward,
        "answer_metrics": answer_metrics,
        "multi_query_metrics": {
            **multi_query_metrics,
            "reward_reasons": multi_query_reward_reasons,
        },
        "parent_comparison_metrics": {
            "parent_agent_id": parent_agent_id,
            "parent_answer_metrics": parent_metrics,
            "parent_metrics_source": parent_metrics_source,
            "materialized_parent_answer_metrics": materialized_parent_metrics,
            "materialized_parent_metrics_source": materialized_parent_metrics_source,
            "archive_parent_answer_metrics": archive_parent_metrics,
            "archive_parent_metrics_source": archive_parent_metrics_source,
            "child_answer_metrics_source": child_metrics_source,
            "comparison_baseline": "dual_materialized_and_archive_parent" if materialized_parent_metrics and archive_parent_metrics else ("materialized_parent_child_eval" if parent_metrics_source and parent_metrics_source.startswith("child_eval.") else "archive_parent_fallback"),
            "child_f1": answer_f1,
            "parent_f1": parent_f1,
            "archive_parent_f1": archive_parent_f1,
            "materialized_parent_f1": materialized_parent_f1,
            "delta_f1": delta_f1,
            "delta_f1_vs_archive_parent": delta_f1_vs_archive_parent,
            "delta_f1_vs_materialized_parent": delta_f1_vs_materialized_parent,
            "relative_improved": relative_improved,
            "archive_parent_regression": archive_parent_regression,
            "materialized_parent_reproduction_gap": materialized_parent_reproduction_gap,
            "restored_to_archive_parent_level": restored_to_archive_parent_level,
            "severe_regression": severe_regression,
        },
        "execution_metrics": {
            "child_exit_code": child_exit_code,
            "child_execution_success": execution_success,
            "child_has_answer_like_output": has_answer_like_output,
        },
        "signal_metrics": {
            "useful_new_signal": useful_new_signal,
            "child_selected_stage": child_status.get("selected_stage") or child_eval.get("child_selected_stage"),
            "child_selected_signal": child_status.get("selected_signal") or child_eval.get("child_selected_signal"),
        },
        "merge_eligible": child_passed,
        "selection_rationale": rationale,
    }

def infer_state(candidate_dir: Path) -> dict[str, Any]:
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    promotion = load_json(candidate_dir / "promotion_decision.json") or {}
    merge_validation = load_json(candidate_dir / "merge_validation/merge_validation_summary.json") or {}

    status = (
        promotion.get("status")
        or review.get("post_child_eval_review_status")
        or child_eval.get("final_status")
        or manifest.get("status")
        or "unknown"
    )
    if merge_validation.get("status") == "passed" and status == "post_child_eval_review_passed":
        status = "ready_for_or_completed_branch_merge_validation"

    state = {
        "candidate_id": candidate_dir.name,
        "status": status,
        "manifest_status": manifest.get("status"),
        "child_eval_status": child_eval.get("final_status"),
        "post_child_eval_review_status": review.get("post_child_eval_review_status"),
        "promotion_decision_status": promotion.get("status"),
        "merge_validation_status": merge_validation.get("status"),
        "merge_recommendation": (
            promotion.get("merge_recommendation")
            or review.get("merge_recommendation")
            or "unknown"
        ),
        "lifecycle": [
            step
            for step in [
                manifest.get("status"),
                child_eval.get("final_status"),
                review.get("post_child_eval_review_status"),
                promotion.get("status"),
                merge_validation.get("status") and f"merge_validation_{merge_validation.get('status')}",
            ]
            if step
        ],
    }
    write_json(candidate_dir / "candidate_state.json", state)
    return state


def build_patch_review(candidate_dir: Path) -> dict[str, Any]:
    manifest = load_json(candidate_dir / "manifest.json") or {}
    patch_text = read_text(candidate_dir / "patch.diff")
    numstat_rows = parse_numstat(read_text(candidate_dir / "patch_numstat.txt"))
    total = sum(row["added"] + row["deleted"] for row in numstat_rows)
    files = diff_files(patch_text)
    return {
        "diff_files": files,
        "manifest_project_changed_files": manifest.get("project_changed_files") or [],
        "patch_numstat": numstat_rows,
        "total_changed_lines": total,
        "manifest_total_changed_lines": manifest.get("total_changed_lines"),
        "control_files_in_project_diff": [
            path
            for path in files
            if path not in {
                "adapters/feedback/common_trace_checks.py",
                "adapters/feedback/dab_patents_checks.py",
            }
        ],
    }


def generate_merge_review(candidate_dir: Path, state: dict[str, Any], scope_note: str) -> Path:
    patch_review = build_patch_review(candidate_dir)
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    merge_validation = load_json(candidate_dir / "merge_validation/merge_validation_summary.json") or {}
    child_status = child_eval.get("child_status") or {}
    parent_status = child_eval.get("parent_status") or {}

    lines = [
        f"# Merge review package: {candidate_dir.name}",
        "",
        "Status: ready for human review; do not auto-merge.",
        "",
        f"Scope: {scope_note}",
        "",
        "## Patch summary",
        "",
        f"- Candidate status: `{state['status']}`",
        f"- Manifest status: `{manifest.get('status')}`",
        f"- Changed files: `{', '.join(patch_review['diff_files'])}`",
        f"- Total changed lines: `{patch_review['total_changed_lines']}`",
        f"- Manifest total changed lines: `{patch_review['manifest_total_changed_lines']}`",
        f"- Control files in project diff: `{patch_review['control_files_in_project_diff']}`",
        "",
        "## Validation",
        "",
        f"- validation_exit_code: `{manifest.get('validation_exit_code')}`",
        f"- patch_spec_status: `{manifest.get('patch_spec_status')}`",
        f"- deterministic_apply_status: `{manifest.get('deterministic_apply_status')}`",
        f"- post_apply_gate_status: `{manifest.get('post_apply_gate_status')}`",
        "",
        "## Child eval",
        "",
        f"- child_eval_final_status: `{child_eval.get('final_status')}`",
        f"- parent_status: `{parent_status.get('status')}`",
        f"- child_status: `{child_status.get('status')}`",
        f"- parent selected_stage: `{parent_status.get('selected_stage')}`",
        f"- child selected_stage: `{child_status.get('selected_stage')}`",
        f"- child selected_signal: `{child_status.get('selected_signal')}`",
        f"- original DAB validation still failed: `{child_status.get('passed_original_dab_validation') is False}`",
        "",
        "## Small regression",
        "",
        f"- post_child_eval_review_status: `{review.get('post_child_eval_review_status')}`",
        f"- regression_status: `{(review.get('regression_results') or {}).get('status')}`",
        f"- public_api_preservation_status: `{(review.get('public_api_preservation_status') or {}).get('status')}`",
        f"- merge_recommendation: `{review.get('merge_recommendation')}`",
        "",
        "## Merge validation",
        "",
        f"- merge_validation_status: `{merge_validation.get('status')}`",
        f"- updated selected_stage: `{merge_validation.get('selected_stage')}`",
        f"- updated selected_signal: `{merge_validation.get('selected_signal')}`",
        "",
        "## Risk and rollback",
        "",
        "- Treat as feedback/error-analysis infrastructure repair only.",
        "- Do not count this as solving the original PATENTS answer-generation failure.",
        "- Roll back an uncommitted apply with `git apply -R <candidate>/patch.diff`.",
        "- Roll back a committed merge with `git revert <commit>`.",
        "",
        "## Next step",
        "",
        "After human confirmation, use the generated next repair seed for the data-agent repair iteration.",
        "",
    ]
    out = candidate_dir / "merge_review_package.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def extract_child_runtime_repair_evidence(child_eval: dict[str, Any]) -> dict[str, Any]:
    """Extract compact, actionable evidence from the child run.

    The primary-signal text is intentionally small and sometimes too abstract
    for the next meta-agent round.  This helper keeps the loop autonomous by
    carrying forward concrete runtime facts from the child trace/code without
    hand-editing the next candidate patch.
    """
    child_run_dir_raw = child_eval.get("child_run_dir")
    if not child_run_dir_raw:
        return {}
    child_run_dir = Path(child_run_dir_raw)
    evidence: dict[str, Any] = {"child_run_dir": str(child_run_dir)}
    child_status = child_eval.get("child_status") or {}
    persisted_signal_raw = str(child_status.get("selected_signal") or child_eval.get("child_selected_signal") or "")
    persisted_reason = str(child_status.get("validation_reason") or child_eval.get("child_validation_reason") or "")
    persisted_text = "\n".join(part for part in (persisted_signal_raw, persisted_reason) if part)
    if persisted_text:
        evidence["persisted_child_signal_excerpt"] = persisted_text[:2000]
        if "Data block not found in CPC definition SQL" in persisted_text or "data_block_not_found" in persisted_text:
            evidence.setdefault("generated_code_findings", []).append(
                {
                    "finding": "generated parser failed to locate COPY data block terminator",
                    "risk": "searching for a fragile literal terminator can fail; generated code should scan lines after the COPY header until a line whose stripped content is exactly backslash-dot",
                }
            )
        if "Malformed header line in CPC definition SQL" in persisted_text or "cpc_definition_header_malformed" in persisted_text:
            evidence.setdefault("generated_code_findings", []).append(
                {
                    "finding": "generated parser treated a CPCDefinition data row as the COPY header",
                    "risk": "COPY header columns are in parentheses on the same COPY command line; the first following line is data, not header metadata",
                }
            )
        if "Failed to parse column names from COPY command" in persisted_text or "Missing required columns" in persisted_text:
            evidence.setdefault("generated_code_findings", []).append(
                {
                    "finding": "generated parser failed to handle CPCDefinition COPY header column names",
                    "risk": "quoted column names such as titleFull with surrounding double quotes may not be stripped before required-column checks, so metadata parsing stops before CPC mapping",
                }
            )

    trace_path = child_run_dir / "stage_trace.json"
    if trace_path.exists():
        trace = load_json(trace_path) or []
        if isinstance(trace, list):
            selected_events: list[dict[str, Any]] = []
            for event in trace:
                if not isinstance(event, dict):
                    continue
                name = event.get("event")
                if name in {
                    "cpc_definition_data_block_not_found",
                    "cpc_definition_header_malformed",
                    "cpc_hierarchy_built",
                    "cpc_level5_symbol_count",
                    "cpc_level5_mapping_summary",
                    "cpc_mapping_summary",
                    "unmapped_cpc_codes_sample",
                    "granularity_mapping_fallback_used",
                    "no_years_with_level5_data",
                    "no_yearly_data_for_ema",
                    "no_years_found",
                    "final_answer_written",
                }:
                    selected_events.append(
                        {
                            "event": name,
                            "trigger": event.get("trigger"),
                            "severity": event.get("severity"),
                            "purpose": event.get("purpose"),
                            "outputs": event.get("outputs"),
                            "inputs": event.get("inputs"),
                        }
                    )
            if selected_events:
                evidence["runtime_trace_events"] = selected_events[:8]

    generated_path = child_run_dir / "generated_solve.py"
    if generated_path.exists():
        text = generated_path.read_text(encoding="utf-8", errors="replace")
        findings: list[dict[str, Any]] = []
        if re.search(r"re\.sub\([^\n]*0\+\$", text) or "Strip trailing zeros" in text:
            findings.append(
                {
                    "finding": "generated normalizer strips trailing zeros from CPC codes",
                    "risk": "can corrupt valid metadata symbols such as C01B33/00 into C01B33 before lookup",
                }
            )
        if "code.replace('.', '/')" in text:
            findings.append(
                {
                    "finding": "generated normalizer rewrites dot separators to slashes without metadata confirmation",
                    "risk": "can create symbols not present in CPCDefinition metadata",
                }
            )
        if "all_years = sorted(level5_to_years.keys())" in text:
            findings.append(
                {
                    "finding": "generated EMA loop uses CPC-code keys as the year axis",
                    "risk": "after mapping is repaired, EMA may still be computed over codes rather than years",
                }
            )
        if "json.loads(parents_str)" in text and "replace('\\n'" not in text and 'replace("\\n"' not in text:
            findings.append(
                {
                    "finding": "generated parser attempts json.loads(parents_str) without decoding escaped COPY newlines",
                    "risk": "CPCDefinition parents may parse as empty for all symbols, preventing traversal from deeper CPC codes to level 5 ancestors",
                }
            )
        if findings:
            evidence["generated_code_findings"] = findings

    result_path = child_run_dir / "result.json"
    if result_path.exists():
        result = load_json(result_path) or {}
        reason = str(result.get("validation_reason") or "")
        if reason:
            evidence["validation_reason_excerpt"] = reason[:2000]
        if "Failed to parse column names from COPY command" in reason or "Missing required columns" in reason:
            evidence.setdefault("generated_code_findings", []).append(
                {
                    "finding": "generated parser failed to handle CPCDefinition COPY header column names",
                    "risk": "quoted column names such as titleFull with surrounding double quotes may not be stripped before required-column checks, so metadata parsing stops before CPC mapping",
                }
            )
        if "Data block not found in CPC definition SQL" in reason:
            evidence.setdefault("generated_code_findings", []).append(
                {
                    "finding": "generated parser failed to locate COPY data block terminator",
                    "risk": "searching for a fragile literal terminator can fail; generated code should scan lines after the COPY header until a line whose stripped content is exactly backslash-dot",
                }
            )

    if evidence.get("runtime_trace_events") or evidence.get("generated_code_findings") or evidence.get("validation_reason_excerpt"):
        evidence["next_prompt_requirements"] = [
            "Generated code should extract CPCDefinition COPY header columns from the same COPY command line inside parentheses; the line after the COPY command is the first data row, not the header.",
            "Generated code should locate the CPCDefinition COPY data block by scanning lines after the COPY header until line.strip() equals backslash-dot, rather than relying on one fragile whole-file substring.",
            "Generated code should strip surrounding double quotes from CPCDefinition COPY header column names before required-column checks, so quoted titleFull matches titleFull.",
            "Generated code should parse CPCDefinition `parents` robustly; if the field contains escaped COPY newlines such as `\\n`, decode them before JSON/list parsing and verify `symbols_with_parents > 0`.",
            "Generated code should try exact raw CPC code lookup in CPCDefinition `symbol` before any normalization.",
            "Do not strip trailing classification zeros or slash groups unless the transformed symbol is confirmed in metadata.",
            "If normalization is attempted, compare coverage before/after and log sample raw->matched mappings.",
            "Map target level through CPCDefinition `level` and `parents`; do not infer level from slash count or string shape.",
            "Build the EMA year axis from publication filing years, not from CPC-code dictionary keys.",
            "Treat zero mapped CPC coverage as a hard runtime error with evidence rather than silently writing an empty answer.",
        ]
    return evidence


def generate_next_seed(candidate_dir: Path, case_id: str, recommended_goal: str) -> tuple[Path, Path]:
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    child_status = child_eval.get("child_status") or {}
    parent_run_id = child_eval.get("parent_run_id")
    selected_signal = compact_signal(child_status.get("selected_signal"))
    selected_stage = child_status.get("selected_stage")
    runtime_repair_evidence = extract_child_runtime_repair_evidence(child_eval)
    failure_observation = compact_failure_observation(load_json(candidate_dir / "failure_observation.json") or {})
    evidence_sufficiency = assess_evidence_sufficiency(
        seed={},
        child_eval=child_eval,
        failure_observation=failure_observation,
    )
    child_batch = child_eval.get("batch") if isinstance(child_eval.get("batch"), dict) else {}
    seed = {
        "seed_id": f"next_data_agent_repair_seed_from_{candidate_dir.name}",
        "created_for": "iter004_data_agent_repair",
        "source_candidate": candidate_dir.name,
        "source_candidate_dir": str(candidate_dir),
        "case": {
            "case_id": case_id,
            "parent_run_id": parent_run_id,
            "parent_run_dir": child_eval.get("parent_run_dir") or child_eval.get("parent_run"),
        },
        "selected_stage": selected_stage,
        "selected_signal": "no_years_found" if selected_signal.get("event") == "no_years_found" else child_status.get("selected_signal"),
        "selected_signal_evidence": selected_signal,
        "runtime_repair_evidence": runtime_repair_evidence,
        "failure_observation": failure_observation,
        "failure_observation_path": str(candidate_dir / "failure_observation.json") if failure_observation else None,
        "evidence_sufficiency": evidence_sufficiency,
        "feedback_evolution_opportunity": evidence_sufficiency.get("feedback_evolution_opportunity"),
        "recommended_evolution_target": evidence_sufficiency.get("recommended_evolution_target"),
        "recommended_observer_subtarget": evidence_sufficiency.get("recommended_observer_subtarget"),
        "batch": child_batch,
        "batch_id": child_batch.get("batch_id") if isinstance(child_batch, dict) else None,
        "original_dab_validation": {
            "passed": child_status.get("passed_original_dab_validation"),
            "validation_reason": child_status.get("validation_reason"),
            "still_failed_after_feedback_repair": child_status.get("passed_original_dab_validation") is False,
        },
        "recommended_iter004_goal": recommended_goal,
        "recommended_constraints": [
            "Do not modify feedback analyzer unless a new analyzer bug is independently proven.",
            "Use structured patch_spec protocol; Qwen should not freely edit source.",
            "Run child eval and small regression before any merge.",
            "Archive every candidate attempt.",
        ],
        "recommended_focus_areas": [
            "CPC definition metadata grounding",
            "CPC definition/group mapping logic",
            "filing_date year extraction",
            "EMA/best-year calculation path",
            "final_answer non-empty contract",
        ],
    }
    json_path = candidate_dir / "next_data_agent_repair_seed.json"
    md_path = candidate_dir / "next_data_agent_repair_seed.md"
    write_json(json_path, seed)
    md = [
        "# next_data_agent_repair_seed",
        "",
        f"- source_candidate: `{candidate_dir.name}`",
        f"- case_id: `{case_id}`",
        f"- selected_stage: `{seed['selected_stage']}`",
        f"- selected_signal: `{seed['selected_signal']}`",
        f"- original_dab_validation_passed: `{seed['original_dab_validation']['passed']}`",
        f"- validation_reason: `{seed['original_dab_validation']['validation_reason']}`",
        "",
        "## Recommended goal",
        "",
        recommended_goal,
        "",
        "## Focus areas",
        "",
    ]
    md.extend(f"- {item}" for item in seed["recommended_focus_areas"])
    if runtime_repair_evidence:
        md.extend(
            [
                "",
                "## Runtime repair evidence",
                "",
                "```json",
                json.dumps(runtime_repair_evidence, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    if evidence_sufficiency:
        md.extend(
            [
                "",
                "## Evidence sufficiency",
                "",
                "```json",
                json.dumps(evidence_sufficiency, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    if failure_observation:
        md.extend(
            [
                "",
                "## Failure observation",
                "",
                "```json",
                json.dumps(failure_observation, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return json_path, md_path


def upsert_jsonl(path: Path, key: str, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    replaced = False
    for index, existing in enumerate(rows):
        if existing.get(key) == row.get(key):
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in rows) + "\n", encoding="utf-8")




def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def upsert_selection_score(archive_root: Path, row: dict[str, Any]) -> None:
    path = archive_root / "indexes/selection_scores.json"
    data = load_json(path) or {"version": 1, "selection_policy": "manual_score_mvp", "scores": []}
    scores = data.setdefault("scores", [])
    replaced = False
    for index, existing in enumerate(scores):
        if existing.get("arm_id") == row.get("arm_id"):
            scores[index] = row
            replaced = True
            break
    if not replaced:
        scores.append(row)
    scores.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    write_json(path, data)


def find_agent_card(archive_root: Path, agent_id: str) -> dict[str, Any] | None:
    for row in load_jsonl(archive_root / "indexes/agents.jsonl"):
        if row.get("agent_id") == agent_id and row.get("card"):
            card_path = ROOT / row["card"]
            card = load_json(card_path)
            return card if isinstance(card, dict) else None
    card = load_json(archive_root / "agents" / agent_id / "agent_card.json")
    return card if isinstance(card, dict) else None


def resolve_parent_prompt_source(archive_root: Path, parent_agent_id: str, source_rel: str) -> tuple[Path, str]:
    card = find_agent_card(archive_root, parent_agent_id)
    prompt_ref = ((card or {}).get("source_refs") or {}).get("prompt")
    if isinstance(prompt_ref, str) and prompt_ref:
        prompt_path = Path(prompt_ref)
        if not prompt_path.is_absolute():
            prompt_path = ROOT / prompt_path
        # Only inherit the archived parent prompt when it is the same logical
        # prompt/policy file being patched.  A legacy data-agent prompt is not a
        # valid base for the new DAB tool-agent policy overlay, and using it can
        # silently prevent improved tool-agent candidates from becoming shadow
        # parents.
        if prompt_path.exists() and Path(prompt_ref).name == Path(source_rel).name:
            return prompt_path, prompt_ref
    return ROOT / source_rel, source_rel


def materialize_prompt_patch(
    candidate_dir: Path,
    archive_root: Path,
    agent_id: str,
    parent_agent_id: str,
    changed_files: list[str],
) -> tuple[str | None, str | None]:
    prompt_files = [path for path in changed_files if path.startswith("prompts/dab/") and path.endswith(".txt")]
    if len(prompt_files) != 1:
        return None, None
    source_rel = prompt_files[0]
    source_path, source_ref = resolve_parent_prompt_source(archive_root, parent_agent_id, source_rel)
    patch_path = candidate_dir / "patch.diff"
    if not source_path.exists() or not patch_path.exists():
        return None, None

    with tempfile.TemporaryDirectory(prefix="archive_shadow_parent.") as tmp:
        temp_root = Path(tmp) / "repo"
        temp_source = temp_root / source_rel
        temp_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, temp_source)
        subprocess.run(["git", "init", "--quiet"], cwd=temp_root, check=True)
        subprocess.run(["git", "config", "user.name", "archive-shadow-parent"], cwd=temp_root, check=True)
        subprocess.run(["git", "config", "user.email", "archive-shadow-parent@localhost"], cwd=temp_root, check=True)
        subprocess.run(["git", "add", "."], cwd=temp_root, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "baseline"], cwd=temp_root, check=True)
        apply_proc = subprocess.run(["git", "apply", f"--include={source_rel}", str(patch_path)], cwd=temp_root, text=True, capture_output=True, check=False)
        if apply_proc.returncode != 0:
            return None, None
        out_rel = Path("archive/prompts") / agent_id / Path(source_rel).name
        out_path = ROOT / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp_source, out_path)
        return str(out_rel), source_ref

def create_shadow_parent_agent(
    *,
    candidate_dir: Path,
    archive_root: Path,
    parent_agent_id: str,
    candidate_type: str,
    patch_review: dict[str, Any],
    assessment: dict[str, Any],
    case_id: str,
    query_workspace: str | None = None,
    source_lineage_family: str | None = None,
) -> dict[str, Any] | None:
    if candidate_type != "data_agent_repair":
        return None
    if not assessment.get("evolution_parent_eligible"):
        return None
    agent_id = f"data_agent_shadow_{candidate_dir.name}"
    query_agent_changes = [
        path for path in patch_review["diff_files"]
        if query_workspace and path.startswith(query_workspace.rstrip("/") + "/agent/")
    ]
    if query_workspace and query_agent_changes:
        prompt_ref = f"{query_workspace.rstrip('/')}/agent/policy.txt"
        base_prompt_ref = prompt_ref
    else:
        prompt_ref, base_prompt_ref = materialize_prompt_patch(
            candidate_dir,
            archive_root,
            agent_id,
            parent_agent_id,
            patch_review["diff_files"],
        )
        if not prompt_ref:
            return None

    is_tool_agent = bool(query_workspace or prompt_ref.endswith("dab_tool_agent_policy_zero_start.txt"))
    card = {
        "agent_id": agent_id,
        "agent_type": "data_agent",
        "status": "shadow_parent_partial_improvement"
        if assessment.get("evolution_status") == "improved_but_failed"
        else "shadow_parent_validated_child",
        "created_or_observed_at": candidate_dir.name.rsplit("_", 2)[-2] if "_" in candidate_dir.name else None,
        "source_lineage_family": source_lineage_family,
        "query_workspace": query_workspace,
        "source_refs": {
            "prompt": prompt_ref,
            "base_prompt": base_prompt_ref,
            "candidate_patch": str((candidate_dir / "patch.diff").relative_to(ROOT)),
            "candidate_card": str((archive_root / "candidates" / candidate_dir.name / "candidate_card.json").relative_to(ROOT)),
            "runner": "experiments/run_dab_tool_agent.py" if is_tool_agent else "experiments/run_dab_agent.py",
        },
        "capabilities": [
            "DAB multi-turn tool workflow" if is_tool_agent else "DAB code generation",
            "tool-agent policy overlay" if is_tool_agent else "runtime observer instrumentation",
            "workflow trace/tool/LLM logging" if is_tool_agent else "stage_trace emission",
            "partial-improvement continuation parent",
        ],
        "known_failures": [
            {
                "case": case_id,
                "status": "failed_strict_validation",
                "reason": assessment.get("signal_metrics", {}).get("child_selected_stage"),
                "merge_note": "Do not merge this shadow parent into main without a later strict-validation pass.",
            }
        ],
        "evals": {
            case_id: {
                "passed_original_dab_validation": assessment.get("merge_eligible"),
                "evolution_status": assessment.get("evolution_status"),
                "answer_metrics": assessment.get("answer_metrics"),
                "execution_metrics": assessment.get("execution_metrics"),
                "selected_stage": assessment.get("signal_metrics", {}).get("child_selected_stage"),
                "selected_signal": assessment.get("signal_metrics", {}).get("child_selected_signal"),
            }
        },
        "lineage": {
            "parent_agent_id": parent_agent_id,
            "derived_from_candidate": candidate_dir.name,
        },
        "evolve_policy": {
            "can_use_as_parent": True,
            "merge_eligible": assessment.get("merge_eligible"),
            "recommended_next_use": "Use only as an isolated evolution parent; continue repairing the child-selected signal before merge.",
        },
    }
    card_path = archive_root / "agents" / agent_id / "agent_card.json"
    write_json(card_path, card)
    upsert_jsonl(
        archive_root / "indexes/agents.jsonl",
        "agent_id",
        {
            "agent_id": agent_id,
            "agent_type": "data_agent",
            "status": card["status"],
            "card": str(card_path.relative_to(ROOT)),
            "can_use_as_parent": True,
        },
    )
    runner_ref = str(card.get("source_refs", {}).get("runner") or "")
    base_reward = float(assessment.get("reward") or 0.0)
    if runner_ref == "experiments/run_dab_tool_agent.py":
        # The active mainline is the DAB tool-agent workflow.  Partial-improvement
        # tool-agent parents should outrank legacy generated-solve shadow parents
        # so the next loop continues evolving the current workflow instead of
        # drifting back to the retired chain.
        score = max(0.70, base_reward + 0.18)
        score_policy = "tool_agent_mainline_partial_improvement_floor"
    else:
        score = max(0.56, base_reward)
        score_policy = "legacy_partial_improvement_floor"
    upsert_selection_score(
        archive_root,
        {
            "arm_id": agent_id,
            "arm_type": "data_agent",
            "score": round(score, 6),
            "score_policy": score_policy,
            "evidence": assessment.get("selection_rationale"),
            "recommended_use": "Use as next isolated evolution parent, not as a merge-ready data agent.",
            "source_candidate": candidate_dir.name,
        },
    )
    return {"agent_id": agent_id, "card": str(card_path.relative_to(ROOT)), "prompt": prompt_ref, "selection_score": round(score, 6)}


def retract_shadow_parent_agent(
    *,
    candidate_dir: Path,
    archive_root: Path,
    reason: str,
) -> dict[str, Any] | None:
    """Retract a stale shadow parent if an older postprocess had promoted it.

    Reprocessing a candidate with stricter dual-baseline logic can make a
    previously generated shadow parent invalid. Keep the artifact for audit, but
    make it unselectable as a future parent.
    """

    agent_id = f"data_agent_shadow_{candidate_dir.name}"
    card_path = archive_root / "agents" / agent_id / "agent_card.json"
    if not card_path.exists():
        return None
    card = load_json(card_path) or {"agent_id": agent_id, "agent_type": "data_agent"}
    card["status"] = "shadow_parent_retracted"
    card["retraction"] = {
        "reason": reason,
        "source_candidate": candidate_dir.name,
    }
    evolve_policy = card.setdefault("evolve_policy", {})
    if isinstance(evolve_policy, dict):
        evolve_policy["can_use_as_parent"] = False
        evolve_policy["recommended_next_use"] = "Do not use as parent; keep only as audit/evidence artifact."
    write_json(card_path, card)
    upsert_jsonl(
        archive_root / "indexes/agents.jsonl",
        "agent_id",
        {
            "agent_id": agent_id,
            "agent_type": "data_agent",
            "status": "shadow_parent_retracted",
            "card": str(card_path.relative_to(ROOT)),
            "can_use_as_parent": False,
            "retraction_reason": reason,
        },
    )
    upsert_selection_score(
        archive_root,
        {
            "arm_id": agent_id,
            "arm_type": "data_agent",
            "score": 0.0,
            "score_policy": "retracted_shadow_parent",
            "evidence": reason,
            "recommended_use": "Do not select as parent; retained for audit only.",
            "source_candidate": candidate_dir.name,
        },
    )
    return {"agent_id": agent_id, "card": str(card_path.relative_to(ROOT)), "status": "shadow_parent_retracted"}


def observation_index_fields(observation: dict[str, Any]) -> dict[str, Any]:
    observations = observation.get("observations") if isinstance(observation.get("observations"), dict) else {}
    metric_delta = observations.get("metric_delta") if isinstance(observations.get("metric_delta"), dict) else {}
    f1_delta = metric_delta.get("f1") if isinstance(metric_delta.get("f1"), dict) else {}
    proposed = observations.get("proposed_contracts") if isinstance(observations.get("proposed_contracts"), dict) else {}
    contract_eval = observations.get("contract_eval") if isinstance(observations.get("contract_eval"), dict) else {}
    promotion = observation.get("promotion") if isinstance(observation.get("promotion"), dict) else {}
    reuse = observation.get("reuse_policy") if isinstance(observation.get("reuse_policy"), dict) else {}
    gate_summary = observation.get("gate_policy_summary") if isinstance(observation.get("gate_policy_summary"), dict) else {}
    return {
        "archive_observation_schema_version": observation.get("schema_version"),
        "gate_policy_schema_version": gate_summary.get("schema_version"),
        "eligible_as_parent": promotion.get("eligible_as_parent"),
        "promotion_reason": promotion.get("reason"),
        "promotion_score": promotion.get("promotion_score"),
        "parent_f1_tolerance": promotion.get("parent_f1_tolerance"),
        "f1_close_enough": promotion.get("f1_close_enough"),
        "catastrophic_answer_failure": promotion.get("catastrophic_answer_failure"),
        "can_seed_next_repair": reuse.get("can_seed_next_repair"),
        "use_as_negative_example": reuse.get("use_as_negative_example"),
        "has_open_diagnosis": bool(observations.get("open_diagnosis")),
        "metric_delta_f1": f1_delta.get("delta"),
        "failure_observation_tags": (observations.get("failure_observation_tags") or [])[:16],
        "proposed_contracts_schema_version": proposed.get("schema_version"),
        "proposed_contracts_present": proposed.get("present"),
        "proposed_contract_count": (proposed.get("summary") or {}).get("contract_count"),
        "contract_eval_schema_version": contract_eval.get("schema_version"),
        "contract_eval_status": contract_eval.get("status"),
        "contract_eval_violated_count": (contract_eval.get("summary") or {}).get("violated_count"),
        "contract_eval_supported_count": (contract_eval.get("summary") or {}).get("supported_count"),
        "contract_eval_unknown_count": (contract_eval.get("summary") or {}).get("unknown_count"),
    }


def archive_candidate(
    candidate_dir: Path,
    archive_root: Path,
    state: dict[str, Any],
    parent_agent_id: str,
    candidate_type: str,
    scope_note: str,
    case_id: str,
    query_workspace: str | None = None,
    source_lineage_family: str | None = None,
) -> Path:
    candidate_id = candidate_dir.name
    patch_review = build_patch_review(candidate_dir)
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    failure_observation = compact_failure_observation(load_json(candidate_dir / "failure_observation.json") or {})
    evidence_sufficiency = state.get("evidence_sufficiency") if isinstance(state.get("evidence_sufficiency"), dict) else assess_evidence_sufficiency(
        seed={},
        child_eval=child_eval,
        failure_observation=failure_observation,
    )
    assessment = compute_evolution_assessment(candidate_type, child_eval, archive_root=archive_root, parent_agent_id=parent_agent_id, case_id=case_id)
    derived_parent = create_shadow_parent_agent(
        candidate_dir=candidate_dir,
        archive_root=archive_root,
        parent_agent_id=parent_agent_id,
        candidate_type=candidate_type,
        patch_review=patch_review,
        assessment=assessment,
        case_id=case_id,
        query_workspace=query_workspace,
        source_lineage_family=source_lineage_family,
    )
    retracted_parent = None
    if derived_parent is None and candidate_type == "data_agent_repair" and not assessment.get("evolution_parent_eligible"):
        retracted_parent = retract_shadow_parent_agent(
            candidate_dir=candidate_dir,
            archive_root=archive_root,
            reason=assessment.get("selection_rationale") or "Candidate is not parent-eligible under current evolution assessment.",
        )
    patch_path = candidate_dir / "patch.diff"
    patch_artifact = str(patch_path.relative_to(ROOT)) if patch_path.exists() and patch_path.is_relative_to(ROOT) else str(patch_path) if patch_path.exists() else None

    card = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "parent_agent_id": parent_agent_id,
        "case_id": case_id,
        "query_workspace": query_workspace,
        "source_lineage_family": source_lineage_family,
        "status": state["status"],
        "changed_files": patch_review["diff_files"],
        "artifacts": {
            "candidate_dir": str(candidate_dir.relative_to(ROOT) if candidate_dir.is_relative_to(ROOT) else candidate_dir),
            "patch": patch_artifact,
            "manifest": str((candidate_dir / "manifest.json").relative_to(ROOT)),
            "validation_log": str((candidate_dir / "validation.log").relative_to(ROOT)) if (candidate_dir / "validation.log").exists() else None,
            "child_eval_report": str((candidate_dir / "child_eval/child_eval_report.json").relative_to(ROOT)) if (candidate_dir / "child_eval/child_eval_report.json").exists() else None,
            "post_child_eval_review": str((candidate_dir / "post_child_eval_review/post_child_eval_review.json").relative_to(ROOT)) if (candidate_dir / "post_child_eval_review/post_child_eval_review.json").exists() else None,
            "merge_review_package": str((candidate_dir / "merge_review_package.md").relative_to(ROOT)) if (candidate_dir / "merge_review_package.md").exists() else None,
            "next_repair_seed": str((candidate_dir / "next_data_agent_repair_seed.json").relative_to(ROOT)) if (candidate_dir / "next_data_agent_repair_seed.json").exists() else None,
            "failure_observation_pack_legacy": str((candidate_dir / "failure_observation_pack.json").relative_to(ROOT)) if (candidate_dir / "failure_observation_pack.json").exists() else None,
            "direct_behavior_observation_input": str((candidate_dir / "direct_behavior_observation_input.json").relative_to(ROOT)) if (candidate_dir / "direct_behavior_observation_input.json").exists() else None,
            "failure_observation": str((candidate_dir / "failure_observation.json").relative_to(ROOT)) if (candidate_dir / "failure_observation.json").exists() else None,
        },
        "eval_summary": {
            "manifest_status": manifest.get("status"),
            "child_eval": child_eval.get("final_status"),
            "post_child_eval_review": review.get("post_child_eval_review_status"),
            "total_changed_lines": patch_review["total_changed_lines"],
            "scope": scope_note,
        },
        "promotion": {
            "promoted_to_agent": state.get("post_child_eval_review_status") == "post_child_eval_review_passed",
            "merge_recommendation": state.get("merge_recommendation"),
        },
        "failure_observation": failure_observation,
        "evidence_sufficiency": evidence_sufficiency,
        "feedback_evolution_opportunity": evidence_sufficiency.get("feedback_evolution_opportunity"),
        "recommended_evolution_target": evidence_sufficiency.get("recommended_evolution_target"),
        "recommended_observer_subtarget": evidence_sufficiency.get("recommended_observer_subtarget"),
        "evolution": {
            **assessment,
            "derived_parent_agent": derived_parent,
            "retracted_parent_agent": retracted_parent,
        },
    }
    card_path = archive_root / "candidates" / candidate_id / "candidate_card.json"
    write_json(card_path, card)
    observation = build_archive_observation(candidate_dir)
    observation_path = card_path.parent / "archive_observation.json"
    write_json(observation_path, observation)
    card["archive_observation_schema_version"] = observation.get("schema_version")
    card["gate_policy_summary"] = observation.get("gate_policy_summary")
    card["observations"] = observation.get("observations")
    card["reuse_policy"] = observation.get("reuse_policy")
    card["observation_source_artifacts"] = observation.get("source_artifacts")
    promotion = dict(card.get("promotion") or {})
    promotion.update(observation.get("promotion") or {})
    card["promotion"] = promotion
    write_json(card_path, card)
    reward = 1.0 if state.get("post_child_eval_review_status") == "post_child_eval_review_passed" else assessment.get("reward", 0.0)
    index_row = {
        "candidate_id": candidate_id,
        "status": state["status"],
        "candidate_type": candidate_type,
        "parent_agent_id": parent_agent_id,
        "source_lineage_family": source_lineage_family,
        "query_workspace": query_workspace,
        "card": str(card_path.relative_to(ROOT)),
        "reward": reward,
        "evolution_parent_eligible": assessment.get("evolution_parent_eligible"),
        "evolution_status": assessment.get("evolution_status"),
        "comparison_baseline": (assessment.get("parent_comparison_metrics") or {}).get("comparison_baseline"),
        "failure_observer_primary_mechanism": failure_observation.get("primary_failure_mechanism"),
        "failure_observer_confidence": failure_observation.get("confidence"),
        "evidence_sufficiency_status": evidence_sufficiency.get("status"),
        "evidence_sufficiency_score": evidence_sufficiency.get("score"),
        "feedback_evolution_opportunity": evidence_sufficiency.get("feedback_evolution_opportunity"),
        "recommended_evolution_target": evidence_sufficiency.get("recommended_evolution_target"),
        "recommended_observer_subtarget": evidence_sufficiency.get("recommended_observer_subtarget"),
    }
    index_row.update(observation_index_fields(observation))
    comparison = assessment.get("parent_comparison_metrics") if isinstance(assessment.get("parent_comparison_metrics"), dict) else {}
    if comparison.get("delta_f1_vs_archive_parent") is not None:
        index_row["metric_delta_f1"] = comparison.get("delta_f1_vs_archive_parent")
    index_row.update(
        {
            "metric_delta_f1_vs_archive_parent": comparison.get("delta_f1_vs_archive_parent"),
            "metric_delta_f1_vs_materialized_parent": comparison.get("delta_f1_vs_materialized_parent"),
            "archive_parent_f1": comparison.get("archive_parent_f1"),
            "materialized_parent_f1": comparison.get("materialized_parent_f1"),
            "child_f1": comparison.get("child_f1"),
            "archive_parent_regression": comparison.get("archive_parent_regression"),
            "materialized_parent_reproduction_gap": comparison.get("materialized_parent_reproduction_gap"),
            "restored_to_archive_parent_level": comparison.get("restored_to_archive_parent_level"),
        }
    )
    upsert_jsonl(
        archive_root / "indexes/candidates.jsonl",
        "candidate_id",
        index_row,
    )
    return card_path


def postprocess_candidate(args: argparse.Namespace) -> int:
    candidate_dir = Path(args.candidate_dir).resolve()
    archive_root = Path(args.archive_root).resolve()
    if not candidate_dir.exists():
        raise SystemExit(f"candidate_dir not found: {candidate_dir}")
    state = infer_state(candidate_dir)
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    assessment = compute_evolution_assessment(args.candidate_type, child_eval, archive_root=archive_root, parent_agent_id=args.parent_agent_id, case_id=args.case_id)
    if state.get("status") == "candidate_child_eval_failed" and assessment.get("evolution_status") == "improved_but_failed":
        state["status"] = "candidate_child_eval_improved_but_failed"
    elif state.get("status") == "candidate_child_eval_failed" and assessment.get("evolution_status") == "stabilization_or_reproduction_repair":
        state["status"] = "candidate_child_eval_stabilization_repair"
    state["evolution_assessment"] = assessment
    state["evidence_sufficiency"] = assess_evidence_sufficiency(seed={}, child_eval=child_eval)
    state["feedback_evolution_opportunity"] = state["evidence_sufficiency"].get("feedback_evolution_opportunity")
    state["recommended_evolution_target"] = state["evidence_sufficiency"].get("recommended_evolution_target")
    state["recommended_observer_subtarget"] = state["evidence_sufficiency"].get("recommended_observer_subtarget")
    write_json(candidate_dir / "candidate_state.json", state)
    if not args.skip_failure_observer:
        failure_observation = ensure_failure_observation(
            candidate_dir,
            use_llm=not args.failure_observer_no_llm,
            parent_agent_id=args.parent_agent_id,
            archive_root=archive_root,
        )
        if failure_observation:
            state["failure_observation"] = compact_failure_observation(failure_observation)
            state["failure_observation_path"] = str(candidate_dir / "failure_observation.json")
            state["failure_observation_pack_path"] = str(candidate_dir / "failure_observation_pack.json") if (candidate_dir / "failure_observation_pack.json").exists() else None
            state["direct_behavior_observation_input_path"] = str(candidate_dir / "direct_behavior_observation_input.json")
            state["evidence_sufficiency"] = assess_evidence_sufficiency(
                seed={},
                child_eval=child_eval,
                failure_observation=state["failure_observation"],
            )
            state["feedback_evolution_opportunity"] = state["evidence_sufficiency"].get("feedback_evolution_opportunity")
            state["recommended_evolution_target"] = state["evidence_sufficiency"].get("recommended_evolution_target")
            state["recommended_observer_subtarget"] = state["evidence_sufficiency"].get("recommended_observer_subtarget")
            write_json(candidate_dir / "candidate_state.json", state)
    review_path = generate_merge_review(candidate_dir, state, args.scope_note)
    seed_json, seed_md = generate_next_seed(candidate_dir, args.case_id, args.recommended_goal)
    card_path = archive_candidate(
        candidate_dir,
        archive_root,
        state,
        parent_agent_id=args.parent_agent_id,
        candidate_type=args.candidate_type,
        scope_note=args.scope_note,
        case_id=args.case_id,
        query_workspace=args.query_workspace,
        source_lineage_family=args.source_lineage_family,
    )
    summary = {
        "status": "postprocess_complete",
        "candidate_id": candidate_dir.name,
        "state": state,
        "outputs": {
            "candidate_state": str(candidate_dir / "candidate_state.json"),
            "merge_review_package": str(review_path),
            "next_seed_json": str(seed_json),
            "next_seed_md": str(seed_md),
            "archive_card": str(card_path),
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    post = sub.add_parser("postprocess-candidate")
    post.add_argument("--candidate-dir", required=True)
    post.add_argument("--archive-root", default=str(ROOT / "archive"))
    post.add_argument("--parent-agent-id", default="codex_qwen_meta_v4_structured_patch_spec")
    post.add_argument("--candidate-type", default="feedback_analyzer_repair")
    post.add_argument(
        "--scope-note",
        default="Feedback/error-analysis infrastructure repair only; not a PATENTS answer solver repair.",
    )
    post.add_argument("--case-id", default="PATENTS_query1")
    post.add_argument("--skip-failure-observer", action="store_true")
    post.add_argument("--failure-observer-no-llm", action="store_true")
    post.add_argument("--query-workspace")
    post.add_argument("--source-lineage-family")
    post.add_argument(
        "--recommended-goal",
        default=(
            "Repair the data-agent side for the active DAB case using the current child-eval "
            "feedback so metadata grounding, date extraction, aggregation, and final "
            "answer generation produce a validated answer."
        ),
    )
    post.set_defaults(func=postprocess_candidate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
