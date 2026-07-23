from experiments.archive_selector import build_selection_pools


def test_archive_selector_splits_agent_parent_and_candidate_evidence_pools():
    agent_rows = [
        {
            "agent_id": "good_agent_parent",
            "agent_type": "data_agent",
            "can_use_as_parent": True,
            "status": "shadow_parent_partial_improvement",
        }
    ]
    candidate_rows = [
        {
            "candidate_id": "useful_failure",
            "eligible_as_parent": False,
            "can_seed_next_repair": True,
            "use_as_negative_example": True,
            "has_open_diagnosis": True,
            "contract_eval_status": "contract_eval_has_violations",
            "failure_observation_tags": ["helper_output_sink_mismatch", "empty_final_answer"],
        },
    ]

    selection = build_selection_pools(
        candidate_rows,
        agent_rows=agent_rows,
        current_failure_tags=["helper_output_sink_mismatch"],
    )

    assert selection["schema_version"] == "archive_selection_v001"
    assert [item["agent_id"] for item in selection["parent_pool"]] == ["good_agent_parent"]
    assert [item["candidate_id"] for item in selection["evidence_pool"]] == ["useful_failure"]
    assert selection["parent_pool"][0]["selection_source"] == "archive_agents"
    assert selection["evidence_pool"][0]["selection_source"] == "archive_candidates"
    assert "matched_current_failure_tags:1" in selection["evidence_pool"][0]["selection_reasons"]


def test_archive_selector_penalizes_repeated_agent_parent():
    agent_rows = [
        {"agent_id": "old_parent", "agent_type": "data_agent", "can_use_as_parent": True, "status": "active_baseline"},
        {"agent_id": "fresh_parent", "agent_type": "data_agent", "can_use_as_parent": True, "status": "active_baseline"},
    ]

    selection = build_selection_pools([], agent_rows=agent_rows, recent_parent_ids=["old_parent"])

    assert selection["parent_pool"][0]["agent_id"] == "fresh_parent"
    assert "recent_parent_penalty" in selection["parent_pool"][1]["selection_reasons"]


def test_archive_selector_can_promote_eligible_candidate_as_parent():
    candidate_rows = [
        {
            "candidate_id": "near_f1_candidate",
            "eligible_as_parent": True,
            "promotion_score": 0.0,
            "metric_delta_f1": -0.02,
            "can_seed_next_repair": True,
        }
    ]

    selection = build_selection_pools(candidate_rows, agent_rows=[])

    assert selection["parent_pool"][0]["candidate_id"] == "near_f1_candidate"
    assert selection["parent_pool"][0]["selection_source"] == "archive_candidates"
    assert selection["evidence_pool"] == []
