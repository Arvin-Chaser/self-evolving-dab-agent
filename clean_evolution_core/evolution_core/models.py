"""Small, serializable records used by the generic evolution loop.

The source versions are the lineage entities. Execution output is evidence on
the child transition; it is deliberately not represented as a graph node.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceVersion:
    version_id: str
    source_tree_sha256: str
    parent_version_id: str | None = None
    generation: int = 0
    changed_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Intent:
    intent_id: str
    mechanism_key: str
    observed_limitation: str
    proposed_mechanism: str
    expected_behavior: str
    validation_expectations: tuple[str, ...] = ()
    bounded_fallback: str = ""
    prior_version_id: str | None = None
    prior_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionEvidence:
    run_id: str
    source_version_id: str
    batch_id: str
    metrics: dict[str, Any] = field(default_factory=dict)
    observations: tuple[dict[str, Any], ...] = ()
    artifact_refs: tuple[str, ...] = ()
    run_sha256: str | None = None


@dataclass(frozen=True)
class Review:
    outcome: str
    implementation_status: str
    activation_evidence: tuple[str, ...] = ()
    behavioral_effect: str = ""
    task_effect: str = ""
    recommendation: str = ""
    parent_decision: str = "retain_parent"
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvolutionRecord:
    record_id: str
    generation: int
    parent: SourceVersion
    child: SourceVersion
    intent: Intent
    child_evidence: ExecutionEvidence
    review: Review
    previous_record_sha256: str | None = None

    def content(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("previous_record_sha256", None)
        return payload

    def record_sha256(self) -> str:
        return digest(self.content())
