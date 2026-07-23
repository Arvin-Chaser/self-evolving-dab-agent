"""Interpret a DAB data-agent run into meta-agent evolution notes.

This script formalizes the "between runs" reasoning step: read a run's
trajectory artifacts, summarize the failure with evidence, and produce concise
notes for the coding meta-agent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report
from llm_client import call_meta_llm, describe_llm_config


IMPORTANT_EVENT_KEYWORDS = (
    "error",
    "failed",
    "empty",
    "missing",
    "mapping",
    "schema",
    "candidate",
    "answer",
    "definition",
    "parent",
    "coverage",
    "granularity",
    "summary",
)


def load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def compact(value: Any, max_chars: int = 12000) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False) if not isinstance(value, str) else value
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]..."


def event_is_important(event: dict[str, Any]) -> bool:
    event_name = str(event.get("event") or event.get("operation") or "").lower()
    severity = str(event.get("severity") or "").lower()
    status = str(event.get("status") or "").lower()
    trigger = str(event.get("trigger") or "").lower()
    if severity in {"warning", "error"} or status in {"failed", "warning"}:
        return True
    if "failed" in trigger or "anomaly" in trigger or "exception" in trigger:
        return True
    return any(keyword in event_name for keyword in IMPORTANT_EVENT_KEYWORDS)


def summarize_trace(trace: Any, max_events: int = 40) -> dict[str, Any]:
    if not isinstance(trace, list):
        return {"event_count": 0, "selected_events": []}

    selected: list[dict[str, Any]] = []
    for event in trace:
        if isinstance(event, dict) and event_is_important(event):
            selected.append(event)

    tail = [event for event in trace[-8:] if isinstance(event, dict)]
    merged: list[dict[str, Any]] = []
    seen = set()
    for event in selected + tail:
        key = json.dumps(event, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            merged.append(event)

    return {
        "event_count": len(trace),
        "selected_events": merged[:max_events],
        "truncated_selected_events": max(0, len(merged) - max_events),
    }


def extract_result_signal(result: dict[str, Any]) -> dict[str, Any]:
    final_answer = result.get("final_answer") or ""
    lines = [line for line in final_answer.splitlines() if line.strip()]
    return {
        "passed": result.get("passed"),
        "validation_reason": result.get("validation_reason"),
        "prompt_version": result.get("prompt_version"),
        "case_group": result.get("case_group"),
        "case_name": result.get("case_name"),
        "final_answer_line_count": len(lines),
        "final_answer_preview": "\n".join(lines[:30]),
        "llm_latency_sec": result.get("llm_latency_sec"),
        "execution": result.get("execution"),
    }


def extract_preserved_invariants(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(analysis, dict):
        return []
    invariants = analysis.get("preserved_invariants")
    if isinstance(invariants, list):
        return [item for item in invariants if isinstance(item, dict)]
    diagnostics = analysis.get("pipeline_diagnostics")
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("preserved_invariants"), list):
        return [item for item in diagnostics["preserved_invariants"] if isinstance(item, dict)]
    return []


def render_invariant_guidance(invariants: list[dict[str, Any]], max_items: int = 8) -> str:
    if not invariants:
        return "No preserved invariants were extracted."
    lines = ["Preserved invariants that candidate patches should not regress:"]
    for item in invariants[:max_items]:
        name = item.get("name") or "unnamed_invariant"
        evidence = item.get("evidence") or ""
        boundary = item.get("repair_boundary") or ""
        lines.append(f"- {name}: {evidence} Boundary: {boundary}")
    if len(invariants) > max_items:
        lines.append(f"- ... {len(invariants) - max_items} more invariant(s) omitted.")
    return "\n".join(lines)


def deterministic_interpretation(run_dir: Path, result: dict[str, Any], analysis: dict[str, Any], trace_summary: dict[str, Any]) -> dict[str, Any]:
    reason = str(result.get("validation_reason") or analysis.get("validation_reason") or "")
    reason_lower = reason.lower()
    final_answer = result.get("final_answer") or ""
    selected_events = trace_summary.get("selected_events") or []
    event_names = " ".join(str(event.get("event") or "") for event in selected_events if isinstance(event, dict)).lower()
    evidence: list[str] = []
    target = "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt"
    failure_type = "unknown_failure"
    priority = "medium"

    if "no such column" in reason_lower or "cpc_prefix" in reason_lower or "schema" in event_names:
        failure_type = "schema_grounding"
        priority = "high"
        evidence.append("Validation/runtime evidence indicates schema grounding failure or guessed column names.")
    if "empty" in reason_lower or "no_valid_cpc_mappings" in event_names or "empty_data_section" in event_names:
        failure_type = "metadata_or_empty_answer"
        priority = "high"
        evidence.append("Run produced empty answer or failed metadata parsing/mapping before useful aggregation.")
    if "strict_match_failed" in reason_lower:
        failure_type = "answer_set_mismatch"
        priority = "high"
        match = re.search(r"expected\s+(\d+)\s+unique.*got\s+(\d+)\s+unique", reason, flags=re.IGNORECASE | re.DOTALL)
        if match:
            expected, got = int(match.group(1)), int(match.group(2))
            if got > expected * 3:
                failure_type = "granularity_or_overbroad_answer"
            elif got < expected:
                failure_type = "undercoverage_or_filtering"
            evidence.append(f"Strict match cardinality: expected {expected} unique items, got {got}.")
        else:
            evidence.append("Strict validator reported missing/extra answer items.")
    if result.get("passed"):
        failure_type = "passed"
        priority = "low"
        evidence.append("Run passed validation.")
    elif final_answer.strip() and failure_type == "unknown_failure":
        failure_type = "nonempty_wrong_answer"
        evidence.append("Run wrote a non-empty final answer but failed validation.")

    preserved_invariants = extract_preserved_invariants(analysis)
    invariant_names = {str(item.get("name")) for item in preserved_invariants}
    contradicted_components: set[str] = set()
    if "publicationinfo_uses_cpc_column" in invariant_names:
        contradicted_components.add("schema_grounding")
    if "cpc_definition_parsed" in invariant_names or "level5_mapping_has_coverage" in invariant_names:
        contradicted_components.update({"granularity_mapping", "cpc_mapping_incomplete"})

    localized = analysis.get("localized_errors") if isinstance(analysis, dict) else []
    suppressed_evidence: list[str] = []
    for item in (localized or [])[:5]:
        stage = item.get("stage")
        kind = item.get("type")
        subtype = item.get("subtype")
        if stage or kind:
            if failure_type == "answer_set_mismatch" and stage in contradicted_components:
                suppressed_evidence.append(f"Suppressed {stage}.{kind}: parent invariants show this path already works.")
                continue
            evidence.append(f"Analyzer localized {stage}.{kind}: {subtype}.")

    invariant_guidance = render_invariant_guidance(preserved_invariants)
    for item in preserved_invariants[:4]:
        name = item.get("name")
        boundary = item.get("repair_boundary")
        if name:
            evidence.append(f"Preserved invariant {name}: {boundary}")

    if not evidence:
        evidence.append("No strong deterministic failure signal was found; inspect runtime logs and generated_solve.py.")

    notes = (
        f"Failure type: {failure_type}. "
        f"Use runtime evidence from {run_dir}. "
        + " ".join(evidence[:4])
        + " Propose a small project-level change grounded in these artifacts. "
        + invariant_guidance
        + " "
        "Prefer improving data-agent prompt/runtime logging/analyzer behavior without hard-coding validator answers."
    )

    return {
        "interpreter": "deterministic",
        "failure_type": failure_type,
        "priority": priority,
        "evidence": evidence,
        "evolution_targets": [target],
        "preserved_invariants": preserved_invariants,
        "suppressed_evidence": suppressed_evidence,
        "invariant_guidance": invariant_guidance,
        "recommended_change": notes,
        "meta_agent_notes": notes,
        "stop_recommendation": "stop" if result.get("passed") else "continue",
        "confidence": "medium",
    }


def build_llm_prompt(
    run_dir: Path,
    result_signal: dict[str, Any],
    analysis: dict[str, Any],
    trace_summary: dict[str, Any],
    deterministic: dict[str, Any],
    extra_notes: str | None,
) -> str:
    return "\n".join(
        [
            "You are the failure interpreter inside a project-level data-agent meta-agent loop.",
            "Read the compact trajectory evidence and turn it into structured evolution guidance.",
            "",
            "Hard requirements:",
            "- Ground every diagnosis in runtime/analyzer/result evidence.",
            "- Do not reveal or hard-code validator ground truth answers.",
            "- Preserve verified parent invariants; do not recommend changing working schema, parser, mapping, or answer-writing components unless evidence identifies that exact component as the remaining failure.",
            "- Prefer small project-level changes to prompts, runtime logging, analyzers, task packaging, or loop orchestration.",
            "- Produce JSON only, no markdown.",
            "",
            "JSON schema:",
            "{",
            '  "failure_type": "short_snake_case",',
            '  "priority": "low|medium|high",',
            '  "evidence": ["specific evidence strings"],',
            '  "root_cause_hypothesis": "one paragraph",',
            '  "evolution_targets": ["repo-relative files or modules"],',
            '  "recommended_change": "specific project-level change",',
            '  "meta_agent_notes": "concise notes to pass to the coding meta-agent",',
            '  "runtime_signals_to_request": ["signals/logs the next child should emit"],',
            '  "stop_recommendation": "continue|stop",',
            '  "confidence": "low|medium|high"',
            "}",
            "",
            f"# Run dir\n{run_dir}",
            "",
            "# Extra human/system notes",
            extra_notes or "",
            "",
            "# Deterministic fallback interpretation",
            compact(deterministic, 6000),
            "",
            "# Result signal",
            compact(result_signal, 8000),
            "",
            "# Analyzer summary",
            compact(analysis, 14000),
            "",
            "# Preserved invariant guidance",
            compact(deterministic.get("invariant_guidance") or "", 6000),
            "",
            "# Runtime trace summary",
            compact(trace_summary, 16000),
        ]
    )


def extract_first_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        if isinstance(value, dict):
            return value
    return {}


def render_markdown(interpretation: dict[str, Any]) -> str:
    lines = [
        f"# Failure Interpretation: {interpretation.get('failure_type')}",
        "",
        f"- Priority: `{interpretation.get('priority')}`",
        f"- Confidence: `{interpretation.get('confidence')}`",
        f"- Stop recommendation: `{interpretation.get('stop_recommendation')}`",
        "",
        "## Evidence",
        "",
    ]
    for item in interpretation.get("evidence") or []:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Root Cause Hypothesis",
            "",
            str(interpretation.get("root_cause_hypothesis") or interpretation.get("recommended_change") or ""),
            "",
            "## Meta-Agent Notes",
            "",
            str(interpretation.get("meta_agent_notes") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def interpret_failure(
    run_dir: Path,
    output_dir: Path | None = None,
    use_llm: bool = True,
    extra_notes: str | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    run_dir = run_dir.resolve()
    output_dir = (output_dir or run_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = load_json_if_exists(run_dir / "result.json") or {}
    analysis = load_json_if_exists(run_dir / "agent_error_summary.json") or {}
    trace = load_json_if_exists(run_dir / "stage_trace.json") or []
    trace_summary = summarize_trace(trace)
    result_signal = extract_result_signal(result)
    deterministic = deterministic_interpretation(run_dir, result, analysis, trace_summary)

    prompt_path = output_dir / "failure_interpreter_prompt.txt"
    raw_path = output_dir / "failure_interpreter_raw_output.txt"
    interpretation_path = output_dir / "failure_interpretation.json"
    markdown_path = output_dir / "failure_interpretation.md"

    operations: list[dict[str, Any]] = [
        {
            "name": "collect_run_evidence",
            "status": "completed",
            "outputs": {
                "result_found": bool(result),
                "analysis_found": bool(analysis),
                "trace_event_count": trace_summary.get("event_count"),
            },
        }
    ]
    error: dict[str, Any] | None = None
    interpretation = deterministic
    raw_text = ""

    if use_llm:
        prompt = build_llm_prompt(run_dir, result_signal, analysis, trace_summary, deterministic, extra_notes)
        prompt_path.write_text(prompt, encoding="utf-8")
        try:
            raw_text = call_meta_llm(prompt)
            raw_path.write_text(raw_text, encoding="utf-8")
            llm_value = extract_first_json(raw_text)
            if llm_value:
                interpretation = {**deterministic, **llm_value, "interpreter": "llm"}
                operations.append(
                    {
                        "name": "call_llm_failure_interpreter",
                        "status": "completed",
                        "outputs": {"llm_config": describe_llm_config()["meta"], "raw_output_path": str(raw_path)},
                    }
                )
            else:
                operations.append(
                    {
                        "name": "call_llm_failure_interpreter",
                        "status": "partial",
                        "outputs": {"reason": "No valid JSON found; used deterministic fallback."},
                    }
                )
        except Exception as exc:  # noqa: BLE001 - keep LLM failures as trajectory artifacts.
            error = {"type": type(exc).__name__, "message": str(exc)}
            operations.append({"name": "call_llm_failure_interpreter", "status": "failed", "outputs": error})
    else:
        prompt_path.write_text("", encoding="utf-8")
        raw_path.write_text("", encoding="utf-8")
        operations.append({"name": "call_llm_failure_interpreter", "status": "skipped", "outputs": {"use_llm": False}})

    interpretation.setdefault("failure_type", deterministic["failure_type"])
    interpretation.setdefault("evidence", deterministic["evidence"])
    interpretation.setdefault("meta_agent_notes", deterministic["meta_agent_notes"])
    interpretation["run_dir"] = str(run_dir)
    interpretation["result_signal"] = result_signal
    interpretation["trace_event_count"] = trace_summary.get("event_count")

    write_json(interpretation_path, interpretation)
    markdown_path.write_text(render_markdown(interpretation), encoding="utf-8")

    status = "success" if interpretation.get("meta_agent_notes") else "partial"
    report_path, _ = write_script_run_report(
        output_dir=output_dir,
        script_name="experiments/interpret_failure.py",
        script_role="failure_interpreter",
        started_at=started_at,
        status=status,
        inputs=[
            path_ref("run_dir", run_dir),
            path_ref("result", run_dir / "result.json"),
            path_ref("agent_error_summary", run_dir / "agent_error_summary.json"),
            path_ref("stage_trace", run_dir / "stage_trace.json"),
        ],
        operations=operations,
        outputs=[
            path_ref("failure_interpretation", interpretation_path),
            path_ref("failure_interpretation_markdown", markdown_path),
            path_ref("failure_interpreter_prompt", prompt_path),
            path_ref("failure_interpreter_raw_output", raw_path),
        ],
        checks=[
            {"name": "run_dir_exists", "passed": run_dir.exists(), "message": str(run_dir)},
            {
                "name": "meta_agent_notes_written",
                "passed": bool(interpretation.get("meta_agent_notes")),
                "message": str(interpretation_path),
            },
        ],
        self_feedback={
            "confidence": interpretation.get("confidence", "medium"),
            "uncertainties": [] if interpretation.get("interpreter") == "llm" else ["Used deterministic fallback."],
            "evolution_hints": [
                "Use meta_agent_notes as the next coding meta-agent task notes.",
                "Treat evidence fields as constraints; do not hard-code validator answers.",
            ],
            "suggested_target_modules": interpretation.get("evolution_targets", []),
        },
        error=error,
        report_stem="interpret_failure",
    )
    interpretation["script_run_report_path"] = str(report_path)
    write_json(interpretation_path, interpretation)
    return interpretation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--notes")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    result = interpret_failure(
        run_dir=Path(args.run_dir),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        use_llm=not args.no_llm,
        extra_notes=args.notes,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
