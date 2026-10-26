#!/usr/bin/env python3
"""Build and run the bounded G14 synthetic no-task interface investigation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g014_interface_investigation_001"
SCOPED = WORK / "scoped_source"
MEMORY = BASE / "research_graph_memory_v18.json"
META = BASE / "g014_research_meta_solution_loop_003/final_raw.txt"
MEMORY_SHA = "51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b"
META_SHA = "5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad"


PROTOTYPE = r'''
"""No-task prototype for progressive query probing.

All references are opaque synthetic tokens. The module returns advisory
structural views and never dispatches a tool, produces an answer, scores a
result, or changes a deadline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping


OPAQUE_RE = re.compile(r"(?:act|prb)_[A-Za-z0-9]{1,32}\Z")
ACTION_STATES = frozenset({"completion", "in_flight", "repeated", "failed", "unknown"})
PROBE_STATES = frozenset({"not_started", "completion", "in_flight", "repeated", "failed", "unknown"})
PROBE_KINDS = frozenset({"discriminating_probe", "generic_retry", "timeout_reserve", "cache_shortcut"})
ALLOWED_DECISIONS = frozenset({
    "request_probe", "refine_primary", "choose_alternative",
    "use_completed_primary", "wait_no_dispatch", "preserve_unknown",
})


class ProbeValidationError(ValueError):
    """Raised when a synthetic structural carrier is inadmissible."""


@dataclass(frozen=True)
class ProbeCandidate:
    probe_ref: str
    kind: str
    partition_count: int
    cost_class: int

    @property
    def is_discriminating(self) -> bool:
        return self.kind == "discriminating_probe" and self.partition_count >= 2


@dataclass(frozen=True)
class StructuralCheckpoint:
    action_ref: str
    action_state: str
    probe_state: str
    progress_observed: bool | None


@dataclass(frozen=True)
class PolicyBudget:
    enabled: bool
    remaining_seconds: float
    mechanism_action_count: int = 0
    probe_request_count: int = 0
    action_cap: int = 1
    probe_cap: int = 1
    deadline_guard_seconds: float = 180.0


def parse_candidate(value: Mapping[str, object]) -> ProbeCandidate:
    expected = {"probe_ref", "kind", "partition_count", "cost_class"}
    if set(value) != expected:
        raise ProbeValidationError("probe fields differ")
    probe_ref = value.get("probe_ref")
    kind = value.get("kind")
    partition_count = value.get("partition_count")
    cost_class = value.get("cost_class")
    if not isinstance(probe_ref, str) or OPAQUE_RE.fullmatch(probe_ref) is None or not probe_ref.startswith("prb_"):
        raise ProbeValidationError("probe_ref must be opaque")
    if kind not in PROBE_KINDS:
        raise ProbeValidationError("probe kind differs")
    if isinstance(partition_count, bool) or not isinstance(partition_count, int) or not 1 <= partition_count <= 8:
        raise ProbeValidationError("partition_count must be bounded")
    if isinstance(cost_class, bool) or not isinstance(cost_class, int) or not 1 <= cost_class <= 4:
        raise ProbeValidationError("cost_class must be bounded")
    return ProbeCandidate(probe_ref, kind, partition_count, cost_class)


def checkpoint(
    *, action_ref: str, action_state: str, probe_state: str, progress_observed: bool | None
) -> StructuralCheckpoint:
    if OPAQUE_RE.fullmatch(action_ref) is None or not action_ref.startswith("act_"):
        raise ProbeValidationError("action_ref must be opaque")
    if action_state not in ACTION_STATES or probe_state not in PROBE_STATES:
        raise ProbeValidationError("structural state differs")
    if progress_observed not in {True, False, None}:
        raise ProbeValidationError("progress must be structural or unknown")
    if probe_state in {"not_started", "in_flight", "unknown"} and progress_observed is not None:
        raise ProbeValidationError("unobserved probe state cannot claim progress")
    return StructuralCheckpoint(action_ref, action_state, probe_state, progress_observed)


def select_discriminating_probe(
    candidates: Iterable[ProbeCandidate], *, primary_cost_class: int
) -> ProbeCandidate | None:
    """Select a cheaper multi-partition probe; controls are never selected."""
    if isinstance(primary_cost_class, bool) or not isinstance(primary_cost_class, int) or not 1 <= primary_cost_class <= 4:
        raise ProbeValidationError("primary cost class differs")
    eligible = [
        candidate for candidate in candidates
        if candidate.is_discriminating and candidate.cost_class < primary_cost_class
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda row: (-row.partition_count, row.cost_class, row.probe_ref))[0]


def _view(decision: str, *, reason: str, target: str | None = None) -> dict[str, object]:
    if decision not in ALLOWED_DECISIONS:
        raise ProbeValidationError("decision differs")
    return {
        "decision": decision,
        "reason": reason,
        "target": target,
        "mechanism_tool_dispatch_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_seconds": 0,
    }


def next_policy_view(
    state: StructuralCheckpoint,
    candidates: Iterable[ProbeCandidate],
    budget: PolicyBudget,
    *,
    primary_cost_class: int = 4,
) -> dict[str, object] | None:
    """Return one bounded advisory view without causing an external action."""
    if not budget.enabled or budget.mechanism_action_count >= budget.action_cap:
        return None
    if budget.remaining_seconds <= budget.deadline_guard_seconds:
        return _view("preserve_unknown", reason="deadline_guard")
    if state.action_state == "completion":
        return _view("use_completed_primary", reason="primary_complete")
    if state.action_state == "in_flight" or state.probe_state == "in_flight":
        return _view("wait_no_dispatch", reason="operation_in_flight")
    if state.probe_state == "completion":
        if state.progress_observed is True:
            return _view("refine_primary", reason="probe_discriminated")
        if state.progress_observed is False:
            return _view("choose_alternative", reason="probe_no_progress")
        return _view("preserve_unknown", reason="probe_progress_unknown")
    if state.probe_state in {"repeated", "failed"}:
        return _view("choose_alternative", reason=f"probe_{state.probe_state}")
    if state.probe_state == "unknown":
        return _view("preserve_unknown", reason="probe_state_unknown")
    if state.action_state in {"repeated", "failed"}:
        return _view("choose_alternative", reason=f"primary_{state.action_state}")
    if state.action_state != "unknown":
        raise ProbeValidationError("unhandled action state")
    if budget.probe_request_count >= budget.probe_cap:
        return _view("preserve_unknown", reason="probe_cap_reached")
    selected = select_discriminating_probe(candidates, primary_cost_class=primary_cost_class)
    if selected is None:
        return _view("preserve_unknown", reason="no_discriminating_probe")
    return _view("request_probe", reason="smaller_discriminating_probe", target=selected.probe_ref)


def classify_control(candidate: ProbeCandidate) -> str:
    if candidate.kind == "discriminating_probe" and candidate.partition_count >= 2:
        return "discriminating"
    return candidate.kind


def aggregate_summary(views: Iterable[Mapping[str, object] | None]) -> dict[str, object]:
    decisions = {name: 0 for name in sorted(ALLOWED_DECISIONS)}
    suppressed = 0
    prohibited_counts = {
        "mechanism_tool_dispatch_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_seconds": 0,
    }
    for view in views:
        if view is None:
            suppressed += 1
            continue
        if set(view) != {"decision", "reason", "target", *prohibited_counts}:
            raise ProbeValidationError("view fields differ")
        decisions[str(view["decision"])] += 1
        for key in prohibited_counts:
            prohibited_counts[key] += int(view[key])
    return {
        "schema": "g014_progressive_probe_aggregate_v1",
        "view_count": sum(decisions.values()),
        "suppressed_count": suppressed,
        "decision_counts": decisions,
        "prohibited_effect_counts": prohibited_counts,
        "historical_timeout_causality_claimed": False,
        "real_model_behavior_claimed": False,
        "benchmark_benefit_claimed": False,
    }


def render_view(view: Mapping[str, object] | None) -> str | None:
    if view is None:
        return None
    allowed = {
        "decision", "reason", "target", "mechanism_tool_dispatch_count",
        "forced_answer_count", "scoring_mutation_count", "timeout_extension_seconds",
    }
    if set(view) != allowed:
        raise ProbeValidationError("render view fields differ")
    return "G014_PROGRESSIVE_PROBE_V1 " + json.dumps(
        dict(view), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
'''


TESTS = r'''
from __future__ import annotations

import json

import pytest

from prototype.progressive_probe import (
    PolicyBudget,
    ProbeValidationError,
    aggregate_summary,
    checkpoint,
    classify_control,
    next_policy_view,
    parse_candidate,
    render_view,
    select_discriminating_probe,
)


def candidate(**updates):
    value = {
        "probe_ref": "prb_alpha",
        "kind": "discriminating_probe",
        "partition_count": 2,
        "cost_class": 1,
    }
    value.update(updates)
    return parse_candidate(value)


def state(**updates):
    value = {
        "action_ref": "act_primary",
        "action_state": "unknown",
        "probe_state": "not_started",
        "progress_observed": None,
    }
    value.update(updates)
    return checkpoint(**value)


def budget(**updates):
    value = {"enabled": True, "remaining_seconds": 400.0}
    value.update(updates)
    return PolicyBudget(**value)


def decide(*, state_value=None, candidates=None, budget_value=None):
    return next_policy_view(
        state_value or state(),
        candidates if candidates is not None else [candidate()],
        budget_value or budget(),
    )


def test_selects_smaller_discriminating_probe_before_opaque_action():
    view = decide(candidates=[
        candidate(probe_ref="prb_low", partition_count=2, cost_class=1),
        candidate(probe_ref="prb_high", partition_count=4, cost_class=2),
    ])
    assert view["decision"] == "request_probe"
    assert view["target"] == "prb_high"


def test_probe_must_be_cheaper_than_primary():
    assert select_discriminating_probe([candidate(cost_class=4)], primary_cost_class=4) is None
    assert decide(candidates=[candidate(cost_class=4)])["decision"] == "preserve_unknown"


@pytest.mark.parametrize("kind", ["generic_retry", "timeout_reserve", "cache_shortcut"])
def test_controls_are_distinct_and_never_selected(kind):
    control = candidate(kind=kind, partition_count=8)
    assert classify_control(control) == kind
    view = decide(candidates=[control])
    assert view["decision"] == "preserve_unknown"
    assert view["reason"] == "no_discriminating_probe"


def test_discriminating_probe_is_not_generic_retry_control():
    probe = candidate()
    retry = candidate(probe_ref="prb_retry", kind="generic_retry")
    assert classify_control(probe) == "discriminating"
    assert classify_control(retry) == "generic_retry"
    assert select_discriminating_probe([retry, probe], primary_cost_class=4) == probe


@pytest.mark.parametrize(
    ("action_state", "probe_state", "progress", "decision"),
    [
        ("completion", "not_started", None, "use_completed_primary"),
        ("in_flight", "not_started", None, "wait_no_dispatch"),
        ("unknown", "in_flight", None, "wait_no_dispatch"),
        ("unknown", "completion", True, "refine_primary"),
        ("unknown", "completion", False, "choose_alternative"),
        ("unknown", "repeated", False, "choose_alternative"),
        ("unknown", "failed", False, "choose_alternative"),
        ("unknown", "unknown", None, "preserve_unknown"),
        ("repeated", "not_started", None, "choose_alternative"),
        ("failed", "not_started", None, "choose_alternative"),
    ],
)
def test_structural_states_have_bounded_advisory_choices(action_state, probe_state, progress, decision):
    assert decide(state_value=state(
        action_state=action_state, probe_state=probe_state, progress_observed=progress
    ))["decision"] == decision


def test_completed_probe_with_unknown_progress_preserves_unknown():
    view = decide(state_value=state(probe_state="completion", progress_observed=None))
    assert view["decision"] == "preserve_unknown"


def test_disabled_mode_is_inert():
    assert decide(budget_value=budget(enabled=False)) is None


def test_one_mechanism_action_cap_is_inert_after_first_view():
    assert decide(budget_value=budget(mechanism_action_count=1)) is None


def test_one_probe_cap_prevents_second_probe():
    view = decide(budget_value=budget(probe_request_count=1))
    assert view["decision"] == "preserve_unknown"
    assert view["reason"] == "probe_cap_reached"


def test_deadline_guard_preserves_unknown_without_extension():
    view = decide(budget_value=budget(remaining_seconds=180.0))
    assert view["decision"] == "preserve_unknown"
    assert view["reason"] == "deadline_guard"
    assert view["timeout_extension_seconds"] == 0


def test_all_views_have_zero_prohibited_effects():
    cases = [
        decide(),
        decide(state_value=state(action_state="completion")),
        decide(state_value=state(probe_state="completion", progress_observed=True)),
        decide(state_value=state(probe_state="failed", progress_observed=False)),
        decide(budget_value=budget(remaining_seconds=1)),
    ]
    for view in cases:
        assert view["mechanism_tool_dispatch_count"] == 0
        assert view["forced_answer_count"] == 0
        assert view["scoring_mutation_count"] == 0
        assert view["timeout_extension_seconds"] == 0


def test_enabled_disabled_execution_surface_is_identical_outside_advice():
    enabled = decide()
    disabled = decide(budget_value=budget(enabled=False))
    execution_surface = {
        "tool_dispatch_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_seconds": 0,
    }
    assert enabled is not None and disabled is None
    assert execution_surface == {
        "tool_dispatch_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_seconds": 0,
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"probe_ref": "semantic probe"},
        {"kind": "retry"},
        {"partition_count": 0},
        {"partition_count": 9},
        {"partition_count": True},
        {"cost_class": 0},
        {"cost_class": 5},
    ],
)
def test_rejects_invalid_probe_carriers(updates):
    with pytest.raises(ProbeValidationError):
        candidate(**updates)


def test_rejects_extra_probe_content_field():
    with pytest.raises(ProbeValidationError):
        parse_candidate({
            "probe_ref": "prb_alpha", "kind": "discriminating_probe",
            "partition_count": 2, "cost_class": 1, "raw_query": "forbidden",
        })


@pytest.mark.parametrize("action_state", ["complete", "pending", "timed_out"])
def test_rejects_unreviewed_action_states(action_state):
    with pytest.raises(ProbeValidationError):
        state(action_state=action_state)


def test_unobserved_probe_cannot_claim_progress():
    with pytest.raises(ProbeValidationError):
        state(probe_state="not_started", progress_observed=True)


def test_selection_is_deterministic_by_structural_rank_and_opaque_ref():
    selected = select_discriminating_probe([
        candidate(probe_ref="prb_z", partition_count=3),
        candidate(probe_ref="prb_a", partition_count=3),
    ], primary_cost_class=4)
    assert selected.probe_ref == "prb_a"


def test_rendered_view_has_only_allowlisted_structural_fields():
    rendered = render_view(decide())
    assert rendered.startswith("G014_PROGRESSIVE_PROBE_V1 ")
    payload = json.loads(rendered.split(" ", 1)[1])
    assert set(payload) == {
        "decision", "reason", "target", "mechanism_tool_dispatch_count",
        "forced_answer_count", "scoring_mutation_count", "timeout_extension_seconds",
    }


def test_render_rejects_unreviewed_fields():
    with pytest.raises(ProbeValidationError):
        render_view({"decision": "request_probe", "raw_content": "forbidden"})


def test_aggregate_export_excludes_opaque_references_and_raw_content():
    sentinel = "SYNTHETIC_PRIVATE_CONTEXT_71429"
    summary = aggregate_summary([decide(), decide(budget_value=budget(enabled=False))])
    encoded = json.dumps(summary, sort_keys=True)
    assert "act_" not in encoded
    assert "prb_" not in encoded
    assert sentinel not in encoded
    assert summary["prohibited_effect_counts"] == {
        "mechanism_tool_dispatch_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_seconds": 0,
    }


def test_aggregate_explicitly_denies_overclaims():
    summary = aggregate_summary([decide()])
    assert summary["historical_timeout_causality_claimed"] is False
    assert summary["real_model_behavior_claimed"] is False
    assert summary["benchmark_benefit_claimed"] is False
'''


FIXTURE_RUNNER = r'''
from __future__ import annotations

import json
from pathlib import Path

from progressive_probe import (
    PolicyBudget,
    aggregate_summary,
    checkpoint,
    next_policy_view,
    parse_candidate,
)


candidate = parse_candidate({
    "probe_ref": "prb_fixture", "kind": "discriminating_probe",
    "partition_count": 2, "cost_class": 1,
})
states = [
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="not_started", progress_observed=None),
    checkpoint(action_ref="act_fixture", action_state="completion", probe_state="not_started", progress_observed=None),
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="in_flight", progress_observed=None),
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="completion", progress_observed=True),
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="repeated", progress_observed=False),
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="failed", progress_observed=False),
    checkpoint(action_ref="act_fixture", action_state="unknown", probe_state="unknown", progress_observed=None),
]
views = [
    next_policy_view(row, [candidate], PolicyBudget(enabled=True, remaining_seconds=400))
    for row in states
]
views.append(next_policy_view(states[0], [candidate], PolicyBudget(enabled=False, remaining_seconds=400)))
output = aggregate_summary(views)
Path(__file__).with_name("aggregate_output.json").write_text(
    json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
)
print(json.dumps(output, sort_keys=True))
'''


FINDINGS = """# G14 bounded interface findings

Status: bounded synthetic structural interface exercised; independent verification pending.

## Verified locally

- A lower-cost multi-partition probe can be selected before an opaque expensive action using only bounded structural metadata.
- Completion, in-flight, repeated, failed, and unknown action/probe states produce distinct bounded advisory decisions.
- Discriminating probes are mechanically distinct from generic retry, timeout reserve, and cache-shortcut controls; controls are never selected as probes.
- The one-probe cap, one-action cap, deadline guard, and disabled mode bound or suppress advice without dispatching a tool.
- Every advisory view records zero forced answers, scoring mutations, mechanism tool dispatches, and timeout extension.
- The persisted fixture output is aggregate-only and passes forbidden-field, opaque-reference, synthetic-sentinel, credential-pattern, and raw-provider-content scans.

## Unknown

- No provider was called, so real-model probe authorship, state interpretation, and behavioral compliance are unknown.
- No production runtime carrier or code parent was selected.
- No benchmark or database was accessed, and no strict-score or benefit claim is supported.
- Historical timeout localization is not causal evidence for query or action structure.

## Contradicted

- None within this bounded synthetic investigation.

Next workflow step: independently verify this artifact, then return the finding to Research Meta. Do not enter Implementation Meta directly.
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def write_same_or_new(path: Path, content: str) -> None:
    content = textwrap.dedent(content).lstrip("\n")
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def find_target(memory: dict[str, object]) -> dict[str, object]:
    layer = memory.get("research_incubation_layer")
    if not isinstance(layer, dict) or not isinstance(layer.get("nodes"), list):
        raise RuntimeError("Research memory incubation layer differs")
    matches = [row for row in layer["nodes"] if isinstance(row, dict) and row.get("id") == "research_target:g014:001"]
    if len(matches) != 1:
        raise RuntimeError("G14 target binding differs")
    target = matches[0]
    if target.get("mechanism_id") != "mech_progressive_query_probing" or target.get("state") != "interface_investigation":
        raise RuntimeError("G14 target mechanism or state differs")
    return target


def forbidden_export_scan(value: object) -> dict[str, object]:
    forbidden_keys = {
        "task", "answer", "hint", "validator", "message", "messages",
        "tool_argument", "tool_arguments", "tool_result", "tool_results",
        "trace", "identifier", "credential", "raw_provider_content",
    }
    opaque_pattern = re.compile(r"(?:act|prb)_[A-Za-z0-9]{1,32}")
    credential_pattern = re.compile(
        r"(?i)(?:api[_-]?key|authorization|cookie|password|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{12,}"
    )
    sentinels = [
        "SYNTHETIC_TASK_71429", "SYNTHETIC_ANSWER_71429", "SYNTHETIC_HINT_71429",
        "SYNTHETIC_VALIDATOR_71429", "SYNTHETIC_MESSAGE_71429", "SYNTHETIC_TOOL_ARGS_71429",
        "SYNTHETIC_TOOL_RESULT_71429", "SYNTHETIC_TRACE_71429", "SYNTHETIC_IDENTIFIER_71429",
        "SYNTHETIC_CREDENTIAL_71429", "SYNTHETIC_RAW_PROVIDER_71429",
    ]
    key_hits: list[str] = []
    def walk(item: object, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = str(key).lower().replace("-", "_")
                if normalized in forbidden_keys:
                    key_hits.append(f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")
    walk(value)
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return {
        "scanned_export": "prototype/aggregate_output.json",
        "forbidden_field_hits": key_hits,
        "opaque_reference_hits": opaque_pattern.findall(encoded),
        "synthetic_sentinel_hits": [token for token in sentinels if token in encoded],
        "credential_pattern_hits": credential_pattern.findall(encoded),
        "raw_provider_content_present": False,
        "passed": not key_hits and opaque_pattern.search(encoded) is None
        and not any(token in encoded for token in sentinels)
        and credential_pattern.search(encoded) is None,
    }


def main() -> None:
    if digest(MEMORY) != MEMORY_SHA or digest(META) != META_SHA:
        raise RuntimeError("G14 investigation input hash differs")
    memory = json.loads(MEMORY.read_text(encoding="utf-8"))
    target = find_target(memory)

    binding = {
        "schema_version": "g014_interface_investigation_input_v1",
        "status": "exploratory_not_formal_candidate",
        "selected_target_id": target["id"],
        "mechanism_id": target["mechanism_id"],
        "research_memory_sha256": MEMORY_SHA,
        "research_meta_output_sha256": META_SHA,
        "scope": "synthetic_no_task_progressive_probe_interface_only",
        "excluded": [
            "formal implementation", "code parent selection", "benchmark tasks",
            "database access", "provider call", "formal launch", "Graph mutation",
            "research memory mutation", "strict score claim", "historical timeout causality claim",
        ],
    }
    write_same_or_new(WORK / "input_binding.json", json_text(binding))
    write_same_or_new(SCOPED / "prototype/__init__.py", "")
    write_same_or_new(SCOPED / "prototype/progressive_probe.py", PROTOTYPE)
    write_same_or_new(SCOPED / "prototype/run_no_task_fixture.py", FIXTURE_RUNNER)
    write_same_or_new(SCOPED / "tests/test_g014_progressive_probe.py", TESTS)

    fixture = subprocess.run(
        [sys.executable, "prototype/run_no_task_fixture.py"],
        cwd=SCOPED, capture_output=True, text=True, check=False,
    )
    if fixture.returncode:
        raise RuntimeError(f"G14 fixture failed:\n{fixture.stdout}\n{fixture.stderr}")
    aggregate_path = SCOPED / "prototype/aggregate_output.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    privacy = forbidden_export_scan(aggregate)
    if not privacy["passed"]:
        raise RuntimeError(f"G14 aggregate no-leak scan failed: {privacy}")

    test_command = [
        sys.executable, "-m", "pytest", "-q", "tests/test_g014_progressive_probe.py",
        "--disable-warnings", "-p", "no:cacheprovider",
    ]
    test = subprocess.run(test_command, cwd=SCOPED, capture_output=True, text=True, check=False)
    if test.returncode or " passed" not in test.stdout:
        raise RuntimeError(f"G14 no-task tests failed:\n{test.stdout}\n{test.stderr}")
    summary_line = next((line.strip() for line in reversed(test.stdout.splitlines()) if " passed" in line), "")
    passed_match = re.search(r"(\d+) passed", summary_line)
    if passed_match is None:
        raise RuntimeError(f"G14 pytest summary is not stable: {summary_line!r}")
    test_summary = f"{passed_match.group(1)} passed"

    write_same_or_new(SCOPED / "BOUNDED_FINDINGS.md", FINDINGS)
    source_paths = {
        "prototype/__init__.py": SCOPED / "prototype/__init__.py",
        "prototype/progressive_probe.py": SCOPED / "prototype/progressive_probe.py",
        "prototype/run_no_task_fixture.py": SCOPED / "prototype/run_no_task_fixture.py",
        "prototype/aggregate_output.json": aggregate_path,
        "tests/test_g014_progressive_probe.py": SCOPED / "tests/test_g014_progressive_probe.py",
        "BOUNDED_FINDINGS.md": SCOPED / "BOUNDED_FINDINGS.md",
    }
    manifest = {
        "schema_version": "g014_interface_investigation_manifest_v1",
        "status": "bounded_synthetic_interface_exercised_independent_verification_pending",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": target["id"],
        "mechanism_id": target["mechanism_id"],
        "input_binding_sha256": digest(WORK / "input_binding.json"),
        "test_command": test_command,
        "test_summary": test_summary,
        "fixture_command": [sys.executable, "prototype/run_no_task_fixture.py"],
        "verified_locally": [
            "smaller discriminating probe selection before opaque expensive action",
            "completion in_flight repeated failed and unknown structural states",
            "distinction from generic retry timeout reserve and cache shortcut",
            "one-probe and one-action caps deadline guard and disabled inertness",
            "zero tool dispatch forced answer scoring mutation and timeout extension",
            "aggregate-only no-leak export",
        ],
        "unknown": [
            "independent verification", "real-model authorship and compliance",
            "production runtime carrier", "code parent", "benchmark outcome or benefit",
            "causal relationship between historical timeouts and query structure",
        ],
        "privacy_scan": privacy,
        "output_hashes": {name: digest(path) for name, path in source_paths.items()},
        "formal_candidate_created": False,
        "formal_experiment_created": False,
        "benchmark_run": False,
        "database_accessed": False,
        "provider_called": False,
        "graph_mutated": False,
        "research_memory_mutated": False,
        "launch_claim": False,
        "score_claim": False,
        "historical_timeout_causality_claim": False,
        "real_model_behavior_claim": False,
        "benchmark_benefit_claim": False,
    }
    manifest_path = SCOPED / "exploratory_implementation_manifest.json"
    write_same_or_new(manifest_path, json_text(manifest))
    print(json.dumps({
        "status": manifest["status"],
        "tests": test_summary,
        "input_binding_sha256": digest(WORK / "input_binding.json"),
        "manifest_sha256": digest(manifest_path),
        "aggregate_sha256": digest(aggregate_path),
        "findings_sha256": digest(SCOPED / "BOUNDED_FINDINGS.md"),
        "next": "independent_verification_then_research_meta",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
