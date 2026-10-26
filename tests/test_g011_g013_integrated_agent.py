from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.g011_g013_integrated_agent import (
    ACTION_STATES,
    CARRIER_PREFIX,
    DEADLINE_GUARD_SECONDS,
    IntegratedController,
    RowAssessment,
    SCHEMA,
    VisibleObservation,
    assert_export_safe,
    install_integrated_agent,
    parse_carrier,
    redact_carriers,
)
from experiments.run_dab_tool_agent import build_parser
from experiments.run_dab_tool_agent_g011_g013_integrated import POLICY, configure_args
from experiments.analyze_dab_tool_agent_trace import analyze_run
from experiments.build_dab_tool_agent_evidence_pack import build_dab_tool_agent_evidence_pack


def record(
    *,
    revision: int = 1,
    state_id: str = "state1",
    supersedes=None,
    steps=None,
    rows=None,
    declared=None,
):
    value = {
        "schema": SCHEMA,
        "state_id": state_id,
        "revision": revision,
        "supersedes": supersedes,
        "plan_steps": steps or ["step1"],
        "requirement_rows": rows
        or [{"row_id": "row1", "step_id": "step1", "observation_refs": []}],
    }
    if declared is not None:
        value["declared_next_action"] = declared
    return value


def carrier(value=None):
    return CARRIER_PREFIX + " " + json.dumps(value or record(), separators=(",", ":"))


def test_t01_exact_schema_grammar_enums_limits_and_single_carrier():
    assert parse_carrier(carrier())["schema"] == SCHEMA
    assert parse_carrier(carrier(record(declared=ACTION_STATES[0])))["declared_next_action"] == ACTION_STATES[0]
    invalid = [
        {**record(), "extra": 1},
        {**record(), "schema": "g011_plan_record_v1"},
        record(state_id="bad token"),
        record(steps=[f"s{i}" for i in range(17)]),
        record(rows=[{"row_id": "r", "step_id": "step1", "observation_refs": [f"var_x{i}" for i in range(17)]}]),
        record(declared="force_tool"),
    ]
    for value in invalid:
        with pytest.raises(ValueError):
            parse_carrier(carrier(value))
    with pytest.raises(ValueError):
        parse_carrier(carrier() + " " + carrier())
    with pytest.raises(ValueError):
        parse_carrier("G011_PLAN_RECORD_V1 {}")


def test_t01_total_reference_cap_and_duplicate_tokens():
    rows = [
        {"row_id": f"r{i}", "step_id": "step1", "observation_refs": [f"var_x{i}_{j}" for j in range(5)]}
        for i in range(26)
    ]
    with pytest.raises(ValueError):
        parse_carrier(carrier(record(rows=rows)))
    with pytest.raises(ValueError):
        parse_carrier(carrier(record(steps=["step1", "step1"])))
    duplicate_rows = [
        {"row_id": "r1", "step_id": "step1", "observation_refs": []},
        {"row_id": "r1", "step_id": "step1", "observation_refs": []},
    ]
    with pytest.raises(ValueError):
        parse_carrier(carrier(record(rows=duplicate_rows)))


def test_t02_revision_supersession_active_head_and_prior_head_preservation():
    controller = IntegratedController()
    assert controller.submit_carrier(carrier(), 1)
    first = controller.active_head
    assert not controller.submit_carrier(carrier(), 2)
    assert controller.active_head == first
    bad = record(revision=3, state_id="state3", supersedes={"state_id": "state1", "revision": 1})
    assert not controller.submit_carrier(carrier(bad), 3)
    assert controller.active_head == first
    second = record(revision=2, state_id="state2", supersedes={"state_id": "state1", "revision": 1})
    assert controller.submit_carrier(carrier(second), 4)
    assert controller.active_head["state_id"] == "state2"
    assert controller.telemetry.accepted_revision_count == 2
    assert controller.telemetry.rejection_reason_counts["revision_invalid"] == 2


@pytest.mark.parametrize(
    "observation,expected",
    [
        (VisibleObservation("var_q1", "task", 1, visible=False), ("unknown", "unknown", "non_visible_reference")),
        (VisibleObservation("var_q1", "other", 1), ("unknown", "unknown", "non_visible_reference")),
        (VisibleObservation("var_q1", "task", 1, ordinary=False), ("unknown", "unknown", "non_visible_reference")),
        (VisibleObservation("var_q1", "task", 3), ("unknown", "unknown", "boundary_mismatch")),
        (VisibleObservation("var_q1", "task", 1, truncated=True), ("unknown", "unknown", "truncated")),
        (VisibleObservation("var_q1", "task", 1, success=None), ("unknown", "unknown", "instrumentation_loss")),
        (VisibleObservation("var_q1", "task", 1, success=False), ("failed", "current", "none")),
        (VisibleObservation("var_q1", "task", 1, available=False), ("unavailable", "current", "none")),
        (VisibleObservation("var_q1", "task", 1), ("observed", "current", "none")),
    ],
)
def test_t03_t04_visible_provenance_and_structural_transitions(observation, expected):
    controller = IntegratedController(task_key="task")
    controller.register_observation(observation)
    rows = [{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}]
    assert controller.submit_carrier(carrier(record(rows=rows)), 2)
    assessment = controller.assess()[0]
    assert (assessment.coverage, assessment.freshness, assessment.fault) == expected
    assert assessment.exact_binding_count == (1 if expected[0] in {"observed", "failed", "unavailable"} else 0)


def test_t03_duplicate_non_evidence_and_pre_boundary_rules():
    controller = IntegratedController(task_key="task")
    controller.register_observation(VisibleObservation("var_q1", "task", 1))
    controller.register_observation(VisibleObservation("var_q1", "task", 1))
    rows = [{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}]
    assert controller.submit_carrier(carrier(record(rows=rows)), 2)
    assert controller.assess()[0].fault == "duplicate"

    non_evidence = IntegratedController(task_key="task")
    non_evidence.register_observation(VisibleObservation("var_q1", "task", 1, ordinary=False))
    assert non_evidence.submit_carrier(carrier(record(rows=rows)), 2)
    assert non_evidence.assess()[0].fault == "non_visible_reference"


def test_t04_uncovered_stale_and_unknown_preservation():
    controller = IntegratedController(task_key="task")
    assert controller.submit_carrier(carrier(), 2)
    empty = controller.assess()[0]
    assert (empty.coverage, empty.freshness, empty.fault) == ("uncovered", "unknown", "missing")

    with_ref = IntegratedController(task_key="task")
    with_ref.register_observation(VisibleObservation("var_q1", "task", 1))
    rows = [{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}]
    assert with_ref.submit_carrier(carrier(record(rows=rows)), 2)
    with_ref.register_observation(VisibleObservation("var_q2", "task", 3))
    assert with_ref.assess()[0].freshness == "stale"


def test_t05_deterministic_action_precedence_and_structural_plan_actions():
    controller = IntegratedController()
    assert controller.submit_carrier(carrier(), 1)
    fault = RowAssessment(0, "unknown", "unknown", "truncated")
    stale = RowAssessment(1, "observed", "stale", "none")
    gap = RowAssessment(2, "uncovered", "unknown", "missing")
    assert controller.select_action([gap, stale, fault]) == ("preserve_unknown", 0)
    assert controller.select_action([gap, stale]) == ("refresh_observation", 1)
    assert controller.select_action([gap]) == ("acquire_evidence", 2)

    bad_mapping = record(rows=[{"row_id": "row1", "step_id": "step2", "observation_refs": []}])
    mapped = IntegratedController()
    assert mapped.submit_carrier(carrier(bad_mapping), 1)
    # Evidence gaps precede lifecycle repairs by contract.
    assert mapped.select_action()[0] == "acquire_evidence"

    plan = IntegratedController()
    rows = [{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}]
    plan.register_observation(VisibleObservation("var_q1", "task", 0))
    assert plan.submit_carrier(carrier(record(steps=["step1", "step2"], rows=rows)), 1)
    assert plan.select_action() == ("revise_plan", None)


def test_t06_t07_bounded_view_caps_deadline_unchanged_and_no_forced_action():
    controller = IntegratedController()
    assert controller.maybe_view(remaining_seconds=1000) is None
    assert controller.submit_carrier(carrier(), 1)
    first = controller.maybe_view(remaining_seconds=1000)
    assert first and "acquire_evidence" in first
    assert controller.maybe_view(remaining_seconds=1000) is None
    second_record = record(revision=2, state_id="state2", supersedes={"state_id": "state1", "revision": 1})
    assert controller.submit_carrier(carrier(second_record), 2)
    assert controller.maybe_view(remaining_seconds=1000)
    third_record = record(revision=3, state_id="state3", supersedes={"state_id": "state2", "revision": 2})
    assert controller.submit_carrier(carrier(third_record), 3)
    assert controller.maybe_view(remaining_seconds=1000)
    fourth = record(revision=4, state_id="state4", supersedes={"state_id": "state3", "revision": 3})
    assert controller.submit_carrier(carrier(fourth), 4)
    assert controller.maybe_view(remaining_seconds=1000) is None
    assert controller.telemetry.view_delivery_count == 3
    assert controller.telemetry.mechanism_initiated_tool_call_count == 0
    assert controller.telemetry.forced_answer_count == 0

    deadline = IntegratedController()
    assert deadline.submit_carrier(carrier(), 1)
    assert deadline.maybe_view(remaining_seconds=DEADLINE_GUARD_SECONDS) is None
    assert deadline.maybe_view(remaining_seconds=1000, boundary_known=False) is None


@pytest.mark.parametrize(
    "payload,status,reason",
    [
        (None, "missing", "missing"),
        (CARRIER_PREFIX + " {", "accepted", "truncated"),
        (CARRIER_PREFIX + " not-json", "accepted", "malformed"),
        (carrier(), "provider_rejected", "provider_rejected"),
        (carrier(), "boundary_mismatch", "boundary_mismatch"),
    ],
)
def test_t09_provider_shaped_fail_closed_fixtures(payload, status, reason):
    controller = IntegratedController()
    if payload is None:
        controller.note_absent_carrier()
        assert controller.active_head is None
        assert controller.telemetry.activation_miss_count == 1
        return
    assert not controller.submit_carrier(payload, 1, provider_status=status)
    assert controller.active_head is None
    assert controller.telemetry.rejection_reason_counts[reason] == 1
    assert controller.maybe_view(remaining_seconds=1000) is None


def test_t10_t11_privacy_safe_aggregate_telemetry_and_zero_activation():
    controller = IntegratedController()
    exported = controller.finalize()
    assert exported["endpoints"]["real_model_authorship"] == "untested"
    assert exported["endpoints"]["view_delivery"] == "untested"
    assert set(exported["cohort_denominators"]) == {
        "strict_pass",
        "known_strict_fail",
        "completed_strict_verdict_unknown",
        "timeout_failure",
        "other_terminal_failure",
    }
    assert exported["pooled_rates_emitted"] is False
    assert_export_safe(exported)
    for prohibited in (
        {"task_id": "PRIVATE_TASK"},
        {"nested": {"answer": "PRIVATE_ANSWER"}},
        {"raw": "var_secret"},
        {"raw": carrier()},
    ):
        with pytest.raises(ValueError):
            assert_export_safe(prohibited)
    nested = {"response": {"arguments": carrier({**record(), "state_id": "PRIVATE_TASK"})}}
    assert "PRIVATE_TASK" not in json.dumps(redact_carriers(nested))
    assert CARRIER_PREFIX not in json.dumps(redact_carriers(nested))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unknown": "PRIVATE_TASK"}),
        lambda value: value.update({"accepted_revision_count": "1"}),
        lambda value: value.update({"accepted_revision_count": float("nan")}),
        lambda value: value.update({"accepted_revision_count": float("inf")}),
        lambda value: value["endpoints"].update({"strict_outcome": "x" * 200}),
        lambda value: value["rejection_reason_counts"].update({"query": 1}),
        lambda value: value["selected_action_counts"].update({"credential": 1}),
        lambda value: value.update({"cohort_denominators": {"answer": {"path": "C:/private"}}}),
        lambda value: value.update({"schema_version": carrier()}),
    ],
)
def test_t10_strict_telemetry_schema_rejects_types_unknown_content_and_nonfinite(mutation):
    telemetry = IntegratedController().finalize()
    mutation(telemetry)
    with pytest.raises(ValueError):
        assert_export_safe(telemetry)


def test_t10_telemetry_serializes_through_analyzer_and_evidence_pack(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    telemetry = IntegratedController().finalize()
    (run_dir / "g011_g013_integrated_telemetry.json").write_text(json.dumps(telemetry), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (run_dir / "final_answer.txt").write_text("done", encoding="utf-8")
    analyzed = analyze_run(run_dir)
    assert analyzed["feedback_summary"]["g011_g013_integrated_telemetry"] == telemetry
    for name, value in (
        ("observations.json", analyzed["observations"]),
        ("feedback_summary.json", analyzed["feedback_summary"]),
        ("meta_agent_seed.json", analyzed["meta_agent_seed"]),
    ):
        (run_dir / name).write_text(json.dumps(value), encoding="utf-8")
    pack = build_dab_tool_agent_evidence_pack(run_dir)
    assert pack["g011_g013_integrated_telemetry"] == telemetry
    serialized = json.dumps(telemetry)
    assert "PRIVATE_TASK" not in serialized
    assert "var_secret" not in serialized

    bad = dict(telemetry, raw_observation_ref="var_secret")
    (run_dir / "g011_g013_integrated_telemetry.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        analyze_run(run_dir)
    with pytest.raises(ValueError, match="schema mismatch"):
        build_dab_tool_agent_evidence_pack(run_dir)


def test_t12_end_to_end_author_view_later_action_revise_finalize(tmp_path: Path):
    telemetry_path = tmp_path / "telemetry.json"
    controller = IntegratedController(task_key="task", telemetry_path=telemetry_path)
    assert controller.submit_carrier(carrier(), 1)
    assert "acquire_evidence" in controller.maybe_view(remaining_seconds=1000)
    controller.register_observation(VisibleObservation("var_q1", "task", 2))
    revised = record(
        revision=2,
        state_id="state2",
        supersedes={"state_id": "state1", "revision": 1},
        rows=[{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}],
    )
    assert controller.submit_carrier(carrier(revised), 3)
    assert controller.assess()[0].coverage == "observed"
    assert controller.maybe_view(remaining_seconds=1000) is None
    final = controller.finalize()
    assert final["accepted_revision_count"] == 2
    assert final["exact_opaque_binding_count"] == 1
    assert final["later_action_class_counts"]["consistent"] == 1
    assert json.loads(telemetry_path.read_text(encoding="ascii"))["schema_version"] == "g011_g013_integrated_telemetry_v1"


class FakeTool:
    def __init__(self, log_path, name):
        self.log_path = Path(log_path)
        self.name = name

    def exec(self, args):
        return {"success": True, "result": args}


class FakeAgent:
    def __init__(self, root: Path):
        self.tool_log_path = root / "tool_calls.jsonl"
        self.messages = [{"role": "system", "content": "base"}]
        self.tools = {"query_db": FakeTool(self.tool_log_path, "query_db")}
        self.calls = 0

    def _handle_tool_call(self, tool_call):
        return {"success": True, "result": json.loads(tool_call.function.arguments)}

    def call_llm(self):
        self.calls += 1
        return "base-result"

    def to_dict(self):
        return {"calls": self.calls}


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))


class FakeCarrierResponseAgent(FakeAgent):
    def call_llm(self):
        self.calls += 1
        return SimpleNamespace(
            tool_calls=[
                FakeToolCall(
                    "s1",
                    "record_self_observation",
                    {"freeform": carrier()},
                )
            ]
        )


def test_t08_install_disabled_is_inert_and_enabled_adds_only_view_channel(tmp_path: Path):
    disabled_module = SimpleNamespace(DataAgent=FakeAgent)
    original = disabled_module.DataAgent
    result = install_integrated_agent(disabled_module, SimpleNamespace(enable_g011_g013_integrated=False))
    assert result["installed"] is False
    assert disabled_module.DataAgent is original

    enabled_module = SimpleNamespace(DataAgent=FakeAgent)
    args = SimpleNamespace(
        enable_g011_g013_integrated=True,
        enable_g0132_task_workspace=False,
        self_observation_tool_name="record_self_observation",
    )
    assert install_integrated_agent(enabled_module, args)["installed"] is True
    agent = enabled_module.DataAgent(tmp_path)
    base_result = agent._handle_tool_call(FakeToolCall("q1", "query_db", {"query": "SELECT 1"}))
    assert base_result == {"success": True, "result": {"query": "SELECT 1"}}
    agent._handle_tool_call(FakeToolCall("s1", "record_self_observation", {"freeform": carrier()}))
    assert agent.call_llm() == "base-result"
    views = [item for item in agent.messages if item.get("content", "").startswith("[REVISIONED")]
    assert len(views) == 1
    assert agent.to_dict()["g011_g013_integrated"]["mechanism_initiated_tool_call_count"] == 0


def test_t08_repeated_install_is_single_path_and_conflicts_fail_closed(tmp_path: Path):
    module = SimpleNamespace(DataAgent=FakeAgent)
    args = SimpleNamespace(
        enable_g011_g013_integrated=True,
        enable_g0132_task_workspace=False,
        self_observation_tool_name="record_self_observation",
    )
    first = install_integrated_agent(module, args)
    installed_class = module.DataAgent
    second = install_integrated_agent(module, args)
    assert second is first
    assert module.DataAgent is installed_class

    agent = module.DataAgent(tmp_path)
    agent._handle_tool_call(FakeToolCall("q1", "query_db", {"query": "SELECT 1"}))
    with_ref = record(rows=[{"row_id": "row1", "step_id": "step1", "observation_refs": ["var_q1"]}])
    agent._handle_tool_call(FakeToolCall("s1", "record_self_observation", {"freeform": carrier(with_ref)}))
    assert agent.g011_g013_controller.finalize()["exact_opaque_binding_count"] == 1

    conflicting = SimpleNamespace(**vars(args))
    conflicting.self_observation_tool_name = "other_recorder"
    with pytest.raises(ValueError, match="conflicting"):
        install_integrated_agent(module, conflicting)
    assert module.DataAgent is installed_class


def test_t11_runtime_activation_miss_once_per_enabled_response(tmp_path: Path):
    disabled_module = SimpleNamespace(DataAgent=FakeAgent)
    disabled_args = SimpleNamespace(enable_g011_g013_integrated=False)
    install_integrated_agent(disabled_module, disabled_args)
    disabled_agent = disabled_module.DataAgent(tmp_path / "disabled")
    disabled_agent.call_llm()
    assert not hasattr(disabled_agent, "g011_g013_controller")

    enabled_module = SimpleNamespace(DataAgent=FakeAgent)
    enabled_args = SimpleNamespace(
        enable_g011_g013_integrated=True,
        enable_g0132_task_workspace=False,
        self_observation_tool_name="record_self_observation",
    )
    install_integrated_agent(enabled_module, enabled_args)
    enabled_agent = enabled_module.DataAgent(tmp_path / "enabled")
    enabled_agent.call_llm()
    enabled_agent.call_llm()
    assert enabled_agent.g011_g013_controller.telemetry.activation_miss_count == 2

    carrier_module = SimpleNamespace(DataAgent=FakeCarrierResponseAgent)
    install_integrated_agent(carrier_module, enabled_args)
    carrier_agent = carrier_module.DataAgent(tmp_path / "carrier")
    carrier_agent.call_llm()
    assert carrier_agent.g011_g013_controller.telemetry.activation_miss_count == 0


def test_launcher_only_selects_candidate_and_preserves_frozen_runtime_defaults():
    assert POLICY.is_file()
    parser = build_parser()
    base = parser.parse_args([])
    args = configure_args(parser.parse_args([]))
    assert args.enable_g011_g013_integrated is True
    assert args.enable_g0132_task_workspace is False
    assert args.disable_self_observation_tool is False
    assert args.max_iterations == base.max_iterations
    assert args.llm_timeout == base.llm_timeout
    assert args.llm_retries == 1
    assert args.client_max_retries == 0
    assert args.tool_agent_policy == POLICY
    assert args.run_id.startswith("g011_g013_integrated_")


def test_integrated_mode_rejects_parallel_g0132_carrier():
    module = SimpleNamespace(DataAgent=FakeAgent)
    args = SimpleNamespace(
        enable_g011_g013_integrated=True,
        enable_g0132_task_workspace=True,
        self_observation_tool_name="record_self_observation",
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        install_integrated_agent(module, args)
