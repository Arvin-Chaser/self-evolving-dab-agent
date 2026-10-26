#!/usr/bin/env python3
"""Create the non-overwriting G14 interface-investigation revision 002."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PRIOR_SCRIPT = ROOT / "experiments/run_research_graph_g014_interface_investigation.py"
_PRIOR_SPEC = importlib.util.spec_from_file_location("g014_interface_investigation_v1", PRIOR_SCRIPT)
if _PRIOR_SPEC is None or _PRIOR_SPEC.loader is None:
    raise RuntimeError("Cannot load the revision 001 investigation builder")
prior = importlib.util.module_from_spec(_PRIOR_SPEC)
_PRIOR_SPEC.loader.exec_module(prior)
PRIOR = BASE / "g014_interface_investigation_001"
WORK = BASE / "g014_interface_investigation_002"
SCOPED = WORK / "scoped_source"
PRIOR_MANIFEST = PRIOR / "scoped_source/exploratory_implementation_manifest.json"
PRIOR_MANIFEST_SHA = "8f8c42f0997f78f637d549f37abae9d165200bc0eae5697b1002814433d38ee4"


VALIDATION_BLOCK = '''
    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ProbeValidationError("enabled must be a strict boolean")
        numeric = {
            "remaining_seconds": self.remaining_seconds,
            "deadline_guard_seconds": self.deadline_guard_seconds,
        }
        for name, value in numeric.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProbeValidationError(f"{name} must be a finite number")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ProbeValidationError(f"{name} must be finite and non-negative")
        if float(self.deadline_guard_seconds) <= 0:
            raise ProbeValidationError("deadline guard must be positive")
        for name, value in {
            "mechanism_action_count": self.mechanism_action_count,
            "probe_request_count": self.probe_request_count,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProbeValidationError(f"{name} must be a non-negative strict integer")
        if isinstance(self.action_cap, bool) or not isinstance(self.action_cap, int) or self.action_cap != 1:
            raise ProbeValidationError("action_cap must equal the frozen cap of one")
        if isinstance(self.probe_cap, bool) or not isinstance(self.probe_cap, int) or self.probe_cap != 1:
            raise ProbeValidationError("probe_cap must equal the frozen cap of one")
'''


EXTRA_TESTS = r'''

@pytest.mark.parametrize("progress", [0, 1])
def test_integer_progress_aliases_fail_closed(progress):
    with pytest.raises(ProbeValidationError):
        state(probe_state="completion", progress_observed=progress)


@pytest.mark.parametrize("field", ["action_cap", "probe_cap"])
def test_caps_above_one_fail_closed_at_construction(field):
    with pytest.raises(ProbeValidationError):
        budget(**{field: 2})


@pytest.mark.parametrize("field", ["remaining_seconds", "deadline_guard_seconds"])
@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_invalid_budget_numbers_fail_closed_at_construction(field, value):
    with pytest.raises(ProbeValidationError):
        budget(**{field: value})


def test_zero_remaining_is_valid_and_guarded():
    view = decide(budget_value=budget(remaining_seconds=0.0))
    assert view["decision"] == "preserve_unknown"
    assert view["reason"] == "deadline_guard"


def test_zero_deadline_guard_fails_closed():
    with pytest.raises(ProbeValidationError):
        budget(deadline_guard_seconds=0.0)


@pytest.mark.parametrize("field", ["mechanism_action_count", "probe_request_count"])
@pytest.mark.parametrize("value", [True, False, -1, 1.0])
def test_invalid_counts_fail_closed_at_construction(field, value):
    with pytest.raises(ProbeValidationError):
        budget(**{field: value})


def test_valid_zero_and_one_counts_remain_distinct():
    assert budget(mechanism_action_count=0).mechanism_action_count == 0
    assert budget(mechanism_action_count=1).mechanism_action_count == 1
    assert decide(budget_value=budget(mechanism_action_count=1)) is None


def test_invalid_budget_object_fails_closed_at_policy_entry():
    with pytest.raises(ProbeValidationError):
        next_policy_view(state(), [candidate()], object())
'''


FINDINGS = """# G14 bounded interface findings revision 002

Status: bounded synthetic structural interface exercised after fail-closed repair; independent verification pending.

## Verified locally

- Revision 002 preserves the `_001` artifact and binds its manifest plus the original G14 Research Meta and memory inputs.
- Structural progress accepts only exact `bool` or `None`; integer aliases `0` and `1` fail closed.
- Policy budgets validate at construction and policy entry: caps are frozen at exactly one, counts are non-negative strict integers, remaining time and guard are finite and non-negative, and the guard must be positive.
- Negative, NaN, infinite, bool-count, float-count, and cap-of-two fixtures fail closed; valid zero/one count behavior remains distinct.
- The previously exercised discriminating-probe, structural-state, control-distinction, inertness, prohibited-effect, and aggregate no-leak properties remain covered.

## Unknown

- Independent verification remains pending.
- No provider was called, so real-model probe authorship, state interpretation, and behavioral compliance remain unknown.
- No production runtime carrier, code parent, formal Experiment, benchmark result, or benefit claim exists.
- Historical timeout localization is not causal evidence for query or action structure.

Next workflow step: independently verify revision 002, then return the finding to Research Meta. Do not enter Implementation Meta directly.
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_same_or_new(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def revised_prototype() -> str:
    source = prior.PROTOTYPE
    source = source.replace("import json\nimport re\n", "import json\nimport math\nimport re\n", 1)
    marker = "    deadline_guard_seconds: float = 180.0\n"
    if source.count(marker) != 1:
        raise RuntimeError("Revision 002 PolicyBudget marker differs")
    source = source.replace(marker, marker + VALIDATION_BLOCK, 1)
    progress_marker = '    if progress_observed not in {True, False, None}:\n'
    progress_replacement = '    if type(progress_observed) not in {bool, type(None)}:\n'
    if source.count(progress_marker) != 1:
        raise RuntimeError("Revision 002 strict-progress marker differs")
    source = source.replace(progress_marker, progress_replacement, 1)
    marker = '''    """Return one bounded advisory view without causing an external action."""\n    if not budget.enabled'''
    replacement = '''    """Return one bounded advisory view without causing an external action."""\n    if not isinstance(state, StructuralCheckpoint) or not isinstance(budget, PolicyBudget):\n        raise ProbeValidationError("policy inputs must use validated structural types")\n    if not budget.enabled'''
    if source.count(marker) != 1:
        raise RuntimeError("Revision 002 policy-entry marker differs")
    return source.replace(marker, replacement, 1)


def main() -> None:
    if digest(PRIOR_MANIFEST) != PRIOR_MANIFEST_SHA:
        raise RuntimeError("Revision 002 prior manifest binding differs")
    if digest(prior.MEMORY) != prior.MEMORY_SHA or digest(prior.META) != prior.META_SHA:
        raise RuntimeError("Revision 002 original G14 input binding differs")
    if WORK.exists() and not (WORK / "input_binding.json").is_file():
        raise RuntimeError("Refusing incomplete pre-existing revision directory")

    binding = {
        "schema_version": "g014_interface_investigation_revision_input_v1",
        "status": "minimal_non_overwriting_revision",
        "selected_target_id": "research_target:g014:001",
        "mechanism_id": "mech_progressive_query_probing",
        "prior_manifest_path": str(PRIOR_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "prior_manifest_sha256": PRIOR_MANIFEST_SHA,
        "research_memory_sha256": prior.MEMORY_SHA,
        "research_meta_output_sha256": prior.META_SHA,
        "repair_scope": [
            "strict bool or none progress",
            "fail-closed PolicyBudget construction and policy entry",
            "negative numeric and Python bool-int alias regression tests",
        ],
        "excluded": [
            "formal implementation", "code parent selection", "provider call",
            "benchmark", "database", "Graph mutation", "research memory mutation",
        ],
    }
    binding_path = WORK / "input_binding.json"
    write_same_or_new(binding_path, json_text(binding))
    write_same_or_new(SCOPED / "prototype/__init__.py", "")
    write_same_or_new(SCOPED / "prototype/progressive_probe.py", revised_prototype())
    write_same_or_new(SCOPED / "prototype/run_no_task_fixture.py", prior.FIXTURE_RUNNER.lstrip("\n"))
    write_same_or_new(SCOPED / "tests/test_g014_progressive_probe.py", prior.TESTS.lstrip("\n") + EXTRA_TESTS)

    fixture_command = [sys.executable, "prototype/run_no_task_fixture.py"]
    fixture = subprocess.run(fixture_command, cwd=SCOPED, capture_output=True, text=True, check=False)
    if fixture.returncode:
        raise RuntimeError(f"Revision 002 fixture failed:\n{fixture.stdout}\n{fixture.stderr}")
    aggregate_path = SCOPED / "prototype/aggregate_output.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    privacy = prior.forbidden_export_scan(aggregate)
    if not privacy["passed"]:
        raise RuntimeError(f"Revision 002 no-leak scan failed: {privacy}")

    test_command = [
        sys.executable, "-m", "pytest", "-q", "tests/test_g014_progressive_probe.py",
        "--disable-warnings", "-p", "no:cacheprovider",
    ]
    test = subprocess.run(test_command, cwd=SCOPED, capture_output=True, text=True, check=False)
    if test.returncode:
        raise RuntimeError(f"Revision 002 tests failed:\n{test.stdout}\n{test.stderr}")
    summary_line = next((line for line in reversed(test.stdout.splitlines()) if " passed" in line), "")
    match = re.search(r"(\d+) passed", summary_line)
    if match is None:
        raise RuntimeError(f"Revision 002 pytest summary differs: {summary_line!r}")
    test_summary = f"{match.group(1)} passed"

    findings_path = SCOPED / "BOUNDED_FINDINGS.md"
    write_same_or_new(findings_path, FINDINGS)
    source_paths = {
        "prototype/__init__.py": SCOPED / "prototype/__init__.py",
        "prototype/progressive_probe.py": SCOPED / "prototype/progressive_probe.py",
        "prototype/run_no_task_fixture.py": SCOPED / "prototype/run_no_task_fixture.py",
        "prototype/aggregate_output.json": aggregate_path,
        "tests/test_g014_progressive_probe.py": SCOPED / "tests/test_g014_progressive_probe.py",
        "BOUNDED_FINDINGS.md": findings_path,
    }
    manifest = {
        "schema_version": "g014_interface_investigation_manifest_v2",
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
            "strict bool or none progress rejects zero and one aliases",
            "PolicyBudget constructor and policy entry fail closed",
            "caps frozen at exactly one and counts strict non-negative integers",
            "remaining and guard finite non-negative with positive guard",
            "prior discriminating probe structural state controls inertness and no-leak checks",
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
        "status": manifest["status"],
        "tests": test_summary,
        "input_binding_sha256": digest(binding_path),
        "manifest_sha256": digest(manifest_path),
        "aggregate_sha256": digest(aggregate_path),
        "findings_sha256": digest(findings_path),
        "next": "independent_verification_then_research_meta",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
