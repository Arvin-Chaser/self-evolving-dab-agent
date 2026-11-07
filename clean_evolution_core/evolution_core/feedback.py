"""Normalize runtime observations without deciding the repair."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def observation_card(observations: Iterable[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    """Return bounded cards grouped by event and stage.

    Cards describe evidence and frequency. They never contain a benchmark
    answer or a hard-coded repair decision.
    """
    rows = list(observations)
    counts = Counter((str(row.get("stage") or "unknown"), str(row.get("event") or "unknown")) for row in rows)
    cards: list[dict[str, Any]] = []
    for (stage, event), count in counts.most_common(limit):
        samples = [
            {"status": row.get("status"), "error": row.get("error"), "outputs": row.get("outputs")}
            for row in rows
            if (str(row.get("stage") or "unknown"), str(row.get("event") or "unknown")) == (stage, event)
        ][:3]
        cards.append({"stage": stage, "event": event, "count": count, "samples": samples})
    return cards


def build_feedback(*, run_id: str, source_version_id: str, observations: list[dict[str, Any]], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "feedback_v1",
        "scope": {"run_id": run_id, "source_version_id": source_version_id},
        "cards": observation_card(observations),
        "metrics": dict(metrics or {}),
        "limitations": ["observations describe evidence; they do not establish causal effect"],
    }
