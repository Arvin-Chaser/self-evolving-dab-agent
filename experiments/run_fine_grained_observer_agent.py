#!/usr/bin/env python3
"""LLM fine-grained feedback generator for a single DataAgent run.

This observer is intended to be the source of flexible fine-grained feedback.
It reads raw DataAgent execution artifacts directly from a run directory and
asks an LLM to infer what went wrong, what evidence supports that inference,
and what kind of repair affordances the meta-agent should consider.

It deliberately does not consume the legacy/pre-shaped evidence pack and does
not require a fixed failure taxonomy.  The JSON schema is only an interchange
container; the substantive observations should emerge from the run artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_direct_failure_observer_agent import (  # noqa: E402
    collect_raw_run,
    extract_json_object,
    read_json,
    utc_now,
    write_json,
)


def build_observer_payload(
    *,
    run_dir: Path,
    query_id: str | None,
    domain: str | None,
    per_file_limit: int,
    max_files_per_run: int,
    max_total_chars_per_run: int,
) -> dict[str, Any]:
    summary = read_json(run_dir / "summary.json", {})
    result = read_json(run_dir / "result.json", {})
    if not query_id:
        query_id = str(summary.get("query_id") or result.get("query_id") or "").strip() or None
    if not domain:
        domain = str(summary.get("domain") or result.get("domain") or "").strip() or None
    raw_run = collect_raw_run(
        {"run_dir": str(run_dir), "query_id": query_id, "domain": domain},
        role="observed_data_agent_run",
        per_file_limit=per_file_limit,
        max_files_per_run=max_files_per_run,
        max_total_chars_per_run=max_total_chars_per_run,
    )
    return {
        "schema_version": "fine_grained_observer_input_v001",
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "query_id": query_id,
        "domain": domain,
        "input_policy": {
            "observer_generates_fine_grained_feedback": True,
            "uses_prebuilt_evidence_pack": False,
            "uses_preinferred_failure_patterns": False,
            "requires_fixed_failure_taxonomy": False,
            "reads_raw_data_agent_behavior": True,
            "data_agent_observability_may_evolve": True,
            "stable_artifact_interface_required": False,
        },
        "raw_behavior_run": raw_run,
    }


def deterministic_feedback(payload: dict[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    raw_files = payload.get("raw_behavior_run", {}).get("raw_files", {})
    text = json.dumps(raw_files, ensure_ascii=False)
    observations: list[dict[str, Any]] = []
    if "final_answer" in text and "\"content\": \"\"" in text:
        observations.append(
            {
                "artifact": "raw run artifacts",
                "observation": "The observed run appears to have an empty final answer artifact.",
                "why_it_matters": "A repair should first explain why the workflow stopped without a usable answer.",
            }
        )
    if "run_evolved_helper" in text and "helper_tool_registered_but_not_called" in text:
        observations.append(
            {
                "artifact": "helper usage summary / tool logs",
                "observation": "A helper tool was available but was not called during the run.",
                "why_it_matters": "The failure may be in tool-selection policy or helper discoverability rather than helper implementation alone.",
            }
        )
    if not observations:
        observations.append(
            {
                "artifact": "raw run artifacts",
                "observation": "Fallback observer could not infer a specific mechanism without LLM support.",
                "why_it_matters": "Use the raw behavior input artifact for manual or meta-agent inspection.",
            }
        )
    return {
        "schema_version": "observer_fine_grained_feedback_v001",
        "created_at": utc_now(),
        "observer_mode": "single_run_deterministic_fallback",
        "fallback_reason": reason,
        "input_policy": payload.get("input_policy"),
        "query_id": payload.get("query_id"),
        "domain": payload.get("domain"),
        "failure_narrative": "Deterministic fallback generated limited observations from raw DataAgent artifacts.",
        "evidence_chain": observations,
        "inferred_failure_mechanisms": [],
        "answer_quality_shape": "unknown_or_unavailable",
        "repair_affordances": [],
        "logging_gaps": [],
        "next_observation_requests": [
            "Let the LLM observer inspect the raw behavior payload for a richer, context-specific diagnosis."
        ],
        "confidence": 0.25,
    }


def build_prompt(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    max_chars = int(os.getenv("FINE_GRAINED_OBSERVER_PROMPT_CHARS", "90000"))
    if len(body) > max_chars:
        body = body[:max_chars] + "\n...<TRUNCATED_FINE_GRAINED_OBSERVER_PAYLOAD>..."
    return f"""You are a Fine-Grained Feedback Observer for a DataAgent evolution system.

Your job is to generate flexible, context-specific fine-grained feedback from
raw DataAgent behavior. Do not choose from a fixed failure taxonomy. Do not rely
on a pre-built evidence pack or pre-inferred selected_stage/selected_signal.
Infer the important failure structure directly from the artifacts you see.

You are not a repair agent. Do not write code patches. Do not hardcode benchmark
answers. Your output should help a later meta-agent decide what to inspect or
change, including whether the DataAgent's own logging/observability should be
changed in future iterations.

Return only strict JSON with this schema. The field names are fixed for machine
readability, but the content should be free-form and grounded in the actual run:
{{
  "schema_version": "observer_fine_grained_feedback_v001",
  "observer_mode": "single_run_llm_fine_grained_feedback_generator",
  "input_policy": {{
    "observer_generates_fine_grained_feedback": true,
    "uses_prebuilt_evidence_pack": false,
    "uses_preinferred_failure_patterns": false,
    "requires_fixed_failure_taxonomy": false,
    "reads_raw_data_agent_behavior": true
  }},
  "query_id": "...",
  "domain": "...",
  "failure_narrative": "a concrete explanation of what happened in this run",
  "evidence_chain": [
    {{"artifact": "raw file path or artifact name", "observation": "what you saw", "why_it_matters": "why it matters"}}
  ],
  "inferred_failure_mechanisms": [
    {{"name": "short free-form mechanism name", "description": "...", "supporting_evidence": ["..."]}}
  ],
  "answer_quality_shape": "free-form description such as empty answer, broad noisy set, near miss, tool-aborted, etc.",
  "repair_affordances": [
    "capabilities, workflow changes, helper/controller/logging changes the meta-agent may consider"
  ],
  "logging_gaps": [
    "what the run did not log clearly enough, if anything"
  ],
  "next_observation_requests": [
    "what future DataAgent runs should expose so the next observer can understand failures better"
  ],
  "confidence": 0.0
}}

Raw DataAgent behavior payload:
{body}
"""


def run_llm_observer(payload: dict[str, Any]) -> dict[str, Any]:
    from llm_client import call_meta_llm

    raw = call_meta_llm(build_prompt(payload))
    parsed = extract_json_object(raw)
    if not parsed:
        raise ValueError("Fine-grained observer did not return parseable JSON")
    parsed.setdefault("schema_version", "observer_fine_grained_feedback_v001")
    parsed.setdefault("observer_mode", "single_run_llm_fine_grained_feedback_generator")
    parsed.setdefault("created_at", utc_now())
    parsed.setdefault("input_policy", payload.get("input_policy"))
    parsed.setdefault("query_id", payload.get("query_id"))
    parsed.setdefault("domain", payload.get("domain"))
    parsed["raw_observer_response_preview"] = raw[:1200]
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--query-id")
    parser.add_argument("--domain")
    parser.add_argument("--output", required=True)
    parser.add_argument("--behavior-input-output", required=True)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--per-file-limit", type=int, default=9000)
    parser.add_argument("--max-files-per-run", type=int, default=36)
    parser.add_argument("--max-total-chars-per-run", type=int, default=70000)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir).resolve()
    payload = build_observer_payload(
        run_dir=run_dir,
        query_id=args.query_id,
        domain=args.domain,
        per_file_limit=args.per_file_limit,
        max_files_per_run=args.max_files_per_run,
        max_total_chars_per_run=args.max_total_chars_per_run,
    )
    behavior_path = Path(args.behavior_input_output).resolve()
    output_path = Path(args.output).resolve()
    write_json(behavior_path, payload)
    if args.no_llm or os.getenv("FINE_GRAINED_OBSERVER_NO_LLM") == "1":
        feedback = deterministic_feedback(payload, reason="no_llm_requested")
    else:
        try:
            feedback = run_llm_observer(payload)
        except Exception as exc:
            feedback = deterministic_feedback(payload, reason=f"{type(exc).__name__}: {exc}")
    feedback["behavior_input"] = str(behavior_path)
    feedback["source_run_dir"] = str(run_dir)
    write_json(output_path, feedback)
    print(json.dumps({"status": "completed", "output": str(output_path), "behavior_input": str(behavior_path), "observer_mode": feedback.get("observer_mode")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
