#!/usr/bin/env python3
"""Small helpers for interpreting DAB tool-agent final answers.

The upstream multi-turn agent can sometimes surface the literal tool payload
as text, e.g. ``{"tool": "return_answer", "args": {"answer": ""}}``.  For
answer-quality metrics, that must be treated as an empty semantic answer, not
as a non-empty string.
"""

from __future__ import annotations

import json
from typing import Any


def semantic_final_answer_text(raw_answer: Any) -> str:
    """Return the answer text that should be scored as the DataAgent answer."""

    if raw_answer is None:
        return ""

    payload: Any = raw_answer
    if isinstance(raw_answer, str):
        stripped = raw_answer.strip()
        if not stripped:
            return ""
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return raw_answer

    if isinstance(payload, dict):
        tool_name = str(payload.get("tool") or payload.get("name") or "")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        if tool_name == "return_answer":
            return str(args.get("answer") or "")
        for key in ("answer", "final_answer", "final_result"):
            if key in payload:
                return str(payload.get(key) or "")

    return str(raw_answer)


def semantic_final_answer_nonempty(raw_answer: Any) -> bool:
    return bool(semantic_final_answer_text(raw_answer).strip())
