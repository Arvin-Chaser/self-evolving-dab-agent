from experiments.gate_policy import classify_validation_gate, should_block_validation


def test_gate_policy_keeps_safety_and_syntax_hard():
    hardcoding = {"name": "no_obvious_answer_hardcoding", "gate_layer": "hard_safety", "gate_type": "anti_cheating", "exit_code": 1}
    syntax = {"name": "py_compile_changed_helper.py", "gate_layer": "validation", "gate_type": "syntax", "exit_code": 1}

    assert classify_validation_gate(hardcoding) == "hard_gate"
    assert should_block_validation(hardcoding) is True
    assert classify_validation_gate(syntax) == "hard_gate"
    assert should_block_validation(syntax) is True


def test_gate_policy_records_semantic_and_real_data_checks_as_soft_observations():
    semantic = {
        "name": "data_agent_tool_helper_quality",
        "gate_layer": "task_contract",
        "gate_type": "no_op_or_metric_gaming_guard",
        "exit_code": 1,
        "hard_fail": False,
        "warning": True,
    }
    real_data = {
        "name": "real_cpc_definition_parser_smoke",
        "gate_layer": "validation",
        "gate_type": "real_data_parser_smoke",
        "exit_code": 1,
        "hard_fail": False,
        "warning": True,
    }

    assert classify_validation_gate(semantic) == "soft_observation"
    assert should_block_validation(semantic) is False
    assert classify_validation_gate(real_data) == "soft_observation"
    assert should_block_validation(real_data) is False