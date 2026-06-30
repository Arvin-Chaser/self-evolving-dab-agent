"""Runtime observer injected into generated DAB agent runs.

Generated solve.py files can import this module from their run directory:

    from runtime_observer import log_event, check_and_log, write_runtime_log

The observer writes structured runtime events to STAGE_TRACE_PATH or
RUNTIME_LOG_PATH. The file name may remain stage_trace.json for compatibility,
but the content is an execution log produced during local code execution.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_EVENTS: list[dict[str, Any]] = []
_DEFAULT_CONTEXT: dict[str, Any] = {}
_LOG_PATH: Path | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any, max_string: int = 800, max_items: int = 20) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + f"...<truncated {len(value) - max_string} chars>"

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        result = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= max_items:
                result["<truncated>"] = f"{len(value) - max_items} more keys"
                break
            result[str(key)] = _json_safe(child, max_string=max_string, max_items=max_items)
        return result

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [
            _json_safe(child, max_string=max_string, max_items=max_items)
            for child in items[:max_items]
        ]
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

    raw_path = os.environ.get("RUNTIME_LOG_PATH") or os.environ.get("STAGE_TRACE_PATH")
    if not raw_path:
        raw_path = "stage_trace.json"

    _LOG_PATH = Path(raw_path)
    return _LOG_PATH


def configure(log_path: str | Path | None = None, default_context: dict[str, Any] | None = None) -> None:
    global _LOG_PATH, _DEFAULT_CONTEXT
    if log_path is not None:
        _LOG_PATH = Path(log_path)
    if default_context:
        _DEFAULT_CONTEXT.update(_json_safe(default_context))


def write_runtime_log() -> None:
    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_EVENTS, indent=2, ensure_ascii=False), encoding="utf-8")


def log_event(
    event: str,
    *,
    trigger: str = "runtime_observation",
    severity: str = "info",
    status: str | None = None,
    purpose: str | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    assumptions: list[Any] | None = None,
    warnings: list[Any] | None = None,
    error: Any = None,
    hypothesis: str | None = None,
    suggested_target: str | None = None,
    tags: list[str] | None = None,
    flush: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "event": str(event),
        "trigger": trigger,
        "severity": severity,
        "status": status or ("failed" if error else "completed"),
        "timestamp": _now(),
        "context": dict(_DEFAULT_CONTEXT),
        "purpose": purpose,
        "inputs": _json_safe(inputs or {}),
        "outputs": _json_safe(outputs or {}),
        "checks": _json_safe(checks or []),
        "evidence": _json_safe(evidence or {}),
        "assumptions": _json_safe(assumptions or []),
        "warnings": _json_safe(warnings or []),
        "error": _json_safe(error),
        "hypothesis": hypothesis,
        "suggested_target": suggested_target,
        "tags": _json_safe(tags or []),
    }

    for key, value in extra.items():
        item[key] = _json_safe(value)

    _EVENTS.append(item)

    if flush:
        write_runtime_log()

    return item


def check_and_log(
    name: str,
    passed: bool,
    *,
    observed: Any = None,
    expected: Any = None,
    message: str | None = None,
    event: str | None = None,
    severity: str | None = None,
    evidence: dict[str, Any] | None = None,
    suggested_target: str | None = None,
) -> bool:
    check = {
        "name": name,
        "passed": bool(passed),
        "message": message,
        "observed": _json_safe(observed),
        "expected": _json_safe(expected),
    }

    if passed:
        trigger = "runtime_check_passed"
        resolved_severity = severity or "info"
    else:
        trigger = "runtime_check_failed"
        resolved_severity = severity or "warning"

    log_event(
        event or name,
        trigger=trigger,
        severity=resolved_severity,
        status="completed" if passed else "warning",
        checks=[check],
        evidence=evidence or {},
        suggested_target=suggested_target,
    )
    return bool(passed)


def log_if_empty(
    name: str,
    value: Any,
    *,
    evidence: dict[str, Any] | None = None,
    suggested_target: str | None = None,
) -> bool:
    try:
        size = len(value)
    except TypeError:
        size = None

    is_empty = size == 0
    if is_empty:
        log_event(
            f"{name}_empty",
            trigger="runtime_anomaly",
            severity="warning",
            status="warning",
            outputs={name: 0},
            evidence=evidence or {},
            warnings=[f"{name} is empty during local execution."],
            suggested_target=suggested_target,
        )
    return is_empty


def log_if_missing_columns(
    required_columns: list[str] | set[str] | tuple[str, ...],
    available_columns: list[str] | set[str] | tuple[str, ...],
    *,
    event: str = "missing_columns",
    suggested_target: str = "schema_grounding",
) -> list[str]:
    required = [str(item) for item in required_columns]
    available = [str(item) for item in available_columns]
    missing = [item for item in required if item not in set(available)]
    if missing:
        log_event(
            event,
            trigger="runtime_check_failed",
            severity="warning",
            status="warning",
            outputs={"missing_columns": missing, "available_columns": available},
            checks=[
                {
                    "name": "required_columns_present",
                    "passed": False,
                    "observed": {"missing_columns": missing},
                    "expected": {"required_columns": required},
                    "message": "One or more required columns were not found.",
                }
            ],
            suggested_target=suggested_target,
        )
    return missing


def log_if_large(
    name: str,
    value: int | float,
    threshold: int | float,
    *,
    evidence: dict[str, Any] | None = None,
    suggested_target: str | None = None,
) -> bool:
    too_large = value > threshold
    if too_large:
        log_event(
            f"{name}_large",
            trigger="runtime_anomaly",
            severity="warning",
            status="warning",
            outputs={name: value, "threshold": threshold},
            evidence=evidence or {},
            warnings=[f"{name}={value} is larger than threshold={threshold}."],
            suggested_target=suggested_target,
        )
    return too_large


def log_exception(
    event: str | BaseException,
    exc: BaseException | None = None,
    *,
    evidence: dict[str, Any] | None = None,
    suggested_target: str | None = None,
) -> None:
    """Log an exception with a stable runtime-observer schema.

    Preferred generated-code usage is::

        log_exception("metadata_parser_failed", exc)

    For robustness with older or weaker generated agents, the one-argument
    form ``log_exception(exc)`` is also accepted and uses the generic event
    name ``"exception"``.  This keeps observer misuse from masking the real
    data-agent failure being diagnosed.
    """
    if exc is None and isinstance(event, BaseException):
        exc = event
        event_name = "exception"
    else:
        event_name = str(event)

    if exc is None:
        exc = RuntimeError("log_exception called without an exception object")

    log_event(
        event_name,
        trigger="exception",
        severity="error",
        status="failed",
        evidence=evidence or {},
        error={
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
        suggested_target=suggested_target,
    )

def get_events() -> list[dict[str, Any]]:
    return list(_EVENTS)



def log_if_heuristic_fallback_used(
    name: str,
    fallback_reason: str,
    *,
    evidence: dict[str, Any] | None = None,
    suggested_target: str | None = None,
) -> None:
    """
    Log when a heuristic fallback is used during metadata parsing.
    
    Used to signal parser resilience to downstream analyzers.
    """
    log_event(
        f"{name}_heuristic_fallback",
        trigger="fallback_used",
        severity="warning",
        status="completed",
        outputs={"fallback_reason": fallback_reason},
        evidence=evidence or {},
        warnings=[f"Heuristic fallback applied for {name}: {fallback_reason}"],
        suggested_target=suggested_target or "metadata_parser",
    )



def log_if_zero(name: str, value: int | float, *, evidence: dict[str, Any] | None = None, suggested_target: str | None = None) -> bool:
    """
    Log when a numeric count is zero during local execution.
    
    Used to signal empty mapping/aggregation outcomes for downstream analysis.
    """
    is_zero = value == 0
    if is_zero:
        log_event(
            f"{name}_zero",
            trigger="runtime_anomaly",
            severity="warning",
            status="warning",
            outputs={name: 0},
            evidence=evidence or {},
            warnings=[f"{name}={value} is zero during local execution."],
            suggested_target=suggested_target,
        )
    return is_zero
