#!/usr/bin/env python3
"""Direct parent/child behavior observer for meta-agent evolution.

Unlike the legacy pack-based observer, this script does not read
failure_observation_pack.json and does not consume pre-inferred failure
patterns.  It gives the LLM raw parent/child execution artifacts plus the
candidate patch and asks it to infer a grounded failure mechanism from the
behavior itself.

The observer remains observer-only: it must not generate patches or prescribe
exact file edits.
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


TEXT_ARTIFACT_SUFFIXES = {".json", ".jsonl", ".txt", ".log", ".md", ".py", ".csv", ".tsv"}
SKIP_ARTIFACT_NAMES = {"__pycache__", ".git"}
OBSERVER_EXCLUDED_EXPLANATION_ARTIFACTS = {
    "feedback_summary.json",
    "meta_agent_seed.json",
    "observations.json",
    "fine_grained_evidence_pack.json",
    "fine_grained_evidence_pack.md",
    "observer_fine_grained_feedback.json",
    "observer_raw_behavior_input.json",
    "failure_observation.json",
    "direct_behavior_observation_input.json",
    "failure_observation_pack.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"_read_error": type(exc).__name__, "path": str(path), "error": str(exc)}


def read_text(path: Path, limit: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return head + "\n...<TRUNCATED_MIDDLE>...\n" + tail


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def query_runs_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = summary.get("per_query_feedback") if isinstance(summary.get("per_query_feedback"), list) else []
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and row.get("run_dir"):
            result.append(
                {
                    "query_id": row.get("query_id"),
                    "domain": row.get("domain"),
                    "run_dir": row.get("run_dir"),
                }
            )
    return result


def child_runs(candidate_dir: Path) -> list[dict[str, Any]]:
    child_eval = read_json(candidate_dir / "child_eval/child_eval_report.json", {})
    summary = child_eval.get("child_multi_query_summary") if isinstance(child_eval.get("child_multi_query_summary"), dict) else {}
    return query_runs_from_summary(summary)


def parent_candidate_from_agent(archive_root: Path, parent_agent_id: str | None) -> Path | None:
    if not parent_agent_id:
        return None
    card = archive_root / "agents" / parent_agent_id / "agent_card.json"
    data = read_json(card, {})
    lineage = data.get("lineage") if isinstance(data.get("lineage"), dict) else {}
    candidate_id = lineage.get("derived_from_candidate")
    if isinstance(candidate_id, str):
        candidate = ROOT / "candidates/dab" / candidate_id
        if candidate.exists():
            return candidate
    source_refs = data.get("source_refs") if isinstance(data.get("source_refs"), dict) else {}
    patch_ref = source_refs.get("candidate_patch")
    if isinstance(patch_ref, str):
        parts = Path(patch_ref).parts
        if "candidates" in parts and len(parts) >= 3:
            candidate_id = Path(patch_ref).parent.name
            candidate = ROOT / "candidates/dab" / candidate_id
            if candidate.exists():
                return candidate
    return None


def parent_runs(*, candidate_dir: Path, parent_run_dir: Path | None, parent_agent_id: str | None, archive_root: Path) -> list[dict[str, Any]]:
    if parent_run_dir and parent_run_dir.exists():
        summary = read_json(parent_run_dir / "multi_query_summary.json", {})
        return query_runs_from_summary(summary)
    parent_candidate = parent_candidate_from_agent(archive_root, parent_agent_id)
    if parent_candidate:
        child_eval = read_json(parent_candidate / "child_eval/child_eval_report.json", {})
        summary = child_eval.get("child_multi_query_summary") if isinstance(child_eval.get("child_multi_query_summary"), dict) else {}
        runs = query_runs_from_summary(summary)
        if runs:
            return runs
    return []


def should_collect_artifact(path: Path) -> bool:
    if any(part in SKIP_ARTIFACT_NAMES for part in path.parts):
        return False
    if path.name in OBSERVER_EXCLUDED_EXPLANATION_ARTIFACTS:
        return False
    if not path.is_file():
        return False
    if path.suffix.lower() in TEXT_ARTIFACT_SUFFIXES:
        return True
    # Some evolved logs may be extensionless; keep small extensionless files.
    try:
        return not path.suffix and path.stat().st_size <= 250_000
    except OSError:
        return False


def discover_run_artifacts(run_dir: Path, *, max_files: int, max_total_chars: int, per_file_limit: int) -> dict[str, Any]:
    files: dict[str, Any] = {}
    if not run_dir.exists():
        return files
    candidates = [path for path in run_dir.rglob("*") if should_collect_artifact(path)]
    priority_order = {
        "full_execution_trace.jsonl": 0,
        "summary.json": 1,
        "final_answer.txt": 2,
        "raw_final_answer.txt": 3,
        "tool_calls.jsonl": 4,
        "llm_calls.jsonl": 5,
    }
    candidates.sort(key=lambda path: (priority_order.get(path.name, 99), path.stat().st_size if path.exists() else 0, str(path)))
    total = 0
    for path in candidates[:max_files]:
        rel = str(path.relative_to(run_dir))
        remaining = max_total_chars - total
        if remaining <= 0:
            break
        limit = min(per_file_limit, remaining)
        content = read_text(path, limit=limit)
        total += len(content)
        files[rel] = {
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "content": content,
        }
    return files


def collect_raw_run(
    run: dict[str, Any],
    *,
    role: str,
    per_file_limit: int,
    max_files_per_run: int,
    max_total_chars_per_run: int,
) -> dict[str, Any]:
    run_dir = Path(str(run.get("run_dir") or ""))
    files = discover_run_artifacts(
        run_dir,
        max_files=max_files_per_run,
        max_total_chars=max_total_chars_per_run,
        per_file_limit=per_file_limit,
    )
    return {
        "role": role,
        "query_id": run.get("query_id"),
        "domain": run.get("domain"),
        "run_dir": str(run_dir),
        "artifact_collection_policy": {
            "stable_file_interface_required": False,
            "recursive_run_dir_scan": True,
            "max_files_per_run": max_files_per_run,
            "max_total_chars_per_run": max_total_chars_per_run,
            "per_file_limit": per_file_limit,
            "collected_file_count": len(files),
        },
        "raw_files": files,
    }


def build_direct_behavior_payload(
    *,
    candidate_dir: Path,
    parent_agent_id: str | None,
    parent_run_dir: Path | None,
    archive_root: Path,
    per_file_limit: int,
    max_files_per_run: int,
    max_total_chars_per_run: int,
) -> dict[str, Any]:
    candidate_dir = candidate_dir.resolve()
    child_eval_path = candidate_dir / "child_eval/child_eval_report.json"
    parent = parent_runs(
        candidate_dir=candidate_dir,
        parent_run_dir=parent_run_dir,
        parent_agent_id=parent_agent_id,
        archive_root=archive_root,
    )
    child = child_runs(candidate_dir)
    return {
        "schema_version": "direct_behavior_observation_input_v001",
        "created_at": utc_now(),
        "candidate_id": candidate_dir.name,
        "candidate_dir": str(candidate_dir),
        "parent_agent_id": parent_agent_id,
        "input_policy": {
            "uses_failure_observation_pack": False,
            "uses_preinferred_failure_patterns": False,
            "observer_reads_raw_parent_child_behavior": True,
            "stable_artifact_interface_required": False,
            "data_agent_observability_may_evolve": True,
        },
        "candidate_patch": {
            "path": str(candidate_dir / "patch.diff"),
            "content": read_text(candidate_dir / "patch.diff", limit=16000),
        },
        "candidate_manifest": {
            "path": str(candidate_dir / "manifest.json"),
            "content": read_text(candidate_dir / "manifest.json", limit=6000),
        },
        "child_eval_report": {
            "path": str(child_eval_path),
            "content": read_text(child_eval_path, limit=20000),
        },
        "parent_behavior_runs": [
            collect_raw_run(
                row,
                role="parent",
                per_file_limit=per_file_limit,
                max_files_per_run=max_files_per_run,
                max_total_chars_per_run=max_total_chars_per_run,
            )
            for row in parent
        ],
        "child_behavior_runs": [
            collect_raw_run(
                row,
                role="child",
                per_file_limit=per_file_limit,
                max_files_per_run=max_files_per_run,
                max_total_chars_per_run=max_total_chars_per_run,
            )
            for row in child
        ],
    }


def deterministic_direct_observation(payload: dict[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False)
    mechanism = "unclassified_direct_behavior_failure"
    confidence = 0.35
    not_to_repeat: list[str] = []
    if "has no attribute" in text and "function" in text and "registry.py" in text:
        mechanism = "helper_registry_callable_mismatch"
        confidence = 0.93
        not_to_repeat = [
            "Do not register helper targets unless the referenced module:function exists in the child runtime.",
            "Do not treat registry edits as helper implementation.",
        ]
    affected = sorted(
        set(
            str(run.get("query_id"))
            for run in payload.get("child_behavior_runs", [])
            if isinstance(run, dict) and run.get("query_id")
        )
    )
    return {
        "schema_version": "failure_observation_v001",
        "created_at": utc_now(),
        "observer_mode": "direct_behavior_deterministic_fallback",
        "fallback_reason": reason,
        "input_policy": payload.get("input_policy"),
        "candidate_id": payload.get("candidate_id"),
        "primary_failure_mechanism": mechanism,
        "confidence": confidence,
        "affected_queries": affected,
        "evidence_chain": [
            {
                "artifact": "direct parent/child behavior payload",
                "observation": "deterministic fallback inferred mechanism from raw patch and raw run logs",
                "detail": mechanism,
            }
        ],
        "fine_grained_effect": {},
        "not_to_repeat": not_to_repeat,
        "open_questions_for_meta_agent": [
            "Inspect raw parent/child behavior artifacts to decide the next repair direction.",
        ],
        "repair_decision_policy": "observer_only_no_patch_no_file_edit_instruction",
    }


def build_prompt(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    max_chars = int(os.getenv("DIRECT_FAILURE_OBSERVER_PROMPT_CHARS", "90000"))
    if len(body) > max_chars:
        body = body[:max_chars] + "\n...<TRUNCATED_DIRECT_BEHAVIOR_PAYLOAD>..."
    return f"""You are a direct Failure Observer for a meta-agent evolution system.

You must observe the parent and child DataAgent behavior directly from the raw
execution artifacts below. Do not rely on any pre-built failure observation pack
or pre-inferred failure pattern. The DataAgent observability/logging format is
allowed to evolve across candidates, so do not assume fixed file names or fixed
schemas; infer behavior from whatever raw artifacts are present in each run
directory, plus the patch and child eval report.

You are NOT a repair agent. Do not write code patches. Do not prescribe exact
file edits. Your job is to infer the concrete failure mechanism that naturally
emerges from comparing parent behavior, child behavior, and candidate patch.

Return only strict JSON with this schema:
{{
  "schema_version": "failure_observation_v001",
  "observer_mode": "direct_behavior_llm_observer",
  "input_policy": {{
    "uses_failure_observation_pack": false,
    "uses_preinferred_failure_patterns": false,
    "observer_reads_raw_parent_child_behavior": true
  }},
  "primary_failure_mechanism": "short_snake_case",
  "confidence": 0.0,
  "affected_queries": ["..."],
  "evidence_chain": [
    {{"artifact": "raw file path or patch.diff", "observation": "...", "detail": "..."}}
  ],
  "fine_grained_effect": {{
    "query_id": {{
      "parent_behavior": "...",
      "child_behavior": "...",
      "behavior_delta": "...",
      "answer_quality_shape": "..."
    }}
  }},
  "not_to_repeat": ["..."],
  "open_questions_for_meta_agent": ["..."],
  "repair_decision_policy": "observer_only_no_patch_no_file_edit_instruction"
}}

Raw parent/child behavior payload:
{body}
"""


def run_llm_direct_observer(payload: dict[str, Any]) -> dict[str, Any]:
    from llm_client import call_meta_llm

    raw = call_meta_llm(build_prompt(payload))
    parsed = extract_json_object(raw)
    if not parsed:
        raise ValueError("Direct observer did not return parseable JSON")
    parsed.setdefault("schema_version", "failure_observation_v001")
    parsed.setdefault("observer_mode", "direct_behavior_llm_observer")
    parsed.setdefault("created_at", utc_now())
    parsed.setdefault("candidate_id", payload.get("candidate_id"))
    parsed.setdefault("input_policy", payload.get("input_policy"))
    parsed["raw_observer_response_preview"] = raw[:1200]
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--parent-agent-id")
    parser.add_argument("--parent-run-dir")
    parser.add_argument("--archive-root", default=str(ROOT / "archive"))
    parser.add_argument("--output", help="Defaults to <candidate-dir>/failure_observation.json")
    parser.add_argument("--behavior-input-output", help="Defaults to <candidate-dir>/direct_behavior_observation_input.json")
    parser.add_argument("--per-file-limit", type=int, default=9000)
    parser.add_argument("--max-files-per-run", type=int, default=32)
    parser.add_argument("--max-total-chars-per-run", type=int, default=50000)
    parser.add_argument("--no-llm", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidate_dir = Path(args.candidate_dir).resolve()
    output = Path(args.output) if args.output else candidate_dir / "failure_observation.json"
    behavior_output = (
        Path(args.behavior_input_output)
        if args.behavior_input_output
        else candidate_dir / "direct_behavior_observation_input.json"
    )
    parent_run_dir = Path(args.parent_run_dir).resolve() if args.parent_run_dir else None
    payload = build_direct_behavior_payload(
        candidate_dir=candidate_dir,
        parent_agent_id=args.parent_agent_id,
        parent_run_dir=parent_run_dir,
        archive_root=Path(args.archive_root).resolve(),
        per_file_limit=args.per_file_limit,
        max_files_per_run=args.max_files_per_run,
        max_total_chars_per_run=args.max_total_chars_per_run,
    )
    write_json(behavior_output, payload)

    if args.no_llm or os.getenv("FAILURE_OBSERVER_NO_LLM") == "1":
        observation = deterministic_direct_observation(payload, reason="llm_disabled")
    else:
        try:
            observation = run_llm_direct_observer(payload)
        except Exception as exc:
            observation = deterministic_direct_observation(payload, reason=f"{type(exc).__name__}: {exc}")
    observation["direct_behavior_input"] = str(behavior_output)
    write_json(output, observation)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "direct_behavior_input": str(behavior_output),
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
