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
