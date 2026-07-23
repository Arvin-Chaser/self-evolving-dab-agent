#!/usr/bin/env python3
"""Run a Failure Observer over a candidate's evidence pack.

The observer is intentionally not a repair agent: it must not generate patches
or prescribe exact file edits.  Its job is to convert raw candidate/runtime
evidence into grounded failure mechanisms, evidence chains, not-to-repeat
lessons, and open questions for the next meta-agent iteration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.build_failure_observation_pack import build_pack, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def deterministic_observation(pack: dict[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    patterns = pack.get("candidate_failure_patterns") if isinstance(pack.get("candidate_failure_patterns"), list) else []
    primary = patterns[0] if patterns else {"pattern": "unclassified_failure_mechanism", "confidence": 0.35}
    affected = [
        row.get("query_id")
        for row in pack.get("query_summaries", [])
        if isinstance(row, dict)
        and (
            row.get("selected_problem_type")
            or (row.get("answer_quality") or {}).get("strict_match_passed") is False
        )
    ]
    evidence_chain: list[dict[str, Any]] = []
    for target in pack.get("registry_targets_added", []) or []:
        evidence_chain.append(
            {
                "artifact": "patch.diff",
                "observation": "patch added helper registry target",
                "detail": target,
            }
        )
    for row in pack.get("query_summaries", []) or []:
        if not isinstance(row, dict):
            continue
        helper = row.get("helper_usage") if isinstance(row.get("helper_usage"), dict) else {}
        for match in helper.get("matched_registry_errors") or []:
            evidence_chain.append(
                {
                    "artifact": "per-query helper_usage_summary",
                    "query_id": row.get("query_id"),
                    "observation": "runtime helper call failed for registered target",
                    "detail": match,
                }
            )
        aq = row.get("answer_quality") if isinstance(row.get("answer_quality"), dict) else {}
        evidence_chain.append(
            {
                "artifact": "feedback_summary.answer_quality",
                "query_id": row.get("query_id"),
                "observation": "answer-quality shape after patch",
                "detail": {
                    "strict_match_passed": aq.get("strict_match_passed"),
                    "strict_match_reason": aq.get("strict_match_reason"),
                    "missing_count": aq.get("missing_count"),
                    "extra_count": aq.get("extra_count"),
                    "f1": aq.get("f1"),
                    "selected_signal": row.get("selected_signal"),
                },
            }
        )
    not_to_repeat = []
    if primary.get("pattern") == "helper_registry_callable_mismatch":
        not_to_repeat.extend(
            [
                "Do not add helper registry entries unless the target module:function imports successfully in the child workspace.",
                "Do not treat helper registration as helper implementation.",
                "Do not generate registry-only helper patches when the runtime requires callable helper behavior.",
            ]
        )
    if primary.get("pattern") == "unclassified_failure_mechanism":
        not_to_repeat.append("Do not rely only on selected_stage/selected_signal; inspect raw tool and answer artifacts before patching.")
    return {
        "schema_version": "failure_observation_v001",
        "created_at": utc_now(),
        "observer_mode": "deterministic_fallback",
        "fallback_reason": reason,
        "candidate_id": pack.get("candidate_id"),
        "primary_failure_mechanism": primary.get("pattern"),
        "confidence": primary.get("confidence"),
        "affected_queries": sorted(set(x for x in affected if x)),
        "evidence_chain": evidence_chain[:20],
        "fine_grained_effect": {
            row.get("query_id"): {
                "selected_stage": row.get("selected_stage"),
                "selected_signal": row.get("selected_signal"),
                "answer_quality": row.get("answer_quality"),
                "helper_usage": row.get("helper_usage"),
                "final_answer_preview": row.get("final_answer_preview"),
            }
            for row in pack.get("query_summaries", [])
            if isinstance(row, dict) and row.get("query_id")
        },
        "not_to_repeat": not_to_repeat,
        "open_questions_for_meta_agent": [
            "What code-level mechanism should make the observed failure less likely on future candidates?",
            "Should the next candidate add callable helper implementation, registry validation, fallback behavior, or another workflow-level structure?",
        ],
        "repair_decision_policy": "observer_only_no_patch_no_file_edit_instruction",
    }


def build_observer_prompt(pack: dict[str, Any]) -> str:
    compact_pack = json.dumps(pack, indent=2, ensure_ascii=False)
    if len(compact_pack) > 45000:
        compact_pack = compact_pack[:45000] + "\n...TRUNCATED..."
    return f"""You are a Failure Observer for a meta-agent evolution system.

Your job is to observe and explain the concrete failure mechanism that emerged
from the candidate's actual patch and runtime evidence. You are NOT a repair
agent. Do not produce code patches. Do not prescribe exact file edits. Do not
claim the final task is solved.

Return only strict JSON with this schema:
{{
  "schema_version": "failure_observation_v001",
  "observer_mode": "llm_failure_observer",
  "primary_failure_mechanism": "short_snake_case",
  "confidence": 0.0,
  "affected_queries": ["..."],
  "evidence_chain": [
    {{"artifact": "...", "observation": "...", "detail": "..."}}
  ],
  "fine_grained_effect": {{"query_id": {{"before_after_or_effect": "...", "answer_quality_shape": "..."}}}},
  "not_to_repeat": ["..."],
  "open_questions_for_meta_agent": ["..."],
  "repair_decision_policy": "observer_only_no_patch_no_file_edit_instruction"
}}

Focus on mechanisms grounded in evidence, such as patch-runtime mismatch,
helper-callable mismatch, missing fallback after tool failure, answer-set
collapse, or workflow-control regression. If evidence is insufficient, say so.

Evidence pack:
{compact_pack}
"""


def run_llm_observer(pack: dict[str, Any]) -> dict[str, Any]:
    from llm_client import call_meta_llm

    raw = call_meta_llm(build_observer_prompt(pack))
    parsed = extract_json_object(raw)
    if not parsed:
        raise ValueError("LLM observer did not return parseable JSON")
    parsed.setdefault("schema_version", "failure_observation_v001")
    parsed.setdefault("observer_mode", "llm_failure_observer")
    parsed.setdefault("created_at", utc_now())
    parsed.setdefault("candidate_id", pack.get("candidate_id"))
    parsed["raw_observer_response_preview"] = raw[:1200]
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--pack", help="Existing failure_observation_pack.json. Built automatically if omitted.")
    parser.add_argument("--output", help="Defaults to <candidate-dir>/failure_observation.json")
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic fallback only.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidate_dir = Path(args.candidate_dir).resolve()
    pack_path = Path(args.pack) if args.pack else candidate_dir / "failure_observation_pack.json"
    if pack_path.exists():
        pack = read_json(pack_path, {})
    else:
        pack = build_pack(candidate_dir)
        write_json(pack_path, pack)
    output = Path(args.output) if args.output else candidate_dir / "failure_observation.json"

    observation: dict[str, Any]
    if args.no_llm or os.getenv("FAILURE_OBSERVER_NO_LLM") == "1":
        observation = deterministic_observation(pack, reason="llm_disabled")
    else:
        try:
            observation = run_llm_observer(pack)
        except Exception as exc:
            observation = deterministic_observation(pack, reason=f"{type(exc).__name__}: {exc}")
    observation["source_pack"] = str(pack_path)
    write_json(output, observation)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "observer_mode": observation.get("observer_mode"),
                "primary_failure_mechanism": observation.get("primary_failure_mechanism"),
                "confidence": observation.get("confidence"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
