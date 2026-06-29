#!/usr/bin/env python3
"""Build a fine-grained evidence pack for Codex-Qwen meta-agent repair.

The pack distills a DAB data-agent run into compact, action-oriented feedback:
parent capabilities, answer delta, key runtime trace events, ranked analyzer
signals, and repair constraints.  It is designed to be embedded in
repair_seed.json and in a Markdown evidence pack, not to replace raw artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


IMPORTANT_TRACE_EVENTS = {
    "cpc_definition_parsed",
    "cpc_definition_parsing_started",
    "cpc_hierarchy_built",
    "cpc_level5_symbol_count",
    "cpc_level5_mapping_summary",
    "cpc_mapping_summary",
    "publication_data_fetched",
    "patent_records_fetched",
    "filing_years_extracted",
    "yearly_counts_built",
    "ema_calculated",
    "ema_best_years_computed",
    "granularity_mapping_fallback_used",
    "unmapped_cpc_codes_sample",
    "no_years_with_level5_data",
    "no_yearly_data_for_ema",
    "no_years_found",
    "final_answer_written",
}


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def read_text(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[:limit] + f"\n[TRUNCATED {len(text) - limit} chars]\n"
    return text


def answer_codes(text: str) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        code = line.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def parse_code_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_answer_delta(validation_reason: str, final_answer: str) -> dict[str, Any]:
    predicted_codes = answer_codes(final_answer)
    delta: dict[str, Any] = {
        "predicted_count": len(predicted_codes),
        "predicted_codes_sample": predicted_codes[:30],
    }
    count_match = re.search(
        r"expected\s+(\d+)\s+unique\s+CPC\s+codes,\s+got\s+(\d+)\s+unique\s+CPC\s+codes",
        validation_reason,
        flags=re.IGNORECASE,
    )
    if count_match:
        delta["expected_count"] = int(count_match.group(1))
        delta["predicted_count"] = int(count_match.group(2))

    missing_match = re.search(r"Missing CPC codes \((\d+)\):\s*([^\n]+)", validation_reason)
    extra_match = re.search(r"Extra CPC codes \((\d+)\):\s*([^\n]+)", validation_reason)
    missing_codes = parse_code_list(missing_match.group(2)) if missing_match else []
    extra_codes = parse_code_list(extra_match.group(2)) if extra_match else []
    if missing_match:
        delta["missing_count"] = int(missing_match.group(1))
        delta["missing_codes"] = missing_codes
        delta["missing_codes_sample"] = missing_codes[:30]
    if extra_match:
        delta["extra_count"] = int(extra_match.group(1))
        delta["extra_codes"] = extra_codes
        delta["extra_codes_sample"] = extra_codes[:30]

    expected_count = delta.get("expected_count")
    predicted_count = delta.get("predicted_count")
    extra_count = delta.get("extra_count")
    missing_count = delta.get("missing_count")
    if isinstance(predicted_count, int) and isinstance(extra_count, int):
        true_positive = max(0, predicted_count - extra_count)
        delta["true_positive_count"] = true_positive
        delta["precision"] = round(true_positive / predicted_count, 4) if predicted_count else 0.0
        if isinstance(expected_count, int) and expected_count:
            delta["recall"] = round(true_positive / expected_count, 4)
        elif isinstance(missing_count, int) and true_positive + missing_count:
            delta["recall"] = round(true_positive / (true_positive + missing_count), 4)
        if delta.get("precision") is not None and delta.get("recall") is not None:
            precision = float(delta["precision"])
            recall = float(delta["recall"])
            delta["f1"] = round((2 * precision * recall / (precision + recall)), 4) if precision + recall else 0.0
    return delta


def trace_events(trace: Any, max_events: int = 12) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    selected: list[dict[str, Any]] = []
    for item in trace:
        if not isinstance(item, dict):
            continue
        name = str(item.get("event") or "")
        trigger = str(item.get("trigger") or "")
        severity = str(item.get("severity") or "")
        if name not in IMPORTANT_TRACE_EVENTS and trigger not in {"runtime_check_failed", "runtime_anomaly"} and severity not in {"warning", "error"}:
            continue
        selected.append(
            {
                "event": name,
                "trigger": item.get("trigger"),
                "severity": item.get("severity"),
                "status": item.get("status"),
                "purpose": item.get("purpose"),
                "inputs": item.get("inputs"),
                "outputs": item.get("outputs"),
                "checks": item.get("checks"),
                "evidence": item.get("evidence"),
                "repair_implication": repair_implication_for_event(name, item),
            }
        )
        if len(selected) >= max_events:
            break
    return selected


def repair_implication_for_event(name: str, item: dict[str, Any]) -> str:
    outputs = item.get("outputs") if isinstance(item.get("outputs"), dict) else {}
    if name in {"cpc_definition_parsed", "cpc_hierarchy_built"}:
        return "Parent has evidence of working CPCDefinition parsing/hierarchy construction; avoid parser/bootstrap rewrites unless contradicted by current failure."
    if name in {"publication_data_fetched", "patent_records_fetched"}:
        return "Parent can read publication data; next repairs should not focus on database access unless current failure says so."
    if name in {"cpc_mapping_summary", "cpc_level5_mapping_summary"}:
        return "Use mapping coverage counts to distinguish mapping coverage from answer ranking/EMA errors."
    if name in {"granularity_mapping_fallback_used", "unmapped_cpc_codes_sample"}:
        return "Fallback/unmapped evidence may support targeted mapping repair, but not vague strict filtering unless answer_delta proves fallback-derived extras."
    if name in {"final_answer_written"} or outputs.get("answer_count"):
        return "Parent/child wrote a non-empty answer; preserve this behavior and avoid empty-answer pseudo-fixes."
    if name in {"no_years_found", "no_yearly_data_for_ema", "no_years_with_level5_data"}:
        return "Year extraction or EMA input construction is a plausible repair target."
    return "Use this event as supporting evidence; do not use trace text as a patch anchor."


def parent_capabilities(result: dict[str, Any], final_answer: str, selected_events: list[dict[str, Any]]) -> dict[str, Any]:
    caps: dict[str, Any] = {
        "execution_success": bool((result.get("execution") or {}).get("execution_success")),
        "final_answer_nonempty": bool(final_answer.strip()),
        "answer_count": len(answer_codes(final_answer)),
    }
    for event in selected_events:
        name = event.get("event")
        outputs = event.get("outputs") if isinstance(event.get("outputs"), dict) else {}
        if name == "cpc_definition_parsed":
            caps["cpc_definition_parsed"] = True
            caps["parsed_rows"] = outputs.get("parsed_rows") or outputs.get("rows_parsed") or outputs.get("data_lines")
        if name == "cpc_hierarchy_built":
            caps["cpc_hierarchy_built"] = True
            caps["symbols_with_parents"] = outputs.get("symbols_with_parents")
            level_distribution = outputs.get("level_distribution") if isinstance(outputs.get("level_distribution"), dict) else {}
            caps["level_5_count"] = level_distribution.get("5") or outputs.get("level_5_count")
        if name in {"publication_data_fetched", "patent_records_fetched"}:
            caps["publication_records_fetched"] = outputs.get("total_records") or outputs.get("record_count")
        if name in {"cpc_mapping_summary", "cpc_level5_mapping_summary"}:
            caps.setdefault("mapping_summaries", []).append(outputs)
    return caps


def ranked_feedback_signals(agent_summary: dict[str, Any], primary_signal: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = primary_signal.get("candidate_signals") if isinstance(primary_signal, dict) else None
    if isinstance(candidates, list) and candidates:
        out = []
        for item in candidates[:8]:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "stage": item.get("stage") or item.get("component"),
                    "type": item.get("type"),
                    "score": item.get("score"),
                    "message": item.get("message"),
                    "source_error": item.get("source_error"),
                }
            )
        return out
    errors = agent_summary.get("localized_errors") if isinstance(agent_summary, dict) else []
    if not isinstance(errors, list):
        return []
    return [
        {
            "stage": err.get("stage") or err.get("component"),
            "type": err.get("type"),
            "confidence": err.get("confidence"),
            "evidence": err.get("evidence"),
            "message": err.get("message") or err.get("subtype"),
        }
        for err in errors[:8]
        if isinstance(err, dict)
    ]



def repair_routing(
    *,
    validation_reason: str,
    selected_stage: Any,
    selected_signal: Any,
    parent_caps: dict[str, Any],
    selected_events: list[dict[str, Any]],
    answer_delta: dict[str, Any],
) -> dict[str, Any]:
    """Infer the project layer and files a meta-agent should consider first."""

    stage = str(selected_stage or "")
    signal = str(selected_signal or "")
    event_names = {str(item.get("event") or "") for item in selected_events if isinstance(item, dict)}
    combined = "\n".join([validation_reason, stage, signal, json.dumps(selected_events, ensure_ascii=False)]).lower()

    base_targets = [
        "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        "experiments/run_dab_agent.py",
        "adapters/runtime_observer.py",
        "experiments/build_meta_agent_evidence_pack.py",
    ]
    analyzer_targets = [
        "adapters/feedback/common_trace_checks.py",
        "adapters/feedback/dab_patents_checks.py",
        "experiments/analyze_agent_error.py",
        "experiments/extract_primary_signal.py",
    ]
    routing: dict[str, Any] = {
        "recommended_repair_layer": "data_agent_prompt_or_generated_code_pattern",
        "recommended_target_files": base_targets,
        "anti_targets": ["logs/**", "candidates/**", "archive/**", "trajectories/**", "benchmarks/**"],
        "prompt_only_policy": {
            "status": "allowed_if_specific",
            "reason": "Prompt-only is acceptable only when it encodes a durable generated-code rule tied to the active failure evidence.",
            "source_change_required": False,
        },
        "routing_reason": "Default to the data-agent generation path unless feedback/analyzer infrastructure or loop control is the active failure.",
    }

    if any(marker in combined for marker in ("importerror", "unboundlocalerror", "recursionerror", "feedback checker", "common_trace_checks", "dab_patents_checks")):
        routing.update(
            {
                "recommended_repair_layer": "feedback_analyzer_infrastructure",
                "recommended_target_files": analyzer_targets,
                "anti_targets": ["prompts/dab/**", "logs/**", "candidates/**", "archive/**", "trajectories/**", "benchmarks/**"],
                "prompt_only_policy": {
                    "status": "reject",
                    "reason": "Analyzer infrastructure failures must be repaired in feedback/analyzer code, not by changing the data-agent prompt.",
                    "source_change_required": True,
                },
                "routing_reason": "The active failure names feedback/analyzer modules or import/runtime exceptions from analyzer code.",
            }
        )
    elif any(marker in combined for marker in ("protocol_failed", "patch_spec", "first_action", "empty patch", "launcher", "candidate_generated")):
        routing.update(
            {
                "recommended_repair_layer": "meta_agent_runner_or_launcher",
                "recommended_target_files": [
                    "experiments/run_codex_qwen_repair_launcher.py",
                    "experiments/run_meta_agent_evolution_loop.py",
                    "experiments/structured_patch_spec_v4.py",
                ],
                "anti_targets": ["prompts/dab/**", "adapters/feedback/**", "logs/**", "candidates/**", "archive/**", "trajectories/**"],
                "prompt_only_policy": {
                    "status": "reject",
                    "reason": "Runner/protocol failures must be repaired in launcher/loop code, not by changing the data-agent prompt.",
                    "source_change_required": True,
                },
                "routing_reason": "The active failure is a meta-agent protocol/launcher control failure.",
            }
        )
    elif "traceback" in combined or "attributeerror" in combined or "typeerror" in combined or "log_exception" in combined:
        routing.update(
            {
                "recommended_repair_layer": "generated_code_pattern_or_runtime_api_usage",
                "recommended_target_files": [
                    "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
                    "adapters/runtime_observer.py",
                    "experiments/run_dab_agent.py",
                    "experiments/build_meta_agent_evidence_pack.py",
                ],
                "anti_targets": ["adapters/feedback/**", "logs/**", "candidates/**", "archive/**", "trajectories/**", "benchmarks/**"],
                "prompt_only_policy": {
                    "status": "weak_allowed",
                    "reason": "A prompt-only repair may be enough only if it directly prevents the concrete traceback/API/type-safety pattern in future generated code; otherwise prefer project-source guardrails.",
                    "source_change_required": False,
                },
                "routing_reason": "The active failure is a generated_solve runtime traceback or runtime observer API misuse.",
            }
        )
    elif any(name in event_names for name in {"no_years_found", "no_yearly_data_for_ema", "no_years_with_level5_data"}) or any(
        marker in combined for marker in ("no_years_found", "yearly", "ema", "best year")
    ):
        routing.update(
            {
                "recommended_repair_layer": "year_axis_or_ema_construction",
                "recommended_target_files": base_targets,
                "anti_targets": ["adapters/feedback/**", "logs/**", "candidates/**", "archive/**", "trajectories/**", "benchmarks/**"],
                "prompt_only_policy": {
                    "status": "allowed_if_specific",
                    "reason": "Prompt-only is acceptable if it gives a concrete year-axis/EMA construction rule grounded in trace evidence.",
                    "source_change_required": False,
                },
                "routing_reason": "Trace or selected signal points to year extraction or EMA input construction.",
            }
        )
    elif parent_caps.get("cpc_definition_parsed") and parent_caps.get("cpc_hierarchy_built") and (
        answer_delta.get("missing_count") is not None or answer_delta.get("extra_count") is not None
    ):
        routing.update(
            {
                "recommended_repair_layer": "answer_delta_mapping_or_ranking",
                "recommended_target_files": base_targets,
                "anti_targets": ["adapters/feedback/**", "logs/**", "candidates/**", "archive/**", "trajectories/**", "benchmarks/**"],
                "prompt_only_policy": {
                    "status": "allowed_if_specific",
                    "reason": "Prompt-only is acceptable if it targets missing/extra evidence rather than rewriting parser bootstrapping.",
                    "source_change_required": False,
                },
                "routing_reason": "Parser/hierarchy evidence is already present and the remaining signal is answer-delta quality.",
            }
        )

    routing["if_prompt_only"] = [
        "Explain why the prompt layer is sufficient for this failure.",
        "Mention the concrete active signal/traceback/answer_delta in rationale.",
        "Do not merely restate existing CPC metadata rules.",
    ]
    routing["if_project_source"] = [
        "Keep the change local to the recommended target files.",
        "Add guardrails or evidence-pack/routing improvements rather than benchmark-specific answer logic.",
        "Preserve public APIs and benchmark/data immutability.",
    ]
    return routing

def generated_code_snippets(run_dir: Path, max_chars: int = 5000) -> list[dict[str, str]]:
    path = run_dir / "generated_solve.py"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    keywords = ("ema", "best_year", "level", "parents", "fallback", "final_answer", "mapping")
    snippets: list[dict[str, str]] = []
    used_ranges: list[range] = []
    for idx, line in enumerate(lines):
        low = line.lower()
        if not any(key in low for key in keywords):
            continue
        start = max(0, idx - 4)
        end = min(len(lines), idx + 12)
        if any(idx in r for r in used_ranges):
            continue
        used_ranges.append(range(start, end))
        text = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
        snippets.append({"line": str(idx + 1), "snippet": text})
        if sum(len(s["snippet"]) for s in snippets) >= max_chars:
            break
    return snippets[:6]


def build_fine_grained_feedback_pack(
    run_dir: Path,
    *,
    primary_signal: dict[str, Any] | None = None,
    max_trace_events: int = 12,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    result = load_json(run_dir / "result.json") or {}
    agent_summary = load_json(run_dir / "agent_error_summary.json") or {}
    pipeline_diagnostics = load_json(run_dir / "pipeline_diagnostics.json") or {}
    trace = load_json(run_dir / "stage_trace.json") or []
    final_answer = read_text(run_dir / "final_answer.txt")
    validation_reason = str(result.get("validation_reason") or agent_summary.get("validation_reason") or "")
    signal = primary_signal or {}

    selected_events = trace_events(trace, max_events=max_trace_events)
    answer_delta = parse_answer_delta(validation_reason, final_answer)
    caps = parent_capabilities(result, final_answer, selected_events)
    selected_stage = signal.get("selected_stage") or signal.get("selected_component")
    selected_signal = signal.get("selected_signal")
    routing = repair_routing(
        validation_reason=validation_reason,
        selected_stage=selected_stage,
        selected_signal=selected_signal,
        parent_caps=caps,
        selected_events=selected_events,
        answer_delta=answer_delta,
    )
    feedback = {
        "feedback_type": "fine_grained_parent_run_feedback",
        "source_run_dir": str(run_dir),
        "selected_stage": selected_stage,
        "selected_signal": selected_signal,
        "repair_routing": routing,
        "parent_capabilities": caps,
        "answer_delta": answer_delta,
        "runtime_trace_evidence": selected_events,
        "ranked_feedback_signals": ranked_feedback_signals(agent_summary, signal),
        "preserved_invariants": agent_summary.get("preserved_invariants") or pipeline_diagnostics.get("preserved_invariants") or [],
        "repair_constraints": {
            "preserve": [
                "already-working CPCDefinition parser/hierarchy construction when trace proves parsed rows and parents mappings are non-empty",
                "non-empty partial-answer behavior",
                "metadata-grounded CPC mapping coverage",
                "runtime observer logging contract",
            ],
            "forbid": [
                "generic strict level == 5 filtering unless answer_delta/runtime evidence proves non-level-5 or fallback-derived extras",
                "COPY parser rewrite unless current trace shows COPY parsing failed",
                "parents parser rewrite unless current trace shows parents mappings are empty or malformed",
                "empty-answer pseudo-fix",
                "stale log_exception signature repair unless selected evidence is runtime observer API failure",
            ],
        },
        "next_repair_focus": [
            "Use answer_delta missing/extra evidence rather than broad granularity labels.",
            "Prefer EMA/year aggregation, ranking, tie-handling, or per-code exclusion diagnostics when parser/mapping capabilities are already present.",
            "If proposing prompt repair, state what the parent already does correctly and how the edit preserves it.",
            "If evidence only supports a vague strict-filtering instruction, output no_op_failed.",
        ],
        "artifact_paths": {
            "result_json": str(run_dir / "result.json"),
            "agent_error_summary_json": str(run_dir / "agent_error_summary.json"),
            "pipeline_diagnostics_json": str(run_dir / "pipeline_diagnostics.json"),
            "stage_trace_json": str(run_dir / "stage_trace.json"),
            "final_answer_txt": str(run_dir / "final_answer.txt"),
            "generated_solve_py": str(run_dir / "generated_solve.py"),
        },
    }
    snippets = generated_code_snippets(run_dir)
    if snippets:
        feedback["generated_code_evidence_snippets"] = snippets
    return feedback


def markdown_for_feedback(feedback: dict[str, Any]) -> str:
    lines = [
        "# Fine-Grained Meta-Agent Evidence Pack",
        "",
        f"- source_run_dir: `{feedback.get('source_run_dir')}`",
        f"- selected_stage: `{feedback.get('selected_stage')}`",
        f"- selected_signal: `{feedback.get('selected_signal')}`",
        "",
        "## Parent Capabilities",
        "",
        "```json",
        json.dumps(feedback.get("parent_capabilities") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Answer Delta",
        "",
        "```json",
        json.dumps(feedback.get("answer_delta") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Repair Routing",
        "",
        "```json",
        json.dumps(feedback.get("repair_routing") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Runtime Trace Evidence",
        "",
        "```json",
        json.dumps(feedback.get("runtime_trace_evidence") or [], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Ranked Feedback Signals",
        "",
        "```json",
        json.dumps(feedback.get("ranked_feedback_signals") or [], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Repair Constraints",
        "",
        "```json",
        json.dumps(feedback.get("repair_constraints") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Next Repair Focus",
        "",
    ]
    lines.extend(f"- {item}" for item in feedback.get("next_repair_focus") or [])
    if feedback.get("generated_code_evidence_snippets"):
        lines += ["", "## Generated Code Evidence Snippets", ""]
        for item in feedback["generated_code_evidence_snippets"]:
            lines += [f"### Around line {item.get('line')}", "", "```python", item.get("snippet", ""), "```", ""]
    lines += ["", "## Raw Artifact Paths", "", "```json", json.dumps(feedback.get("artifact_paths") or {}, indent=2, ensure_ascii=False), "```", ""]
    return "\n".join(lines)


def write_pack(feedback: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(feedback, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown_for_feedback(feedback), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--primary-signal-json")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--max-trace-events", type=int, default=12)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    primary_signal = load_json(Path(args.primary_signal_json)) if args.primary_signal_json else None
    feedback = build_fine_grained_feedback_pack(
        Path(args.run_dir),
        primary_signal=primary_signal if isinstance(primary_signal, dict) else None,
        max_trace_events=args.max_trace_events,
    )
    write_pack(feedback, Path(args.output_json), Path(args.output_md))
    print(json.dumps({"output_json": args.output_json, "output_md": args.output_md}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
