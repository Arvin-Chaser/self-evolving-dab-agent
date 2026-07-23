"""Initial contract evaluation for archived meta-agent candidates.

This module intentionally performs lightweight, evidence-based observation. It
does not introduce a hard taxonomy for what repairs must be. The goal is to
compare a candidate's own proposed contracts against child-eval artifacts and
record whether the archive has supporting or contradicting evidence.
"""

from __future__ import annotations

from typing import Any


CONTRACT_EVAL_SCHEMA_VERSION = "contract_eval_v001"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {_as_text(val)}" for key, val in value.items())
    return str(value)


def _metric_delta_value(metric_delta: dict[str, Any], key: str) -> float | None:
    item = metric_delta.get(key) if isinstance(metric_delta, dict) else None
    if not isinstance(item, dict):
        return None
    value = item.get("delta")
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _has_helper_sink_mismatch(interface_mismatch_evidence: list[dict[str, Any]]) -> bool:
    return any(item.get("kind") == "helper_output_sink_mismatch" for item in interface_mismatch_evidence or [])


def _contract_text(contract: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _as_text(contract.get("statement")),
            _as_text(contract.get("expected_observable_effect")),
            _as_text(contract.get("validation_hint")),
            _as_text(contract.get("scope")),
            _as_text(contract.get("target_files")),
        )
        if part
    ).lower()


def evaluate_contracts(
    proposed_contracts: dict[str, Any],
    *,
    child_eval: dict[str, Any],
    metric_delta: dict[str, Any],
    interface_mismatch_evidence: list[dict[str, Any]],
    contract_failure_evidence: list[dict[str, Any]],
    soft_gate_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate proposed contracts against available child-eval observations.

    The result is deliberately soft: it gives later selectors/meta-agents
    structured evidence, but it is not a hard validation gate.
    """

    contracts = proposed_contracts.get("contracts") if isinstance(proposed_contracts, dict) else []
    if not contracts:
        return {
            "schema_version": CONTRACT_EVAL_SCHEMA_VERSION,
            "status": "not_evaluated_no_proposed_contracts",
            "layer": "soft_observation",
            "blocks_parent_selection": False,
            "evaluated_contracts": [],
            "summary": {
                "contract_count": 0,
                "supported_count": 0,
                "violated_count": 0,
                "unknown_count": 0,
            },
        }

    child_reason = str(child_eval.get("child_validation_reason") or child_eval.get("validation_reason") or "").lower()
    child_passed = bool(child_eval.get("child_passed") or child_eval.get("final_status") == "candidate_child_eval_passed")
    failure_gates = [str(item) for item in child_eval.get("child_failure_gates") or []]
    helper_sink_mismatch = _has_helper_sink_mismatch(interface_mismatch_evidence)
    f1_delta = _metric_delta_value(metric_delta, "f1")
    precision_delta = _metric_delta_value(metric_delta, "precision")
    recall_delta = _metric_delta_value(metric_delta, "recall")

    evaluated: list[dict[str, Any]] = []
    for idx, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            contract = {"contract_id": f"contract_{idx + 1}", "statement": _as_text(contract)}
        text = _contract_text(contract)
        supporting: list[dict[str, Any]] = []
        contradicting: list[dict[str, Any]] = []

        wants_metric_improvement = any(token in text for token in ("improve", "f1", "precision", "recall", "reduce extra", "answer_delta", "better answer"))
        wants_final_answer = any(token in text for token in ("final_answer", "final answer", "non-empty answer", "write answer"))
        wants_helper_flow = any(token in text for token in ("helper", "flow", "sink", "consume", "consumed", "used for final", "construction"))

        if wants_metric_improvement:
            if f1_delta is not None and f1_delta > 0:
                supporting.append({"kind": "metric_delta_positive", "metric": "f1", "delta": f1_delta})
            elif f1_delta is not None and f1_delta < 0:
                contradicting.append({"kind": "metric_delta_negative", "metric": "f1", "delta": f1_delta})
            elif precision_delta is not None and recall_delta is not None and precision_delta >= 0 and recall_delta >= 0:
                supporting.append({"kind": "precision_recall_non_regression", "precision_delta": precision_delta, "recall_delta": recall_delta})

        if wants_final_answer and "missing_final_answer_file_or_empty_answer" in child_reason:
            contradicting.append({"kind": "empty_or_missing_final_answer", "reason": child_reason})

        if wants_helper_flow:
            if helper_sink_mismatch:
                contradicting.append({"kind": "helper_output_sink_mismatch", "source": "child_eval.helper_usage.final_answer_dependency"})
            elif child_passed:
                supporting.append({"kind": "child_eval_passed_without_helper_sink_mismatch"})

        for gate in failure_gates:
            if gate == "severe_child_answer_regression" and wants_metric_improvement:
                contradicting.append({"kind": "severe_child_answer_regression", "source": "child_failure_gates"})
            if gate == "helper_called_but_output_not_used_for_final_answer" and wants_helper_flow:
                contradicting.append({"kind": gate, "source": "child_failure_gates"})

        for item in contract_failure_evidence or []:
            if wants_helper_flow or wants_final_answer:
                contradicting.append({"kind": item.get("kind") or "contract_failure_evidence", "source": item.get("source"), "observed_status": item.get("observed_status")})

        if contradicting:
            status = "violated_by_child_observation"
        elif supporting:
            status = "supported_by_child_observation"
        else:
            status = "unknown_insufficient_archive_evidence"

        evaluated.append(
            {
                "contract_id": contract.get("contract_id") or f"contract_{idx + 1}",
                "status": status,
                "statement": contract.get("statement"),
                "expected_observable_effect": contract.get("expected_observable_effect"),
                "supporting_evidence": supporting,
                "contradicting_evidence": contradicting,
                "soft_gate_observation_names": [item.get("name") for item in soft_gate_observations or [] if isinstance(item, dict) and item.get("name")],
            }
        )

    supported_count = sum(1 for item in evaluated if item["status"] == "supported_by_child_observation")
    violated_count = sum(1 for item in evaluated if item["status"] == "violated_by_child_observation")
    unknown_count = sum(1 for item in evaluated if item["status"] == "unknown_insufficient_archive_evidence")
    if violated_count:
        status = "contract_eval_has_violations"
    elif supported_count == len(evaluated):
        status = "contract_eval_supported"
    elif supported_count and unknown_count:
        status = "contract_eval_partially_supported"
    else:
        status = "contract_eval_unknown"

    return {
        "schema_version": CONTRACT_EVAL_SCHEMA_VERSION,
        "status": status,
        "layer": "soft_observation",
        "blocks_parent_selection": False,
        "evaluated_contracts": evaluated,
        "summary": {
            "contract_count": len(evaluated),
            "supported_count": supported_count,
            "violated_count": violated_count,
            "unknown_count": unknown_count,
        },
    }
