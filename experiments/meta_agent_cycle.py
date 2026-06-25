#!/usr/bin/env python3
"""Postprocess a meta-agent candidate into review, seed, and archive artifacts.

This script captures the glue work that previously happened in conversation:

- infer candidate lifecycle state;
- generate a human merge review package;
- generate the next repair seed;
- write/update archive candidate cards and indexes.

It deliberately does not run Qwen, apply patches, merge to main, or modify
candidate patches. Human approval remains the boundary before merge/promotion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_numstat(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        rows.append({"path": path, "added": int(added), "deleted": int(deleted)})
    return rows


def diff_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            files.append(line.split(" b/", 1)[1])
    return sorted(set(files))


def compact_signal(signal: Any) -> dict[str, Any]:
    if isinstance(signal, dict):
        return signal
    if not isinstance(signal, str):
        return {"raw": signal}
    text = signal.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"raw": text}


def infer_state(candidate_dir: Path) -> dict[str, Any]:
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    promotion = load_json(candidate_dir / "promotion_decision.json") or {}
    merge_validation = load_json(candidate_dir / "merge_validation/merge_validation_summary.json") or {}

    status = (
        promotion.get("status")
        or review.get("post_child_eval_review_status")
        or child_eval.get("final_status")
        or manifest.get("status")
        or "unknown"
    )
    if merge_validation.get("status") == "passed" and status == "post_child_eval_review_passed":
        status = "ready_for_or_completed_branch_merge_validation"

    state = {
        "candidate_id": candidate_dir.name,
        "status": status,
        "manifest_status": manifest.get("status"),
        "child_eval_status": child_eval.get("final_status"),
        "post_child_eval_review_status": review.get("post_child_eval_review_status"),
        "promotion_decision_status": promotion.get("status"),
        "merge_validation_status": merge_validation.get("status"),
        "merge_recommendation": (
            promotion.get("merge_recommendation")
            or review.get("merge_recommendation")
            or "unknown"
        ),
        "lifecycle": [
            step
            for step in [
                manifest.get("status"),
                child_eval.get("final_status"),
                review.get("post_child_eval_review_status"),
                promotion.get("status"),
                merge_validation.get("status") and f"merge_validation_{merge_validation.get('status')}",
            ]
            if step
        ],
    }
    write_json(candidate_dir / "candidate_state.json", state)
    return state


def build_patch_review(candidate_dir: Path) -> dict[str, Any]:
    manifest = load_json(candidate_dir / "manifest.json") or {}
    patch_text = read_text(candidate_dir / "patch.diff")
    numstat_rows = parse_numstat(read_text(candidate_dir / "patch_numstat.txt"))
    total = sum(row["added"] + row["deleted"] for row in numstat_rows)
    files = diff_files(patch_text)
    return {
        "diff_files": files,
        "manifest_project_changed_files": manifest.get("project_changed_files") or [],
        "patch_numstat": numstat_rows,
        "total_changed_lines": total,
        "manifest_total_changed_lines": manifest.get("total_changed_lines"),
        "control_files_in_project_diff": [
            path
            for path in files
            if path not in {
                "adapters/feedback/common_trace_checks.py",
                "adapters/feedback/dab_patents_checks.py",
            }
        ],
    }


def generate_merge_review(candidate_dir: Path, state: dict[str, Any], scope_note: str) -> Path:
    patch_review = build_patch_review(candidate_dir)
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    merge_validation = load_json(candidate_dir / "merge_validation/merge_validation_summary.json") or {}
    child_status = child_eval.get("child_status") or {}
    parent_status = child_eval.get("parent_status") or {}

    lines = [
        f"# Merge review package: {candidate_dir.name}",
        "",
        "Status: ready for human review; do not auto-merge.",
        "",
        f"Scope: {scope_note}",
        "",
        "## Patch summary",
        "",
        f"- Candidate status: `{state['status']}`",
        f"- Manifest status: `{manifest.get('status')}`",
        f"- Changed files: `{', '.join(patch_review['diff_files'])}`",
        f"- Total changed lines: `{patch_review['total_changed_lines']}`",
        f"- Manifest total changed lines: `{patch_review['manifest_total_changed_lines']}`",
        f"- Control files in project diff: `{patch_review['control_files_in_project_diff']}`",
        "",
        "## Validation",
        "",
        f"- validation_exit_code: `{manifest.get('validation_exit_code')}`",
        f"- patch_spec_status: `{manifest.get('patch_spec_status')}`",
        f"- deterministic_apply_status: `{manifest.get('deterministic_apply_status')}`",
        f"- post_apply_gate_status: `{manifest.get('post_apply_gate_status')}`",
        "",
        "## Child eval",
        "",
        f"- child_eval_final_status: `{child_eval.get('final_status')}`",
        f"- parent_status: `{parent_status.get('status')}`",
        f"- child_status: `{child_status.get('status')}`",
        f"- parent selected_stage: `{parent_status.get('selected_stage')}`",
        f"- child selected_stage: `{child_status.get('selected_stage')}`",
        f"- child selected_signal: `{child_status.get('selected_signal')}`",
        f"- original DAB validation still failed: `{child_status.get('passed_original_dab_validation') is False}`",
        "",
        "## Small regression",
        "",
        f"- post_child_eval_review_status: `{review.get('post_child_eval_review_status')}`",
        f"- regression_status: `{(review.get('regression_results') or {}).get('status')}`",
        f"- public_api_preservation_status: `{(review.get('public_api_preservation_status') or {}).get('status')}`",
        f"- merge_recommendation: `{review.get('merge_recommendation')}`",
        "",
        "## Merge validation",
        "",
        f"- merge_validation_status: `{merge_validation.get('status')}`",
        f"- updated selected_stage: `{merge_validation.get('selected_stage')}`",
        f"- updated selected_signal: `{merge_validation.get('selected_signal')}`",
        "",
        "## Risk and rollback",
        "",
        "- Treat as feedback/error-analysis infrastructure repair only.",
        "- Do not count this as solving the original PATENTS answer-generation failure.",
        "- Roll back an uncommitted apply with `git apply -R <candidate>/patch.diff`.",
        "- Roll back a committed merge with `git revert <commit>`.",
        "",
        "## Next step",
        "",
        "After human confirmation, use the generated next repair seed for the data-agent repair iteration.",
        "",
    ]
    out = candidate_dir / "merge_review_package.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def generate_next_seed(candidate_dir: Path, case_id: str, recommended_goal: str) -> tuple[Path, Path]:
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    child_status = child_eval.get("child_status") or {}
    parent_run_id = child_eval.get("parent_run_id")
    selected_signal = compact_signal(child_status.get("selected_signal"))
    selected_stage = child_status.get("selected_stage")
    seed = {
        "seed_id": f"next_data_agent_repair_seed_from_{candidate_dir.name}",
        "created_for": "iter004_data_agent_repair",
        "source_candidate": candidate_dir.name,
        "source_candidate_dir": str(candidate_dir),
        "case": {
            "case_id": case_id,
            "parent_run_id": parent_run_id,
            "parent_run_dir": "logs/dab_agent/run_demo_full_loop_20260619_200238_parent_query_PATENTS_query1_20260619_200238",
        },
        "selected_stage": selected_stage,
        "selected_signal": "no_years_found" if selected_signal.get("event") == "no_years_found" else child_status.get("selected_signal"),
        "selected_signal_evidence": selected_signal,
        "original_dab_validation": {
            "passed": child_status.get("passed_original_dab_validation"),
            "validation_reason": child_status.get("validation_reason"),
            "still_failed_after_feedback_repair": child_status.get("passed_original_dab_validation") is False,
        },
        "recommended_iter004_goal": recommended_goal,
        "recommended_constraints": [
            "Do not modify feedback analyzer unless a new analyzer bug is independently proven.",
            "Use structured patch_spec protocol; Qwen should not freely edit source.",
            "Run child eval and small regression before any merge.",
            "Archive every candidate attempt.",
        ],
        "recommended_focus_areas": [
            "CPC definition metadata grounding",
            "CPC level-5 mapping logic",
            "filing_date year extraction",
            "EMA/best-year calculation path",
            "final_answer non-empty contract",
        ],
    }
    json_path = candidate_dir / "next_data_agent_repair_seed.json"
    md_path = candidate_dir / "next_data_agent_repair_seed.md"
    write_json(json_path, seed)
    md = [
        "# next_data_agent_repair_seed",
        "",
        f"- source_candidate: `{candidate_dir.name}`",
        f"- case_id: `{case_id}`",
        f"- selected_stage: `{seed['selected_stage']}`",
        f"- selected_signal: `{seed['selected_signal']}`",
        f"- original_dab_validation_passed: `{seed['original_dab_validation']['passed']}`",
        f"- validation_reason: `{seed['original_dab_validation']['validation_reason']}`",
        "",
        "## Recommended goal",
        "",
        recommended_goal,
        "",
        "## Focus areas",
        "",
    ]
    md.extend(f"- {item}" for item in seed["recommended_focus_areas"])
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return json_path, md_path


def upsert_jsonl(path: Path, key: str, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    replaced = False
    for index, existing in enumerate(rows):
        if existing.get(key) == row.get(key):
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in rows) + "\n", encoding="utf-8")


def archive_candidate(
    candidate_dir: Path,
    archive_root: Path,
    state: dict[str, Any],
    parent_agent_id: str,
    candidate_type: str,
    scope_note: str,
) -> Path:
    candidate_id = candidate_dir.name
    patch_review = build_patch_review(candidate_dir)
    manifest = load_json(candidate_dir / "manifest.json") or {}
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json") or {}
    review = load_json(candidate_dir / "post_child_eval_review/post_child_eval_review.json") or {}
    card = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "parent_agent_id": parent_agent_id,
        "status": state["status"],
        "changed_files": patch_review["diff_files"],
        "artifacts": {
            "candidate_dir": str(candidate_dir.relative_to(ROOT) if candidate_dir.is_relative_to(ROOT) else candidate_dir),
            "patch": str((candidate_dir / "patch.diff").relative_to(ROOT)),
            "manifest": str((candidate_dir / "manifest.json").relative_to(ROOT)),
            "validation_log": str((candidate_dir / "validation.log").relative_to(ROOT)) if (candidate_dir / "validation.log").exists() else None,
            "child_eval_report": str((candidate_dir / "child_eval/child_eval_report.json").relative_to(ROOT)) if (candidate_dir / "child_eval/child_eval_report.json").exists() else None,
            "post_child_eval_review": str((candidate_dir / "post_child_eval_review/post_child_eval_review.json").relative_to(ROOT)) if (candidate_dir / "post_child_eval_review/post_child_eval_review.json").exists() else None,
            "merge_review_package": str((candidate_dir / "merge_review_package.md").relative_to(ROOT)) if (candidate_dir / "merge_review_package.md").exists() else None,
            "next_repair_seed": str((candidate_dir / "next_data_agent_repair_seed.json").relative_to(ROOT)) if (candidate_dir / "next_data_agent_repair_seed.json").exists() else None,
        },
        "eval_summary": {
            "manifest_status": manifest.get("status"),
            "child_eval": child_eval.get("final_status"),
            "post_child_eval_review": review.get("post_child_eval_review_status"),
            "total_changed_lines": patch_review["total_changed_lines"],
            "scope": scope_note,
        },
        "promotion": {
            "promoted_to_agent": state.get("post_child_eval_review_status") == "post_child_eval_review_passed",
            "merge_recommendation": state.get("merge_recommendation"),
        },
    }
    card_path = archive_root / "candidates" / candidate_id / "candidate_card.json"
    write_json(card_path, card)
    reward = 1.0 if state.get("post_child_eval_review_status") == "post_child_eval_review_passed" else 0.0
    upsert_jsonl(
        archive_root / "indexes/candidates.jsonl",
        "candidate_id",
        {
            "candidate_id": candidate_id,
            "status": state["status"],
            "candidate_type": candidate_type,
            "parent_agent_id": parent_agent_id,
            "card": str(card_path.relative_to(ROOT)),
            "reward": reward,
        },
    )
    return card_path


def postprocess_candidate(args: argparse.Namespace) -> int:
    candidate_dir = Path(args.candidate_dir).resolve()
    archive_root = Path(args.archive_root).resolve()
    if not candidate_dir.exists():
        raise SystemExit(f"candidate_dir not found: {candidate_dir}")
    state = infer_state(candidate_dir)
    review_path = generate_merge_review(candidate_dir, state, args.scope_note)
    seed_json, seed_md = generate_next_seed(candidate_dir, args.case_id, args.recommended_goal)
    card_path = archive_candidate(
        candidate_dir,
        archive_root,
        state,
        parent_agent_id=args.parent_agent_id,
        candidate_type=args.candidate_type,
        scope_note=args.scope_note,
    )
    summary = {
        "status": "postprocess_complete",
        "candidate_id": candidate_dir.name,
        "state": state,
        "outputs": {
            "candidate_state": str(candidate_dir / "candidate_state.json"),
            "merge_review_package": str(review_path),
            "next_seed_json": str(seed_json),
            "next_seed_md": str(seed_md),
            "archive_card": str(card_path),
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    post = sub.add_parser("postprocess-candidate")
    post.add_argument("--candidate-dir", required=True)
    post.add_argument("--archive-root", default=str(ROOT / "archive"))
    post.add_argument("--parent-agent-id", default="codex_qwen_meta_v4_structured_patch_spec")
    post.add_argument("--candidate-type", default="feedback_analyzer_repair")
    post.add_argument(
        "--scope-note",
        default="Feedback/error-analysis infrastructure repair only; not a PATENTS answer solver repair.",
    )
    post.add_argument("--case-id", default="PATENTS_query1")
    post.add_argument(
        "--recommended-goal",
        default=(
            "Repair the data-agent side for PATENTS_query1 so CPC level-5 mapping, "
            "filing-date year extraction, EMA/best-year calculation, and final answer "
            "generation produce a non-empty validated answer."
        ),
    )
    post.set_defaults(func=postprocess_candidate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

