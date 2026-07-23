import json

from experiments.archive_observation import build_archive_observation, normalize_proposed_contracts


def test_normalize_proposed_contracts_preserves_open_contract_payload():
    payload = [
        {
            "id": "helper_final_answer_sink",
            "statement": "Helper output must flow into final_answer construction.",
            "target_files": ["generated_solve.py"],
            "expected_observable_effect": "final_answer contains helper-filtered symbols",
            "validation_hint": "trace helper output variable to final_answer write",
            "custom_meta_agent_field": {"kept": True},
        }
    ]

    normalized = normalize_proposed_contracts(payload)

    assert normalized["schema_version"] == "proposed_contracts_v001"
    assert normalized["present"] is True
    assert normalized["summary"]["contract_count"] == 1
    assert normalized["summary"]["target_files"] == ["generated_solve.py"]
    assert normalized["contracts"][0]["contract_id"] == "helper_final_answer_sink"
    assert normalized["contracts"][0]["statement"] == "Helper output must flow into final_answer construction."
    assert normalized["contracts"][0]["raw"]["custom_meta_agent_field"] == {"kept": True}


def test_archive_observation_saves_proposed_contracts_from_patch_spec(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "patch_spec_raw.txt").write_text(
        json.dumps(
            {
                "status": "patch_spec",
                "proposed_contracts": [
                    {
                        "contract_id": "parser_contract",
                        "contract": "Parser output must be consumed by ranking logic.",
                        "target_files": ["adapters/patents/candidate_filtering.py"],
                        "success_condition": "answer_delta.f1 improves",
                    }
                ],
            }
        )
    )
    child_eval = candidate / "child_eval"
    child_eval.mkdir()
    (child_eval / "child_eval_report.json").write_text(
        json.dumps(
            {
                "final_status": "candidate_child_eval_failed",
                "child_answer_metrics": {"f1": 0.25},
                "parent_answer_metrics": {"f1": 0.5},
            }
        )
    )

    observation = build_archive_observation(candidate)
    proposed = observation["observations"]["proposed_contracts"]

    assert proposed["schema_version"] == "proposed_contracts_v001"
    assert proposed["present"] is True
    assert proposed["summary"]["contract_count"] == 1
    assert proposed["contracts"][0]["contract_id"] == "parser_contract"
    assert proposed["contracts"][0]["expected_observable_effect"] == "answer_delta.f1 improves"
    assert "has_proposed_contracts" in observation["observations"]["failure_observation_tags"]


def test_archive_observation_contract_eval_flags_violated_helper_flow_contract(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "patch_spec_raw.txt").write_text(
        json.dumps(
            {
                "status": "patch_spec",
                "proposed_contracts": [
                    {
                        "contract_id": "helper_flow",
                        "statement": "Helper output must be consumed by final_answer construction.",
                        "target_files": ["generated_solve.py"],
                    }
                ],
            }
        )
    )
    child_eval = candidate / "child_eval"
    child_eval.mkdir()
    (child_eval / "child_eval_report.json").write_text(
        json.dumps(
            {
                "final_status": "candidate_child_eval_failed",
                "child_failure_gates": ["helper_called_but_output_not_used_for_final_answer"],
                "helper_usage": {
                    "final_answer_dependency": {
                        "required": True,
                        "status": "helper_called_but_output_not_used_for_final_answer",
                    }
                },
                "child_answer_metrics": {"f1": 0.0},
                "parent_answer_metrics": {"f1": 0.5},
            }
        )
    )

    observation = build_archive_observation(candidate)
    contract_eval = observation["observations"]["contract_eval"]

    assert contract_eval["schema_version"] == "contract_eval_v001"
    assert contract_eval["layer"] == "soft_observation"
    assert contract_eval["blocks_parent_selection"] is False
    assert contract_eval["status"] == "contract_eval_has_violations"
    assert contract_eval["summary"]["violated_count"] == 1
    assert contract_eval["evaluated_contracts"][0]["status"] == "violated_by_child_observation"
    assert "contract_eval_has_violations" in observation["observations"]["failure_observation_tags"]


def test_archive_observation_parent_eligibility_allows_small_f1_drop(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    child_eval = candidate / "child_eval"
    child_eval.mkdir()
    (child_eval / "child_eval_report.json").write_text(
        json.dumps(
            {
                "final_status": "candidate_child_eval_passed",
                "child_passed": True,
                "child_failure_gates": [],
                "child_answer_metrics": {"f1": 0.571},
                "parent_answer_metrics": {"f1": 0.6},
            }
        )
    )

    observation = build_archive_observation(candidate)

    assert observation["promotion"]["eligible_as_parent"] is True
    assert observation["promotion"]["f1_close_enough"] is True
    assert observation["promotion"]["parent_f1_tolerance"] == 0.03
