import json
from pathlib import Path

from experiments.build_meta_agent_evidence_pack import build_fine_grained_feedback_pack
from experiments.helper_repair_planner import plan_helper_repair
from experiments.meta_agent_cycle import compute_evolution_assessment
from experiments.run_codex_qwen_repair_launcher import data_agent_tool_helper_plan_check


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


def test_answer_delta_routes_to_diagnostics_before_ema_or_granularity():
    feedback = {
        "selected_stage": "granularity_mapping",
        "selected_signal": "EMA/best year and CPC granularity are suspicious",
        "answer_delta": {"expected_count": 50, "predicted_count": 55, "missing_count": 19, "extra_count": 24, "f1": 0.590476},
        "runtime_trace_evidence": [],
        "ranked_feedback_signals": [],
    }

    plan = plan_helper_repair(feedback, "data_agent_tool_repair")

    assert plan["recommended_helper_file"] == "adapters/patents/answer_diagnostics.py"
    assert plan["required_functions"][0]["name"] == "summarize_candidate_decisions"


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