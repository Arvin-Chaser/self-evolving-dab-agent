#!/usr/bin/env python3
"""Build meta-agent evidence packs for zero-start DAB tool-agent workflow runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.near_miss_causal_diagnosis import build_near_miss_causal_diagnosis


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "path": str(path)}


def read_text(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[:limit] + f"\n[TRUNCATED {len(text) - limit} chars]\n"
    return text


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_dab_tool_agent_analysis(run_dir: Path) -> None:
    required = [run_dir / "observations.json", run_dir / "feedback_summary.json", run_dir / "meta_agent_seed.json"]
    if all(path.exists() for path in required):
        feedback_summary = load_json(run_dir / "feedback_summary.json", {}) or {}
        required_feedback_fields = {"answer_quality", "helper_usage_summary", "selected_stage", "selected_signal", "candidate_repair_layers", "routing_policy", "meta_agent_decision_required"}
        if isinstance(feedback_summary, dict) and required_feedback_fields.issubset(feedback_summary):
            return
    from experiments.analyze_dab_tool_agent_trace import analyze_run, write_json as analyzer_write_json

    result = analyze_run(run_dir)
    analyzer_write_json(run_dir / "observations.json", result["observations"])
    analyzer_write_json(run_dir / "feedback_summary.json", result["feedback_summary"])
    analyzer_write_json(run_dir / "meta_agent_seed.json", result["meta_agent_seed"])


def build_dab_tool_agent_evidence_pack(
    run_dir: Path,
    *,
    zero_start_profile: Path | None = None,
    max_observations: int = 8,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    ensure_dab_tool_agent_analysis(run_dir)

    summary = load_json(run_dir / "summary.json", {}) or {}
    feedback_summary = load_json(run_dir / "feedback_summary.json", {}) or {}
    observations = load_json(run_dir / "observations.json", []) or []
    meta_agent_seed = load_json(run_dir / "meta_agent_seed.json", {}) or {}
    final_answer = read_text(run_dir / "final_answer.txt", limit=1000)
    zero_start_text = read_text(zero_start_profile, limit=8000) if zero_start_profile else ""

    if not isinstance(observations, list):
        observations = []

    artifact_paths = {
        "summary_json": str(run_dir / "summary.json"),
        "workflow_trace_jsonl": str(run_dir / "workflow_trace.jsonl"),
        "llm_calls_jsonl": str(run_dir / "llm_calls.jsonl"),
        "tool_calls_jsonl": str(run_dir / "tool_calls.jsonl"),
        "final_agent_json": str(run_dir / "final_agent.json"),
        "final_answer_txt": str(run_dir / "final_answer.txt"),
        "validation_jsonl": str(run_dir / "validation.jsonl"),
        "agent_self_observations_jsonl": str(run_dir / "agent_self_observations.jsonl"),
        "observations_json": str(run_dir / "observations.json"),
        "feedback_summary_json": str(run_dir / "feedback_summary.json"),
        "meta_agent_seed_json": str(run_dir / "meta_agent_seed.json"),
    }

    feedback = {
        "feedback_type": "dab_tool_agent_workflow_feedback",
        "schema_version": "dab_tool_agent_evidence_pack_v001",
        "source_run_dir": str(run_dir),
        "profile": "zero_start_dab_tool_agent",
        "zero_start_profile_path": str(zero_start_profile) if zero_start_profile else None,
        "zero_start_profile_excerpt": zero_start_text,
        "zero_start_constraints": {
            "allowed_initial_tools": ["list_db", "query_db", "execute_python", "return_answer"],
            "forbidden_initial_domain_helpers": [
                "cpc_level_helper",
                "ema_helper",
                "patents_schema_helper",
                "metadata_parser_helper",
                "query-specific answer repair helper",
            ],
            "principle": "Initial feedback is generic and evidence-only; domain helpers must be proposed by the meta-agent in later iterations.",
        },
        "run_summary": {
            "status": summary.get("status"),
            "deployment_name": summary.get("deployment_name"),
            "terminate_reason": summary.get("terminate_reason"),
            "run_error": summary.get("run_error"),
            "llm_call_count": summary.get("llm_call_count"),
            "tool_call_count": summary.get("tool_call_count"),
            "workflow_event_count": summary.get("workflow_event_count"),
            "final_answer_nonempty": summary.get("final_answer_nonempty"),
            "docker_status": summary.get("docker_status"),
            "postgres_status": summary.get("postgres_status"),
        },
        "workflow_feedback_summary": feedback_summary,
        "answer_quality": feedback_summary.get("answer_quality") if isinstance(feedback_summary, dict) else None,
        "helper_usage_summary": feedback_summary.get("helper_usage_summary") if isinstance(feedback_summary, dict) else None,
        "agent_self_observation_summary": feedback_summary.get("agent_self_observation_summary") if isinstance(feedback_summary, dict) else None,
        "selected_stage": feedback_summary.get("selected_stage") if isinstance(feedback_summary, dict) else None,
        "selected_signal": feedback_summary.get("selected_signal") if isinstance(feedback_summary, dict) else None,
        "recommended_repair_layer": feedback_summary.get("recommended_repair_layer") if isinstance(feedback_summary, dict) else None,
        "candidate_repair_layers": feedback_summary.get("candidate_repair_layers") if isinstance(feedback_summary, dict) else None,
        "routing_policy": feedback_summary.get("routing_policy") if isinstance(feedback_summary, dict) else None,
        "meta_agent_decision_required": feedback_summary.get("meta_agent_decision_required") if isinstance(feedback_summary, dict) else None,
        "primary_signal": feedback_summary.get("primary_signal") if isinstance(feedback_summary, dict) else None,
        "structured_observations": observations[:max_observations],
        "meta_agent_seed": meta_agent_seed,
        "final_answer_preview": final_answer,
        "repair_guidance": {
            "use_feedback_as": "evidence_not_fixed_repair_decision",
            "script_first_policy": "Prefer executable helper/script/tool/runner/observer capability plus minimal prompt glue over standalone prompt edits; if prompt-only, explain why no executable repair was appropriate.",
            "preferred_initial_targets": ["generic_helper_tool", "tool_registration", "tool_schema", "workflow_observer", "runner_tool_glue", "trace_analyzer", "prompt_glue"],
            "allowed_evolution_targets": ["generic_helper_tool", "tool_registration", "workflow_observer", "runner_tool_glue", "trace_analyzer", "evidence_pack_builder", "prompt_glue"],
            "domain_helper_policy": "Do not add CPC/PATENTS helpers unless repeated workflow/validation evidence justifies them; if added, they must be generated as an evolution candidate, not treated as seed capability.",
            "context_policy": "Embed summaries and top observations only; use raw artifact paths for detailed inspection instead of inlining full logs.",
            "open_self_observation_policy": "If agent_self_observation_summary is available, treat it as DataAgent-authored evidence for meta-agent interpretation, not as a fixed repair label.",
        },
        "artifact_paths": artifact_paths,
    }
    feedback["near_miss_causal_diagnosis"] = build_near_miss_causal_diagnosis(feedback, run_dir=run_dir)
    return feedback


def markdown_for_dab_tool_agent_feedback(feedback: dict[str, Any]) -> str:
    sections = [
        ("Zero-Start Constraints", feedback.get("zero_start_constraints") or {}),
        ("Run Summary", feedback.get("run_summary") or {}),
        ("Workflow Feedback Summary", feedback.get("workflow_feedback_summary") or {}),
        ("Primary Signal", feedback.get("primary_signal") or {}),
        ("Routing Context", {"candidate_repair_layers": feedback.get("candidate_repair_layers") or [], "routing_policy": feedback.get("routing_policy") or {}, "meta_agent_decision_required": feedback.get("meta_agent_decision_required")}),
        ("Answer Quality", feedback.get("answer_quality") or {}),
        ("Near-Miss Causal Diagnosis", feedback.get("near_miss_causal_diagnosis") or {}),
        ("Helper Usage Summary", feedback.get("helper_usage_summary") or {}),
        ("Agent Self-Observation Summary", feedback.get("agent_self_observation_summary") or {}),
        ("Structured Observations", feedback.get("structured_observations") or []),
        ("Meta-Agent Seed", feedback.get("meta_agent_seed") or {}),
        ("Repair Guidance", feedback.get("repair_guidance") or {}),
        ("Raw Artifact Paths", feedback.get("artifact_paths") or {}),
    ]
    lines = [
        "# DAB Tool-Agent Workflow Evidence Pack",
        "",
        f"- source_run_dir: `{feedback.get('source_run_dir')}`",
        f"- profile: `{feedback.get('profile')}`",
        f"- feedback_type: `{feedback.get('feedback_type')}`",
        "",
    ]
    for title, value in sections:
        lines += [f"## {title}", "", "```json", json.dumps(value, indent=2, ensure_ascii=False), "```", ""]
    lines += ["## Final Answer Preview", "", "```text", str(feedback.get("final_answer_preview") or ""), "```", ""]
    if feedback.get("zero_start_profile_excerpt"):
        lines += ["## Zero-Start Profile Excerpt", "", "```markdown", str(feedback.get("zero_start_profile_excerpt") or ""), "```", ""]
    return "\n".join(lines)


def write_pack(feedback: dict[str, Any], output_json: Path, output_md: Path) -> None:
    write_json(output_json, feedback)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown_for_dab_tool_agent_feedback(feedback), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--zero-start-profile", default="meta_agent/zero_start_data_agent_profile.md")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--max-observations", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    feedback = build_dab_tool_agent_evidence_pack(
        Path(args.run_dir),
        zero_start_profile=Path(args.zero_start_profile) if args.zero_start_profile else None,
        max_observations=args.max_observations,
    )
    write_pack(feedback, Path(args.output_json), Path(args.output_md))
    print(json.dumps({"output_json": args.output_json, "output_md": args.output_md, "feedback_type": feedback.get("feedback_type")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
