#!/usr/bin/env python3
"""Provider-free G11-G13 revisioned requirement/evidence controller."""

from __future__ import annotations

import copy
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA = "revisioned_requirement_evidence_state_v1"
CARRIER_PREFIX = "REVISIONED_REQUIREMENT_EVIDENCE_STATE_V1"
VIEW_PREFIX = "[REVISIONED_REQUIREMENT_EVIDENCE_VIEW_V1]"
TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
OBSERVATION_REF_RE = re.compile(r"^var_[A-Za-z0-9][A-Za-z0-9_-]{0,59}$")
ACTION_STATES = (
    "acquire_evidence",
    "refresh_observation",
    "revise_requirement_row",
    "revise_plan",
    "preserve_unknown",
    "proceed",
)
COVERAGE_STATES = ("uncovered", "observed", "ambiguous", "failed", "unavailable", "unknown")
FRESHNESS_STATES = ("current", "stale", "unknown")
FAULT_STATES = (
    "none",
    "missing",
    "malformed",
    "truncated",
    "duplicate",
    "invalid_reference",
    "non_visible_reference",
    "instrumentation_loss",
    "provider_rejected",
    "boundary_mismatch",
    "revision_invalid",
    "unknown",
)
MAX_PLAN_STEPS = 16
MAX_REQUIREMENT_ROWS = 32
MAX_REFS_PER_ROW = 16
MAX_TOTAL_REFS = 128
MAX_VIEWS_PER_TASK = 3
DEADLINE_GUARD_SECONDS = 180.0
EXPECTED_FIELDS = {
    "schema",
    "state_id",
    "revision",
    "supersedes",
    "plan_steps",
    "requirement_rows",
}
MAX_TELEMETRY_COUNT = 1_000_000_000
TELEMETRY_COUNTER_KEYS = {
    "rejection_reason_counts": {
        "missing",
        "mixed_or_duplicate",
        "truncated",
        "malformed",
        "additional_or_missing_field",
        "schema_or_token_invalid",
        "revision_invalid",
        "limit_or_token_invalid",
        "duplicate_or_token_invalid",
        "invalid_reference",
        "duplicate",
        "provider_rejected",
        "boundary_mismatch",
    },
    "coverage_state_counts": set(COVERAGE_STATES),
    "freshness_state_counts": set(FRESHNESS_STATES),
    "fault_state_counts": set(FAULT_STATES),
    "selected_action_counts": set(ACTION_STATES),
    "cap_and_deadline_suppression_counts": {"unknown_boundary", "deadline", "view_cap", "unchanged"},
    "later_action_class_counts": {"consistent", "contradictory", "unknown"},
}
TELEMETRY_SCALAR_COUNT_KEYS = {
    "carrier_attempt_count",
    "accepted_revision_count",
    "active_row_count",
    "view_delivery_count",
    "mechanism_initiated_tool_call_count",
    "forced_answer_count",
    "privacy_hit_count",
    "exact_opaque_binding_count",
    "activation_miss_count",
}
TELEMETRY_ENDPOINT_VALUES = {
    "real_model_authorship": {"observed", "untested"},
    "structural_binding": {"observed", "untested"},
    "coverage_state_behavior": {"observed", "untested"},
    "view_delivery": {"observed", "untested"},
    "behavioral_action_choice": {"observed", "untested"},
    "strict_outcome": {"unknown"},
    "protocol_integrity": {"preserved", "invalid"},
}
TELEMETRY_COHORT_KEYS = {
    "strict_pass",
    "known_strict_fail",
    "completed_strict_verdict_unknown",
    "timeout_failure",
    "other_terminal_failure",
}


class CarrierValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class VisibleObservation:
    ref: str
    task_key: str
    boundary: int
    ordinary: bool = True
    visible: bool = True
    success: bool | None = True
    truncated: bool = False
    available: bool = True


@dataclass(frozen=True)
class RowAssessment:
    row_index: int
    coverage: str
    freshness: str
    fault: str
    exact_binding_count: int = 0


@dataclass
class Telemetry:
    carrier_attempt_count: int = 0
    accepted_revision_count: int = 0
    rejection_reason_counts: Counter[str] = field(default_factory=Counter)
    active_row_count: int = 0
    coverage_state_counts: Counter[str] = field(default_factory=Counter)
    freshness_state_counts: Counter[str] = field(default_factory=Counter)
    fault_state_counts: Counter[str] = field(default_factory=Counter)
    selected_action_counts: Counter[str] = field(default_factory=Counter)
    view_delivery_count: int = 0
    cap_and_deadline_suppression_counts: Counter[str] = field(default_factory=Counter)
    later_action_class_counts: Counter[str] = field(default_factory=Counter)
    mechanism_initiated_tool_call_count: int = 0
    forced_answer_count: int = 0
    privacy_hit_count: int = 0
    exact_opaque_binding_count: int = 0
    activation_miss_count: int = 0

    def export(self) -> dict[str, Any]:
        return {
            "schema_version": "g011_g013_integrated_telemetry_v1",
            "carrier_attempt_count": self.carrier_attempt_count,
            "accepted_revision_count": self.accepted_revision_count,
            "rejection_reason_counts": dict(sorted(self.rejection_reason_counts.items())),
            "active_row_count": self.active_row_count,
            "coverage_state_counts": dict(sorted(self.coverage_state_counts.items())),
            "freshness_state_counts": dict(sorted(self.freshness_state_counts.items())),
            "fault_state_counts": dict(sorted(self.fault_state_counts.items())),
            "selected_action_counts": dict(sorted(self.selected_action_counts.items())),
            "view_delivery_count": self.view_delivery_count,
            "cap_and_deadline_suppression_counts": dict(sorted(self.cap_and_deadline_suppression_counts.items())),
            "later_action_class_counts": dict(sorted(self.later_action_class_counts.items())),
            "mechanism_initiated_tool_call_count": self.mechanism_initiated_tool_call_count,
            "forced_answer_count": self.forced_answer_count,
            "privacy_hit_count": self.privacy_hit_count,
            "exact_opaque_binding_count": self.exact_opaque_binding_count,
            "activation_miss_count": self.activation_miss_count,
        }


def _strict_keys(value: dict[str, Any], expected: set[str], reason: str) -> None:
    if set(value) != expected:
        raise CarrierValidationError(reason)


def _valid_token(value: Any) -> bool:
    return isinstance(value, str) and TOKEN_RE.fullmatch(value) is not None


def parse_carrier(text: Any) -> dict[str, Any]:
    """Parse exactly one prefixed JSON object and validate its bounded grammar."""
    if not isinstance(text, str) or not text.strip():
        raise CarrierValidationError("missing")
    stripped = text.strip()
    if stripped.count(CARRIER_PREFIX) != 1 or not stripped.startswith(CARRIER_PREFIX + " "):
        raise CarrierValidationError("mixed_or_duplicate")
    payload_text = stripped[len(CARRIER_PREFIX) :].strip()
    try:
        decoder = json.JSONDecoder()
        value, end = decoder.raw_decode(payload_text)
    except json.JSONDecodeError as exc:
        reason = "truncated" if exc.pos >= max(0, len(payload_text) - 2) else "malformed"
        raise CarrierValidationError(reason) from exc
    if payload_text[end:].strip():
        raise CarrierValidationError("mixed_or_duplicate")
    if not isinstance(value, dict):
        raise CarrierValidationError("malformed")
    allowed = EXPECTED_FIELDS | {"declared_next_action"}
    if set(value) - allowed or not EXPECTED_FIELDS.issubset(value):
        raise CarrierValidationError("additional_or_missing_field")
    if value["schema"] != SCHEMA or not _valid_token(value["state_id"]):
        raise CarrierValidationError("schema_or_token_invalid")
    revision = value["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise CarrierValidationError("revision_invalid")
    supersedes = value["supersedes"]
    if supersedes is not None:
        if not isinstance(supersedes, dict):
            raise CarrierValidationError("revision_invalid")
        _strict_keys(supersedes, {"state_id", "revision"}, "revision_invalid")
        if not _valid_token(supersedes["state_id"]):
            raise CarrierValidationError("revision_invalid")
        prior_revision = supersedes["revision"]
        if isinstance(prior_revision, bool) or not isinstance(prior_revision, int) or prior_revision < 1:
            raise CarrierValidationError("revision_invalid")
    plan_steps = value["plan_steps"]
    if not isinstance(plan_steps, list) or not plan_steps or len(plan_steps) > MAX_PLAN_STEPS:
        raise CarrierValidationError("limit_or_token_invalid")
    if not all(_valid_token(item) for item in plan_steps) or len(set(plan_steps)) != len(plan_steps):
        raise CarrierValidationError("duplicate_or_token_invalid")
    rows = value["requirement_rows"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_REQUIREMENT_ROWS:
        raise CarrierValidationError("limit_or_token_invalid")
    row_ids: list[str] = []
    total_refs = 0
    for row in rows:
        if not isinstance(row, dict):
            raise CarrierValidationError("malformed")
        _strict_keys(row, {"row_id", "step_id", "observation_refs"}, "additional_or_missing_field")
        if not _valid_token(row["row_id"]) or not _valid_token(row["step_id"]):
            raise CarrierValidationError("schema_or_token_invalid")
        row_ids.append(row["row_id"])
        refs = row["observation_refs"]
        if not isinstance(refs, list) or len(refs) > MAX_REFS_PER_ROW:
            raise CarrierValidationError("limit_or_token_invalid")
        if not all(isinstance(ref, str) and OBSERVATION_REF_RE.fullmatch(ref) for ref in refs):
            raise CarrierValidationError("invalid_reference")
        if len(refs) != len(set(refs)):
            raise CarrierValidationError("duplicate")
        total_refs += len(refs)
    if len(row_ids) != len(set(row_ids)):
        raise CarrierValidationError("duplicate")
    if total_refs > MAX_TOTAL_REFS:
        raise CarrierValidationError("limit_or_token_invalid")
    declared = value.get("declared_next_action")
    if declared is not None and declared not in ACTION_STATES:
        raise CarrierValidationError("schema_or_token_invalid")
    return copy.deepcopy(value)


class IntegratedController:
    """Own the single active head, provenance registry, assessment, and view path."""

    def __init__(self, task_key: str = "task", telemetry_path: Path | None = None):
        self.task_key = task_key
        self.telemetry_path = telemetry_path
        self.active_head: dict[str, Any] | None = None
        self.active_boundary: int | None = None
        self.observations: list[VisibleObservation] = []
        self.telemetry = Telemetry()
        self._last_presented_fingerprint: str | None = None
        self._pending_action: str | None = None
        self._suppress_next_view = False

    def register_observation(self, observation: VisibleObservation) -> None:
        self.observations.append(observation)
        if self._pending_action is not None and observation.ordinary:
            classification = "consistent" if self._pending_action in {"acquire_evidence", "refresh_observation"} else "unknown"
            self.telemetry.later_action_class_counts[classification] += 1
            self._pending_action = None
        if self.active_head is not None:
            self._refresh_state_counters()
        self._persist()

    def note_absent_carrier(self) -> None:
        self.telemetry.activation_miss_count += 1
        self._persist()

    def submit_carrier(self, text: Any, boundary: int, *, provider_status: str = "accepted") -> bool:
        self.telemetry.carrier_attempt_count += 1
        if provider_status != "accepted":
            self.telemetry.rejection_reason_counts[provider_status] += 1
            self._suppress_next_view = True
            self._persist()
            return False
        try:
            candidate = parse_carrier(text)
        except CarrierValidationError as exc:
            self.telemetry.rejection_reason_counts[exc.reason] += 1
            self._suppress_next_view = True
            self._persist()
            return False
        if not self._valid_revision(candidate):
            self.telemetry.rejection_reason_counts["revision_invalid"] += 1
            self._suppress_next_view = True
            self._persist()
            return False
        self.active_head = candidate
        self.active_boundary = boundary
        self.telemetry.accepted_revision_count += 1
        self.telemetry.active_row_count = len(candidate["requirement_rows"])
        if self._pending_action is not None:
            classification = "consistent" if self._pending_action in {"revise_requirement_row", "revise_plan", "preserve_unknown"} else "unknown"
            self.telemetry.later_action_class_counts[classification] += 1
            self._pending_action = None
        self._last_presented_fingerprint = None
        self._suppress_next_view = False
        self._refresh_state_counters()
        self._persist()
        return True

    def _valid_revision(self, candidate: dict[str, Any]) -> bool:
        revision = candidate["revision"]
        supersedes = candidate["supersedes"]
        if self.active_head is None:
            return revision == 1 and supersedes is None
        return (
            revision == self.active_head["revision"] + 1
            and supersedes
            == {"state_id": self.active_head["state_id"], "revision": self.active_head["revision"]}
        )

    def _matches(self, ref: str) -> list[VisibleObservation]:
        boundary = self.active_boundary if self.active_boundary is not None else -1
        return [
            item
            for item in self.observations
            if item.ref == ref
            and item.task_key == self.task_key
            and item.boundary < boundary
            and item.ordinary
            and item.visible
        ]

    def assess(self) -> list[RowAssessment]:
        if self.active_head is None:
            return []
        assessments: list[RowAssessment] = []
        for index, row in enumerate(self.active_head["requirement_rows"]):
            refs = row["observation_refs"]
            if not refs:
                assessments.append(RowAssessment(index, "uncovered", "unknown", "missing"))
                continue
            row_matches: list[VisibleObservation] = []
            fault: str | None = None
            for ref in refs:
                matches = self._matches(ref)
                if not matches:
                    same_ref = [item for item in self.observations if item.ref == ref]
                    if any(
                        item.task_key == self.task_key and item.ordinary and item.visible
                        for item in same_ref
                    ):
                        fault = "boundary_mismatch"
                    elif same_ref:
                        fault = "non_visible_reference"
                    else:
                        fault = "invalid_reference"
                    break
                if len(matches) != 1:
                    fault = "duplicate"
                    break
                row_matches.append(matches[0])
            if fault:
                coverage = "ambiguous" if fault == "duplicate" else "unknown"
                assessments.append(RowAssessment(index, coverage, "unknown", fault))
                continue
            if any(item.truncated for item in row_matches):
                assessments.append(RowAssessment(index, "unknown", "unknown", "truncated"))
                continue
            if any(item.success is None for item in row_matches):
                assessments.append(RowAssessment(index, "unknown", "unknown", "instrumentation_loss"))
                continue
            if any(item.success is False for item in row_matches):
                assessments.append(RowAssessment(index, "failed", "current", "none", len(row_matches)))
                continue
            if any(not item.available for item in row_matches):
                assessments.append(RowAssessment(index, "unavailable", "current", "none", len(row_matches)))
                continue
            newest_bound = max(item.boundary for item in row_matches)
            later = any(
                item.task_key == self.task_key
                and item.ordinary
                and item.visible
                and item.boundary > newest_bound
                for item in self.observations
            )
            assessments.append(RowAssessment(index, "observed", "stale" if later else "current", "none", len(row_matches)))
        return assessments

    def select_action(self, assessments: list[RowAssessment] | None = None) -> tuple[str, int | None]:
        rows = assessments if assessments is not None else self.assess()
        if not rows:
            return "preserve_unknown", None
        for row in rows:
            if row.fault in {"instrumentation_loss", "boundary_mismatch", "malformed", "truncated", "unknown", "invalid_reference", "non_visible_reference", "duplicate"}:
                return "preserve_unknown", row.row_index
        for row in rows:
            if row.freshness == "stale":
                return "refresh_observation", row.row_index
        for row in rows:
            if row.coverage in {"uncovered", "failed", "unavailable"}:
                return "acquire_evidence", row.row_index
        plan_steps = set(self.active_head["plan_steps"]) if self.active_head else set()
        for index, row in enumerate(self.active_head["requirement_rows"] if self.active_head else []):
            if row["step_id"] not in plan_steps:
                return "revise_requirement_row", index
        mapped_steps = {row["step_id"] for row in self.active_head["requirement_rows"]} if self.active_head else set()
        if plan_steps - mapped_steps:
            return "revise_plan", None
        return "proceed", None

    def maybe_view(self, *, remaining_seconds: float | None, boundary_known: bool = True) -> str | None:
        if self._suppress_next_view:
            self._suppress_next_view = False
            return None
        if self.active_head is None or not boundary_known:
            if not boundary_known:
                self.telemetry.cap_and_deadline_suppression_counts["unknown_boundary"] += 1
            self._persist()
            return None
        action, row_index = self.select_action()
        self.telemetry.selected_action_counts[action] += 1
        if action == "proceed":
            self._persist()
            return None
        if remaining_seconds is not None and remaining_seconds <= DEADLINE_GUARD_SECONDS:
            self.telemetry.cap_and_deadline_suppression_counts["deadline"] += 1
            self._persist()
            return None
        if self.telemetry.view_delivery_count >= MAX_VIEWS_PER_TASK:
            self.telemetry.cap_and_deadline_suppression_counts["view_cap"] += 1
            self._persist()
            return None
        rows = self.assess()
        selected = rows[row_index] if row_index is not None else None
        view = {
            "schema": "revisioned_requirement_evidence_view_v1",
            "selected_action": action,
            "target": f"row_{row_index + 1}" if row_index is not None else "active_plan",
            "coverage": selected.coverage if selected else "unknown",
            "freshness": selected.freshness if selected else "unknown",
            "fault": selected.fault if selected else "none",
            "semantic_status": "unknown",
        }
        fingerprint = json.dumps(view, sort_keys=True, separators=(",", ":"))
        if fingerprint == self._last_presented_fingerprint:
            self.telemetry.cap_and_deadline_suppression_counts["unchanged"] += 1
            self._persist()
            return None
        self._last_presented_fingerprint = fingerprint
        self.telemetry.view_delivery_count += 1
        self._pending_action = action
        self._persist()
        return VIEW_PREFIX + " " + json.dumps(view, sort_keys=True, separators=(",", ":"))

    def finalize(self) -> dict[str, Any]:
        exported = self.telemetry.export()
        activated = exported["accepted_revision_count"] > 0
        delivered = exported["view_delivery_count"] > 0
        measured = sum(exported["later_action_class_counts"].values()) > 0
        exported["endpoints"] = {
            "real_model_authorship": "observed" if activated else "untested",
            "structural_binding": "observed" if exported["exact_opaque_binding_count"] > 0 else "untested",
            "coverage_state_behavior": "observed" if activated else "untested",
            "view_delivery": "observed" if delivered else "untested",
            "behavioral_action_choice": "observed" if measured else "untested",
            "strict_outcome": "unknown",
            "protocol_integrity": "preserved" if exported["privacy_hit_count"] == 0 else "invalid",
        }
        exported["cohort_denominators"] = {
            "strict_pass": 0,
            "known_strict_fail": 0,
            "completed_strict_verdict_unknown": 0,
            "timeout_failure": 0,
            "other_terminal_failure": 0,
        }
        exported["pooled_rates_emitted"] = False
        assert_export_safe(exported)
        return exported

    def _refresh_state_counters(self) -> None:
        assessments = self.assess()
        self.telemetry.coverage_state_counts = Counter(row.coverage for row in assessments)
        self.telemetry.freshness_state_counts = Counter(row.freshness for row in assessments)
        self.telemetry.fault_state_counts = Counter(row.fault for row in assessments)
        self.telemetry.exact_opaque_binding_count = sum(row.exact_binding_count for row in assessments)

    def _persist(self) -> None:
        if self.telemetry_path is None:
            return
        payload = self.finalize()
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        self.telemetry_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="ascii")


def assert_export_safe(payload: Any) -> None:
    """Validate the complete aggregate-only telemetry schema before export."""

    def require_dict(value: Any, expected: set[str], location: str) -> dict[str, Any]:
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError(f"telemetry {location} must be an object with string keys")
        unknown = set(value) - expected
        missing = expected - set(value)
        if unknown or missing:
            raise ValueError(
                f"telemetry {location} schema mismatch: unknown={sorted(unknown)} missing={sorted(missing)}"
            )
        return value

    def require_count(value: Any, location: str) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > MAX_TELEMETRY_COUNT
        ):
            raise ValueError(f"telemetry {location} must be a bounded nonnegative integer")

    top_level_keys = (
        {"schema_version", "endpoints", "cohort_denominators", "pooled_rates_emitted"}
        | TELEMETRY_SCALAR_COUNT_KEYS
        | set(TELEMETRY_COUNTER_KEYS)
    )
    root = require_dict(payload, top_level_keys, "root")
    if root["schema_version"] != "g011_g013_integrated_telemetry_v1":
        raise ValueError("telemetry schema_version is invalid")
    for key in TELEMETRY_SCALAR_COUNT_KEYS:
        require_count(root[key], key)
    for key, allowed_keys in TELEMETRY_COUNTER_KEYS.items():
        counters = root[key]
        if not isinstance(counters, dict) or any(not isinstance(name, str) for name in counters):
            raise ValueError(f"telemetry {key} must be an object with string keys")
        unknown = set(counters) - allowed_keys
        if unknown:
            raise ValueError(f"telemetry {key} has unknown keys: {sorted(unknown)}")
        for name, count in counters.items():
            require_count(count, f"{key}.{name}")
    endpoints = require_dict(root["endpoints"], set(TELEMETRY_ENDPOINT_VALUES), "endpoints")
    for key, allowed_values in TELEMETRY_ENDPOINT_VALUES.items():
        value = endpoints[key]
        if not isinstance(value, str) or len(value) > 32 or value not in allowed_values:
            raise ValueError(f"telemetry endpoints.{key} is invalid")
    cohorts = require_dict(root["cohort_denominators"], TELEMETRY_COHORT_KEYS, "cohort_denominators")
    for key, count in cohorts.items():
        require_count(count, f"cohort_denominators.{key}")
    if root["pooled_rates_emitted"] is not False:
        raise ValueError("telemetry pooled_rates_emitted must be false")


def redact_carriers(value: Any) -> Any:
    """Remove carrier-bearing strings from operational logs and serialized agent state."""
    if isinstance(value, dict):
        return {key: redact_carriers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact_carriers(child) for child in value]
    if isinstance(value, tuple):
        return [redact_carriers(child) for child in value]
    if isinstance(value, str) and CARRIER_PREFIX in value:
        return "[INTEGRATED_STRUCTURAL_CARRIER_REDACTED]"
    return value


def _tool_call_parts(tool_call: Any) -> tuple[str | None, str | None, dict[str, Any] | None]:
    function = getattr(tool_call, "function", None)
    name = getattr(function, "name", None)
    raw = getattr(function, "arguments", None)
    try:
        args = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        return name, getattr(tool_call, "id", None), None
    return name, getattr(tool_call, "id", None), args if isinstance(args, dict) else None


def _sanitize_tool_call(tool_call: Any, args: dict[str, Any]) -> Any:
    serialized = json.dumps(args)
    try:
        tool_call.function.arguments = serialized
        return tool_call
    except (AttributeError, TypeError, ValueError):
        pass

    class FunctionProxy:
        def __init__(self, name: str | None, arguments: str):
            self.name = name
            self.arguments = arguments

    class ToolCallProxy:
        def __init__(self):
            self.id = getattr(tool_call, "id", None)
            self.type = getattr(tool_call, "type", "function")
            self.function = FunctionProxy(getattr(getattr(tool_call, "function", None), "name", None), serialized)

        def model_dump(self) -> dict[str, Any]:
            return {"id": self.id, "type": self.type, "function": {"name": self.function.name, "arguments": self.function.arguments}}

    return ToolCallProxy()


def _response_has_carrier(response: Any, record_tool_name: str) -> bool:
    """Inspect one provider response without mutating it or persisting its content."""
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls is None and isinstance(response, dict):
        tool_calls = response.get("tool_calls")
    if not isinstance(tool_calls, (list, tuple)):
        return False
    for tool_call in tool_calls:
        name, _, tool_args = _tool_call_parts(tool_call)
        if tool_args is None:
            continue
        if name == record_tool_name:
            value = tool_args.get("freeform")
            if isinstance(value, str) and CARRIER_PREFIX in value:
                return True
        sidecar = tool_args.get("self_observation")
        if isinstance(sidecar, dict):
            value = sidecar.get("freeform")
            if isinstance(value, str) and CARRIER_PREFIX in value:
                return True
    return False


def install_integrated_agent(data_agent_module: Any, args: Any) -> dict[str, Any]:
    """Install one integrated carrier/controller/view path; disabled mode is inert."""
    if not getattr(args, "enable_g011_g013_integrated", False):
        return {"installed": False, "reason": "disabled"}
    if getattr(args, "disable_self_observation_tool", False):
        raise ValueError("integrated G11-G13 mode requires the configured self-observation boundary")
    if getattr(args, "enable_g0132_task_workspace", False):
        raise ValueError("integrated G11-G13 mode cannot be combined with G13.2 workspace")
    original_agent = data_agent_module.DataAgent
    record_tool_name = getattr(args, "self_observation_tool_name", "record_self_observation")
    install_config = (SCHEMA, record_tool_name)
    prior_config = getattr(original_agent, "__g011_g013_integrated_config__", None)
    if prior_config is not None:
        if prior_config != install_config:
            raise ValueError("conflicting integrated G11-G13 reinstallation")
        attachment = getattr(original_agent, "__g011_g013_integrated_attachment__", None)
        if not isinstance(attachment, dict):
            raise ValueError("integrated G11-G13 installation marker is incomplete")
        return attachment

    class IntegratedDataAgent(original_agent):
        def __init__(self, *agent_args: Any, **agent_kwargs: Any):
            super().__init__(*agent_args, **agent_kwargs)
            log_path = Path(self.tool_log_path).parent / "g011_g013_integrated_telemetry.json"
            self.g011_g013_controller = IntegratedController(task_key="current_task", telemetry_path=log_path)
            self._g011_g013_boundary = 0
            self._g011_g013_started_at = time.monotonic()

        def _handle_tool_call(self, tool_call: Any):
            self._g011_g013_boundary += 1
            boundary = self._g011_g013_boundary
            name, tool_call_id, tool_args = _tool_call_parts(tool_call)
            carrier: Any = None
            if tool_args is not None and name == record_tool_name:
                carrier = tool_args.get("freeform")
                if isinstance(carrier, str) and CARRIER_PREFIX in carrier:
                    self.g011_g013_controller.submit_carrier(carrier, boundary)
                    sanitized = dict(tool_args)
                    sanitized["freeform"] = "Integrated structural carrier processed; raw payload suppressed."
                    tool_call = _sanitize_tool_call(tool_call, sanitized)
            elif tool_args is not None and isinstance(tool_args.get("self_observation"), dict):
                sidecar = dict(tool_args["self_observation"])
                carrier = sidecar.get("freeform")
                if isinstance(carrier, str) and CARRIER_PREFIX in carrier:
                    self.g011_g013_controller.submit_carrier(carrier, boundary)
                    sanitized = dict(tool_args)
                    sanitized.pop("self_observation", None)
                    tool_call = _sanitize_tool_call(tool_call, sanitized)
            result = super()._handle_tool_call(tool_call)
            if name not in {record_tool_name, "return_answer", None} and tool_call_id:
                ref = f"var_{tool_call_id}"
                success = result.get("success") if isinstance(result, dict) else None
                if success is None and isinstance(getattr(self, "result_storage", None), dict):
                    success = True if ref in self.result_storage else None
                self.g011_g013_controller.register_observation(
                    VisibleObservation(ref=ref, task_key="current_task", boundary=boundary, success=success)
                )
            return result

        def call_llm(self):
            remaining = getattr(self, "remaining_seconds", None)
            if remaining is None:
                remaining = 1200.0 - (time.monotonic() - self._g011_g013_started_at)
            view = self.g011_g013_controller.maybe_view(remaining_seconds=remaining, boundary_known=True)
            if view is not None:
                self.messages.append({"role": "user", "content": view})
            response = super().call_llm()
            if response is not None and not _response_has_carrier(response, record_tool_name):
                self.g011_g013_controller.note_absent_carrier()
            return response

        def to_dict(self):
            value = super().to_dict()
            if isinstance(value, dict):
                value = redact_carriers(value)
                value["g011_g013_integrated"] = self.g011_g013_controller.finalize()
            return value

    attachment = {
        "installed": True,
        "schema": SCHEMA,
        "carrier_prefix": CARRIER_PREFIX,
        "max_views_per_task": MAX_VIEWS_PER_TASK,
        "deadline_guard_seconds": DEADLINE_GUARD_SECONDS,
    }
    IntegratedDataAgent.__g011_g013_integrated_config__ = install_config
    IntegratedDataAgent.__g011_g013_integrated_attachment__ = attachment
    data_agent_module.DataAgent = IntegratedDataAgent
    return attachment
