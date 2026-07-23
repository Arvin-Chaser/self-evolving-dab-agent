import json
from pathlib import Path

from experiments.build_meta_agent_evidence_pack import build_fine_grained_feedback_pack
from experiments.helper_repair_planner import plan_helper_repair
from experiments.meta_agent_cycle import compute_evolution_assessment
from experiments.run_codex_qwen_repair_launcher import (
    data_agent_tool_gate_soft_warning,
    data_agent_tool_helper_integration_check,
    data_agent_tool_helper_plan_check,
    data_agent_tool_helper_quality_check,
    load_helper_repair_plan,
)
from experiments.run_meta_agent_evolution_loop import generated_code_uses_helper


VALIDATION_REASON = (
    "Expected 50 unique CPC codes, got 55 unique CPC codes.\n"
    "Missing CPC codes (19): A01B1/00, A01B3/00\n"
    "Extra CPC codes (24): A01B5/00, A01B7/00"
)


def test_answer_delta_overrides_broad_primary_signal(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text(json.dumps({"validation_reason": VALIDATION_REASON}), encoding="utf-8")
    (run_dir / "agent_error_summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "pipeline_diagnostics.json").write_text("{}", encoding="utf-8")
    (run_dir / "stage_trace.json").write_text(
        json.dumps(
            [
                {"event": "cpc_definition_parsed", "outputs": {"parsed_rows": 10}},
                {"event": "cpc_hierarchy_built", "outputs": {"symbols_with_parents": 10, "level_distribution": {"5": 8}}},
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "final_answer.txt").write_text("A01B1/00\nA01B5/00\n", encoding="utf-8")

    feedback = build_fine_grained_feedback_pack(
        run_dir,
        primary_signal={"selected_stage": "granularity_mapping", "selected_signal": "broad CPC granularity issue"},
    )

    assert feedback["selected_stage"] == "answer_delta"
    assert "expected_count=50" in feedback["selected_signal"]
    assert feedback["repair_routing"]["recommended_repair_layer"] == "answer_delta_mapping_or_ranking"


def test_answer_delta_routes_to_action_filtering_before_ema_or_granularity():
    feedback = {
        "selected_stage": "granularity_mapping",
        "selected_signal": "EMA/best year and CPC granularity are suspicious",
        "answer_delta": {"expected_count": 50, "predicted_count": 55, "missing_count": 19, "extra_count": 24, "f1": 0.590476},
        "runtime_trace_evidence": [],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/candidate_filtering.py"
    assert plan["required_functions"][0]["name"] == "rank_or_filter_candidates"


def test_declared_helper_target_must_have_real_helper_diff(tmp_path: Path):
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "patch_numstat.txt").write_text(
        "1\t1\tprompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt\n",
        encoding="utf-8",
    )
    spec = {
        "target_files": [
            "adapters/patents/answer_diagnostics.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [],
    }

    ok, reason = data_agent_tool_helper_plan_check(spec, None, candidate_dir)

    assert not ok
    assert "declared_helper_target_no_effect" in reason


def test_shadow_parent_requires_relative_f1_improvement(tmp_path: Path):
    archive_root = tmp_path / "archive"
    parent_dir = archive_root / "agents" / "parent_agent"
    parent_dir.mkdir(parents=True)
    (parent_dir / "agent_card.json").write_text(
        json.dumps(
            {
                "evals": {
                    "PATENTS_query1": {
                        "answer_metrics": {"f1": 0.590476, "precision": 0.563636, "recall": 0.62}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    child_eval = {
        "child_run_exit_code": 0,
        "child_status": {
            "validation_reason": VALIDATION_REASON,
            "selected_stage": "answer_delta",
            "selected_signal": "same metrics as parent",
        },
    }

    assessment = compute_evolution_assessment(
        "data_agent_repair",
        child_eval,
        archive_root=archive_root,
        parent_agent_id="parent_agent",
    )

    assert assessment["evolution_status"] == "failed_no_relative_answer_improvement"
    assert assessment["evolution_parent_eligible"] is False
    assert assessment["parent_comparison_metrics"]["delta_f1"] == 0.0


def test_materialized_parent_recovery_does_not_replace_archive_best(tmp_path: Path):
    archive_root = tmp_path / "archive"
    parent_dir = archive_root / "agents" / "query2_best_parent"
    parent_dir.mkdir(parents=True)
    (parent_dir / "agent_card.json").write_text(
        json.dumps(
            {
                "evals": {
                    "PATENTS_query2": {
                        "answer_metrics": {"f1": 0.9545, "precision": 1.0, "recall": 0.913}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    child_eval = {
        "child_run_exit_code": 0,
        "parent_answer_metrics": {"available": True, "f1": 0.0, "precision": 0.0, "recall": 0.0, "predicted_count": 0},
        "child_answer_metrics": {"available": True, "f1": 0.9545, "precision": 1.0, "recall": 0.913, "predicted_count": 21},
        "child_status": {
            "selected_stage": "answer_validation",
            "selected_signal": "answer_quality_mismatch;f1=0.9545",
        },
    }

    assessment = compute_evolution_assessment(
        "data_agent_repair",
        child_eval,
        archive_root=archive_root,
        parent_agent_id="query2_best_parent",
        case_id="PATENTS_query2",
    )

    assert assessment["evolution_status"] == "stabilization_or_reproduction_repair"
    assert assessment["evolution_parent_eligible"] is False
    comparison = assessment["parent_comparison_metrics"]
    assert comparison["comparison_baseline"] == "dual_materialized_and_archive_parent"
    assert comparison["delta_f1_vs_materialized_parent"] == 0.9545
    assert comparison["delta_f1_vs_archive_parent"] == 0.0
    assert comparison["materialized_parent_reproduction_gap"] is True
    assert comparison["restored_to_archive_parent_level"] is True

def test_negated_ground_truth_is_not_hardcoding():
    from experiments.run_codex_qwen_repair_launcher import no_hardcoded_answer_check

    spec = {
        "edits": [
            {
                "file": "adapters/patents/answer_diagnostics.py",
                "intended_change": "Summarize candidates without using ground truth answers or expected answer values.",
                "rationale": "Benchmark-safe diagnostic helper; no hardcoded expected CPC answers.",
            }
        ]
    }

    ok, reason = no_hardcoded_answer_check(spec)

    assert ok, reason


def test_answer_delta_routing_preempts_ema_when_answer_delta_actionable(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text(json.dumps({"validation_reason": VALIDATION_REASON}), encoding="utf-8")
    (run_dir / "agent_error_summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "pipeline_diagnostics.json").write_text("{}", encoding="utf-8")
    (run_dir / "stage_trace.json").write_text(
        json.dumps([{"event": "ema_summary", "outputs": {"best_year": 2020}}]),
        encoding="utf-8",
    )
    (run_dir / "final_answer.txt").write_text("A01B1/00\nA01B5/00\n", encoding="utf-8")

    feedback = build_fine_grained_feedback_pack(
        run_dir,
        primary_signal={"selected_stage": "schema_grounding", "selected_signal": "EMA and best year look suspicious"},
    )

    assert feedback["selected_stage"] == "answer_delta"
    assert feedback["repair_routing"]["recommended_repair_layer"] == "answer_delta_mapping_or_ranking"

def test_candidate_filtering_rejects_best_year_only_noop():
    spec = {
        "target_files": ["adapters/patents/candidate_filtering.py"],
        "edits": [
            {
                "file": "adapters/patents/candidate_filtering.py",
                "intended_change": """
def rank_or_filter_candidates(candidate_rows, *, target_year=2022):
    filtered = [row for row in candidate_rows if row.get('best_year') == target_year]
    sorted_candidates = sorted(filtered, key=lambda r: (-r.get('count', 0), r.get('symbol', '')))
    return [row['symbol'] for row in sorted_candidates]
""",
                "rationale": "Filter by target year and sort by count.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_quality_check(spec)

    assert not ok
    assert "weak_filtering_no_op" in reason


def test_candidate_filtering_glue_requires_full_candidate_rows():
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [
            {
                "file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
                "anchor": "Answer synthesis and validation:",
                "intended_change": "You MUST import and use rank_or_filter_candidates from adapters.patents.candidate_filtering on candidates_2022. Do not reimplement this logic inline.",
                "rationale": "Use candidate filtering helper after pre-filtering.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_integration_check(spec)

    assert not ok
    assert "weak_filtering_no_op" in reason


def test_candidate_filtering_glue_allows_full_candidate_rows():
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [
            {
                "file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
                "anchor": "Answer synthesis and validation:",
                "intended_change": "You MUST import and use rank_or_filter_candidates from adapters.patents.candidate_filtering on full candidate_rows before final filtering. Do not reimplement this logic inline.",
                "rationale": "The helper must consume full candidate_rows and produce the final answer symbols.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_integration_check(spec)

    assert ok, reason


def test_shadow_parent_negative_delta_is_explicitly_flagged(tmp_path: Path):
    archive_root = tmp_path / "archive"
    parent_dir = archive_root / "agents" / "parent_agent"
    parent_dir.mkdir(parents=True)
    (parent_dir / "agent_card.json").write_text(
        json.dumps(
            {
                "evals": {
                    "PATENTS_query1": {
                        "answer_metrics": {"f1": 0.590476, "precision": 0.563636, "recall": 0.62}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    child_eval = {
        "child_run_exit_code": 0,
        "child_status": {
            "validation_reason": (
                "strict_match_failed: expected 50 unique CPC codes, got 60 unique CPC codes.\n"
                "Missing CPC codes (18): A23P, A24D\n"
                "Extra CPC codes (28): A01P, A21C"
            ),
            "selected_stage": "answer_delta",
            "selected_signal": "worse metrics than parent",
        },
    }

    assessment = compute_evolution_assessment(
        "data_agent_repair",
        child_eval,
        archive_root=archive_root,
        parent_agent_id="parent_agent",
    )

    assert assessment["evolution_status"] == "failed_negative_delta"
    assert assessment["evolution_parent_eligible"] is False
    assert assessment["parent_comparison_metrics"]["delta_f1"] < 0


def test_candidate_filtering_glue_allows_unfiltered_candidate_rows_phrase():
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [
            {
                "file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
                "anchor": "Answer synthesis and validation:",
                "intended_change": "You MUST import and use rank_or_filter_candidates from adapters.patents.candidate_filtering. Pass the full list of unfiltered candidate rows to rank_or_filter_candidates and use its output as final CPC symbols. Do not reimplement this logic inline.",
                "rationale": "The helper must consume unfiltered candidate rows and produce the final answer symbols.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_integration_check(spec)

    assert ok, reason



def test_v002_action_helper_requires_behavior_change_contract(tmp_path: Path):
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
    seed = tmp_path / "repair_seed.json"
    seed.write_text(json.dumps({"helper_repair_plan": plan}), encoding="utf-8")
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [
            {
                "file": "adapters/patents/candidate_filtering.py",
                "operation": "create_file",
                "anchor": "",
                "intended_change": "def rank_or_filter_candidates(candidate_rows, *, target_year=2022):\n    return [row['symbol'] for row in candidate_rows]",
                "rationale": "Implements rank_or_filter_candidates.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_plan_check(spec, seed)

    assert not ok
    assert "behavior_change_contract_missing" in reason


def test_v002_action_helper_accepts_behavior_changing_contract(tmp_path: Path):
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
    seed = tmp_path / "repair_seed.json"
    seed.write_text(json.dumps({"helper_repair_plan": plan}), encoding="utf-8")
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "behavior_change_contract": {
            "before": "Parent generated_solve wrote final answer directly from generated heuristic candidates.",
            "after": "Child generated_solve calls rank_or_filter_candidates on full candidate_rows and uses selected_symbols for final_answer.txt.",
            "decision_path_change": "Move selection/filtering into rank_or_filter_candidates and exclude weak candidates before final_answer construction.",
            "child_observable_effect": "generated_solve imports the helper and final_answer.txt is constructed from helper output selected_symbols.",
            "why_not_diagnostics_only": "The helper output is used to construct final_answer.txt, not just to log diagnostics.",
        },
        "edits": [
            {
                "file": "adapters/patents/candidate_filtering.py",
                "operation": "create_file",
                "anchor": "",
                "intended_change": "def rank_or_filter_candidates(candidate_rows, *, target_year=2022):\n    selected_symbols = []\n    for row in candidate_rows:\n        if row.get('best_year') == target_year and row.get('count', 0) > 1:\n            selected_symbols.append(row['symbol'])\n    return selected_symbols",
                "rationale": "Implements rank_or_filter_candidates to produce selected_symbols for final answer filtering.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_plan_check(spec, seed)

    assert ok, reason


def test_data_agent_tool_rejects_diagnostics_only_helper():
    spec = {
        "target_files": ["adapters/patents/answer_diagnostics.py"],
        "edits": [
            {
                "file": "adapters/patents/answer_diagnostics.py",
                "intended_change": "def summarize_candidate_decisions(candidate_rows): return {'total': len(candidate_rows)}",
                "rationale": "Add candidate diagnostics and log candidate_decision_summary.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_quality_check(spec)

    assert not ok
    assert "diagnostics_only_action_helper_rejected" in reason


def test_generated_helper_call_must_feed_final_answer(tmp_path: Path):
    generated = tmp_path / "generated_solve.py"
    generated.write_text(
        """
from adapters.patents.answer_diagnostics import summarize_candidate_decisions
FINAL_ANSWER_PATH = Path('final_answer.txt')
summary = summarize_candidate_decisions(candidate_rows)
log_event(event='candidate_decision_summary', outputs={'summary': summary})
FINAL_ANSWER_PATH.write_text('\n'.join(result_codes) + '\n')
""",
        encoding="utf-8",
    )

    usage = generated_code_uses_helper(
        generated,
        [{"path": "adapters/patents/answer_diagnostics.py", "module": "adapters.patents.answer_diagnostics", "stem": "answer_diagnostics"}],
    )

    assert usage["status"] == "helper_called_by_child_generated_code"
    assert usage["final_answer_dependency"]["status"] == "helper_called_but_output_not_used_for_final_answer"


def test_generated_candidate_filtering_helper_feeds_final_answer(tmp_path: Path):
    generated = tmp_path / "generated_solve.py"
    generated.write_text(
        """
from adapters.patents.candidate_filtering import rank_or_filter_candidates
FINAL_ANSWER_PATH = Path('final_answer.txt')
selected_symbols = rank_or_filter_candidates(candidate_rows, target_year=2022)
FINAL_ANSWER_PATH.write_text('\n'.join(selected_symbols) + '\n')
""",
        encoding="utf-8",
    )

    usage = generated_code_uses_helper(
        generated,
        [{"path": "adapters/patents/candidate_filtering.py", "module": "adapters.patents.candidate_filtering", "stem": "candidate_filtering"}],
    )

    assert usage["status"] == "helper_called_by_child_generated_code"
    assert usage["final_answer_dependency"]["status"] == "helper_output_used_for_final_answer"


def test_candidate_filtering_glue_allows_negated_prefiltered_language():
    spec = {
        "target_files": [
            "adapters/patents/candidate_filtering.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ],
        "edits": [
            {
                "file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
                "anchor": "Answer synthesis and validation:",
                "intended_change": "You MUST import and use rank_or_filter_candidates from adapters.patents.candidate_filtering. MUST pass the full unfiltered candidate_rows list, not pre-filtered subsets, and use returned symbols for final_answer.txt. Do not reimplement this logic inline.",
                "rationale": "The helper must consume full candidate_rows and produce the final answer symbols.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_integration_check(spec)

    assert ok, reason


def test_candidate_filtering_quality_allows_negated_expected_count_language():
    spec = {
        "target_files": ["adapters/patents/candidate_filtering.py"],
        "edits": [
            {
                "file": "adapters/patents/candidate_filtering.py",
                "intended_change": "def rank_or_filter_candidates(candidate_rows, *, target_year=2022):\n    selected = [row['symbol'] for row in candidate_rows if row.get('best_year') == target_year and row.get('count', 0) > 1]\n    return selected",
                "rationale": "Uses evidence-based filtering. No hardcoded answers or expected counts are used.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_quality_check(spec)

    assert ok, reason


def test_data_agent_tool_gate_soft_warning_classification():
    assert data_agent_tool_gate_soft_warning("weak_filtering_no_op: maybe too weak") is True
    assert data_agent_tool_gate_soft_warning("metric_gaming_guard: suspicious expected count wording") is True
    assert data_agent_tool_gate_soft_warning("diagnostics_only_action_helper_rejected: likely observation only") is True
    assert data_agent_tool_gate_soft_warning("helper_plan_target_mismatch: alternative helper selected") is True
    assert data_agent_tool_gate_soft_warning("helper_not_integrated: child eval should decide actual usage") is True

    assert data_agent_tool_gate_soft_warning("declared_helper_target_no_effect: no real helper diff") is True
    assert data_agent_tool_gate_soft_warning("helper_plan_target_no_effect: final patch did not change required helper") is True
    assert data_agent_tool_gate_soft_warning("behavior_change_contract_missing: malformed action helper") is True
    assert data_agent_tool_gate_soft_warning("metadata_grounding_violation: unsafe CPC fallback") is True


def test_repair_seed_override_recomputes_stale_helper_plan(tmp_path: Path):
    seed = {
        "repair_profile": "data_agent_tool_repair",
        "selected_stage": "schema_grounding",
        "selected_signal": "The task has a hierarchy/level requirement and a definition/metadata source is provided, but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH.",
        "answer_delta": {"predicted_count": 0},
        "helper_repair_plan": {
            "status": "planned",
            "recommended_helper_file": "adapters/patents/candidate_filtering.py",
            "required_functions": [{"name": "rank_or_filter_candidates"}],
        },
        "fine_grained_feedback": {
            "selected_stage": "schema_grounding",
            "selected_signal": "The task has a hierarchy/level requirement and a definition/metadata source is provided, but generated_solve.py does not actually read CPC_DEFINITION_SQL_PATH.",
            "answer_delta": {"predicted_count": 0},
            "helper_repair_plan": {
                "status": "planned",
                "recommended_helper_file": "adapters/patents/candidate_filtering.py",
                "required_functions": [{"name": "rank_or_filter_candidates"}],
            },
        },
    }
    seed_path = tmp_path / "repair_seed.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")

    plan = load_helper_repair_plan(seed_path)

    assert plan["recommended_helper_file"] == "adapters/patents/cpc_definition_parser.py"
    assert plan["required_functions"][0]["name"] == "parse_cpc_definition_sql"
    assert plan["plan_source"] == "recomputed_from_repair_seed_with_current_planner"
    assert plan["cached_helper_repair_plan_ignored"] is True
    assert "recomputed_from_cached_helper_repair_plan" not in plan


def test_cpc_definition_parser_rejects_tuple_return_contract():
    spec = {
        "target_files": ["adapters/patents/cpc_definition_parser.py"],
        "edits": [
            {
                "file": "adapters/patents/cpc_definition_parser.py",
                "intended_change": "def parse_cpc_definition_sql(sql_path) -> tuple[dict, dict]:\n    symbol_to_level = {}\n    symbol_to_parents = {}\n    return symbol_to_level, symbol_to_parents",
                "rationale": "Return parsed CPC metadata.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_quality_check(spec)

    assert not ok
    assert "cpc_definition_parser_return_contract_violation" in reason


def test_cpc_definition_parser_accepts_dict_return_contract():
    spec = {
        "target_files": ["adapters/patents/cpc_definition_parser.py"],
        "edits": [
            {
                "file": "adapters/patents/cpc_definition_parser.py",
                "intended_change": "def parse_cpc_definition_sql(sql_path) -> dict[str, dict]:\n    symbol_to_level = {}\n    symbol_to_parents = {}\n    return {'symbol_to_level': symbol_to_level, 'symbol_to_parents': symbol_to_parents}",
                "rationale": "Return metadata dict with symbol_to_level and symbol_to_parents keys.",
            }
        ],
    }

    ok, reason = data_agent_tool_helper_quality_check(spec)

    assert ok, reason


def test_multi_query_empty_child_answers_are_not_parent_eligible():
    child_eval = {
        "final_status": "candidate_child_eval_improved_but_failed",
        "parent_child_delta": {
            "delta_successful_run_count": 2,
            "child_successful_run_count": 2,
            "child_final_answer_nonempty_count": 0,
            "delta_final_answer_nonempty_count": 0,
            "delta_tool_failure_count": 2,
            "delta_helper_registered_but_not_called_count": 2,
            "improved_success_count": True,
        },
        "child_multi_query_summary": {
            "query_count": 2,
            "successful_run_count": 2,
            "final_answer_nonempty_count": 0,
            "average_f1": 0.0,
            "per_query_feedback": [
                {
                    "query_id": "PATENTS/query1",
                    "final_answer_nonempty": False,
                    "answer_quality": {
                        "strict_match_passed": False,
                        "missing_count": 72,
                        "extra_count": 0,
                        "f1": 0.0,
                    },
                },
                {
                    "query_id": "stockindex/query1",
                    "final_answer_nonempty": False,
                    "answer_quality": {
                        "strict_match_passed": False,
                        "missing_count": 1,
                        "extra_count": 0,
                        "f1": 0.0,
                    },
                },
            ],
        },
        "child_status": {
            "selected_stage": "tool_execution",
            "selected_signal": "multi_query_child_eval_failed",
        },
    }

    assessment = compute_evolution_assessment("data_agent_repair", child_eval)

    assert assessment["evolution_status"] == "failed_empty_child_answers_not_parent_eligible"
    assert assessment["evolution_parent_eligible"] is False
    assert assessment["reward"] == 0.0
    assert assessment["multi_query_metrics"]["answer_parent_gate_blocked_empty_child_answer"] is True
    assert assessment["multi_query_metrics"]["reward_reasons"] == ["blocked_empty_child_answers_no_parent_reward"]
