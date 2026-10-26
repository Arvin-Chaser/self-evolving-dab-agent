#!/usr/bin/env python3
"""Create non-overwriting G14 interface-investigation revision 003."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PRIOR = BASE / "g014_interface_investigation_002"
WORK = BASE / "g014_interface_investigation_003"
SCOPED = WORK / "scoped_source"
PRIOR_MANIFEST = PRIOR / "scoped_source/exploratory_implementation_manifest.json"
PRIOR_MANIFEST_SHA = "d4c9b6ed8cc4f73b90455b29145172b644d8ff53cfb718b5aa3d9f9d83f0b5ad"
MEMORY = BASE / "research_graph_memory_v18.json"
META = BASE / "g014_research_meta_solution_loop_003/final_raw.txt"
MEMORY_SHA = "51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b"
META_SHA = "5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad"


CANDIDATE_CLASS = '''@dataclass(frozen=True)
class ProbeCandidate:
    probe_ref: str
    kind: str
    partition_count: int
    cost_class: int

    def __post_init__(self) -> None:
        if type(self.probe_ref) is not str or OPAQUE_RE.fullmatch(self.probe_ref) is None or not self.probe_ref.startswith("prb_"):
            raise ProbeValidationError("probe_ref must be an opaque probe token")
        if type(self.kind) is not str or self.kind not in PROBE_KINDS:
            raise ProbeValidationError("probe kind differs")
        if isinstance(self.partition_count, bool) or not isinstance(self.partition_count, int) or not 1 <= self.partition_count <= 8:
            raise ProbeValidationError("partition_count must be a bounded strict integer")
        if isinstance(self.cost_class, bool) or not isinstance(self.cost_class, int) or not 1 <= self.cost_class <= 4:
            raise ProbeValidationError("cost_class must be a bounded strict integer")

    @property
    def is_discriminating(self) -> bool:
        return self.kind == "discriminating_probe" and self.partition_count >= 2
'''


CHECKPOINT_CLASS = '''@dataclass(frozen=True)
class StructuralCheckpoint:
    action_ref: str
    action_state: str
    probe_state: str
    progress_observed: bool | None

    def __post_init__(self) -> None:
        if type(self.action_ref) is not str or OPAQUE_RE.fullmatch(self.action_ref) is None or not self.action_ref.startswith("act_"):
            raise ProbeValidationError("action_ref must be an opaque action token")
        if type(self.action_state) is not str or self.action_state not in ACTION_STATES:
            raise ProbeValidationError("action state differs")
        if type(self.probe_state) is not str or self.probe_state not in PROBE_STATES:
            raise ProbeValidationError("probe state differs")
        if type(self.progress_observed) not in {bool, type(None)}:
            raise ProbeValidationError("progress must be an exact boolean or unknown")
        if self.probe_state in {"not_started", "in_flight", "unknown"} and self.progress_observed is not None:
            raise ProbeValidationError("unobserved probe state cannot claim progress")
'''


PARSE_FUNCTION = '''def parse_candidate(value: Mapping[str, object]) -> ProbeCandidate:
    expected = {"probe_ref", "kind", "partition_count", "cost_class"}
    if type(value) is not dict or set(value) != expected:
        raise ProbeValidationError("probe fields differ")
    return ProbeCandidate(**value)
'''


CHECKPOINT_FUNCTION = '''def checkpoint(
    *, action_ref: str, action_state: str, probe_state: str, progress_observed: bool | None
) -> StructuralCheckpoint:
    return StructuralCheckpoint(action_ref, action_state, probe_state, progress_observed)
'''


VIEW_VALIDATOR = '''
ALLOWED_REASONS = frozenset({
    "deadline_guard", "primary_complete", "operation_in_flight",
    "probe_discriminated", "probe_no_progress", "probe_progress_unknown",
    "probe_repeated", "probe_failed", "probe_state_unknown",
    "primary_repeated", "primary_failed", "probe_cap_reached",
    "no_discriminating_probe", "smaller_discriminating_probe",
})


def _validate_view(view: object) -> dict[str, object]:
    allowed = {
        "decision", "reason", "target", "mechanism_tool_dispatch_count",
        "forced_answer_count", "scoring_mutation_count", "timeout_extension_seconds",
    }
    if type(view) is not dict or set(view) != allowed:
        raise ProbeValidationError("view fields differ")
    decision = view["decision"]
    reason = view["reason"]
    target = view["target"]
    if type(decision) is not str or decision not in ALLOWED_DECISIONS:
        raise ProbeValidationError("view decision differs")
    if type(reason) is not str or reason not in ALLOWED_REASONS:
        raise ProbeValidationError("view reason differs")
    if target is not None and (
        type(target) is not str or OPAQUE_RE.fullmatch(target) is None or not target.startswith("prb_")
    ):
        raise ProbeValidationError("view target must be an opaque probe token or null")
    if (decision == "request_probe") != (target is not None):
        raise ProbeValidationError("only request_probe may expose a target")
    for key in (
        "mechanism_tool_dispatch_count", "forced_answer_count",
        "scoring_mutation_count", "timeout_extension_seconds",
    ):
        if type(view[key]) is not int or view[key] != 0:
            raise ProbeValidationError("prohibited effect count must be exact integer zero")
    return view
'''


EXTRA_TESTS = r'''

from prototype.progressive_probe import ProbeCandidate, StructuralCheckpoint


@pytest.mark.parametrize(
    "kwargs",
    [
        {"probe_ref": "SYNTHETIC_PRIVATE_SENTINEL_8301"},
        {"probe_ref": "act_wrong_kind"},
        {"probe_ref": 7},
        {"kind": "not_reviewed"},
        {"kind": 7},
        {"partition_count": 0},
        {"partition_count": 9},
        {"partition_count": True},
        {"partition_count": "2"},
        {"cost_class": 0},
        {"cost_class": 5},
        {"cost_class": False},
        {"cost_class": 1.0},
    ],
)
def test_direct_probe_candidate_construction_cannot_bypass_invariants(kwargs):
    value = {
        "probe_ref": "prb_direct", "kind": "discriminating_probe",
        "partition_count": 2, "cost_class": 1,
    }
    value.update(kwargs)
    with pytest.raises(ProbeValidationError):
        ProbeCandidate(**value)


def test_direct_probe_candidate_rejects_extra_field():
    with pytest.raises(TypeError):
        ProbeCandidate(
            probe_ref="prb_direct", kind="discriminating_probe",
            partition_count=2, cost_class=1, raw_query="SYNTHETIC_PRIVATE_SENTINEL_8301",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_ref": "SYNTHETIC_PRIVATE_SENTINEL_8301"},
        {"action_ref": "prb_wrong_kind"},
        {"action_ref": object()},
        {"action_state": "complete"},
        {"action_state": 7},
        {"probe_state": "pending"},
        {"probe_state": object()},
        {"probe_state": "completion", "progress_observed": 0},
        {"probe_state": "completion", "progress_observed": 1},
        {"probe_state": "completion", "progress_observed": "yes"},
        {"probe_state": "not_started", "progress_observed": True},
    ],
)
def test_direct_checkpoint_construction_cannot_bypass_invariants(kwargs):
    value = {
        "action_ref": "act_direct", "action_state": "unknown",
        "probe_state": "not_started", "progress_observed": None,
    }
    value.update(kwargs)
    with pytest.raises(ProbeValidationError):
        StructuralCheckpoint(**value)


def test_direct_checkpoint_rejects_extra_field():
    with pytest.raises(TypeError):
        StructuralCheckpoint(
            action_ref="act_direct", action_state="unknown", probe_state="not_started",
            progress_observed=None, raw_message="SYNTHETIC_PRIVATE_SENTINEL_8301",
        )


def test_policy_entry_rejects_non_candidate_extra_type():
    with pytest.raises(ProbeValidationError):
        next_policy_view(state(), [object()], budget())


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason", "SYNTHETIC_PRIVATE_SENTINEL_8301"),
        ("target", "SYNTHETIC_PRIVATE_SENTINEL_8301"),
        ("target", "act_wrong_kind"),
        ("decision", "SYNTHETIC_PRIVATE_SENTINEL_8301"),
        ("mechanism_tool_dispatch_count", True),
        ("forced_answer_count", 1),
        ("scoring_mutation_count", "0"),
        ("timeout_extension_seconds", 0.0),
    ],
)
def test_render_revalidates_values_and_cannot_leak(field, value):
    view = decide()
    view[field] = value
    with pytest.raises(ProbeValidationError):
        render_view(view)


def test_rendered_valid_view_contains_no_private_sentinel():
    assert "SYNTHETIC_PRIVATE_SENTINEL_8301" not in render_view(decide())
'''


FINDINGS = """# G14 bounded interface findings revision 003

Status: bounded synthetic structural interface exercised after constructor-invariant repair; independent verification pending.

## Verified locally

- Revision 003 preserves revisions 001 and 002 and binds the revision 002 manifest plus the original G14 inputs.
- `ProbeCandidate` and `StructuralCheckpoint` now enforce their invariants in strict `__post_init__` methods, so direct public construction cannot bypass the factories.
- Factories reuse the same dataclass validation; policy selection also rejects non-exact checkpoint, budget, and candidate types.
- Direct-construction tests reject sentinel/non-opaque references, invalid kinds and states, bool/string/out-of-range numeric fields, progress aliases 0/1, unexpected fields, and unrelated object types.
- Render validation checks both fields and values, permits only reviewed reasons and opaque probe targets, and requires all prohibited-effect counters to be exact integer zero.
- Earlier budget, cap, structural-state, control-distinction, inertness, and aggregate no-leak checks remain covered.

## Unknown

- Independent verification remains pending.
- No provider was called, so real-model probe authorship, interpretation, and compliance remain unknown.
- No production runtime carrier, code parent, formal Experiment, benchmark result, causal timeout claim, or benefit claim exists.

Next workflow step: independently verify revision 003, then return the finding to Research Meta. Do not enter Implementation Meta directly.
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def write_same_or_new(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Revision 003 {label} marker differs")
    return source.replace(old, new, 1)


def revised_prototype(source: str) -> str:
    start = source.index("@dataclass(frozen=True)\nclass ProbeCandidate:")
    end = source.index("\n\n@dataclass(frozen=True)\nclass StructuralCheckpoint:", start)
    source = source[:start] + CANDIDATE_CLASS.rstrip() + source[end:]
    start = source.index("@dataclass(frozen=True)\nclass StructuralCheckpoint:")
    end = source.index("\n\n@dataclass(frozen=True)\nclass PolicyBudget:", start)
    source = source[:start] + CHECKPOINT_CLASS.rstrip() + source[end:]
    start = source.index("def parse_candidate(")
    end = source.index("\n\ndef checkpoint(", start)
    source = source[:start] + PARSE_FUNCTION.rstrip() + source[end:]
    start = source.index("def checkpoint(")
    end = source.index("\n\ndef select_discriminating_probe(", start)
    source = source[:start] + CHECKPOINT_FUNCTION.rstrip() + source[end:]
    insert = source.index("\n\nclass ProbeValidationError")
    source = source[:insert] + "\n" + VIEW_VALIDATOR.rstrip() + source[insert:]
    old = '''    eligible = [
        candidate for candidate in candidates
        if candidate.is_discriminating and candidate.cost_class < primary_cost_class
    ]'''
    new = '''    candidates = tuple(candidates)
    if any(type(candidate) is not ProbeCandidate for candidate in candidates):
        raise ProbeValidationError("candidates must use validated exact types")
    eligible = [
        candidate for candidate in candidates
        if candidate.is_discriminating and candidate.cost_class < primary_cost_class
    ]'''
    source = replace_once(source, old, new, "candidate-entry")
    source = replace_once(
        source,
        "    if not isinstance(state, StructuralCheckpoint) or not isinstance(budget, PolicyBudget):\n",
        "    if type(state) is not StructuralCheckpoint or type(budget) is not PolicyBudget:\n",
        "policy-exact-types",
    )
    source = replace_once(
        source,
        '''def classify_control(candidate: ProbeCandidate) -> str:
    if candidate.kind == "discriminating_probe" and candidate.partition_count >= 2:''',
        '''def classify_control(candidate: ProbeCandidate) -> str:
    if type(candidate) is not ProbeCandidate:
        raise ProbeValidationError("control must use a validated exact type")
    if candidate.kind == "discriminating_probe" and candidate.partition_count >= 2:''',
        "control-entry",
    )
    old_render = '''def render_view(view: Mapping[str, object] | None) -> str | None:
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
    )'''
    new_render = '''def render_view(view: Mapping[str, object] | None) -> str | None:
    if view is None:
        return None
    validated = _validate_view(view)
    return "G014_PROGRESSIVE_PROBE_V1 " + json.dumps(
        validated, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )'''
    return replace_once(source, old_render, new_render, "render-validation")


def privacy_scan(value: object) -> dict[str, object]:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
    forbidden_keys = {
        "task", "answer", "hint", "validator", "message", "messages",
        "tool_argument", "tool_arguments", "tool_result", "tool_results",
        "trace", "identifier", "credential", "raw_provider_content",
    }
    opaque = re.compile(r"(?:act|prb)_[A-Za-z0-9]{1,32}")
    credential = re.compile(r"(?i)(?:api[_-]?key|authorization|cookie|password|private[_-]?key)\s*[:=]")
    sentinel = "SYNTHETIC_PRIVATE_SENTINEL_8301"
    forbidden_hits: list[str] = []
    def walk(item: object, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower().replace("-", "_") in forbidden_keys:
                    forbidden_hits.append(f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")
    walk(value)
    hits = {
        "forbidden_field_hits": forbidden_hits,
        "opaque_reference_hits": opaque.findall(encoded),
        "credential_pattern_hits": credential.findall(encoded),
        "synthetic_sentinel_hits": [sentinel] if sentinel in encoded else [],
        "raw_provider_content_present": False,
    }
    hits["passed"] = not any(hits[key] for key in (
        "forbidden_field_hits", "opaque_reference_hits", "credential_pattern_hits", "synthetic_sentinel_hits"
    ))
    return hits


def main() -> None:
    if digest(PRIOR_MANIFEST) != PRIOR_MANIFEST_SHA:
        raise RuntimeError("Revision 003 prior manifest binding differs")
    if digest(MEMORY) != MEMORY_SHA or digest(META) != META_SHA:
        raise RuntimeError("Revision 003 original G14 input binding differs")
    prior_source = PRIOR / "scoped_source/prototype/progressive_probe.py"
    prior_tests = PRIOR / "scoped_source/tests/test_g014_progressive_probe.py"
    binding = {
        "schema_version": "g014_interface_investigation_revision_input_v2",
        "status": "minimal_non_overwriting_revision",
        "selected_target_id": "research_target:g014:001",
        "mechanism_id": "mech_progressive_query_probing",
        "prior_manifest_sha256": PRIOR_MANIFEST_SHA,
        "research_memory_sha256": MEMORY_SHA,
        "research_meta_output_sha256": META_SHA,
        "repair_scope": [
            "non-bypassable ProbeCandidate dataclass invariants",
            "non-bypassable StructuralCheckpoint dataclass invariants",
            "policy candidate revalidation and render value no-leak validation",
        ],
        "excluded": ["formal implementation", "provider", "benchmark", "database", "Graph", "memory", "docs"],
    }
    binding_path = WORK / "input_binding.json"
    write_same_or_new(binding_path, json_text(binding))
    write_same_or_new(SCOPED / "prototype/__init__.py", "")
    write_same_or_new(
        SCOPED / "prototype/progressive_probe.py",
        revised_prototype(prior_source.read_text(encoding="utf-8")),
    )
    runner = PRIOR / "scoped_source/prototype/run_no_task_fixture.py"
    write_same_or_new(SCOPED / "prototype/run_no_task_fixture.py", runner.read_text(encoding="utf-8"))
    write_same_or_new(
        SCOPED / "tests/test_g014_progressive_probe.py",
        prior_tests.read_text(encoding="utf-8") + EXTRA_TESTS,
    )
    fixture_command = [sys.executable, "prototype/run_no_task_fixture.py"]
    fixture = subprocess.run(fixture_command, cwd=SCOPED, capture_output=True, text=True, check=False)
    if fixture.returncode:
        raise RuntimeError(f"Revision 003 fixture failed:\n{fixture.stdout}\n{fixture.stderr}")
    aggregate_path = SCOPED / "prototype/aggregate_output.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    privacy = privacy_scan(aggregate)
    if not privacy["passed"]:
        raise RuntimeError(f"Revision 003 no-leak scan failed: {privacy}")
    test_command = [sys.executable, "-m", "pytest", "-q", "tests/test_g014_progressive_probe.py", "--disable-warnings", "-p", "no:cacheprovider"]
    test = subprocess.run(test_command, cwd=SCOPED, capture_output=True, text=True, check=False)
    if test.returncode:
        raise RuntimeError(f"Revision 003 tests failed:\n{test.stdout}\n{test.stderr}")
    line = next((line for line in reversed(test.stdout.splitlines()) if " passed" in line), "")
    match = re.search(r"(\d+) passed", line)
    if match is None:
        raise RuntimeError("Revision 003 test summary differs")
    test_summary = f"{match.group(1)} passed"
    findings_path = SCOPED / "BOUNDED_FINDINGS.md"
    write_same_or_new(findings_path, FINDINGS)
    paths = {
        "prototype/__init__.py": SCOPED / "prototype/__init__.py",
        "prototype/progressive_probe.py": SCOPED / "prototype/progressive_probe.py",
        "prototype/run_no_task_fixture.py": SCOPED / "prototype/run_no_task_fixture.py",
        "prototype/aggregate_output.json": aggregate_path,
        "tests/test_g014_progressive_probe.py": SCOPED / "tests/test_g014_progressive_probe.py",
        "BOUNDED_FINDINGS.md": findings_path,
    }
    manifest = {
        "schema_version": "g014_interface_investigation_manifest_v3",
        "status": "bounded_synthetic_interface_revised_independent_verification_pending",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g014:001",
        "mechanism_id": "mech_progressive_query_probing",
        "prior_manifest_sha256": PRIOR_MANIFEST_SHA,
        "input_binding_sha256": digest(binding_path),
        "test_command": test_command,
        "test_summary": test_summary,
        "fixture_command": fixture_command,
        "verified_locally": [
            "dataclass invariants cannot be bypassed by direct public construction",
            "factories and policy entry reuse exact validated structural types",
            "render fields and values fail closed against sentinel leakage",
            "prior budget cap state control inertness and aggregate privacy properties",
        ],
        "unknown": ["independent verification", "real-model behavior", "runtime carrier", "code parent", "benchmark benefit", "timeout causality"],
        "privacy_scan": privacy,
        "output_hashes": {name: digest(path) for name, path in paths.items()},
        "formal_candidate_created": False,
        "formal_experiment_created": False,
        "provider_called": False,
        "benchmark_run": False,
        "database_accessed": False,
        "graph_mutated": False,
        "research_memory_mutated": False,
        "historical_timeout_causality_claim": False,
        "real_model_behavior_claim": False,
        "benchmark_benefit_claim": False,
    }
    manifest_path = SCOPED / "exploratory_implementation_manifest.json"
    write_same_or_new(manifest_path, json_text(manifest))
    print(json.dumps({
        "status": manifest["status"], "tests": test_summary,
        "input_binding_sha256": digest(binding_path), "manifest_sha256": digest(manifest_path),
        "aggregate_sha256": digest(aggregate_path), "findings_sha256": digest(findings_path),
        "next": "independent_verification_then_research_meta",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
