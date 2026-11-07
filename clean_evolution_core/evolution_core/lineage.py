"""Append-only source lineage.

Only source versions are lineage entities. Evaluation results and reviews are
attached to a child transition as evidence. This keeps the graph about code
inheritance while still preserving all measurements and explanations.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from .models import EvolutionRecord, SourceVersion, digest


class LineageGraph:
    def __init__(self, *, campaign_id: str, initial_parent: SourceVersion):
        self.campaign_id = campaign_id
        self.initial_parent = initial_parent
        self.records: list[EvolutionRecord] = []

    @property
    def head_sha256(self) -> str | None:
        return self.records[-1].record_sha256() if self.records else None

    def append(self, record: EvolutionRecord) -> None:
        if record.generation != len(self.records) + 1:
            raise ValueError("generation must be contiguous")
        if record.parent.version_id not in {version.version_id for version in self.source_versions()}:
            raise ValueError("parent is not present in the accumulated lineage")
        if record.previous_record_sha256 != self.head_sha256:
            raise ValueError("record hash chain mismatch")
        if record.child.parent_version_id != record.parent.version_id:
            raise ValueError("child parent_version_id mismatch")
        self.records.append(record)

    def source_versions(self) -> list[SourceVersion]:
        """Return the initial parent and every recorded child version."""
        versions = [self.initial_parent]
        versions.extend(record.child for record in self.records)
        return versions

    def source_by_id(self, version_id: str) -> SourceVersion:
        for version in self.source_versions():
            if version.version_id == version_id:
                return version
        raise KeyError(f"unknown source version: {version_id}")

    def snapshot(self, *, limit: int = 32) -> dict[str, Any]:
        rows = self.records[-limit:]
        return {
            "schema": "source_lineage_v1",
            "campaign_id": self.campaign_id,
            "initial_parent": asdict(self.initial_parent),
            "source_versions": [asdict(version) for version in self.source_versions()],
            "head_version_id": rows[-1].child.version_id if rows else self.initial_parent.version_id,
            "records": [self._compact(record) for record in rows],
            "selection_note": "The next meta-agent selects a source version using these records and attached evidence.",
        }

    @staticmethod
    def _compact(record: EvolutionRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "generation": record.generation,
            "parent": asdict(record.parent),
            "child": asdict(record.child),
            "intent": asdict(record.intent),
            "child_evidence": asdict(record.child_evidence),
            "review": asdict(record.review),
            "record_sha256": record.record_sha256(),
        }

    def to_jsonl(self) -> str:
        return "".join(json.dumps(self._compact(record), ensure_ascii=False, sort_keys=True) + "\n" for record in self.records)
