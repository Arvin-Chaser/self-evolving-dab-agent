from experiments.helper_repair_planner import plan_helper_repair


def test_cpc_mapping_typeerror_routes_to_cpc_mapping_helper():
    feedback = {
        "selected_stage": "runtime_execution",
        "selected_signal": "unknown execution error",
        "runtime_trace_evidence": [
            {
                "event": "exception",
                "error": {
                    "type": "TypeError",
                    "message": "'>' not supported between instances of 'int' and 'str'",
                    "traceback": "File \"adapters/patents/cpc_mapping.py\", line 31, in get_level5_symbol\n    elif level and level > 5",
                },
            }
        ],
        "ranked_feedback_signals": [
            {
                "stage": "unknown_component",
                "message": "TypeError in adapters/patents/cpc_mapping.py get_level5_symbol: level > 5",
            }
        ],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/cpc_mapping.py"
    assert plan["required_functions"][0]["name"] == "get_level5_symbol"
    must_handle = "\n".join(plan["required_functions"][0]["must_handle"]).lower()
    assert "coerce numeric-like level values to int" in must_handle
    assert "typeerror" in "\n".join(plan["success_criteria"]).lower()


def test_answer_delta_with_existing_diagnostics_routes_to_action_filtering_helper():
    feedback = {
        "selected_stage": "answer_delta",
        "selected_signal": "non-empty answer has measurable expected/predicted CPC delta",
        "answer_delta": {"expected_count": 50, "predicted_count": 55, "missing_count": 19, "extra_count": 24, "f1": 0.590476},
        "runtime_trace_evidence": [
            {
                "event": "candidate_decision_summary",
                "outputs": {"total_candidates": 55, "included_count": 55, "excluded_count": 0},
            }
        ],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/candidate_filtering.py"
    assert plan["required_functions"][0]["name"] == "rank_or_filter_candidates"
    assert "not merely for logging" in "\n".join(plan["success_criteria"]).lower()


def test_action_filtering_plan_emits_behavior_contract_v002():
    feedback = {
        "selected_stage": "answer_delta",
        "selected_signal": "non-empty answer has measurable expected/predicted CPC delta",
        "answer_delta": {"expected_count": 50, "predicted_count": 55, "missing_count": 19, "extra_count": 24, "f1": 0.590476},
        "runtime_trace_evidence": [
            {"event": "candidate_decision_summary", "outputs": {"total_candidates": 55, "included_count": 55, "excluded_count": 0}}
        ],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")
    contract = plan["patch_generation_contract"]

    assert contract["schema_version"] == "helper_patch_generation_contract_v002"
    assert contract["behavior_change_contract"]["required"] is True
    assert contract["behavior_change_contract"]["must_change_decision_path"] is True
    assert "diagnostics-only" in "\n".join(contract["behavior_change_contract"]["insufficient_patch_shapes"])


def test_schema_grounding_not_read_cpc_definition_preempts_answer_delta_filtering():
    feedback = {
        "selected_stage": "schema_grounding",
        "selected_signal": "The task has a hierarchy/level requirement and a definition/metadata source is provided, but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH.",
        "answer_delta": {"predicted_count": 0, "predicted_codes_sample": []},
        "runtime_trace_evidence": [],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/cpc_definition_parser.py"
    assert plan["required_functions"][0]["name"] == "parse_cpc_definition_sql"
    assert "-> dict" in plan["required_functions"][0]["signature"]
    assert "tuple" not in plan["required_functions"][0]["signature"].lower()
    assert "metadata.get" in plan["helper_focus"]
    assert "CPC_DEFINITION_SQL_PATH" in plan["helper_focus"]
    contract = plan["patch_generation_contract"]
    assert "CPC_DEFINITION_SQL_PATH" in contract["helper_io_contract"]["inputs"]
    assert "symbol_to_level" in contract["helper_io_contract"]["outputs"]


def test_cpc_definition_tuple_get_error_preempts_answer_delta_filtering():
    feedback = {
        "selected_stage": "unknown_component",
        "selected_signal": "AttributeError: 'tuple' object has no attribute 'get' in generated_solve.py while reading symbol_to_level = cpc_hierarchy.get('symbol_to_level', {}) after parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH)",
        "answer_delta": {"predicted_count": 0},
        "runtime_trace_evidence": [
            {
                "event": "exception",
                "error": {
                    "type": "AttributeError",
                    "message": "'tuple' object has no attribute 'get'",
                    "traceback": "symbol_to_level = cpc_hierarchy.get('symbol_to_level', {}) after parse_cpc_definition_sql",
                },
            }
        ],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/cpc_definition_parser.py"
    assert plan["required_functions"][0]["name"] == "parse_cpc_definition_sql"
    assert "-> dict" in plan["required_functions"][0]["signature"]


def test_cpc_definition_copy_header_failure_routes_to_parser_repair():
    feedback = {
        "selected_stage": "schema_grounding",
        "selected_signal": "The task has a hierarchy/level requirement and a definition/metadata source is provided, but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH.",
        "analysis_summary": {
            "passed": False,
            "validation_reason": "ValueError: Failed to extract columns from COPY header in /home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql after parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH)",
        },
        "answer_delta": {"predicted_count": 0},
        "runtime_trace_evidence": [],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/cpc_definition_parser.py"
    assert plan["required_functions"][0]["name"] == "parse_cpc_definition_sql"
    assert "COPY public.cpc_definition" in plan["helper_focus"]
    assert "slicing between" in plan["helper_focus"]
    assert "real patent_CPCDefinition.sql" in "\n".join(plan["focused_validation_tests"])


def test_answer_delta_active_signal_not_overridden_by_stale_schema_routing():
    feedback = {
        "selected_stage": "answer_delta",
        "selected_signal": "non-empty answer has measurable expected/predicted CPC delta; expected_count=50; predicted_count=60; missing_count=18; extra_count=28; f1=0.5818",
        "answer_delta": {"expected_count": 50, "predicted_count": 60, "missing_count": 18, "extra_count": 28, "f1": 0.5818},
        "repair_routing": {
            "helper_repair_plan_summary": {
                "recommended_helper_file": "adapters/patents/cpc_definition_parser.py",
                "helper_focus": "stale schema_grounding plan says generated_solve.py did not read CPC_DEFINITION_SQL_PATH",
            }
        },
        "runtime_trace_evidence": [],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/candidate_filtering.py"
    assert plan["required_functions"][0]["name"] == "rank_or_filter_candidates"
