"""Gate policy split for meta-agent evolution.

Gate results should act mostly as instruments: hard gates protect experiment
safety/protocol/executability; soft observations describe semantic/interface
failures for later meta-agent learning; promotion gates decide whether a child
can become a future parent.
"""

from __future__ import annotations

from typing import Any


GATE_POLICY_SCHEMA_VERSION = "gate_policy_v002"

HARD_GATE_LAYERS = {"hard_safety", "protocol"}
HARD_GATE_TYPES = {
    "anti_cheating",
    "scope_control",
    "real_diff_required",
    "syntax",
    "module_import",
}
HARD_GATE_NAMES = {
    "no_obvious_answer_hardcoding",
    "py_compile_changed_python_files",
}
SOFT_GATE_LAYERS = {"task_contract"}
SOFT_GATE_TYPES = {
    "fine_grained_feedback_alignment",
    "runtime_integration",
    "no_op_or_metric_gaming_guard",
    "static_tool_contract",
    "real_data_parser_smoke",
    "static_prompt_contract",
    "static_project_contract",
}


def classify_validation_gate(result: dict[str, Any]) -> str:
    """Classify a validation gate as hard_gate, soft_observation, or pass_observation."""
    name = str(result.get("name") or "")
    gate_layer = str(result.get("gate_layer") or "")
    gate_type = str(result.get("gate_type") or "")
    warning = bool(result.get("warning")) or result.get("hard_fail") is False
    exit_code = result.get("exit_code")

    if warning:
        return "soft_observation"
    if gate_layer in HARD_GATE_LAYERS or gate_type in HARD_GATE_TYPES or name in HARD_GATE_NAMES:
        return "hard_gate"
    if gate_layer in SOFT_GATE_LAYERS or gate_type in SOFT_GATE_TYPES:
        return "soft_observation" if exit_code not in (None, 0) else "pass_observation"
    if exit_code not in (None, 0):
        return "hard_gate" if result.get("hard_fail", True) else "soft_observation"
    return "pass_observation"


def decorate_validation_gate(result: dict[str, Any]) -> dict[str, Any]:
    decorated = dict(result)
    decorated["gate_policy_schema_version"] = GATE_POLICY_SCHEMA_VERSION
    decorated["gate_policy_layer"] = classify_validation_gate(decorated)
    return decorated


def should_block_validation(result: dict[str, Any]) -> bool:
    """Return True only when a failed hard gate should stop candidate validation."""
    return classify_validation_gate(result) == "hard_gate" and result.get("exit_code") not in (None, 0)


def classify_child_failure_gate(gate: str | None) -> str:
    if not gate:
        return "pass_observation"
    return "promotion_gate"


def summarize_gate_policy(validation_results: list[dict[str, Any]], child_eval: dict[str, Any] | None = None) -> dict[str, Any]:
    child_eval = child_eval or {}
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for item in validation_results or []:
        if not isinstance(item, dict):
            continue
        decorated = decorate_validation_gate(item)
        layer = decorated.get("gate_policy_layer")
        compact = {
            "name": decorated.get("name"),
            "exit_code": decorated.get("exit_code"),
            "reason": decorated.get("reason"),
            "gate_layer": decorated.get("gate_layer"),
            "gate_type": decorated.get("gate_type"),
            "warning": decorated.get("warning"),
            "hard_fail": decorated.get("hard_fail"),
        }
        if layer == "hard_gate":
            hard.append(compact)
        elif layer == "soft_observation":
            soft.append(compact)
        else:
            passed.append(compact)
    promotion = []
    for gate in child_eval.get("child_failure_gates") or []:
        promotion.append({"name": gate, "gate_policy_layer": classify_child_failure_gate(str(gate))})
    return {
        "schema_version": GATE_POLICY_SCHEMA_VERSION,
        "hard_gates": hard,
        "soft_observations": soft,
        "pass_observations": passed,
        "promotion_gates": promotion,
    }