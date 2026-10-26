"""Workflow-level observer for DAB-style multi-turn DataAgent runs.

This module is intentionally domain-neutral. It records workflow events such as
LLM calls, tool calls, answer submission, validation, and termination. It does
not encode PATENTS/CPC-specific solving knowledge.

`runtime_observer.py` remains useful for code executed inside a single generated
Python script. This module is for the outer multi-turn workflow.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_CONTEXT: dict[str, Any] = {}
_LOG_PATH: Path | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any, *, max_string: int = 1200, max_items: int = 40) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + f"...<truncated {len(value) - max_string} chars>"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= max_items:
                result["<truncated>"] = f"{len(value) - max_items} more keys"
                break
            result[str(key)] = _json_safe(child, max_string=max_string, max_items=max_items)
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [_json_safe(child, max_string=max_string, max_items=max_items) for child in items[:max_items]]
        if len(items) > max_items:
            result.append(f"<truncated {len(items) - max_items} items>")
        return result
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def get_log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    raw_path = os.environ.get("WORKFLOW_TRACE_PATH") or os.environ.get("DAB_WORKFLOW_TRACE_PATH")
    if not raw_path:
        raw_path = "workflow_events.jsonl"
    _LOG_PATH = Path(raw_path)
    return _LOG_PATH


def configure(log_path: str | Path | None = None, default_context: dict[str, Any] | None = None) -> None:
    global _LOG_PATH, _DEFAULT_CONTEXT
    if log_path is not None:
        _LOG_PATH = Path(log_path)
    if default_context:
        _DEFAULT_CONTEXT.update(_json_safe(default_context))


def emit_event(
    event: str,
    *,
    run_id: str | None = None,
    turn_id: int | None = None,
    llm_call_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    status: str = "completed",
    severity: str = "info",
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    warnings: list[Any] | None = None,
    error: Any = None,
    suggested_target: str | list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event": event,
        "timestamp": _now(),
        "context": dict(_DEFAULT_CONTEXT),
        "run_id": run_id,
        "turn_id": turn_id,
        "llm_call_id": llm_call_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "status": "failed" if error and status == "completed" else status,
        "severity": "error" if error and severity == "info" else severity,
        "inputs": _json_safe(inputs or {}),
        "outputs": _json_safe(outputs or {}),
        "checks": _json_safe(checks or []),
        "evidence": _json_safe(evidence or {}),
        "warnings": _json_safe(warnings or []),
        "error": _json_safe(error),
        "suggested_target": _json_safe(suggested_target),
    }
    for key, value in extra.items():
        row[key] = _json_safe(value)

    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def run_started(**kwargs: Any) -> dict[str, Any]:
    return emit_event("run_started", **kwargs)


def llm_call_completed(**kwargs: Any) -> dict[str, Any]:
    return emit_event("llm_call_completed", **kwargs)


def tool_call_completed(**kwargs: Any) -> dict[str, Any]:
    return emit_event("tool_call_completed", **kwargs)


def run_terminated(**kwargs: Any) -> dict[str, Any]:
    return emit_event("run_terminated", **kwargs)
