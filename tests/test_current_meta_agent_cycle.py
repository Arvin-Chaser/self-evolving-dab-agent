from experiments.meta_agent_cycle import score_multi_query_progress, summarize_multi_query_child_eval


def test_multi_query_empty_child_answers_are_not_parent_rewarded():
    child_eval = {
        "query_count": 2,
        "final_answer_nonempty_count": 0,
        "child_multi_query_summary": {
            "query_count": 2,
            "per_query_feedback": [
                {"query_id": "PATENTS_query1", "final_answer_nonempty": False},
                {"query_id": "STOCKINDEX_query1", "final_answer_nonempty": False},
            ],
        },
        "parent_child_delta": {
            "child_final_answer_nonempty_count": 0,
            "delta_final_answer_nonempty_count": 0,
        },
    }

    metrics = summarize_multi_query_child_eval(child_eval)
    reward, reasons = score_multi_query_progress(metrics)

    assert metrics["answer_parent_gate_blocked_empty_child_answer"] is True
    assert metrics["child_has_nonempty_answer"] is False
    assert reward == 0.0
    assert "blocked_empty_child_answers_no_parent_reward" in reasons
