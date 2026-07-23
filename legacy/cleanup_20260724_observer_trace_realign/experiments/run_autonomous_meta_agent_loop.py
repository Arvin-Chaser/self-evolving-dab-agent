"""Run a multi-iteration meta-agent -> data-agent evolution loop.

This script turns the previous human/Codex-in-the-loop workflow into a
repeatable pipeline:

parent run -> failure interpretation -> meta-agent patch -> patch repair/apply
-> child run -> comparison -> repeat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from experiments.analyze_agent_error import analyze_run
from experiments.apply_candidate_patch import apply_candidate_patch
from experiments.call_meta_agent import (
    DEFAULT_SCHEMA as DEFAULT_META_AGENT_RESPONSE_SCHEMA,
    extract_first_json,
    extract_unified_diff,
    git_apply_check,
    patch_from_structured_edits,
)
from experiments.interpret_failure import interpret_failure
from experiments.run_dab_agent import run_dab_agent
from experiments.run_meta_agent_loop import compare_parent_child_runs, run_loop
from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report
from adapters.feedback.common_trace_checks import parse_strict_reason
from llm_client import call_meta_llm, describe_llm_config


DEFAULT_PROMPT = BASE_DIR / "prompts" / "dab" / "dab_code_agent_prompt_v005_runtime_observer.txt"
DEFAULT_OUTPUT_DIR = BASE_DIR / "logs" / "meta_agent" / "autonomous_loop"
DEFAULT_PROXY = "http://172.17.240.1:17891"
CONCISE_TERMINAL = os.getenv("DAB_CONCISE_TERMINAL", "").lower() in {"1", "true", "yes"}


def terminal_step(message: str) -> None:
    if CONCISE_TERMINAL:
        print(f"[loop] {message}", flush=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def added_patch_lines(patch_text: str) -> list[str]:
    lines = []
    for line in patch_text.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        lines.append(line[1:])
    return lines


def added_function_names(added_lines: list[str]) -> list[str]:
    names: list[str] = []
    for line in added_lines:
        match = re.match(r"\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
        if match:
            names.append(match.group(1))
    return names


def added_function_has_call_site(function_name: str, added_lines: list[str]) -> bool:
    call_pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(")
    definition_pattern = re.compile(rf"\s*def\s+{re.escape(function_name)}\s*\(")
    for line in added_lines:
        if definition_pattern.match(line):
            continue
        if call_pattern.search(line):
            return True
    return False


def normalize_patch_path(path_text: str) -> str | None:
    path_text = path_text.strip()
    if not path_text or path_text == "/dev/null":
        return None
    if path_text.startswith("a/") or path_text.startswith("b/"):
        path_text = path_text[2:]
    return path_text


def touched_paths_from_patch_text(patch_text: str) -> list[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            for item in parts[2:4]:
                normalized = normalize_patch_path(item)
                if normalized:
                    paths.add(normalized)
        elif line.startswith("--- ") or line.startswith("+++ "):
            normalized = normalize_patch_path(line[4:].split("\t", 1)[0])
            if normalized:
                paths.add(normalized)
    return sorted(paths)


def python_syntax_check(paths: list[str]) -> dict[str, Any]:
    py_paths = [str(BASE_DIR / path) for path in paths if path.endswith(".py")]
    if not py_paths:
        return {"passed": True, "checked_paths": [], "returncode": 0, "stdout": "", "stderr": ""}
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *py_paths],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "passed": result.returncode == 0,
        "checked_paths": py_paths,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def target_for_path(path: str) -> str:
    if path.startswith("prompts/dab/meta_agent/") or path.startswith("meta_agent/"):
        return "meta_agent_policy"
    if path.startswith("prompts/dab/"):
        return "object_prompt"
    if path.startswith("adapters/feedback/") or path.startswith("adapters/runtime_observer.py"):
        return "feedback_adapter"
    if path == "experiments/run_dab_agent.py":
        return "runner"
    if path == "experiments/analyze_agent_error.py":
        return "analyzer"
    if path in {
        "experiments/build_evolution_task.py",
        "experiments/run_meta_agent_loop.py",
        "experiments/call_meta_agent.py",
    }:
        return "task_packaging"
    if path == "experiments/run_autonomous_meta_agent_loop.py":
        return "loop_guard"
    return "unknown"


def reverse_candidate_patch(candidate_path: Path) -> dict[str, Any]:
    patch_path = candidate_path / "patch.diff"
    if not patch_path.exists():
        return {"status": "skipped", "reason": "patch.diff missing", "reversed": False}
    result = subprocess.run(
        ["git", "apply", "--reverse", "--whitespace=nowarn", str(patch_path)],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "status": "success" if result.returncode == 0 else "failed",
        "reversed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def lint_candidate_patch(
    candidate_path: Path,
    parent_analysis: dict[str, Any],
    interpretation: dict[str, Any],
    repair_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch_path = candidate_path / "patch.diff"
    patch_text = patch_path.read_text(encoding="utf-8", errors="replace") if patch_path.exists() else ""
    proposal = load_json_if_exists(candidate_path / "proposal.json")
    touched_paths = touched_paths_from_patch_text(patch_text)
    touched_targets = sorted({target_for_path(path) for path in touched_paths})
    added_lines = added_patch_lines(patch_text)
    added_text = "\n".join(added_lines)
    lowered_added = added_text.lower()
    invariants = parent_analysis.get("preserved_invariants") or []
    invariant_names = {str(item.get("name")) for item in invariants if isinstance(item, dict)}
    failure_type = str(interpretation.get("failure_type") or "")
    findings: list[dict[str, Any]] = []

    def reject(rule: str, message: str, evidence: str) -> None:
        findings.append({"rule": rule, "message": message, "evidence": evidence})

    proposed_target = str(proposal.get("repair_target") or "").strip()
    evidence_quality = str(proposal.get("evidence_quality") or "").strip()
    feedback_sufficient = proposal.get("feedback_layer_sufficient")
    policy_evidence_quality = str((repair_policy or {}).get("evidence_quality") or "").strip()
    allowed_targets = set((repair_policy or {}).get("allowed_repair_targets") or [])
    preferred_targets = set((repair_policy or {}).get("preferred_repair_targets") or [])
    disallowed_targets = set((repair_policy or {}).get("disallowed_repair_targets") or [])

    if not proposed_target:
        reject(
            "missing_repair_target",
            "Meta-agent proposal must explicitly choose a project-level repair_target.",
            "proposal.json lacks repair_target.",
        )
    elif proposed_target not in {
        "object_prompt",
        "runner",
        "analyzer",
        "feedback_adapter",
        "task_packaging",
        "loop_guard",
        "meta_agent_policy",
    }:
        reject(
            "unknown_repair_target",
            "Meta-agent proposal used an unknown repair_target.",
            proposed_target,
        )

    if proposed_target == "object_prompt" and feedback_sufficient is not True:
        reject(
            "prompt_edit_requires_feedback_sufficiency",
            "Object-level prompt edits must explicitly justify that feedback/analyzer/runner/task packaging is already sufficient.",
            f"feedback_layer_sufficient={feedback_sufficient!r}",
        )

    if proposed_target and touched_targets and proposed_target not in touched_targets:
        reject(
            "repair_target_mismatch",
            "Proposal repair_target must match the primary changed component.",
            f"repair_target={proposed_target}; touched_targets={touched_targets}; touched_paths={touched_paths}",
        )

    if proposed_target and allowed_targets and proposed_target not in allowed_targets:
        reject(
            "repair_target_not_allowed_by_policy",
            "Deterministic repair policy does not allow this target for the current failure.",
            f"repair_target={proposed_target}; allowed={sorted(allowed_targets)}",
        )

    if proposed_target in disallowed_targets:
        reject(
            "repair_target_disallowed_by_policy",
            "Deterministic repair policy explicitly disallows this target for the current failure.",
            f"repair_target={proposed_target}; disallowed={sorted(disallowed_targets)}",
        )

    if (
        evidence_quality in {"coarse", "contradictory", "missing"}
        and proposed_target == "object_prompt"
    ):
        reject(
            "coarse_evidence_should_not_patch_prompt",
            "Coarse/contradictory/missing evidence should improve feedback/analyzer/runner/task packaging before object-level prompt constraints.",
            f"evidence_quality={evidence_quality}",
        )

    if (
        policy_evidence_quality in {"coarse", "contradictory", "missing"}
        and proposed_target == "object_prompt"
    ):
        reject(
            "policy_evidence_should_not_patch_prompt",
            "The deterministic repair policy says evidence is not clean enough for another object prompt edit.",
            f"policy_evidence_quality={policy_evidence_quality}; proposal_evidence_quality={evidence_quality}",
        )

    if preferred_targets and proposed_target == "object_prompt" and "object_prompt" not in preferred_targets:
        reject(
            "wrong_repair_target_prompt_default",
            "The current policy prefers project-level feedback/guard repairs over another object prompt edit.",
            f"preferred={sorted(preferred_targets)}",
        )

    syntax_result = python_syntax_check(touched_paths)
    if not syntax_result.get("passed"):
        reject(
            "python_syntax_check_failed",
            "Candidate patch must leave touched Python files syntactically valid before running a child.",
            str(syntax_result.get("stderr") or syntax_result.get("stdout") or syntax_result.get("checked_paths")),
        )

    if proposed_target in {"feedback_adapter", "analyzer"}:
        new_functions = added_function_names(added_lines)
        unwired_functions = [
            name
            for name in new_functions
            if not added_function_has_call_site(name, added_lines)
        ]
        if unwired_functions:
            reject(
                "new_feedback_function_not_wired",
                "Feedback/analyzer patches must wire new helper functions into the extraction or analysis path in the same patch.",
                ", ".join(unwired_functions),
            )

    if "publicationinfo_uses_cpc_column" in invariant_names:
        if re.search(r"\bcpc_prefix\b", added_text):
            reject(
                "forbid_nonexistent_cpc_prefix",
                "Parent schema proves publicationinfo.cpc exists and cpc_prefix does not.",
                "Patch added cpc_prefix.",
            )
        if re.search(r"\bpublication_year\b", added_text):
            reject(
                "forbid_nonexistent_publication_year",
                "Parent schema does not expose publication_year.",
                "Patch added publication_year.",
            )

    protected_mapping = {
        "cpc_definition_parsed",
        "level5_mapping_has_coverage",
    } & invariant_names
    if protected_mapping and failure_type == "answer_set_mismatch":
        protected_tokens = [
            "copy public.cpc_definition",
            "parse_cpc_definition",
            "cpc_definition_sql",
            "cpc_hierarchy",
            "symbol -> parents",
            "parents list",
            "parents json",
            "prefix truncation",
            "string-shape",
            "metadata level",
            "level == 5",
            "level 5 mapping",
        ]
        matched = [token for token in protected_tokens if token in lowered_added]
        if matched:
            reject(
                "protect_working_cpc_parser_and_mapping",
                "Parent already parsed CPC metadata and produced high-coverage/non-empty mapping; answer_set_mismatch should not rewrite parser or mapping guidance.",
                ", ".join(matched),
            )

    if "nonempty_final_answer" in invariant_names:
        empty_answer_tokens = [
            'write("")',
            "write('')",
            "empty answer",
            "stop with an empty",
            "return an empty",
        ]
        matched = [token for token in empty_answer_tokens if token in lowered_added]
        if matched and failure_type == "answer_set_mismatch":
            reject(
                "protect_nonempty_answer_contract",
                "Parent has a non-empty answer; answer-set repair candidates should not encourage empty output.",
                ", ".join(matched),
            )

    result = {
        "status": "passed" if not findings else "failed",
        "passed": not findings,
        "patch_path": str(patch_path),
        "failure_type": failure_type,
        "repair_policy": repair_policy or {},
        "proposal_repair_target": proposed_target,
        "proposal_evidence_quality": evidence_quality,
        "touched_paths": touched_paths,
        "touched_targets": touched_targets,
        "invariant_names": sorted(invariant_names),
        "findings": findings,
    }
    write_json(candidate_path / "patch_lint_result.json", result)
    return result


def read_limited(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]..."


def set_proxy_env(proxy_url: str) -> None:
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        os.environ[key] = proxy_url
    for key in ("no_proxy", "NO_PROXY"):
        os.environ[key] = "localhost,127.0.0.1,::1"


def final_answer_line_count(run_dir: Path) -> int:
    result = load_json_if_exists(run_dir / "result.json")
    answer = result.get("final_answer") or ""
    if not answer and (run_dir / "final_answer.txt").exists():
        answer = (run_dir / "final_answer.txt").read_text(encoding="utf-8", errors="replace")
    return len([line for line in answer.splitlines() if line.strip()])


def run_passed(run_dir: Path) -> bool:
    result = load_json_if_exists(run_dir / "result.json")
    return bool(result.get("passed"))


def run_metrics(run_dir: Path | None) -> dict[str, Any]:
    if not run_dir:
        return {
            "run_dir": None,
            "passed": False,
            "execution_success": False,
            "returncode": None,
            "final_answer_lines": 0,
            "validation_reason": None,
        }

    result = load_json_if_exists(run_dir / "result.json")
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    strict_info = parse_strict_reason(str(result.get("validation_reason") or ""))
    strict_distance = None
    if strict_info.get("missing_count") is not None or strict_info.get("extra_count") is not None:
        strict_distance = (strict_info.get("missing_count") or 0) + (strict_info.get("extra_count") or 0)
    return {
        "run_dir": str(run_dir),
        "passed": bool(result.get("passed")),
        "execution_success": bool(execution.get("execution_success")),
        "returncode": execution.get("returncode"),
        "final_answer_lines": final_answer_line_count(run_dir),
        "validation_reason": result.get("validation_reason"),
        "strict_info": strict_info,
        "strict_distance": strict_distance,
    }


def answer_cardinality_exploded(parent_lines: int, child_lines: int) -> bool:
    if parent_lines <= 0 or child_lines <= 0:
        return False
    absolute_jump = child_lines - parent_lines
    ratio = child_lines / max(parent_lines, 1)
    return child_lines >= 500 and absolute_jump >= 250 and ratio >= 3.0


def strict_mismatch_materially_worse(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    parent_distance = parent.get("strict_distance")
    child_distance = child.get("strict_distance")
    if parent_distance is None or child_distance is None:
        return False
    if child_distance <= parent_distance:
        return False

    parent_strict = parent.get("strict_info") or {}
    child_strict = child.get("strict_info") or {}
    parent_missing = parent_strict.get("missing_count")
    parent_extra = parent_strict.get("extra_count")
    child_missing = child_strict.get("missing_count")
    child_extra = child_strict.get("extra_count")

    if None in {parent_missing, parent_extra, child_missing, child_extra}:
        return False

    tolerance = max(10, int(parent_distance * 0.25))
    both_sides_worse = child_missing >= parent_missing and child_extra >= parent_extra
    return both_sides_worse and child_distance > parent_distance + tolerance


def build_regression_guard(
    parent_run_dir: Path | None,
    child_run_dir: Path | None,
    comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    parent = run_metrics(parent_run_dir)
    child = run_metrics(child_run_dir)
    reasons: list[str] = []

    comparison_regressions = (
        (comparison or {})
        .get("comparison_to_parent", {})
        .get("regressed_cases", [])
    )
    if comparison_regressions:
        reasons.append("comparison_marked_regressed_cases")
    if parent["passed"] and not child["passed"]:
        reasons.append("parent_passed_child_failed")
    if parent["execution_success"] and not child["execution_success"]:
        reasons.append("child_execution_failed_after_executable_parent")
    if parent["final_answer_lines"] > 0 and child["final_answer_lines"] == 0:
        reasons.append("child_lost_nonempty_answer")
    if answer_cardinality_exploded(parent["final_answer_lines"], child["final_answer_lines"]):
        reasons.append("child_answer_cardinality_explosion")

    parent_distance = parent.get("strict_distance")
    child_distance = child.get("strict_distance")
    if (
        parent_distance is not None
        and child_distance is not None
        and child_distance > max(parent_distance * 2, parent_distance + 100)
    ):
        reasons.append("child_strict_mismatch_distance_exploded")
    if strict_mismatch_materially_worse(parent, child):
        reasons.append("child_strict_mismatch_materially_worse")

    return {
        "accepted_as_next_parent": not reasons,
        "rejected": bool(reasons),
        "reasons": reasons,
        "parent": parent,
        "child": child,
    }


def stop_condition_met(run_dir: Path, mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "pass":
        return run_passed(run_dir)
    if mode == "nonempty_answer":
        return final_answer_line_count(run_dir) > 0
    if mode == "pass_or_nonempty_answer":
        return run_passed(run_dir) or final_answer_line_count(run_dir) > 0
    raise ValueError(f"Unknown stop mode: {mode}")


def candidate_dir(candidate_id: str) -> Path:
    return BASE_DIR / "candidates" / "dab" / candidate_id


def proposal_paths(proposal: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for path in proposal.get("changed_files") or []:
        if isinstance(path, str):
            paths.append(path)
    for edit in proposal.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("path"), str):
            paths.append(edit["path"])
    return sorted(set(paths))


def build_proposal_grounding_prompt(
    candidate_path: Path,
    proposal: dict[str, Any],
    max_source_chars: int,
) -> str:
    source_sections: list[str] = []
    for rel_path in proposal_paths(proposal):
        path = BASE_DIR / rel_path
        if not path.exists() or not path.is_file():
            continue
        source_sections.append(
            "\n".join(
                [
                    f"## Current File: {rel_path}",
                    "",
                    "```text",
                    read_limited(path, max_source_chars).rstrip(),
                    "```",
                ]
            )
        )

    raw_path = candidate_path / "meta_agent_raw_output.txt"
    raw_text = read_limited(raw_path, max_source_chars) if raw_path.exists() else ""

    return "\n".join(
        [
            "You are repairing a failed coding meta-agent candidate.",
            "The previous meta-agent proposal was directionally useful but produced an empty patch or exact-find mismatch.",
            "Ground the proposal in the current source text and return a valid project patch.",
            "",
            "Hard requirements:",
            "- Prefer JSON structured edits over handwritten diffs.",
            "- Use `mode: \"append_to_file\"` when adding helper functions at the end of a file.",
            "- Use `mode: \"insert_after\"` with a short unique anchor when adding a small block after existing text.",
            "- Use `mode: \"exact_replace\"` only for short spans copied exactly from the current source.",
            "- You may output a fenced ```diff block only if structured edits are impractical.",
            "- Do not edit validators, ground truth, legacy files, old logs, .env, or llm_client.py.",
            "- Do not hard-code expected answers or validator-only missing/extra examples.",
            "- Keep the patch small and in the allowed evolution scope.",
            "",
            "Expected JSON shape if using structured edits:",
            '{"edits": [{"path": "repo/relative/path", "mode": "append_to_file", "content": "text to append"}]}',
            '{"edits": [{"path": "repo/relative/path", "mode": "insert_after", "anchor": "short exact unique anchor", "insert": "text to insert"}]}',
            '{"edits": [{"path": "repo/relative/path", "mode": "exact_replace", "find": "short exact current text", "replace": "new text"}]}',
            "",
            "# Candidate Directory",
            str(candidate_path),
            "",
            "# Parsed Proposal",
            "```json",
            json.dumps(proposal, indent=2, ensure_ascii=False),
            "```",
            "",
            "# Previous Raw Meta-Agent Output",
            "```text",
            raw_text,
            "```",
            "",
            "# Current Source Files",
            "",
            "\n\n".join(source_sections) or "No current source files were resolved from the proposal.",
        ]
    )


def ground_failed_proposal(
    candidate_path: Path,
    max_source_chars: int,
) -> dict[str, Any]:
    proposal_path = candidate_path / "proposal.json"
    patch_path = candidate_path / "patch.diff"
    if not proposal_path.exists():
        return {"status": "skipped", "reason": "proposal.json missing", "applied": False}

    proposal = load_json(proposal_path)
    prompt = build_proposal_grounding_prompt(candidate_path, proposal, max_source_chars=max_source_chars)
    prompt_path = candidate_path / "proposal_grounding_prompt.txt"
    raw_path = candidate_path / "proposal_grounding_raw_output.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    try:
        raw_text = call_meta_llm(prompt)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "reason": "proposal grounding LLM call failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "applied": False,
        }

    raw_path.write_text(raw_text, encoding="utf-8")
    grounded = extract_first_json(raw_text)
    patch = ""
    edit_results: list[dict[str, Any]] = []
    if grounded:
        edits = grounded.get("edits")
        if isinstance(edits, list):
            patch, edit_results = patch_from_structured_edits(edits, candidate_path)
    if not patch:
        patch = extract_unified_diff(raw_text)

    patch_path.write_text(patch, encoding="utf-8")
    if not patch:
        return {
            "status": "failed",
            "reason": "proposal grounding produced no patch",
            "prompt_path": str(prompt_path),
            "raw_output_path": str(raw_path),
            "edit_results": edit_results,
            "applied": False,
        }

    check = git_apply_check(patch_path)
    if not check.get("passed"):
        return {
            "status": "failed",
            "reason": "grounded patch failed git apply check",
            "prompt_path": str(prompt_path),
            "raw_output_path": str(raw_path),
            "patch_path": str(patch_path),
            "edit_results": edit_results,
            "check": check,
            "applied": False,
        }

    apply_result = apply_candidate_patch(candidate_dir=candidate_path, repo_root=BASE_DIR, dry_run=False)
    return {
        "status": "success" if apply_result.get("applied") else "failed",
        "reason": "grounded proposal patch applied" if apply_result.get("applied") else "grounded proposal patch not applied",
        "prompt_path": str(prompt_path),
        "raw_output_path": str(raw_path),
        "patch_path": str(patch_path),
        "edit_results": edit_results,
        "check": check,
        "apply_result": apply_result,
        "applied": bool(apply_result.get("applied")),
    }


def make_namespace(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def run_meta_iteration(
    iteration_dir: Path,
    parent_run_dir: Path,
    iteration_index: int,
    args: argparse.Namespace,
    interpretation: dict[str, Any],
    filtered_context_path: Path | None = None,
) -> dict[str, Any]:
    loop_id = f"{args.loop_prefix}_iter{iteration_index:03d}_meta"
    child_candidate_id = f"{args.candidate_prefix}_iter{iteration_index:03d}_child"
    notes_parts = [
        build_safe_meta_agent_notes(interpretation),
    ]
    if args.notes:
        notes_parts.append(args.notes)
    notes = "\n\n".join(part for part in notes_parts if part)

    loop_args = make_namespace(
        case_dir=[],
        cases=[],
        parent_run_dir=[str(parent_run_dir)],
        child_run_dir=[],
        prompt=str(Path(args.prompt).resolve()),
        version=args.version_prefix,
        dab_root=str(Path(args.dab_root).resolve()),
        timeout_sec=args.timeout_sec,
        max_cases=None,
        output_dir=str(args.output_dir),
        loop_id=loop_id,
        parent_candidate_id=args.parent_candidate_id,
        child_candidate_id=child_candidate_id,
        notes=notes,
        auto_meta_agent=True,
        meta_agent_dry_run=args.meta_agent_dry_run,
        apply_meta_agent_patch=True,
        apply_patch_dry_run=False,
        meta_agent_response_schema=str(Path(args.meta_agent_response_schema).resolve()),
        meta_agent_max_source_chars=args.meta_agent_max_source_chars,
        meta_agent_max_total_source_chars=args.meta_agent_max_total_source_chars,
        meta_agent_patch_repair_attempts=args.meta_agent_patch_repair_attempts,
        filtered_analyzer_refs=[str(filtered_context_path)] if filtered_context_path else [],
        dry_run=False,
    )
    state = run_loop(loop_args)
    state["child_candidate_id"] = child_candidate_id
    state["iteration_dir"] = str(iteration_dir)
    return state


def build_safe_meta_agent_notes(interpretation: dict[str, Any]) -> str:
    repair_policy = interpretation.get("repair_policy") or {}
    policy_lines = []
    if repair_policy:
        policy_lines = [
            f"Deterministic repair policy preferred targets: {repair_policy.get('preferred_repair_targets')}.",
            f"Deterministic repair policy allowed targets: {repair_policy.get('allowed_repair_targets')}.",
            f"Deterministic repair policy disallowed targets: {repair_policy.get('disallowed_repair_targets')}.",
            f"Policy reason: {repair_policy.get('reason')}.",
        ]
    return "\n".join(
        [
            "Use the filtered analyzer context as authoritative.",
            *policy_lines,
            "The strict validator expected/got counts are diagnostic evidence only.",
            "Do not infer a top-K, first-K, exact-K, threshold, or hard cap from validator-only counts unless the original natural-language task explicitly states that cardinality.",
            "For answer_set_mismatch with preserved parser/schema/mapping invariants, target semantic counting, per-patent deduplication, EMA year-grid/initialization, best-year selection, final filtering, or additional runtime signals.",
            "Do not modify schema assumptions, CPC definition parsing, level-5 mapping fallback, parent-chain traversal, runtime observer API, or final answer serialization.",
            "Do not add runtime-observer APIs or feedback helpers as standalone future prerequisites; the same patch must wire the signal into generated code via prompt/runner changes or into the analyzer/context path.",
            "Do not introduce cpc_prefix or publication_year columns.",
        ]
    )


def build_repair_policy(
    parent_run_dir: Path,
    parent_analysis: dict[str, Any],
    interpretation: dict[str, Any],
    prior_records: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = run_metrics(parent_run_dir)
    reason = str(metrics.get("validation_reason") or "")
    strict = metrics.get("strict_info") or {}
    got = strict.get("got_unique")
    expected = strict.get("expected_unique")
    final_lines = metrics.get("final_answer_lines") or 0
    localized_errors = parent_analysis.get("localized_errors") or []
    error_keys = {
        f"{item.get('stage')}.{item.get('type')}"
        for item in localized_errors
        if isinstance(item, dict)
    }
    regression_reasons = {
        reason
        for record in prior_records
        for reason in ((record.get("regression_guard") or {}).get("reasons") or [])
    }
    prompt_patch_count = 0
    for record in prior_records:
        loop_state = record.get("loop_state") or {}
        child_id = loop_state.get("child_candidate_id")
        if not child_id:
            continue
        patch_text = (candidate_dir(child_id) / "patch.diff").read_text(encoding="utf-8", errors="replace") if (candidate_dir(child_id) / "patch.diff").exists() else ""
        if any(target_for_path(path) == "object_prompt" for path in touched_paths_from_patch_text(patch_text)):
            prompt_patch_count += 1

    base = {
        "metrics": metrics,
        "reason": "",
        "preferred_repair_targets": ["object_prompt", "feedback_adapter", "analyzer"],
        "allowed_repair_targets": [
            "object_prompt",
            "runner",
            "analyzer",
            "feedback_adapter",
            "task_packaging",
            "loop_guard",
            "meta_agent_policy",
        ],
        "disallowed_repair_targets": [],
        "evidence_quality": "sufficient",
    }

    if reason.startswith("generated_code_schema_lint_failed:"):
        base.update(
            {
                "reason": "Generated code failed pre-execution schema lint; repair feedback/runner/analyzer before prompt semantics.",
                "preferred_repair_targets": ["runner", "analyzer", "feedback_adapter"],
                "allowed_repair_targets": ["runner", "analyzer", "feedback_adapter", "task_packaging"],
                "disallowed_repair_targets": ["object_prompt"],
                "evidence_quality": "sufficient",
            }
        )
        return base

    if final_lines == 0 or "missing_final_answer_file_or_empty_answer" in reason:
        base.update(
            {
                "reason": "Current parent has empty answer or lost answer contract; repair guard/feedback before further prompt mutation.",
                "preferred_repair_targets": ["loop_guard", "analyzer", "feedback_adapter"],
                "allowed_repair_targets": ["loop_guard", "analyzer", "feedback_adapter", "task_packaging"],
                "disallowed_repair_targets": ["object_prompt"],
                "evidence_quality": "coarse",
            }
        )
        return base

    if got and expected and got > max(expected * 5, expected + 500):
        base.update(
            {
                "reason": "Current parent has answer cardinality explosion; first repair loop acceptance/feedback classification so explosive children cannot become parents.",
                "preferred_repair_targets": ["loop_guard", "analyzer", "feedback_adapter"],
                "allowed_repair_targets": ["loop_guard", "analyzer", "feedback_adapter", "task_packaging", "meta_agent_policy"],
                "disallowed_repair_targets": ["object_prompt"],
                "evidence_quality": "sufficient",
            }
        )
        return base

    if (
        "child_answer_cardinality_explosion" in regression_reasons
        or "child_strict_mismatch_distance_exploded" in regression_reasons
    ):
        base.update(
            {
                "reason": "A prior child showed cardinality explosion; strengthen regression guard before continuing prompt-level search.",
                "preferred_repair_targets": ["loop_guard", "analyzer"],
                "allowed_repair_targets": ["loop_guard", "analyzer", "feedback_adapter", "task_packaging"],
                "disallowed_repair_targets": ["object_prompt"],
                "evidence_quality": "sufficient",
            }
        )
        return base

    if prompt_patch_count >= 2 and not metrics.get("passed"):
        base.update(
            {
                "reason": "Multiple prompt patches have not solved the case; prefer project-level feedback or policy repair.",
                "preferred_repair_targets": ["analyzer", "feedback_adapter", "loop_guard", "meta_agent_policy"],
                "allowed_repair_targets": ["analyzer", "feedback_adapter", "loop_guard", "meta_agent_policy", "task_packaging"],
                "disallowed_repair_targets": ["object_prompt"],
                "evidence_quality": "contradictory",
            }
        )
        return base

    if any("schema_grounding" in key or "granularity_mapping" in key for key in error_keys):
        base.update(
            {
                "reason": "Analyzer still reports schema/granularity evidence alongside answer mismatch; prompt edits are allowed only if feedback sufficiency is explicit.",
                "preferred_repair_targets": ["analyzer", "feedback_adapter", "object_prompt"],
                "evidence_quality": "contradictory",
            }
        )
        return base

    base["reason"] = "Failure is localized enough to allow a bounded prompt or feedback repair."
    return base


def write_filtered_meta_agent_context(
    iteration_dir: Path,
    parent_run_dir: Path,
    parent_analysis: dict[str, Any],
    interpretation: dict[str, Any],
    repair_policy: dict[str, Any],
) -> Path:
    strict_info = parent_analysis.get("strict_info") or {}
    top_problem = {
        "stage": "answer_synthesis",
        "type": "output_set_mismatch",
        "subtype": "missing_and_extra_items",
        "confidence": "high",
        "evidence": (
            f"Strict match expected {strict_info.get('expected_unique')} unique items "
            f"and got {strict_info.get('got_unique')}."
        ),
        "target_modules": ["answer_synthesis", "final_answer_filtering", "counting_semantics"],
    }
    context = {
        "role": "filtered_meta_agent_failure_context",
        "run_dir": str(parent_run_dir),
        "failure_type": interpretation.get("failure_type"),
        "priority": interpretation.get("priority"),
        "instruction": (
            "Use this filtered context as the authoritative analyzer signal for the meta-agent. "
            "Do not revive suppressed localized errors from raw agent_error_summary.json, stage_trace.json, "
            "or generated_solve.py when they contradict preserved invariants."
        ),
        "allowed_evidence": interpretation.get("evidence") or [],
        "top_problem_candidates": [top_problem],
        "preserved_invariants": interpretation.get("preserved_invariants") or parent_analysis.get("preserved_invariants") or [],
        "suppressed_evidence": interpretation.get("suppressed_evidence") or [],
        "repair_policy": repair_policy,
        "recommended_change": (
            "Refine answer-synthesis semantics or add runtime signals for count/EMA diagnosis. "
            "Do not add a hard top-K/count cap unless the natural-language task explicitly contains that K."
        ),
        "meta_agent_notes": build_safe_meta_agent_notes(interpretation),
        "discarded_llm_recommendation": {
            "recommended_change": interpretation.get("recommended_change"),
            "meta_agent_notes": interpretation.get("meta_agent_notes"),
            "reason": "LLM interpretation may convert validator-only counts into answer rules; keep it as audit text only.",
        },
        "allowed_repair_targets": repair_policy.get("allowed_repair_targets", []),
        "preferred_repair_targets": repair_policy.get("preferred_repair_targets", []),
        "disallowed_repair_targets": repair_policy.get("disallowed_repair_targets", []),
        "semantic_repair_areas": [
            "counting semantics",
            "per-patent deduplication",
            "first or inventive CPC semantics",
            "EMA year grid and initialization",
            "best-year selection",
            "final answer filtering",
            "additional runtime signals for count/EMA diagnosis",
        ],
        "forbidden_repair_targets": [
            "CPC definition SQL parser",
            "publicationinfo schema assumptions",
            "CPC level-5 metadata mapping",
            "prefix fallback or parent-chain traversal behavior",
            "final answer serialization contract",
            "validator answers, expected counts, or missing/extra examples as rules",
        ],
    }
    path = iteration_dir / "filtered_meta_agent_context.json"
    write_json(path, context)
    return path


def patch_applied(loop_state: dict[str, Any]) -> bool:
    apply_result = loop_state.get("apply_patch_result") or {}
    return bool(apply_result.get("applied"))


def run_child(
    case_dir: Path,
    prompt_path: Path,
    dab_root: Path,
    timeout_sec: int,
    version: str,
) -> dict[str, Any]:
    return run_dab_agent(
        case_dir=case_dir,
        prompt_path=prompt_path,
        version=version,
        dab_root=dab_root,
        timeout_sec=timeout_sec,
    )


def summarize_iteration_record(record: dict[str, Any]) -> dict[str, Any]:
    child_run_dir = Path(record["child_run_dir"]) if record.get("child_run_dir") else None
    parent_run_dir = Path(record["parent_run_dir"]) if record.get("parent_run_dir") else None
    regression_guard = record.get("regression_guard") or {}
    patch_lint = record.get("patch_lint_result") or {}
    repair_policy = (record.get("interpretation") or {}).get("repair_policy") or {}
    return {
        "iteration": record.get("iteration"),
        "parent_run_dir": str(parent_run_dir) if parent_run_dir else None,
        "child_run_dir": str(child_run_dir) if child_run_dir else None,
        "failure_type": (record.get("interpretation") or {}).get("failure_type"),
        "repair_policy_preferred_targets": repair_policy.get("preferred_repair_targets"),
        "repair_policy_allowed_targets": repair_policy.get("allowed_repair_targets"),
        "repair_policy_reason": repair_policy.get("reason"),
        "patch_applied": record.get("patch_applied"),
        "patch_lint_status": patch_lint.get("status"),
        "patch_lint_findings": patch_lint.get("findings", []),
        "proposal_repair_target": patch_lint.get("proposal_repair_target"),
        "child_passed": run_passed(child_run_dir) if child_run_dir else None,
        "child_final_answer_lines": final_answer_line_count(child_run_dir) if child_run_dir else None,
        "child_accepted_as_next_parent": regression_guard.get("accepted_as_next_parent"),
        "regression_reasons": regression_guard.get("reasons", []),
        "comparison_summary_path": record.get("comparison_summary_path"),
    }


def run_autonomous_loop(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now_iso()
    if args.qwen_proxy:
        set_proxy_env(args.qwen_proxy)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    history_path = output_dir / "iteration_history.json"
    prompt_path = Path(args.prompt).resolve()
    dab_root = Path(args.dab_root).resolve()
    case_dir = Path(args.case_dir).resolve() if args.case_dir else None
    parent_run_dir = Path(args.parent_run_dir).resolve() if args.parent_run_dir else None

    operations: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    if not parent_run_dir:
        if not case_dir:
            raise ValueError("Provide either --parent-run-dir or --case-dir.")
        parent_version = f"{args.version_prefix}_parent"
        terminal_step(f"running_parent_data_agent version={parent_version}")
        parent_result = run_child(
            case_dir=case_dir,
            prompt_path=prompt_path,
            dab_root=dab_root,
            timeout_sec=args.timeout_sec,
            version=parent_version,
        )
        parent_run_dir = Path(parent_result["run_dir"]).resolve()
        operations.append(
            {
                "name": "run_initial_parent",
                "status": "completed",
                "outputs": {"parent_run_dir": str(parent_run_dir)},
            }
        )
    elif not case_dir:
        result = load_json_if_exists(parent_run_dir / "result.json")
        case_dir_text = result.get("case_dir")
        if not case_dir_text:
            raise ValueError("Existing parent run does not contain case_dir; pass --case-dir explicitly.")
        case_dir = Path(case_dir_text).resolve()

    stop_reason = None
    for iteration in range(1, args.iterations + 1):
        iteration_dir = output_dir / f"iter_{iteration:03d}"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        terminal_step(f"iteration={iteration} analyzing_parent")
        parent_analysis = analyze_run(parent_run_dir)
        terminal_step(f"iteration={iteration} interpreting_failure")
        interpretation = interpret_failure(
            run_dir=parent_run_dir,
            output_dir=iteration_dir / "failure_interpretation",
            use_llm=not args.no_interpreter_llm,
            extra_notes=args.notes,
        )
        repair_policy = build_repair_policy(
            parent_run_dir=parent_run_dir,
            parent_analysis=parent_analysis,
            interpretation=interpretation,
            prior_records=records,
        )
        interpretation["repair_policy"] = repair_policy
        filtered_context_path = write_filtered_meta_agent_context(
            iteration_dir=iteration_dir,
            parent_run_dir=parent_run_dir,
            parent_analysis=parent_analysis,
            interpretation=interpretation,
            repair_policy=repair_policy,
        )

        if stop_condition_met(parent_run_dir, args.stop_condition):
            stop_reason = f"parent_run_met_stop_condition:{args.stop_condition}"
            terminal_step(f"iteration={iteration} stop={stop_reason}")
            records.append(
                {
                    "iteration": iteration,
                    "parent_run_dir": str(parent_run_dir),
                    "interpretation": interpretation,
                    "stopped_before_meta": True,
                    "stop_reason": stop_reason,
                }
            )
            break

        terminal_step(f"iteration={iteration} calling_meta_agent")
        loop_state = run_meta_iteration(
            iteration_dir,
            parent_run_dir,
            iteration,
            args,
            interpretation,
            filtered_context_path=filtered_context_path,
        )
        child_candidate_id = loop_state["child_candidate_id"]
        child_candidate_path = candidate_dir(child_candidate_id)
        applied = patch_applied(loop_state)
        grounding_result: dict[str, Any] | None = None
        patch_lint_result: dict[str, Any] | None = None

        if not applied and args.repair_failed_patch and not args.meta_agent_dry_run:
            terminal_step(f"iteration={iteration} grounding_failed_patch")
            grounding_result = ground_failed_proposal(
                candidate_path=child_candidate_path,
                max_source_chars=args.patch_grounding_max_source_chars,
            )
            applied = bool(grounding_result.get("applied"))

        if applied and args.patch_lint:
            terminal_step(f"iteration={iteration} linting_patch")
            patch_lint_result = lint_candidate_patch(
                candidate_path=child_candidate_path,
                parent_analysis=parent_analysis,
                interpretation=interpretation,
                repair_policy=repair_policy,
            )
            if not patch_lint_result.get("passed"):
                patch_lint_result["rollback_result"] = reverse_candidate_patch(child_candidate_path)
                applied = False
                stop_reason = f"patch_lint_rejected:iter_{iteration:03d}"
                terminal_step(f"iteration={iteration} patch_lint_rejected")

        child_run_dir: Path | None = None
        child_result: dict[str, Any] | None = None
        comparison_summary_path: str | None = None
        comparison: dict[str, Any] | None = None
        regression_guard: dict[str, Any] | None = None
        scores_path: str | None = None
        if applied:
            child_version = f"{args.version_prefix}_iter{iteration:03d}_child"
            terminal_step(f"iteration={iteration} running_child_data_agent version={child_version}")
            child_result = run_child(
                case_dir=case_dir,
                prompt_path=prompt_path,
                dab_root=dab_root,
                timeout_sec=args.timeout_sec,
                version=child_version,
            )
            child_run_dir = Path(child_result["run_dir"]).resolve()
            terminal_step(f"iteration={iteration} analyzing_child")
            analyze_run(child_run_dir)

            terminal_step(f"iteration={iteration} comparing_parent_child")
            comparison = compare_parent_child_runs([parent_run_dir], [child_run_dir])
            regression_guard = build_regression_guard(parent_run_dir, child_run_dir, comparison)
            comparison["regression_guard"] = regression_guard
            comparison_path = iteration_dir / "comparison_summary.json"
            scores = child_candidate_path / "scores.json"
            write_json(comparison_path, comparison)
            write_json(scores, comparison)
            comparison_summary_path = str(comparison_path)
            scores_path = str(scores)
        else:
            if not stop_reason:
                stop_reason = f"patch_not_applied:iter_{iteration:03d}"
            terminal_step(f"iteration={iteration} stop={stop_reason}")

        record = {
            "iteration": iteration,
            "parent_run_dir": str(parent_run_dir),
            "interpretation": interpretation,
            "loop_state": loop_state,
            "patch_applied": applied,
            "patch_lint_result": patch_lint_result,
            "proposal_grounding_result": grounding_result,
            "child_run_dir": str(child_run_dir) if child_run_dir else None,
            "child_result": child_result,
            "regression_guard": regression_guard,
            "comparison_summary_path": comparison_summary_path,
            "scores_path": scores_path,
        }
        records.append(record)
        write_json(history_path, {"records": records, "summary": [summarize_iteration_record(item) for item in records]})

        if child_run_dir and stop_condition_met(child_run_dir, args.stop_condition):
            stop_reason = f"child_run_met_stop_condition:{args.stop_condition}"
            terminal_step(f"iteration={iteration} stop={stop_reason}")
            break
        if not applied:
            break
        if child_run_dir:
            if regression_guard and regression_guard.get("rejected") and not args.allow_regression_parent:
                stop_reason = f"child_regression_guard:iter_{iteration:03d}"
                terminal_step(f"iteration={iteration} stop={stop_reason}")
                break
            parent_run_dir = child_run_dir

    summary = [summarize_iteration_record(item) for item in records]
    state = {
        "status": "completed" if stop_reason else "iteration_budget_exhausted",
        "stop_reason": stop_reason,
        "output_dir": str(output_dir),
        "iteration_history_path": str(history_path),
        "summary": summary,
        "proxy_enabled": bool(args.qwen_proxy),
        "llm_config": describe_llm_config(),
    }
    write_json(output_dir / "auto_loop_state.json", state)

    report_path, _ = write_script_run_report(
        output_dir=output_dir,
        script_name="experiments/run_autonomous_meta_agent_loop.py",
        script_role="autonomous_meta_agent_orchestrator",
        started_at=started_at,
        status=state["status"],
        inputs=[
            path_ref("case_dir", case_dir) if case_dir else {"name": "case_dir", "path": None, "exists": False},
            path_ref("parent_run_dir", parent_run_dir) if parent_run_dir else {"name": "parent_run_dir", "path": None, "exists": False},
            path_ref("prompt", prompt_path),
            path_ref("dab_root", dab_root),
        ],
        operations=operations
        + [
            {
                "name": "run_autonomous_iterations",
                "status": "completed",
                "outputs": {
                    "iteration_count": len(records),
                    "stop_reason": stop_reason,
                    "history_path": str(history_path),
                },
            }
        ],
        outputs=[
            path_ref("auto_loop_state", output_dir / "auto_loop_state.json"),
            path_ref("iteration_history", history_path),
        ],
        checks=[
            {"name": "has_iterations", "passed": bool(records), "message": str(history_path)},
            {
                "name": "stop_condition_or_budget",
                "passed": bool(stop_reason) or len(records) == args.iterations,
                "message": stop_reason or "iteration budget exhausted",
            },
        ],
        self_feedback={
            "confidence": "medium",
            "uncertainties": [
                "Patch grounding uses an LLM when the coding meta-agent produces a proposal but no usable patch."
            ],
            "evolution_hints": [
                "Inspect iteration_history.json for failure interpretation, applied patch status, child results, and comparison summaries.",
                "Use --stop-condition pass for correctness-seeking runs, or nonempty_answer for smoke-loop validation.",
                "The regression guard rejects a child as next parent when it loses execution success or a non-empty answer.",
            ],
            "suggested_target_modules": [
                "experiments/interpret_failure.py",
                "experiments/run_autonomous_meta_agent_loop.py",
                "experiments/call_meta_agent.py",
            ],
        },
        report_stem="run_autonomous_meta_agent_loop",
    )
    state["script_run_report_path"] = str(report_path)
    write_json(output_dir / "auto_loop_state.json", state)
    terminal_step(f"completed status={state['status']} stop_reason={state.get('stop_reason')} output_dir={output_dir}")
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir")
    parser.add_argument("--parent-run-dir")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--version-prefix", default="v005_auto_meta")
    parser.add_argument("--loop-prefix", default="auto_meta")
    parser.add_argument("--candidate-prefix", default="auto_meta")
    parser.add_argument("--parent-candidate-id", default="iter_000_parent")
    parser.add_argument("--dab-root", default=str(Path.home() / "research" / "DataAgentBench"))
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--notes")
    parser.add_argument(
        "--stop-condition",
        choices=["pass", "nonempty_answer", "pass_or_nonempty_answer", "never"],
        default="pass",
    )
    parser.add_argument("--no-interpreter-llm", action="store_true")
    parser.add_argument("--meta-agent-dry-run", action="store_true")
    parser.add_argument("--meta-agent-response-schema", default=str(DEFAULT_META_AGENT_RESPONSE_SCHEMA))
    parser.add_argument("--meta-agent-max-source-chars", type=int, default=24000)
    parser.add_argument("--meta-agent-max-total-source-chars", type=int, default=100000)
    parser.add_argument("--meta-agent-patch-repair-attempts", type=int, default=1)
    parser.add_argument("--repair-failed-patch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--patch-lint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reject and reverse candidate patches that violate preserved parent invariants before running a child.",
    )
    parser.add_argument("--patch-grounding-max-source-chars", type=int, default=24000)
    parser.add_argument(
        "--allow-regression-parent",
        action="store_true",
        help="Allow an obviously regressed child run to become the next parent. By default, the loop stops instead.",
    )
    parser.add_argument(
        "--qwen-proxy",
        nargs="?",
        const=DEFAULT_PROXY,
        default=None,
        help="Set the WSL proxy environment before Qwen/DashScope calls. Optional value defaults to the known local proxy.",
    )
    args = parser.parse_args()

    state = run_autonomous_loop(args)
    if CONCISE_TERMINAL:
        print(f"[loop] summary={state['output_dir']}/auto_loop_state.json")
        print(f"[loop] history={state['iteration_history_path']}")
    else:
        print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
