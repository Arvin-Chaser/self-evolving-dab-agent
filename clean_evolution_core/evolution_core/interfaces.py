"""Adapter contracts for a benchmark-specific experiment."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .models import ExecutionEvidence, Intent, SourceVersion


class RunnerAdapter(Protocol):
    def run(self, source: SourceVersion, *, batch_id: str, output_dir: Path) -> ExecutionEvidence:
        ...


class EvaluatorAdapter(Protocol):
    def evaluate(self, evidence: ExecutionEvidence) -> dict[str, Any]:
        ...


class MetaAgentAdapter(Protocol):
    def select_parent(self, *, lineage_context: dict[str, Any]) -> str | None:
        """Return a source version id from the accumulated lineage, or None for the latest child."""
        ...

    def propose(self, *, parent: SourceVersion, feedback: dict[str, Any], lineage_context: dict[str, Any]) -> Intent:
        ...

    def review(self, *, intent: Intent, parent: SourceVersion, child: SourceVersion, evidence: ExecutionEvidence, evaluation: dict[str, Any]) -> dict[str, Any]:
        ...


class SourceBuilder(Protocol):
    def build(self, *, parent: SourceVersion, intent: Intent, output_dir: Path) -> SourceVersion:
        ...
