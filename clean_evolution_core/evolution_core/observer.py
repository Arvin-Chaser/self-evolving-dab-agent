"""Bounded JSONL observation for outer workflows and generated runtimes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe(value: Any, limit: int = 1200) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...<truncated>"
    if isinstance(value, dict):
        return {str(k): _safe(v, limit) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, limit) for v in list(value)[:40]]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


class JsonlObserver:
    def __init__(self, path: str | Path, context: dict[str, Any] | None = None):
        self.path = Path(path)
        self.context = dict(context or {})

    def emit(self, event: str, **data: Any) -> dict[str, Any]:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **_safe(self.context),
            **_safe(data),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row
