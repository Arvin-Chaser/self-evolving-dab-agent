"""Focused no-task tests for the bounded competing-hypothesis prototype."""

from __future__ import annotations

import json

import pytest

from experiments.research_graph_role_scoped_wiring import (
    CompetingHypothesisRegister,
    synthetic_competing_hypothesis_register,
    validate_competing_hypothesis_aggregate_export,
)


def _two_branch_register(*, first_value: str = "value:1") -> CompetingHypothesisRegister:
    return CompetingHypothesisRegister(
        (
            {
                "hypothesis_id": "hyp:left",
                "expectations": {
                    "obs:first": "value:0",
                    "obs:second": "value:0",
                },
            },
            {
                "hypothesis_id": "hyp:right",
                "expectations": {
                    "obs:first": first_value,
                    "obs:second": "value:1",
                },
            },
        )
    )


def test_synthetic_register_starts_with_three_viable_hypotheses() -> None:
    register = synthetic_competing_hypothesis_register()

    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1", "hyp:2")
    exported = validate_competing_hypothesis_aggregate_export(
        register.aggregate_export()
    )
    assert exported["hypothesis_count"] == 3
    assert exported["viable_count"] == 3
    assert exported["retired_count"] == 0


def test_observation_selection_is_deterministic_and_pending_is_idempotent() -> None:
    first = synthetic_competing_hypothesis_register()
    second = synthetic_competing_hypothesis_register()

    first_action = first.select_discriminating_observation(at_tick=1)
    second_action = second.select_discriminating_observation(at_tick=1)
    repeated_action = first.select_discriminating_observation(at_tick=1)

    assert first_action == second_action
    assert first_action["observation_id"] == "obs:0"
    assert first_action["new_action"] is True
    assert repeated_action["observation_id"] == "obs:0"
    assert repeated_action["new_action"] is False
    assert first.aggregate_export()["actions_issued"] == 1


def test_observed_value_retires_only_the_contradicted_branch_and_changes_the_next_choice() -> None:
    register = synthetic_competing_hypothesis_register()
    first = register.select_discriminating_observation(at_tick=1)
    assert first["observation_id"] == "obs:0"

    outcome = register.record_observation(
        {
            "observation_id": first["observation_id"],
            "status": "observed",
            "value": "value:0",
        },
        at_tick=1,
    )

    assert outcome["status"] == "observed"
    assert outcome["retired_count"] == 1
    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1")

    # obs:0 no longer splits the survivors; obs:1 now becomes the unique
    # deterministic discriminator.
    second = register.select_discriminating_observation(at_tick=2)
    assert second["observation_id"] == "obs:1"
    second_outcome = register.record_observation(
        {
            "observation_id": second["observation_id"],
            "status": "observed",
            "value": "value:1",
        },
        at_tick=2,
    )
    assert second_outcome["retired_count"] == 1
    assert register.viable_hypothesis_ids == ("hyp:1",)
    assert register.aggregate_export()["contradicted_retirements"] == 2


def test_selection_is_branch_sensitive_to_declared_structural_values() -> None:
    first_splits = _two_branch_register(first_value="value:1")
    second_splits = _two_branch_register(first_value="value:0")

    assert first_splits.select_discriminating_observation()["observation_id"] == "obs:first"
    # The first observation now carries the same value for both branches, so
    # only the second declared observation remains discriminating.
    assert second_splits.select_discriminating_observation()["observation_id"] == "obs:second"


@pytest.mark.parametrize(
    "status",
    [
        "missing",
        "stale",
        "conflicting",
        "non_discriminating",
        "instrumentation_loss",
    ],
)
def test_observation_faults_are_explicit_unknowns_and_never_retire(
    status: str,
) -> None:
    register = synthetic_competing_hypothesis_register()
    action = register.select_discriminating_observation()

    outcome = register.record_observation(
        {"observation_id": action["observation_id"], "status": status}
    )

    assert outcome["status"] == "unknown"
    assert outcome["reason"] == status
    assert outcome["retired_count"] == 0
    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1", "hyp:2")
    exported = register.aggregate_export()
    assert exported["retired_count"] == 0
    assert exported["observation_faults"] == 1
    assert exported["fault_status_counts"][status] == 1


def test_undeclared_observed_value_is_instrumentation_loss_without_retirement() -> None:
    register = synthetic_competing_hypothesis_register()
    action = register.select_discriminating_observation()

    outcome = register.record_observation(
        {
            "observation_id": action["observation_id"],
            "status": "observed",
            "value": "value:undeclared",
        }
    )

    assert outcome["status"] == "unknown"
    assert outcome["reason"] == "instrumentation_loss"
    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1", "hyp:2")


def test_action_budget_guard_blocks_further_selection() -> None:
    register = synthetic_competing_hypothesis_register(max_actions=1)
    action = register.select_discriminating_observation()
    register.record_observation(
        {
            "observation_id": action["observation_id"],
            "status": "observed",
            "value": "value:0",
        }
    )

    blocked = register.select_discriminating_observation()

    assert blocked["status"] == "unknown"
    assert blocked["reason"] == "action_budget_exhausted"
    assert register.aggregate_export()["actions_issued"] == 1
    assert register.aggregate_export()["guard_counts"]["action_budget_exhausted"] == 1


def test_observation_budget_guard_blocks_further_observation_attempts() -> None:
    register = synthetic_competing_hypothesis_register(max_observations=1)
    action = register.select_discriminating_observation()
    first = register.record_observation(
        {"observation_id": action["observation_id"], "status": "missing"}
    )
    assert first["reason"] == "missing"

    blocked = register.select_discriminating_observation()

    assert blocked["status"] == "unknown"
    assert blocked["reason"] == "observation_budget_exhausted"
    assert register.aggregate_export()["observation_attempts"] == 1


def test_deadline_guard_is_bounded_and_does_not_issue_an_action() -> None:
    register = synthetic_competing_hypothesis_register(deadline_tick=2)
    action = register.select_discriminating_observation(at_tick=1)
    register.record_observation(
        {
            "observation_id": action["observation_id"],
            "status": "observed",
            "value": "value:0",
        },
        at_tick=1,
    )

    blocked = register.select_discriminating_observation(at_tick=2)

    assert blocked["status"] == "unknown"
    assert blocked["reason"] == "deadline_exceeded"
    assert register.aggregate_export()["actions_issued"] == 1
    assert register.aggregate_export()["guard_counts"]["deadline_exceeded"] == 1


def test_backward_tick_is_a_stale_unknown_without_state_change() -> None:
    register = synthetic_competing_hypothesis_register()
    action = register.select_discriminating_observation(at_tick=3)

    stale = register.record_observation(
        {
            "observation_id": action["observation_id"],
            "status": "observed",
            "value": "value:0",
        },
        at_tick=2,
    )

    assert stale["status"] == "unknown"
    assert stale["reason"] == "stale_tick"
    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1", "hyp:2")
    assert register.aggregate_export()["retired_count"] == 0


def test_same_state_generic_control_message_does_not_issue_or_mutate() -> None:
    enabled = synthetic_competing_hypothesis_register(enabled=True)
    disabled = synthetic_competing_hypothesis_register(enabled=False)
    before = enabled.aggregate_export()

    enabled_control = enabled.generic_message_control()
    disabled_control = disabled.generic_message_control()
    after = enabled.aggregate_export()

    assert before == after
    assert enabled_control == disabled_control
    assert enabled_control["message"] == (
        "Continue with the next bounded structural observation."
    )
    assert enabled_control["observation_id"] is None
    assert enabled.pending_observation_id is None


def test_disabled_mode_is_inert_for_actions_observations_and_exports() -> None:
    register = synthetic_competing_hypothesis_register(enabled=False)
    before = register.aggregate_export()

    action = register.select_discriminating_observation(at_tick=1)
    observation = register.record_observation(
        {"observation_id": "obs:0", "status": "observed", "value": "value:0"},
        at_tick=1,
    )
    after = register.aggregate_export()

    assert action["status"] == "disabled"
    assert observation["status"] == "disabled"
    assert before == after
    assert register.viable_hypothesis_ids == ("hyp:0", "hyp:1", "hyp:2")
    assert register.pending_observation_id is None


def test_aggregate_export_is_structural_only_and_does_not_leak_opaque_inputs() -> None:
    secret = "LEAK_SECRET"
    register = CompetingHypothesisRegister(
        (
            {
                "hypothesis_id": f"hyp:{secret}_A",
                "expectations": {
                    f"obs:{secret}": f"value:{secret}_0",
                    "obs:shared": "value:0",
                },
            },
            {
                "hypothesis_id": f"hyp:{secret}_B",
                "expectations": {
                    f"obs:{secret}": f"value:{secret}_1",
                    "obs:shared": "value:0",
                },
            },
        )
    )
    action = register.select_discriminating_observation()
    register.record_observation(
        {
            "observation_id": action["observation_id"],
            "status": "observed",
            "value": f"value:{secret}_0",
        }
    )
    exported = register.aggregate_export()

    serialised = json.dumps(exported, sort_keys=True)
    assert secret not in serialised
    assert "hyp:" not in serialised
    assert "obs:" not in serialised
    assert "value:" not in serialised
    assert validate_competing_hypothesis_aggregate_export(exported) == exported

    leaky = {**exported, "raw": secret}
    with pytest.raises(ValueError, match="schema differs"):
        validate_competing_hypothesis_aggregate_export(leaky)


def test_register_rejects_unbounded_or_duplicate_hypothesis_declarations() -> None:
    with pytest.raises(ValueError, match="count is outside its bound"):
        CompetingHypothesisRegister(
            (
                {
                    "hypothesis_id": "hyp:only",
                    "expectations": {"obs:0": "value:0"},
                },
            )
        )

    with pytest.raises(ValueError, match="IDs must be unique"):
        CompetingHypothesisRegister(
            (
                {
                    "hypothesis_id": "hyp:duplicate",
                    "expectations": {"obs:0": "value:0"},
                },
                {
                    "hypothesis_id": "hyp:duplicate",
                    "expectations": {"obs:0": "value:1"},
                },
            )
        )
