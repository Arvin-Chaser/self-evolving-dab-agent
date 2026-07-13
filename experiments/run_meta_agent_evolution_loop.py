#!/usr/bin/env python3
"""Run the high-level meta-agent evolution loop.

This is the loop orchestrator, not a single candidate launcher.

Responsibilities:

1. Select a parent agent checkpoint from archive.
2. Run or reuse a parent data-agent case.
3. Analyze the parent run and extract a repair seed.
4. Invoke a candidate launcher to let the meta-agent propose/apply a repair.
5. Optionally run a generic child data-agent eval in an isolated workspace.
6. Postprocess the candidate into state/review/seed/archive artifacts.
7. Select the next parent candidate for the following iteration.

Human merge approval remains outside this script.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.analyze_agent_error import analyze_run
from experiments.archive_selector import select_from_archive
from experiments.build_meta_agent_evidence_pack import build_fine_grained_feedback_pack, write_pack
from experiments.extract_primary_signal import extract_primary_signal
from experiments.helper_repair_planner import plan_helper_repair
from experiments.open_diagnosis import build_open_diagnosis_evidence, compact_open_diagnosis_evidence
from experiments.run_dab_agent import run_dab_agent


DEFAULT_ARCHIVE = ROOT / "archive"
DEFAULT_CASE_DIR = Path("/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1")
DEFAULT_DAB_ROOT = Path("/home/m0st1ma/research/DataAgentBench")
DATA_AGENT_CANONICAL_PROMPT = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")
DAB_TOOL_AGENT_CANONICAL_POLICY = Path("prompts/dab/dab_tool_agent_policy_zero_start.txt")


def utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_patents_helper_modules(candidate_dir: Path) -> list[dict[str, str]]:
    modules: list[dict[str, str]] = []
    numstat = candidate_dir / "patch_numstat.txt"
    if not numstat.exists():
        return modules
    for line in numstat.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("	", 2)
        if len(parts) != 3:
            continue
        rel = parts[2].strip()
        if rel.startswith("adapters/patents/") and rel.endswith(".py"):
            stem = Path(rel).stem
            modules.append({"path": rel, "module": f"adapters.patents.{stem}", "stem": stem})
    return modules


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        value = node.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
            return ".".join(reversed(parts))
    return None


def _ast_name_refs(node: ast.AST) -> set[str]:
    refs: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            refs.add(child.id)
    return refs


def _target_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names |= _target_names(elt)
    elif isinstance(target, ast.Attribute):
        full = _call_name(target)
        if full:
            names.add(full)
    return names


def _expr_has_helper_call(node: ast.AST, helper_call_names: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            call = _call_name(child.func)
            if call and (call in helper_call_names or any(call.endswith(f".{name}") for name in helper_call_names)):
                return True
    return False


def _helper_output_final_answer_dependency(tree: ast.AST, details: list[dict[str, Any]]) -> dict[str, Any]:
    helper_call_names: set[str] = set()
    action_required = False
    for detail in details:
        module = str(detail.get("module") or "")
        stem = module.rsplit(".", 1)[-1]
        called_names = {str(name) for name in detail.get("called_names") or []}
        helper_call_names |= called_names
        if stem in {"candidate_filtering", "answer_diagnostics"}:
            action_required = True
        if any("rank_or_filter" in name or "summarize_candidate" in name for name in called_names):
            action_required = True
    if not action_required:
        return {"required": False, "status": "not_required"}
    if not helper_call_names:
        return {"required": True, "status": "helper_not_called"}

    tainted: set[str] = set()
    assignment_events: list[dict[str, Any]] = []
    # Small fixed-point pass: helper output may be assigned to summary, then
    # selected_symbols/result_codes/final_answer_lines in a later statement.
    for _ in range(5):
        changed = False
        for node in ast.walk(tree):
            targets: set[str] = set()
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                for target in node.targets:
                    targets |= _target_names(target)
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                targets |= _target_names(node.target)
            elif isinstance(node, ast.AugAssign):
                value = node.value
                targets |= _target_names(node.target)
            if value is None or not targets:
                continue
            if _expr_has_helper_call(value, helper_call_names) or bool(_ast_name_refs(value) & tainted):
                new_targets = targets - tainted
                if new_targets:
                    tainted |= new_targets
                    changed = True
                    assignment_events.append({"targets": sorted(targets), "line": getattr(node, "lineno", None)})
        if not changed:
            break

    final_sinks: list[dict[str, Any]] = []
    log_sinks: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = _call_name(node.func) or ""
        arg_refs: set[str] = set()
        for arg in list(node.args) + [kw.value for kw in node.keywords if kw.value is not None]:
            arg_refs |= _ast_name_refs(arg)
        helper_in_args = _expr_has_helper_call(node, helper_call_names) or bool(arg_refs & tainted)
        if call.endswith("log_event") and helper_in_args:
            log_sinks.append({"call": call, "line": getattr(node, "lineno", None), "tainted_refs": sorted(arg_refs & tainted)})
        is_write_text = call.endswith(".write_text")
        receiver = _call_name(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        receiver_low = (receiver or "").lower()
        call_low = call.lower()
        final_receiver = "final_answer" in receiver_low or "final_answer" in call_low or receiver == "FINAL_ANSWER_PATH"
        if is_write_text and final_receiver and helper_in_args:
            final_sinks.append({"call": call, "line": getattr(node, "lineno", None), "tainted_refs": sorted(arg_refs & tainted)})

    status = "helper_output_used_for_final_answer" if final_sinks else "helper_called_but_output_not_used_for_final_answer"
    return {
        "required": True,
        "status": status,
        "helper_call_names": sorted(helper_call_names),
        "tainted_vars": sorted(tainted),
        "assignment_events": assignment_events[:20],
        "final_answer_sinks": final_sinks,
        "log_sinks": log_sinks[:20],
    }


def generated_code_uses_helper(generated_code_path: Path, helpers: list[dict[str, str]]) -> dict[str, Any]:
    """Check whether generated_solve.py actually calls changed helper APIs.

    Older logic treated an import as usage.  That created false positives for
    patches that only added prompt glue/imports but did not change the decision
    path.  This checker records imports separately and requires an AST call to a
    helper function/module attribute before marking the helper as used.
    """
    if not helpers:
        return {"required": False, "status": "not_required", "helpers": []}
    code = generated_code_path.read_text(encoding="utf-8", errors="replace") if generated_code_path.exists() else ""
    code_low = code.lower()
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "required": True,
            "status": "helper_usage_parse_failed",
            "helpers": helpers,
            "observed_modules": [],
            "called_modules": [],
            "missing_modules": [helper["module"] for helper in helpers],
            "parse_error": str(exc),
            "generated_solve_path": str(generated_code_path),
        }

    imports_by_module: dict[str, set[str]] = {}
    module_aliases: dict[str, set[str]] = {}
    calls = {name for name in (_call_name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)) if name}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported = imports_by_module.setdefault(node.module.lower(), set())
            for alias in node.names:
                local = alias.asname or alias.name
                imported.add(local)
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                module_aliases.setdefault(alias.name.lower(), set()).add(local)

    observed: list[str] = []
    called: list[str] = []
    missing: list[str] = []
    details: list[dict[str, Any]] = []
    for helper in helpers:
        module = helper["module"]
        module_low = module.lower()
        stem = helper["stem"]
        import_locals = set(imports_by_module.get(module_low, set()))
        import_locals |= set(imports_by_module.get("adapters.patents", set()) & {stem})
        import_locals |= set(module_aliases.get(module_low, set()))
        import_seen = bool(import_locals) or module_low in code_low or f"import adapters.patents.{stem}" in code_low

        call_seen = False
        called_names: list[str] = []
        # from adapters.patents.foo import bar -> bar(...)
        for local in import_locals:
            if local == "*":
                continue
            if local in calls:
                call_seen = True
                called_names.append(local)
            for call in calls:
                if call.startswith(f"{local}."):
                    call_seen = True
                    called_names.append(call)
        # import adapters.patents.foo / import foo -> module.function(...)
        module_tail = module.split(".")[-1]
        for call in calls:
            if call.startswith(f"{module}.") or call.startswith(f"{module_tail}.") or call.startswith(f"{stem}."):
                call_seen = True
                called_names.append(call)

        if import_seen:
            observed.append(module)
        if call_seen:
            called.append(module)
        else:
            missing.append(module)
        details.append(
            {
                "module": module,
                "import_seen": import_seen,
                "call_seen": call_seen,
                "imported_names_or_aliases": sorted(import_locals),
                "called_names": sorted(set(called_names)),
            }
        )

    if called:
        status = "helper_called_by_child_generated_code"
    elif observed:
        status = "helper_imported_but_not_called_by_child_generated_code"
    else:
        status = "helper_not_used_by_child_generated_code"
    final_answer_dependency = _helper_output_final_answer_dependency(tree, details)
    return {
        "required": True,
        "status": status,
        "helpers": helpers,
        "observed_modules": observed,
        "called_modules": called,
        "missing_modules": missing,
        "details": details,
        "final_answer_dependency": final_answer_dependency,
        "generated_solve_path": str(generated_code_path),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def upsert_jsonl(path: Path, key: str, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(path)
    replaced = False
    for idx, existing in enumerate(rows):
        if existing.get(key) == row.get(key):
            rows[idx] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    with path.open("w", encoding="utf-8") as handle:
        for item in rows:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def answer_quality_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key in (
        "available",
        "metric_type",
        "strict_match_passed",
        "expected_count",
        "predicted_count",
        "true_positive_count",
        "missing_count",
        "extra_count",
        "precision",
        "recall",
        "f1",
    ):
        if key in value:
            out[key] = value.get(key)
    if "true_positive_count" not in out and "true_positive" in value:
        out["true_positive_count"] = value.get("true_positive")
    if "missing_count" not in out and "false_negative" in value:
        out["missing_count"] = value.get("false_negative")
    if "extra_count" not in out and "false_positive" in value:
        out["extra_count"] = value.get("false_positive")
    for key in ("missing_codes_sample", "extra_codes_sample", "predicted_codes_sample"):
        sample = value.get(key)
        if isinstance(sample, list):
            out[key] = sample[:12]
    reason = value.get("strict_match_reason")
    if isinstance(reason, str) and reason:
        out["strict_match_reason_excerpt"] = reason[:500]
    return out


def first_answer_quality_from_report(report: dict[str, Any], *, role: str) -> dict[str, Any]:
    keys = (
        ("child_answer_quality", "child_answer_metrics", "answer_quality")
        if role == "child"
        else ("parent_answer_quality", "parent_answer_metrics")
    )
    for key in keys:
        value = report.get(key)
        if isinstance(value, dict) and value:
            return value
    child_status = report.get("child_status") if isinstance(report.get("child_status"), dict) else {}
    if role == "child" and isinstance(child_status.get("answer_quality"), dict):
        return child_status["answer_quality"]
    return {}


def compact_helper_usage(report: dict[str, Any]) -> dict[str, Any]:
    helper = report.get("helper_usage") if isinstance(report.get("helper_usage"), dict) else {}
    child_status = report.get("child_status") if isinstance(report.get("child_status"), dict) else {}
    if not helper and isinstance(child_status.get("helper_usage_summary"), dict):
        helper = child_status["helper_usage_summary"]
    if not helper:
        return {}
    return {
        "helper_tool_enabled": helper.get("helper_tool_enabled"),
        "helper_tool_called": helper.get("helper_tool_called"),
        "helper_call_count": helper.get("helper_call_count"),
        "registered_helper_names": helper.get("registered_helper_names"),
        "return_answer_after_helper": helper.get("return_answer_after_helper"),
        "status": helper.get("status"),
        "final_answer_dependency_status": helper.get("final_answer_dependency_status"),
    }


def f1_from_quality(value: dict[str, Any]) -> float | None:
    try:
        if value.get("f1") is None:
            return None
        return float(value.get("f1"))
    except Exception:
        return None


def build_iteration_handoff(
    *,
    archive_root: Path,
    loop_dir: Path,
    iteration_dir: Path,
    iteration: int,
    candidate_dir: Path,
    candidate_id: str,
    parent_agent_id: str,
    meta_agent_id: str | None,
    parent_run: Path,
    seed_path: Path,
    launcher_exit: int | None,
    child_eval: dict[str, Any] | None,
    postprocess_exit: int | None,
) -> dict[str, Any]:
    manifest = safe_load_json(candidate_dir / "manifest.json")
    state = safe_load_json(candidate_dir / "candidate_state.json")
    report = child_eval if isinstance(child_eval, dict) else safe_load_json(candidate_dir / "child_eval/child_eval_report.json")
    patch_numstat = (candidate_dir / "patch_numstat.txt").read_text(encoding="utf-8", errors="replace") if (candidate_dir / "patch_numstat.txt").exists() else ""
    child_quality_raw = first_answer_quality_from_report(report, role="child")
    parent_quality_raw = first_answer_quality_from_report(report, role="parent")
    child_quality = answer_quality_summary(child_quality_raw)
    parent_quality = answer_quality_summary(parent_quality_raw)
    child_f1 = f1_from_quality(child_quality_raw)
    parent_f1 = f1_from_quality(parent_quality_raw)
    delta_f1 = round(child_f1 - parent_f1, 6) if child_f1 is not None and parent_f1 is not None else None
    evolution = state.get("evolution_assessment") if isinstance(state.get("evolution_assessment"), dict) else {}
    child_status = report.get("child_status") if isinstance(report.get("child_status"), dict) else {}
    child_failure_gates = report.get("child_failure_gates") if isinstance(report.get("child_failure_gates"), list) else []
    selected_stage = child_status.get("selected_stage") or report.get("child_selected_stage") or manifest.get("selected_stage")
    selected_signal = child_status.get("selected_signal") or report.get("child_selected_signal") or manifest.get("selected_signal")
    if evolution.get("evolution_parent_eligible"):
        handoff_role = "candidate_can_seed_parent_selection"
    elif delta_f1 is not None and delta_f1 < 0:
        handoff_role = "negative_evidence_for_next_repair"
    elif child_quality:
        handoff_role = "diagnostic_evidence_for_next_repair"
    else:
        handoff_role = "protocol_or_validation_evidence"
    lessons: list[str] = []
    if delta_f1 is not None:
        direction = "improved" if delta_f1 > 0 else "regressed" if delta_f1 < 0 else "unchanged"
        lessons.append(f"child_f1 {direction} relative to materialized parent: delta_f1={delta_f1}")
    if child_failure_gates:
        lessons.append("child_failure_gates=" + ",".join(str(item) for item in child_failure_gates[:6]))
    helper_usage = compact_helper_usage(report)
    helper_status = helper_usage.get("status")
    if helper_status:
        lessons.append(f"helper_usage_status={helper_status}")
    if selected_signal:
        lessons.append(f"selected_signal={selected_signal}")
    return {
        "schema_version": "meta_loop_handoff_v001",
        "handoff_id": f"{loop_dir.name}_iter{iteration:03d}_{candidate_id}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "loop_dir": str(loop_dir),
        "iteration_dir": str(iteration_dir),
        "iteration": iteration,
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate_dir),
        "parent_agent_id": parent_agent_id,
        "meta_agent_id": meta_agent_id,
        "parent_run": str(parent_run),
        "repair_seed_path": str(seed_path),
        "candidate_status": state.get("status") or report.get("final_status") or manifest.get("status"),
        "manifest_status": manifest.get("status"),
        "launcher_exit_code": launcher_exit,
        "postprocess_exit_code": postprocess_exit,
        "changed_files": manifest.get("project_changed_files") or [],
        "total_changed_lines": manifest.get("total_changed_lines"),
        "patch_numstat": patch_numstat.strip().splitlines()[:12],
        "child_eval_status": report.get("final_status") or report.get("status"),
        "selected_stage": selected_stage,
        "selected_signal": selected_signal,
        "parent_answer_quality": parent_quality,
        "child_answer_quality": child_quality,
        "delta_f1": delta_f1,
        "child_failure_gates": child_failure_gates,
        "helper_usage_summary": helper_usage,
        "evolution_assessment": {
            "evolution_status": evolution.get("evolution_status"),
            "evolution_parent_eligible": evolution.get("evolution_parent_eligible"),
            "reward": evolution.get("reward"),
            "selection_rationale": evolution.get("selection_rationale"),
            "comparison_baseline": (evolution.get("parent_comparison_metrics") or {}).get("comparison_baseline") if isinstance(evolution.get("parent_comparison_metrics"), dict) else None,
        },
        "handoff_role": handoff_role,
        "objective_lessons": lessons,
        "meta_agent_interpretation_required": True,
        "next_loop_usage": "Inject this handoff into the next repair seed as recent loop memory, regardless of whether this candidate becomes the selected parent.",
        "artifact_paths": {
            "manifest": str(candidate_dir / "manifest.json"),
            "candidate_state": str(candidate_dir / "candidate_state.json"),
            "child_eval_report": str(candidate_dir / "child_eval/child_eval_report.json"),
            "archive_candidate_card": str(archive_root / "candidates" / candidate_id / "candidate_card.json"),
            "archive_observation": str(archive_root / "candidates" / candidate_id / "archive_observation.json"),
            "patch": str(candidate_dir / "patch.diff"),
        },
    }


def record_iteration_handoff(archive_root: Path, handoff: dict[str, Any], iteration_dir: Path) -> Path:
    handoff_path = iteration_dir / "next_iteration_handoff.json"
    write_json(handoff_path, handoff)
    upsert_jsonl(archive_root / "indexes/loop_handoffs.jsonl", "handoff_id", handoff)
    return handoff_path


def recent_loop_handoffs(archive_root: Path, limit: int = 5) -> list[dict[str, Any]]:
    rows = load_jsonl(archive_root / "indexes/loop_handoffs.jsonl")
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        compact.append(
            {
                "handoff_id": row.get("handoff_id"),
                "created_at": row.get("created_at"),
                "candidate_id": row.get("candidate_id"),
                "parent_agent_id": row.get("parent_agent_id"),
                "candidate_status": row.get("candidate_status"),
                "handoff_role": row.get("handoff_role"),
                "selected_stage": row.get("selected_stage"),
                "selected_signal": row.get("selected_signal"),
                "delta_f1": row.get("delta_f1"),
                "parent_answer_quality": row.get("parent_answer_quality"),
                "child_answer_quality": row.get("child_answer_quality"),
                "child_failure_gates": row.get("child_failure_gates"),
                "helper_usage_summary": row.get("helper_usage_summary"),
                "changed_files": row.get("changed_files"),
                "objective_lessons": row.get("objective_lessons"),
                "artifact_paths": row.get("artifact_paths"),
            }
        )
    return compact


def attach_recent_loop_handoffs_to_seed(seed: dict[str, Any], seed_path: Path, archive_root: Path, loop_dir: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    handoffs = recent_loop_handoffs(archive_root, limit=limit)
    if not handoffs:
        return []
    payload = {
        "schema_version": "recent_loop_handoff_memory_v001",
        "source": str(archive_root / "indexes/loop_handoffs.jsonl"),
        "usage": "Recent loop outcomes are objective memory for the meta-agent. Interpret them, but do not treat them as fixed human repair instructions.",
        "handoffs": handoffs,
    }
    seed["recent_loop_handoff_memory"] = payload
    seed.setdefault("fine_grained_feedback", {})["recent_loop_handoff_memory"] = payload
    write_json(loop_dir / "recent_loop_handoffs.json", payload)
    write_json(seed_path, seed)
    return handoffs


def repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def adapt_feedback_for_repair_profile(feedback: dict[str, Any], repair_profile: str) -> dict[str, Any]:
    """Return the repair-seed view of feedback for a specific repair profile.

    The full evidence pack remains evidence-first and profile-neutral.  This
    adapter only changes the compact seed that is handed to a candidate
    launcher, so a tool-first profile is not accidentally nudged back into a
    prompt-only repair.
    """

    if repair_profile != "data_agent_tool_repair":
        return feedback

    out = json.loads(json.dumps(feedback, ensure_ascii=False))
    base_routing = out.get("repair_routing") if isinstance(out.get("repair_routing"), dict) else {}
    base_layer = str(base_routing.get("recommended_repair_layer") or "data_agent_generation")
    base_reason = str(base_routing.get("routing_reason") or "Active evidence points to the data-agent generation path.")
    layer_low = base_layer.lower()
    signal_low = "\n".join(
        str(item)
        for item in (
            out.get("selected_stage"),
            out.get("selected_signal"),
            base_reason,
            json.dumps(out.get("answer_delta") or {}, ensure_ascii=False),
        )
    ).lower()
    combined = f"{layer_low}\n{signal_low}"

    if any(marker in combined for marker in ("year", "ema", "best year", "year_axis")):
        helper_targets = [
            "adapters/patents/ema.py",
            "adapters/patents/patent_query_utils.py",
            "adapters/patents/cpc_mapping.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ]
        helper_focus = "Create or update a reusable EMA/year-axis helper; prompt text may only tell generated_solve.py to use that helper."
    elif any(marker in combined for marker in ("mapping", "granularity", "level", "missing", "extra", "answer_delta")):
        helper_targets = [
            "adapters/patents/cpc_mapping.py",
            "adapters/patents/cpc_definition.py",
            "adapters/patents/patent_query_utils.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ]
        helper_focus = "Create or update reusable CPC mapping/answer-delta helper logic; prompt text may only provide thin import/use glue."
    elif any(marker in combined for marker in ("traceback", "runtime", "api", "exception")):
        helper_targets = [
            "adapters/patents/patent_query_utils.py",
            "adapters/runtime_observer.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ]
        helper_focus = "Create or update reusable generated-code safety/helper logic for the concrete runtime pattern."
    else:
        helper_targets = [
            "adapters/patents/patent_query_utils.py",
            "adapters/patents/cpc_mapping.py",
            "adapters/patents/ema.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ]
        helper_focus = "Create or update a reusable PATENTS helper module before considering prompt glue."

    routing = dict(base_routing)
    routing.update(
        {
            "base_repair_routing": base_routing,
            "recommended_repair_layer": f"data_agent_tool_helper_for_{base_layer}",
            "recommended_target_files": helper_targets,
            "anti_targets": [
                "adapters/feedback/**",
                "logs/**",
                "candidates/**",
                "archive/**",
                "trajectories/**",
                "benchmarks/**",
                "legacy/**",
                "data/**",
            ],
            "prompt_only_policy": {
                "status": "weak_allowed",
                "reason": "For data_agent_tool_repair, prompt-only is a fallback only when no safe reusable adapters/patents helper can be created; the rationale must contain `prompt-only fallback` and the evidence reason.",
                "source_change_required": False,
                "helper_target_required": True,
            },
            "routing_reason": f"{base_reason} Profile override: data_agent_tool_repair should turn this repeated generated-code failure into reusable adapters/patents helper code before adding prompt glue.",
            "tool_first_policy": {
                "required_primary_target": "adapters/patents/*.py",
                "preferred_operations": ["create_file", "replace_text_once", "insert_after_anchor"],
                "helper_focus": helper_focus,
                "prompt_glue_limit": "Prompt edits are allowed only as small glue after at least one helper target is included, unless using explicit prompt-only fallback.",
            },
        }
    )
    routing["if_project_source"] = [
        helper_focus,
        "Keep helper code benchmark-safe: no hardcoded expected CPC answers, exact answer counts, or ground-truth lists.",
        "Preserve current working parser/mapping capabilities shown by runtime trace evidence.",
    ]
    routing["if_prompt_only"] = [
        "Use prompt-only only as an explicit fallback with phrase `prompt-only fallback` and evidence that no safe reusable helper can be created.",
        "Do not merely restate existing CPC metadata or EMA instructions.",
    ]

    focus = list(out.get("next_repair_focus") or [])
    out["next_repair_focus"] = [
        helper_focus,
        "In data_agent_tool_repair, include at least one adapters/patents/*.py helper target unless explicitly using prompt-only fallback.",
    ] + focus
    out["base_repair_routing"] = base_routing
    out["repair_routing"] = routing
    out["repair_profile_adaptation"] = {
        "profile": "data_agent_tool_repair",
        "status": "tool_first_routing_applied",
        "base_repair_layer": base_layer,
        "preferred_helper_targets": helper_targets,
    }
    return out


def run_cmd(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    stdout = stdout_path.open("w", encoding="utf-8") if stdout_path else subprocess.PIPE
    stderr = stderr_path.open("w", encoding="utf-8") if stderr_path else subprocess.PIPE
    try:
        return subprocess.run(args, cwd=cwd, env=env, text=True, stdout=stdout, stderr=stderr, check=False)
    finally:
        if stdout_path:
            stdout.close()
        if stderr_path:
            stderr.close()


def archive_card_path(row: dict[str, Any]) -> Path:
    card_ref = Path(row["card"])
    return card_ref if card_ref.is_absolute() else ROOT / card_ref


def archive_card_age_hours(card_path: Path) -> float | None:
    if not card_path.exists():
        return None
    now_ts = datetime.now(timezone.utc).timestamp()
    return max(0.0, (now_ts - card_path.stat().st_mtime) / 3600.0)


def card_lineage_family(card: dict[str, Any]) -> str:
    value = card.get("source_lineage_family") or card.get("lineage_family")
    if value:
        return str(value)
    source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
    runner = str(source_refs.get("runner") or "")
    if runner == "experiments/run_dab_tool_agent.py":
        return "dab_tool_agent_workflow"
    if runner == "experiments/run_dab_agent.py":
        return "generated_solve_legacy"
    return "unknown"


def card_matches_lineage_family(card: dict[str, Any], requested: str | None) -> bool:
    if not requested:
        return True
    return card_lineage_family(card) == requested


def archive_card_is_recent(card_path: Path, max_age_hours: float | None) -> bool:
    if max_age_hours is None or max_age_hours <= 0:
        return True
    age_hours = archive_card_age_hours(card_path)
    return age_hours is not None and age_hours <= max_age_hours


def selection_score_with_penalty(
    item: dict[str, Any],
    *,
    repeated_parent_ids: list[str] | None,
    repeated_parent_penalty: float,
) -> dict[str, Any]:
    arm_id = item.get("arm_id")
    base_score = float(item.get("score") or 0.0)
    repeated_count = (repeated_parent_ids or []).count(arm_id)
    adjusted_score = base_score - max(0.0, repeated_parent_penalty) * repeated_count
    out = dict(item)
    out["base_score"] = round(base_score, 6)
    out["repeated_parent_count"] = repeated_count
    out["repeated_parent_penalty"] = round(max(0.0, repeated_parent_penalty) * repeated_count, 6)
    out["adjusted_score"] = round(adjusted_score, 6)
    return out


def select_archive_agent(
    archive_root: Path,
    *,
    requested: str | None = None,
    agent_type: str | None = None,
    require_prompt: bool = False,
    max_age_hours: float | None = None,
    repeated_parent_ids: list[str] | None = None,
    repeated_parent_penalty: float = 0.0,
    source_lineage_family: str | None = None,
) -> dict[str, Any]:
    agents = {row["agent_id"]: row for row in load_jsonl(archive_root / "indexes/agents.jsonl")}
    if requested:
        row = agents.get(requested)
        if not row:
            raise SystemExit(f"agent not found in archive index: {requested}")
        card = load_json(archive_card_path(row))
        if agent_type and card.get("agent_type") != agent_type:
            raise SystemExit(f"requested agent {requested} is {card.get('agent_type')}, not {agent_type}")
        if require_prompt and not card.get("source_refs", {}).get("prompt"):
            raise SystemExit(f"requested agent {requested} has no data-agent prompt source")
        return {"index": row, "card": card}

    scores_path = archive_root / "indexes/selection_scores.json"
    if scores_path.exists():
        scores = load_json(scores_path).get("scores") or []
        adjusted_scores: list[dict[str, Any]] = []
        for item in scores:
            adjusted_scores.append(
                selection_score_with_penalty(
                    item,
                    repeated_parent_ids=repeated_parent_ids,
                    repeated_parent_penalty=repeated_parent_penalty,
                )
            )
        for item in sorted(adjusted_scores, key=lambda x: x.get("adjusted_score", x.get("score", 0)), reverse=True):
            arm_id = item.get("arm_id")
            if arm_id in agents:
                row = agents[arm_id]
                card_path = archive_card_path(row)
                if not archive_card_is_recent(card_path, max_age_hours):
                    continue
                card = load_json(card_path)
                if agent_type and card.get("agent_type") != agent_type:
                    continue
                if not card_matches_lineage_family(card, source_lineage_family):
                    continue
                if require_prompt and not card.get("source_refs", {}).get("prompt"):
                    continue
                if card.get("evolve_policy", {}).get("can_use_as_parent"):
                    item["card_mtime_age_hours"] = archive_card_age_hours(card_path)
                    return {"index": row, "card": card, "selection_score": item}

    fallback_rows: list[tuple[float, dict[str, Any], dict[str, Any], Path]] = []
    for row in agents.values():
        card_path = archive_card_path(row)
        if not archive_card_is_recent(card_path, max_age_hours):
            continue
        card = load_json(card_path)
        if agent_type and card.get("agent_type") != agent_type:
            continue
        if not card_matches_lineage_family(card, source_lineage_family):
            continue
        if require_prompt and not card.get("source_refs", {}).get("prompt"):
            continue
        if card.get("evolve_policy", {}).get("can_use_as_parent"):
            fallback_rows.append((card_path.stat().st_mtime if card_path.exists() else 0.0, row, card, card_path))
    if fallback_rows:
        _, row, card, card_path = sorted(fallback_rows, key=lambda x: x[0], reverse=True)[0]
        return {
            "index": row,
            "card": card,
            "selection_score": {
                "arm_id": row.get("agent_id"),
                "score": None,
                "adjusted_score": None,
                "card_mtime_age_hours": archive_card_age_hours(card_path),
                "selection_note": "fallback_most_recent_recent_agent_without_score",
            },
        }
    suffix = f" type={agent_type}" if agent_type else ""
    recent_suffix = f" within {max_age_hours}h" if max_age_hours and max_age_hours > 0 else ""
    raise SystemExit(f"no selectable archive agent found{suffix}{recent_suffix}")


def select_parent_agent(
    archive_root: Path,
    requested: str | None = None,
    *,
    max_age_hours: float | None = None,
    repeated_parent_ids: list[str] | None = None,
    repeated_parent_penalty: float = 0.0,
    source_lineage_family: str | None = None,
) -> dict[str, Any]:
    if requested:
        return select_archive_agent(
            archive_root,
            requested=requested,
            agent_type="data_agent",
            require_prompt=True,
            max_age_hours=max_age_hours,
            repeated_parent_ids=repeated_parent_ids,
            repeated_parent_penalty=repeated_parent_penalty,
            source_lineage_family=source_lineage_family,
        )

    selection = select_from_archive(
        candidates_index_path=archive_root / "indexes/candidates.jsonl",
        agents_index_path=archive_root / "indexes/agents.jsonl",
        recent_parent_ids=repeated_parent_ids or [],
        parent_limit=10,
        evidence_limit=0,
        parent_agent_type="data_agent",
        source_lineage_family=source_lineage_family,
    )
    for row in selection.get("parent_pool") or []:
        card_ref = row.get("card")
        if not card_ref:
            continue
        card_path = Path(card_ref)
        if not card_path.is_absolute():
            card_path = ROOT / card_path
        if not archive_card_is_recent(card_path, max_age_hours):
            continue
        card = load_json(card_path)
        if card.get("agent_type") != "data_agent":
            continue
        if not card_matches_lineage_family(card, source_lineage_family):
            continue
        if not card.get("source_refs", {}).get("prompt"):
            continue
        if not card.get("evolve_policy", {}).get("can_use_as_parent") and not row.get("can_use_as_parent"):
            continue
        row = dict(row)
        row["selection_policy"] = "archive_selector_v001_parent_pool"
        return {"index": row, "card": card, "selection_score": row}

    return select_archive_agent(
        archive_root,
        requested=None,
        agent_type="data_agent",
        require_prompt=True,
        max_age_hours=max_age_hours,
        repeated_parent_ids=repeated_parent_ids,
        repeated_parent_penalty=repeated_parent_penalty,
        source_lineage_family=source_lineage_family,
    )


def select_meta_agent(archive_root: Path, requested: str | None = None) -> dict[str, Any] | None:
    try:
        return select_archive_agent(
            archive_root,
            requested=requested,
            agent_type="meta_agent_protocol",
            require_prompt=False,
        )
    except SystemExit:
        if requested:
            raise
        return None


def prompt_for_parent(parent: dict[str, Any], override: Path | None = None) -> Path:
    if override:
        return override
    prompt = parent["card"].get("source_refs", {}).get("prompt")
    if not prompt:
        raise SystemExit(f"selected parent has no prompt source: {parent['card'].get('agent_id')}")
    return ROOT / prompt


def preflight_parent_materialization(parent_agent_card: dict[str, Any] | None) -> dict[str, Any]:
    """Check whether selected parent source patches can be materialized.

    Clean current-mainline parents have no candidate_patch and return skipped.
    Historical shadow parents with stale patches are caught before expensive
    parent/data-agent runs start.
    """
    patch_paths = resolve_parent_candidate_patches(parent_agent_card)
    if not patch_paths:
        return {"status": "skipped", "reason": "no parent source patches declared"}
    parent_root = Path(tempfile.mkdtemp(prefix="meta_loop_parent_preflight."))
    parent_ws = parent_root / "workspace"
    shutil.copytree(ROOT, parent_ws, ignore=ignore_workspace, symlinks=True)
    run_cmd(["git", "init", "--quiet"], cwd=parent_ws)
    run_cmd(["git", "config", "user.name", "meta-loop-parent-preflight"], cwd=parent_ws)
    run_cmd(["git", "config", "user.email", "meta-loop-parent-preflight@localhost"], cwd=parent_ws)
    run_cmd(["git", "add", "."], cwd=parent_ws)
    run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=parent_ws)
    result = materialize_child_parent_source(parent_ws, parent_agent_card)
    return {**result, "workspace": str(parent_ws), "preflight": True}


def run_parent_case(
    *,
    case_dir: Path,
    prompt_path: Path,
    version: str,
    dab_root: Path,
    timeout_sec: int,
    parent_agent_card: dict[str, Any] | None = None,
    loop_dir: Path | None = None,
) -> Path:
    """Run the selected parent with archived source patches materialized.

    Archive agents may include prompt changes plus project-source helper patches.
    Running only an archived prompt against the current main workspace can create
    fake parent failures, because helpers/policies may only exist in the parent
    lineage.  When a parent agent card is available, run the parent in an
    isolated snapshot with its lineage patches applied, matching child eval.

    The active research mainline is now the DAB multi-turn tool-agent workflow.
    The old generated_solve.py parent runner is intentionally not used here: it
    can create parent evidence about one-shot code generation failures that is
    not aligned with the new DataAgent workflow.
    """
    patch_paths = resolve_parent_candidate_patches(parent_agent_card)
    if not patch_paths:
        run_dir = run_dab_tool_agent_parent_case(
            workspace=ROOT,
            case_dir=case_dir,
            version=version,
            dab_root=dab_root,
            loop_dir=loop_dir,
        )
        if loop_dir:
            write_json(
                loop_dir / "parent_source_materialization.json",
                {
                    "status": "skipped",
                    "reason": "no parent source patches declared",
                    "active_workflow": "dab_tool_agent",
                    "run_dir": str(run_dir),
                },
            )
        return run_dir

    parent_root = Path(tempfile.mkdtemp(prefix="meta_loop_parent_eval."))
    parent_ws = parent_root / "workspace"
    shutil.copytree(ROOT, parent_ws, ignore=ignore_workspace, symlinks=True)
    run_cmd(["git", "init", "--quiet"], cwd=parent_ws)
    run_cmd(["git", "config", "user.name", "meta-loop-parent-eval"], cwd=parent_ws)
    run_cmd(["git", "config", "user.email", "meta-loop-parent-eval@localhost"], cwd=parent_ws)
    run_cmd(["git", "add", "."], cwd=parent_ws)
    run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=parent_ws)

    parent_source_materialization = materialize_child_parent_source(parent_ws, parent_agent_card)
    if parent_source_materialization.get("status") == "failed":
        if loop_dir:
            write_json(loop_dir / "parent_source_materialization.json", {**parent_source_materialization, "workspace": str(parent_ws)})
        raise RuntimeError(f"parent source materialization failed: {parent_source_materialization}")
    try:
        materialize_child_parent_prompt(parent_ws, prompt_path)
    except FileNotFoundError:
        pass
    run_cmd(["git", "add", "."], cwd=parent_ws)
    run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=parent_ws)

    parent_version = f"{version}_materialized"
    run_dir = run_dab_tool_agent_parent_case(
        workspace=parent_ws,
        case_dir=case_dir,
        version=parent_version,
        dab_root=dab_root,
        loop_dir=loop_dir,
    )
    if loop_dir:
        write_json(
            loop_dir / "parent_source_materialization.json",
            {
                **parent_source_materialization,
                "workspace": str(parent_ws),
                "run_status": "completed",
                "active_workflow": "dab_tool_agent",
                "run_dir": str(run_dir),
            },
        )
    return run_dir


def run_dab_tool_agent_parent_case(
    *,
    workspace: Path,
    case_dir: Path,
    version: str,
    dab_root: Path,
    loop_dir: Path | None,
) -> Path:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    env.setdefault("DAB_TOOL_AGENT_API_KEY_ENV", "DASHSCOPE_API_KEY")
    max_iterations = str(
        env.get("DAB_TOOL_AGENT_PARENT_MAX_ITERATIONS")
        or env.get("CODEX_NATIVE_DATA_AGENT_MAX_ITERATIONS")
        or env.get("DAB_TOOL_AGENT_MAX_ITERATIONS")
        or "10"
    )
    output_root = workspace / "logs" / "dab_tool_agent"
    policy_path = workspace / DAB_TOOL_AGENT_CANONICAL_POLICY
    cmd = [
        str(ROOT / ".venv/bin/python"),
        str(workspace / "experiments/run_dab_tool_agent.py"),
        "--query-dir",
        str(case_dir),
        "--dab-data-root",
        str(dab_root),
        "--output-root",
        str(output_root),
        "--run-id",
        version,
        "--max-iterations",
        max_iterations,
    ]
    if policy_path.exists():
        cmd += ["--tool-agent-policy", str(policy_path)]
    proc = run_cmd(
        cmd,
        cwd=workspace,
        env=env,
        stdout_path=(loop_dir / "parent_dab_tool_run.stdout") if loop_dir else None,
        stderr_path=(loop_dir / "parent_dab_tool_run.stderr") if loop_dir else None,
    )
    run_dir = output_root / version
    if not run_dir.exists():
        run_dirs = sorted(output_root.glob(f"*{version}*"), key=lambda path: path.stat().st_mtime)
        run_dir = run_dirs[-1] if run_dirs else run_dir
    if not run_dir.exists():
        raise RuntimeError(f"DAB tool-agent parent run produced no run_dir; exit_code={proc.returncode}; expected={run_dir}")
    if loop_dir:
        write_json(
            loop_dir / "parent_workflow_runner.json",
            {
                "status": "completed" if proc.returncode == 0 else "completed_with_nonzero_exit",
                "workflow": "dab_tool_agent",
                "exit_code": proc.returncode,
                "run_dir": str(run_dir),
                "max_iterations": max_iterations,
                "policy_path": str(policy_path) if policy_path.exists() else None,
            },
        )
    return run_dir


def is_dab_tool_agent_run_dir(run_dir: Path) -> bool:
    try:
        summary = load_json(run_dir / "summary.json")
    except Exception:
        summary = {}
    if isinstance(summary, dict) and summary.get("schema_version") == "dab_tool_agent_run_v001":
        return True
    return (run_dir / "workflow_trace.jsonl").exists() or (run_dir / "tool_calls.jsonl").exists()


def analyze_dab_tool_agent_and_seed(
    *,
    run_dir: Path,
    loop_dir: Path,
    candidate_context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    env = os.environ.copy()
    analyzer_proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "experiments/analyze_dab_tool_agent_trace.py"),
            "--run-dir",
            str(run_dir),
            "--output-dir",
            str(loop_dir),
        ],
        cwd=ROOT,
        env=env,
        stdout_path=loop_dir / "parent_dab_tool_analyze.stdout",
        stderr_path=loop_dir / "parent_dab_tool_analyze.stderr",
    )
    fine_grained_json_path = loop_dir / "fine_grained_evidence_pack.json"
    fine_grained_md_path = loop_dir / "fine_grained_evidence_pack.md"
    evidence_proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "experiments/build_dab_tool_agent_evidence_pack.py"),
            "--run-dir",
            str(run_dir),
            "--output-json",
            str(fine_grained_json_path),
            "--output-md",
            str(fine_grained_md_path),
        ],
        cwd=ROOT,
        env=env,
        stdout_path=loop_dir / "parent_dab_tool_evidence.stdout",
        stderr_path=loop_dir / "parent_dab_tool_evidence.stderr",
    )
    feedback_summary = load_json(loop_dir / "feedback_summary.json")
    observations = load_json(loop_dir / "observations.json")
    meta_agent_seed = load_json(loop_dir / "meta_agent_seed.json")
    evidence_pack = load_json(fine_grained_json_path)
    obs_top = observations[:8] if isinstance(observations, list) else []
    seed = dict(meta_agent_seed) if isinstance(meta_agent_seed, dict) else {}
    seed.update(
        {
            "seed_id": f"repair_seed_{loop_dir.name}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent_run_dir": str(run_dir),
            "feedback_type": "dab_tool_agent_workflow_feedback",
            "repair_profile": candidate_context.get("repair_profile"),
            "candidate_context": candidate_context,
            "analysis_commands": {
                "analyzer_exit_code": analyzer_proc.returncode,
                "evidence_pack_exit_code": evidence_proc.returncode,
            },
            "fine_grained_feedback": {
                "feedback_type": "dab_tool_agent_workflow_feedback",
                "source_run_dir": str(run_dir),
                "selected_stage": feedback_summary.get("selected_stage"),
                "selected_signal": feedback_summary.get("selected_signal"),
                "selected_problem_type": feedback_summary.get("selected_problem_type"),
                "answer_quality": feedback_summary.get("answer_quality"),
                "helper_usage_summary": feedback_summary.get("helper_usage_summary"),
                "candidate_repair_layers": feedback_summary.get("candidate_repair_layers"),
                "routing_policy": feedback_summary.get("routing_policy"),
                "meta_agent_decision_required": feedback_summary.get("meta_agent_decision_required"),
                "primary_signal": feedback_summary.get("primary_signal"),
                "top_observations": obs_top,
                "structured_observations": evidence_pack.get("structured_observations"),
                "repair_guidance": evidence_pack.get("repair_guidance"),
                "artifact_paths": evidence_pack.get("artifact_paths"),
                "full_evidence_pack_paths": {
                    "json": str(fine_grained_json_path),
                    "markdown": str(fine_grained_md_path),
                },
            },
            "full_evidence_pack_paths": {
                "json": str(fine_grained_json_path),
                "markdown": str(fine_grained_md_path),
            },
        }
    )
    seed.setdefault("selected_stage", feedback_summary.get("selected_stage"))
    seed.setdefault("selected_signal", feedback_summary.get("selected_signal"))
    seed.setdefault("answer_quality", feedback_summary.get("answer_quality"))
    seed.setdefault("helper_usage_summary", feedback_summary.get("helper_usage_summary"))
    seed.setdefault("candidate_repair_layers", feedback_summary.get("candidate_repair_layers") or [])
    seed.setdefault("routing_policy", feedback_summary.get("routing_policy") or {})
    seed.setdefault("top_observations", obs_top)
    seed_path = loop_dir / "repair_seed.json"
    write_json(seed_path, seed)
    return seed, seed_path


def analyze_run_quiet(run_dir: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return analyze_run(run_dir)
    finally:
        stdout_path.write_text(stdout.getvalue(), encoding="utf-8")
        stderr_path.write_text(stderr.getvalue(), encoding="utf-8")


def current_failure_tags_from_seed(seed: dict[str, Any]) -> list[str]:
    tags: list[str] = []

    def add(tag: str | None) -> None:
        if tag and tag not in tags:
            tags.append(tag)

    add(str(seed.get("selected_stage") or ""))
    text = json.dumps(seed, ensure_ascii=False).lower()[:20000]
    if "missing_final_answer_file_or_empty_answer" in text or ("line_count" in text and "0" in text) or "empty answer" in text:
        add("empty_final_answer")
    if "helper_called_but_output_not_used_for_final_answer" in text or "helper_output_sink_mismatch" in text:
        add("helper_output_sink_mismatch")
        add("helper_output_not_used_for_final_answer")
    if "data_agent_tool_helper_integration" in text or "helper_glue_too_weak" in text:
        add("data_agent_tool_helper_integration")
    if "severe_child_answer_regression" in text:
        add("severe_child_answer_regression")
    if "granularity" in text:
        add("granularity_mapping")
    if "schema_grounding" in text:
        add("schema_grounding")
    return tags


def compact_archive_evidence_item(row: dict[str, Any]) -> dict[str, Any]:
    card_ref = row.get("card")
    observation: dict[str, Any] = {}
    if card_ref:
        card_path = Path(str(card_ref))
        if not card_path.is_absolute():
            card_path = ROOT / card_path
        obs_path = card_path.parent / "archive_observation.json"
        if obs_path.exists():
            try:
                observation = json.loads(obs_path.read_text(encoding="utf-8"))
            except Exception:
                observation = {}
    obs_body = observation.get("observations") if isinstance(observation.get("observations"), dict) else {}
    return {
        "candidate_id": row.get("candidate_id"),
        "status": row.get("status"),
        "card": row.get("card"),
        "archive_observation": str((Path(str(row.get("card"))).parent / "archive_observation.json")) if row.get("card") else None,
        "selection_score": row.get("selection_score"),
        "selection_reasons": row.get("selection_reasons"),
        "promotion_reason": row.get("promotion_reason"),
        "metric_delta_f1": row.get("metric_delta_f1"),
        "failure_observation_tags": row.get("failure_observation_tags") or [],
        "contract_eval_status": row.get("contract_eval_status"),
        "open_diagnosis": obs_body.get("open_diagnosis"),
        "soft_gate_observations": (obs_body.get("soft_gate_observations") or [])[:4],
        "interface_mismatch_evidence": (obs_body.get("interface_mismatch_evidence") or [])[:4],
        "contract_failure_evidence": (obs_body.get("contract_failure_evidence") or [])[:4],
        "not_to_repeat": (obs_body.get("not_to_repeat") or [])[:8],
    }


def archive_priority_observations_from_selection(selection: dict[str, Any]) -> list[dict[str, Any]]:
    priority: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(candidate_id: str | None, kind: str, detail: Any, why: str) -> None:
        key = (str(candidate_id), kind + ":" + str(detail)[:160])
        if key in seen:
            return
        seen.add(key)
        priority.append({
            "candidate_id": candidate_id,
            "kind": kind,
            "detail": detail,
            "why_it_matters": why,
        })

    for item in selection.get("evidence_pool") or []:
        candidate_id = item.get("candidate_id")
        for tag in item.get("failure_observation_tags") or []:
            if tag in {
                "helper_output_sink_mismatch",
                "helper_output_not_used_for_final_answer",
                "data_agent_tool_helper_integration",
                "data_agent_tool_helper_quality",
                "weak_filtering_warning",
                "empty_final_answer",
                "severe_child_answer_regression",
            }:
                add(candidate_id, "failure_tag", tag, "Prior candidate failed with this exact observation; the next patch should not repeat it.")
        for obs in item.get("soft_gate_observations") or []:
            reason = str(obs.get("reason") or "")
            name = str(obs.get("name") or "")
            lowered = reason.lower()
            if any(token in lowered for token in ("weak_filtering", "helper_glue_too_weak", "helper_plan_target_mismatch", "diagnostics_only")):
                add(candidate_id, "soft_gate_observation", {"name": name, "reason": reason}, "Soft gate identified a likely ineffective patch shape; require the next patch contract to avoid it.")
        for obs in item.get("interface_mismatch_evidence") or []:
            add(candidate_id, "interface_mismatch", obs, "Prior helper output did not reach final answer construction; next patch must specify and satisfy the output sink contract.")
        for obs in item.get("contract_failure_evidence") or []:
            add(candidate_id, "contract_failure", obs, "Prior candidate violated an inferred behavior contract; next patch must state a concrete proposed_contract and validation hint.")
    return priority[:12]


def attach_archive_selection_to_seed(
    *,
    seed: dict[str, Any],
    seed_path: Path,
    archive_root: Path,
    loop_dir: Path,
    repeated_parent_ids: list[str] | None = None,
) -> dict[str, Any]:
    current_tags = current_failure_tags_from_seed(seed)
    selection = select_from_archive(
        candidates_index_path=archive_root / "indexes/candidates.jsonl",
        agents_index_path=archive_root / "indexes/agents.jsonl",
        current_failure_tags=current_tags,
        recent_parent_ids=repeated_parent_ids or [],
        parent_limit=5,
        evidence_limit=5,
        parent_agent_type="data_agent",
    )
    loop_selection_path = loop_dir / "archive_selection.json"
    write_json(loop_selection_path, selection)
    priority_observations = archive_priority_observations_from_selection(selection)
    seed["archive_selection"] = {
        "schema_version": selection.get("schema_version"),
        "selection_path": str(loop_selection_path),
        "current_failure_tags": current_tags,
        "parent_pool_preview": [
            {
                "agent_id": item.get("agent_id"),
                "selection_score": item.get("selection_score"),
                "selection_reasons": item.get("selection_reasons"),
                "best_f1": item.get("best_f1"),
                "card": item.get("card"),
            }
            for item in (selection.get("parent_pool") or [])[:3]
        ],
        "evidence_pool": [compact_archive_evidence_item(item) for item in (selection.get("evidence_pool") or [])[:5]],
    }
    seed["archive_evidence_priority_observations"] = priority_observations
    seed.setdefault("fine_grained_feedback", {})["archive_evidence_pool"] = seed["archive_selection"]["evidence_pool"]
    seed["fine_grained_feedback"]["archive_evidence_priority_observations"] = priority_observations
    write_json(seed_path, seed)
    return selection


def analyze_and_seed(
    *,
    run_dir: Path,
    loop_dir: Path,
    candidate_context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    if is_dab_tool_agent_run_dir(run_dir):
        return analyze_dab_tool_agent_and_seed(
            run_dir=run_dir,
            loop_dir=loop_dir,
            candidate_context=candidate_context,
        )

    # Legacy generated_solve.py fallback.  This branch is kept only for
    # historical run directories explicitly supplied through --parent-run; the
    # active loop no longer creates this format.
    analysis = analyze_run_quiet(
        run_dir,
        loop_dir / "parent_analyze.stdout",
        loop_dir / "parent_analyze.stderr",
    )
    signal = extract_primary_signal(run_dir / "agent_error_summary.json")
    signal_path = loop_dir / "parent_primary_signal.json"
    write_json(signal_path, signal)
    fine_grained_feedback = build_fine_grained_feedback_pack(
        run_dir,
        primary_signal=signal,
        max_trace_events=12,
    )
    fine_grained_json_path = loop_dir / "fine_grained_evidence_pack.json"
    fine_grained_md_path = loop_dir / "fine_grained_evidence_pack.md"
    write_pack(fine_grained_feedback, fine_grained_json_path, fine_grained_md_path)
    repair_profile = str(candidate_context.get("repair_profile") or "")
    seed_feedback = adapt_feedback_for_repair_profile(fine_grained_feedback, repair_profile)
    helper_repair_plan = plan_helper_repair(seed_feedback, repair_profile)
    if helper_repair_plan.get("status") == "planned":
        routing = dict(seed_feedback.get("repair_routing") or {})
        recommended_helper = helper_repair_plan.get("recommended_helper_file")
        recommended_prompt = helper_repair_plan.get("recommended_prompt_glue_file")
        existing_targets = [str(item) for item in routing.get("recommended_target_files") or []]
        prioritized_targets = []
        for item in (recommended_helper, recommended_prompt):
            if item and str(item) not in prioritized_targets:
                prioritized_targets.append(str(item))
        for item in existing_targets:
            if item not in prioritized_targets:
                prioritized_targets.append(item)
        if prioritized_targets:
            routing["recommended_target_files"] = prioritized_targets
        routing["helper_repair_plan_summary"] = {
            "recommended_helper_file": recommended_helper,
            "helper_focus": helper_repair_plan.get("helper_focus"),
            "required_functions": helper_repair_plan.get("required_functions"),
            "success_criteria": helper_repair_plan.get("success_criteria"),
        }
        tool_policy = dict(routing.get("tool_first_policy") or {})
        if recommended_helper:
            tool_policy["required_primary_target"] = recommended_helper
        if helper_repair_plan.get("helper_focus"):
            tool_policy["helper_focus"] = helper_repair_plan.get("helper_focus")
        routing["tool_first_policy"] = tool_policy
        seed_feedback["repair_routing"] = routing
        seed_feedback["next_repair_focus"] = [
            str(helper_repair_plan.get("helper_focus") or "Use the helper_repair_plan as the primary target."),
            "Implement the helper API named in helper_repair_plan; if that API cannot be safely implemented, output no_op_failed.",
            "Validation should address helper_repair_plan.focused_validation_tests before relying on broad child eval.",
        ] + list(seed_feedback.get("next_repair_focus") or [])
    seed_feedback["helper_repair_plan"] = helper_repair_plan
    compact_feedback = {
        "feedback_type": seed_feedback.get("feedback_type"),
        "source_run_dir": seed_feedback.get("source_run_dir"),
        "selected_stage": seed_feedback.get("selected_stage"),
        "selected_signal": seed_feedback.get("selected_signal"),
        "repair_routing": seed_feedback.get("repair_routing"),
        "base_repair_routing": seed_feedback.get("base_repair_routing"),
        "repair_profile_adaptation": seed_feedback.get("repair_profile_adaptation"),
        "helper_repair_plan": seed_feedback.get("helper_repair_plan"),
        "patch_generation_feedback": seed_feedback.get("patch_generation_feedback"),
        "parent_capabilities": seed_feedback.get("parent_capabilities"),
        "answer_delta": seed_feedback.get("answer_delta"),
        "runtime_trace_evidence": (seed_feedback.get("runtime_trace_evidence") or [])[:8],
        "ranked_feedback_signals": (seed_feedback.get("ranked_feedback_signals") or [])[:5],
        "repair_constraints": seed_feedback.get("repair_constraints"),
        "next_repair_focus": seed_feedback.get("next_repair_focus"),
        "full_evidence_pack_paths": {
            "json": str(fine_grained_json_path),
            "markdown": str(fine_grained_md_path),
        },
    }
    seed = {
        "seed_id": f"repair_seed_{loop_dir.name}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parent_run_dir": str(run_dir),
        "selected_stage": compact_feedback.get("selected_stage"),
        "selected_signal": compact_feedback.get("selected_signal"),
        "total_observations": signal.get("total_observations"),
        "analysis_summary": {
            "passed": analysis.get("passed"),
            "validation_reason": analysis.get("validation_reason"),
        },
        "repair_profile": repair_profile,
        "repair_routing": compact_feedback.get("repair_routing"),
        "base_repair_routing": compact_feedback.get("base_repair_routing"),
        "repair_profile_adaptation": compact_feedback.get("repair_profile_adaptation"),
        "helper_repair_plan": compact_feedback.get("helper_repair_plan"),
        "patch_generation_feedback": compact_feedback.get("patch_generation_feedback"),
        "answer_delta": compact_feedback.get("answer_delta"),
        "parent_capabilities": compact_feedback.get("parent_capabilities"),
        "fine_grained_feedback": compact_feedback,
        "candidate_context": candidate_context,
    }
    seed_path = loop_dir / "repair_seed.json"
    write_json(seed_path, seed)
    return seed, seed_path


def candidate_id_for(prefix: str, iteration: int) -> str:
    return f"{prefix}_iter{iteration:03d}_{utc_now_slug()}"


def run_candidate_launcher(
    *,
    launcher: Path,
    candidate_id: str,
    candidate_dir: Path,
    seed_path: Path,
    parent_run: Path,
    parent_agent_id: str,
    parent_prompt: Path,
    case_dir: Path,
    dab_root: Path,
    loop_dir: Path,
    env_candidate_id_name: str,
    repair_profile: str = "data_agent_prompt_repair",
    repair_seed_override: bool = False,
) -> int:
    env = os.environ.copy()
    env.update(
        {
            env_candidate_id_name: candidate_id,
            "CANDIDATE_ID": candidate_id,
            "META_LOOP_CANDIDATE_ID": candidate_id,
            "META_LOOP_CANDIDATE_DIR": str(candidate_dir),
            "META_LOOP_REPAIR_SEED": str(seed_path),
            "META_LOOP_REPAIR_SEED_OVERRIDE": "1" if repair_seed_override else "0",
            "META_LOOP_PARENT_RUN": str(parent_run),
            "META_LOOP_PARENT_AGENT_ID": parent_agent_id,
            "META_LOOP_PARENT_PROMPT": str(parent_prompt),
            "META_LOOP_CASE_DIR": str(case_dir),
            "META_LOOP_DAB_ROOT": str(dab_root),
            "META_LOOP_DIR": str(loop_dir),
            "REPAIR_PROFILE": repair_profile,
        }
    )
    launcher_cmd = [sys.executable, str(launcher)] if launcher.suffix == ".py" else ["/bin/bash", str(launcher)]
    proc = run_cmd(
        launcher_cmd,
        cwd=ROOT,
        env=env,
        stdout_path=loop_dir / "candidate_launcher.stdout",
        stderr_path=loop_dir / "candidate_launcher.stderr",
    )
    return proc.returncode


def ignore_workspace(_: str, names: list[str]) -> list[str]:
    ignored = {".git", ".venv", ".env", ".codex", "__pycache__", "logs", "candidates", "reports", "trajectories"}
    return [name for name in names if name in ignored]



def resolve_prompt_source_for_child(prompt_path: Path, child_ws: Path) -> Path:
    if prompt_path.is_absolute():
        return prompt_path
    root_candidate = ROOT / prompt_path
    if root_candidate.exists():
        return root_candidate
    return child_ws / prompt_path


def materialize_child_parent_prompt(child_ws: Path, prompt_path: Path) -> Path:
    source = resolve_prompt_source_for_child(prompt_path, child_ws)
    if not source.exists():
        raise FileNotFoundError(f"selected parent prompt not found for child eval: {prompt_path}")
    target = child_ws / DATA_AGENT_CANONICAL_PROMPT
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target

def load_archive_agent_card(agent_id: str | None) -> dict[str, Any] | None:
    if not agent_id:
        return None
    card_path = ROOT / "archive" / "agents" / agent_id / "agent_card.json"
    if not card_path.exists():
        return None
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return card if isinstance(card, dict) else None


def resolve_parent_candidate_patches(parent_agent_card: dict[str, Any] | None) -> list[Path]:
    patches: list[Path] = []
    seen: set[str] = set()

    def compatible_source_lineage(card: dict[str, Any], parent_card: dict[str, Any] | None) -> bool:
        if not parent_card:
            return False
        source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
        parent_refs = parent_card.get("source_refs") if isinstance(parent_card.get("source_refs"), dict) else {}
        runner = str(source_refs.get("runner") or "")
        parent_runner = str(parent_refs.get("runner") or "")
        if runner and parent_runner and runner != parent_runner:
            return False
        return True

    def collect(card: dict[str, Any] | None) -> None:
        if not card:
            return
        agent_id = str(card.get("agent_id") or "")
        if agent_id and agent_id in seen:
            return
        if agent_id:
            seen.add(agent_id)
        lineage = card.get("lineage") if isinstance(card.get("lineage"), dict) else {}
        parent_card = load_archive_agent_card(str(lineage.get("parent_agent_id") or ""))
        if compatible_source_lineage(card, parent_card):
            collect(parent_card)
        source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
        patch_ref = source_refs.get("candidate_patch")
        if not patch_ref:
            return
        patch_path = Path(str(patch_ref))
        if not patch_path.is_absolute():
            patch_path = ROOT / patch_path
        if patch_path.exists() and patch_path not in patches:
            patches.append(patch_path)

    collect(parent_agent_card)
    return patches


def materialize_child_parent_source(child_ws: Path, parent_agent_card: dict[str, Any] | None) -> dict[str, Any]:
    patch_paths = resolve_parent_candidate_patches(parent_agent_card)
    if not patch_paths:
        return {"status": "skipped", "reason": "parent candidate patch missing or not declared"}
    applied_patches: list[str] = []
    for patch_path in patch_paths:
        if not patch_path.read_text(encoding="utf-8", errors="replace").strip():
            continue
        proc = run_cmd(
            [
                "git",
                "apply",
                f"--exclude={DATA_AGENT_CANONICAL_PROMPT.as_posix()}",
                str(patch_path),
            ],
            cwd=child_ws,
        )
        if proc.returncode != 0:
            return {
                "status": "failed",
                "reason": "parent source patch apply failed",
                "patch_path": str(patch_path),
                "applied_patches": applied_patches,
                "stderr": proc.stderr,
            }
        applied_patches.append(str(patch_path))
    if not applied_patches:
        return {"status": "skipped", "reason": "parent candidate patches empty", "patch_paths": [str(path) for path in patch_paths]}
    changed = run_cmd(["git", "status", "--short"], cwd=child_ws)
    changed_files: list[str] = []
    for line in changed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path and path not in changed_files:
            changed_files.append(path)
    return {
        "status": "applied",
        "patch_paths": applied_patches,
        "excluded_prompt": DATA_AGENT_CANONICAL_PROMPT.as_posix(),
        "changed_files": changed_files,
    }



def is_dab_tool_agent_workflow_seed(seed: dict[str, Any]) -> bool:
    if not isinstance(seed, dict):
        return False
    if seed.get("schema_version") == "dab_tool_agent_meta_agent_seed_v001":
        return True
    if seed.get("feedback_type") == "dab_tool_agent_workflow_feedback":
        return True
    fine = seed.get("fine_grained_feedback") if isinstance(seed.get("fine_grained_feedback"), dict) else {}
    if fine.get("feedback_type") == "dab_tool_agent_workflow_feedback":
        return True
    paths = seed.get("artifact_paths") if isinstance(seed.get("artifact_paths"), dict) else {}
    return any("dab_tool_agent" in str(value) for value in paths.values())


def answer_quality_from_feedback(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    direct = value.get("answer_quality")
    if isinstance(direct, dict) and direct:
        return direct
    feedback = value.get("feedback_summary") if isinstance(value.get("feedback_summary"), dict) else {}
    direct = feedback.get("answer_quality")
    if isinstance(direct, dict) and direct:
        return direct
    workflow = value.get("workflow_feedback_summary") if isinstance(value.get("workflow_feedback_summary"), dict) else {}
    direct = workflow.get("answer_quality")
    if isinstance(direct, dict) and direct:
        return direct
    fine = value.get("fine_grained_feedback") if isinstance(value.get("fine_grained_feedback"), dict) else {}
    direct = fine.get("answer_quality")
    if isinstance(direct, dict) and direct:
        return direct
    return {}


def run_dab_tool_agent_child_eval(
    *,
    candidate_dir: Path,
    case_dir: Path,
    dab_root: Path,
    loop_dir: Path,
    iteration: int,
    parent_agent_card: dict[str, Any] | None = None,
    parent_prompt: Path | None = None,
    repair_seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch_path = candidate_dir / "patch.diff"
    if not patch_path.exists() or not patch_path.read_text(encoding="utf-8", errors="replace").strip():
        return {"status": "skipped", "reason": "candidate patch.diff missing or empty", "eval_kind": "dab_tool_agent"}

    child_root = Path(tempfile.mkdtemp(prefix="meta_loop_dab_tool_child_eval."))
    child_ws = child_root / "workspace"
    shutil.copytree(ROOT, child_ws, ignore=ignore_workspace, symlinks=True)
    run_cmd(["git", "init", "--quiet"], cwd=child_ws)
    run_cmd(["git", "config", "user.name", "meta-loop-dab-tool-child-eval"], cwd=child_ws)
    run_cmd(["git", "config", "user.email", "meta-loop-dab-tool-child-eval@localhost"], cwd=child_ws)
    run_cmd(["git", "add", "."], cwd=child_ws)
    run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=child_ws)

    parent_source_materialization = materialize_child_parent_source(child_ws, parent_agent_card)
    if parent_source_materialization.get("status") == "failed":
        return {
            "status": "parent_source_materialization_failed",
            "eval_kind": "dab_tool_agent",
            "parent_source_materialization": parent_source_materialization,
            "workspace": str(child_ws),
        }

    parent_prompt_materialization: dict[str, Any] | None = None
    if parent_prompt is not None:
        try:
            materialized_prompt = materialize_child_parent_prompt(child_ws, parent_prompt)
            parent_prompt_materialization = {
                "status": "materialized_parent_prompt",
                "source_prompt": str(parent_prompt),
                "canonical_target": str(materialized_prompt),
            }
        except Exception as exc:
            parent_prompt_materialization = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
            report = {
                "status": "parent_prompt_materialization_failed",
                "final_status": "candidate_child_eval_failed",
                "eval_kind": "dab_tool_agent",
                "parent_source_materialization": parent_source_materialization,
                "parent_prompt_materialization": parent_prompt_materialization,
                "workspace": str(child_ws),
            }
            child_eval_dir = candidate_dir / "child_eval"
            child_eval_dir.mkdir(parents=True, exist_ok=True)
            write_json(child_eval_dir / "child_eval_report.json", report)
            write_json(child_eval_dir / "generic_child_eval_report.json", report)
            return report

    run_cmd(["git", "add", "."], cwd=child_ws)
    run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=child_ws)
    apply_proc = run_cmd(["git", "apply", str(patch_path)], cwd=child_ws)
    child_eval_dir = candidate_dir / "child_eval"
    child_eval_dir.mkdir(parents=True, exist_ok=True)
    if apply_proc.returncode != 0:
        report = {
            "status": "patch_apply_failed",
            "final_status": "candidate_child_eval_failed",
            "eval_kind": "dab_tool_agent",
            "stderr": apply_proc.stderr,
            "workspace": str(child_ws),
            "parent_source_materialization": parent_source_materialization,
            "parent_prompt_materialization": parent_prompt_materialization,
        }
        write_json(child_eval_dir / "child_eval_report.json", report)
        write_json(child_eval_dir / "generic_child_eval_report.json", report)
        return report
    child_version = f"dab_tool_agent_child_iter{iteration:03d}_{utc_now_slug()}"
    child_output_root = child_ws / "logs/dab_tool_agent"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(child_ws)
    env.setdefault("DAB_TOOL_AGENT_API_KEY_ENV", "DASHSCOPE_API_KEY")
    max_iterations = str(env.get("DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS") or env.get("DAB_TOOL_AGENT_MAX_ITERATIONS") or "10")
    proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(child_ws / "experiments/run_dab_tool_agent.py"),
            "--query-dir",
            str(case_dir),
            "--dab-data-root",
            str(dab_root),
            "--output-root",
            str(child_output_root),
            "--run-id",
            child_version,
            "--max-iterations",
            max_iterations,
        ],
        cwd=child_ws,
        env=env,
        stdout_path=loop_dir / "child_dab_tool_run.stdout",
        stderr_path=loop_dir / "child_dab_tool_run.stderr",
    )
    child_run_dir = child_output_root / child_version
    if not child_run_dir.exists():
        run_dirs = sorted(child_output_root.glob(f"*{child_version}*"), key=lambda path: path.stat().st_mtime)
        child_run_dir = run_dirs[-1] if run_dirs else child_run_dir
    if not child_run_dir.exists():
        report = {
            "status": "child_run_failed_no_run_dir",
            "final_status": "candidate_child_eval_failed",
            "eval_kind": "dab_tool_agent",
            "workspace": str(child_ws),
            "child_run_exit_code": proc.returncode,
            "child_run_dir": str(child_run_dir),
        }
        write_json(child_eval_dir / "child_eval_report.json", report)
        write_json(child_eval_dir / "generic_child_eval_report.json", report)
        return report

    analyzer_proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(child_ws / "experiments/analyze_dab_tool_agent_trace.py"),
            "--run-dir",
            str(child_run_dir),
            "--output-dir",
            str(child_eval_dir),
        ],
        cwd=child_ws,
        env=env,
        stdout_path=loop_dir / "child_dab_tool_analyze.stdout",
        stderr_path=loop_dir / "child_dab_tool_analyze.stderr",
    )
    feedback_summary = load_json(child_eval_dir / "feedback_summary.json")
    observations = load_json(child_eval_dir / "observations.json")
    meta_agent_seed = load_json(child_eval_dir / "meta_agent_seed.json")

    evidence_json = child_eval_dir / "child_dab_tool_agent_evidence_pack.json"
    evidence_md = child_eval_dir / "child_dab_tool_agent_evidence_pack.md"
    evidence_proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(child_ws / "experiments/build_dab_tool_agent_evidence_pack.py"),
            "--run-dir",
            str(child_run_dir),
            "--output-json",
            str(evidence_json),
            "--output-md",
            str(evidence_md),
        ],
        cwd=child_ws,
        env=env,
        stdout_path=loop_dir / "child_dab_tool_evidence.stdout",
        stderr_path=loop_dir / "child_dab_tool_evidence.stderr",
    )
    child_answer_quality = answer_quality_from_feedback(feedback_summary)
    parent_answer_quality = answer_quality_from_feedback(repair_seed or {})
    helper_usage_summary = feedback_summary.get("helper_usage_summary") if isinstance(feedback_summary.get("helper_usage_summary"), dict) else {}
    child_failure_gates: list[str] = []
    if proc.returncode != 0:
        child_failure_gates.append("child_run_exit_nonzero")
    if analyzer_proc.returncode != 0:
        child_failure_gates.append("child_analyzer_exit_nonzero")
    if evidence_proc.returncode != 0:
        child_failure_gates.append("child_evidence_pack_exit_nonzero")
    if feedback_summary.get("final_answer_nonempty") is False:
        child_failure_gates.append("missing_final_answer")
    if child_answer_quality.get("strict_match_passed") is False:
        child_failure_gates.append("answer_quality_mismatch")
    helper_status = helper_usage_summary.get("status")
    if helper_status and helper_status not in {"no_evolved_helper_registered", "helper_tool_called_before_final_answer"}:
        child_failure_gates.append(str(helper_status))

    child_passed = bool(child_answer_quality.get("strict_match_passed") is True and proc.returncode == 0 and analyzer_proc.returncode == 0)
    next_seed = dict(meta_agent_seed) if isinstance(meta_agent_seed, dict) else {}
    next_seed.update(
        {
            "seed_id": f"next_dab_tool_agent_repair_seed_iter{iteration:03d}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "child_eval_dab_tool_agent_workflow_feedback",
            "parent_candidate_dir": str(candidate_dir),
            "child_run_dir": str(child_run_dir),
            "repair_profile": "data_agent_project_repair",
            "answer_quality": child_answer_quality,
            "helper_usage_summary": helper_usage_summary,
            "full_evidence_pack_paths": {"json": str(evidence_json), "markdown": str(evidence_md)},
        }
    )
    next_seed_path = child_eval_dir / "next_data_agent_repair_seed.json"
    write_json(next_seed_path, next_seed)

    report = {
        "status": "completed",
        "final_status": "candidate_child_eval_passed" if child_passed and not child_failure_gates else "candidate_child_eval_failed",
        "eval_kind": "dab_tool_agent",
        "workspace": str(child_ws),
        "parent_source_materialization": parent_source_materialization,
        "child_run_dir": str(child_run_dir),
        "child_run_exit_code": proc.returncode,
        "child_analyzer_exit_code": analyzer_proc.returncode,
        "child_evidence_pack_exit_code": evidence_proc.returncode,
        "child_answer_quality": child_answer_quality,
        "parent_answer_quality": parent_answer_quality,
        "child_answer_metrics": child_answer_quality,
        "parent_answer_metrics": parent_answer_quality,
        "helper_usage_summary": helper_usage_summary,
        "helper_usage": helper_usage_summary,
        "child_failure_gates": child_failure_gates,
        "child_passed": child_passed and not child_failure_gates,
        "child_original_dab_passed": child_answer_quality.get("strict_match_passed"),
        "child_validation_reason": child_answer_quality.get("strict_match_reason"),
        "child_selected_stage": feedback_summary.get("selected_stage"),
        "child_selected_signal": feedback_summary.get("selected_signal"),
        "candidate_repair_layers": feedback_summary.get("candidate_repair_layers") or [],
        "routing_policy": feedback_summary.get("routing_policy") or {},
        "meta_agent_decision_required": feedback_summary.get("meta_agent_decision_required"),
        "workflow_feedback_summary": feedback_summary,
        "structured_observations": observations if isinstance(observations, list) else [],
        "child_dab_tool_agent_evidence_pack": {"json": str(evidence_json), "markdown": str(evidence_md)},
        "next_data_agent_repair_seed": str(next_seed_path),
        "child_status": {
            "status": "completed",
            "passed_original_dab_validation": child_answer_quality.get("strict_match_passed"),
            "validation_reason": child_answer_quality.get("strict_match_reason"),
            "selected_stage": feedback_summary.get("selected_stage"),
            "selected_signal": feedback_summary.get("selected_signal"),
            "answer_quality": child_answer_quality,
            "helper_usage_summary": helper_usage_summary,
            "candidate_repair_layers": feedback_summary.get("candidate_repair_layers") or [],
            "meta_agent_decision_required": feedback_summary.get("meta_agent_decision_required"),
        },
    }
    write_json(child_eval_dir / "generic_child_eval_report.json", report)
    write_json(child_eval_dir / "child_eval_report.json", report)
    return report


def run_generic_child_eval(
    *,
    candidate_dir: Path,
    case_dir: Path,
    prompt_path: Path,
    dab_root: Path,
    timeout_sec: int,
    loop_dir: Path,
    iteration: int,
    parent_agent_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch_path = candidate_dir / "patch.diff"
    if not patch_path.exists() or not patch_path.read_text(encoding="utf-8", errors="replace").strip():
        return {"status": "skipped", "reason": "candidate patch.diff missing or empty"}

    child_root = Path(tempfile.mkdtemp(prefix="meta_loop_child_eval."))
    child_ws = child_root / "workspace"
    shutil.copytree(ROOT, child_ws, ignore=ignore_workspace, symlinks=True)
    run_cmd(["git", "init", "--quiet"], cwd=child_ws)
    run_cmd(["git", "config", "user.name", "meta-loop-child-eval"], cwd=child_ws)
    run_cmd(["git", "config", "user.email", "meta-loop-child-eval@localhost"], cwd=child_ws)
    run_cmd(["git", "add", "."], cwd=child_ws)
    run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=child_ws)

    parent_source_materialization = materialize_child_parent_source(child_ws, parent_agent_card)
    if parent_source_materialization.get("status") == "failed":
        return {
            "status": "parent_source_materialization_failed",
            "parent_source_materialization": parent_source_materialization,
            "workspace": str(child_ws),
        }

    try:
        child_prompt = materialize_child_parent_prompt(child_ws, prompt_path)
    except FileNotFoundError as exc:
        return {"status": "child_prompt_materialization_failed", "reason": str(exc), "workspace": str(child_ws), "parent_source_materialization": parent_source_materialization}

    # The candidate patch is defined against the canonical data-agent prompt path.
    # Baseline must include the selected parent source helpers and parent prompt before applying the candidate patch.
    run_cmd(["git", "add", "."], cwd=child_ws)
    run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=child_ws)
    apply_proc = run_cmd(["git", "apply", str(patch_path)], cwd=child_ws)
    if apply_proc.returncode != 0:
        return {"status": "patch_apply_failed", "stderr": apply_proc.stderr}
    child_prompt = child_ws / DATA_AGENT_CANONICAL_PROMPT

    child_version = f"meta_loop_child_iter{iteration:03d}_{utc_now_slug()}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(child_ws)
    proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(child_ws / "experiments/run_dab_agent.py"),
            "--case-dir",
            str(case_dir),
            "--prompt",
            str(child_prompt),
            "--version",
            child_version,
            "--dab-root",
            str(dab_root),
            "--timeout-sec",
            str(timeout_sec),
        ],
        cwd=child_ws,
        env=env,
        stdout_path=loop_dir / "child_run.stdout",
        stderr_path=loop_dir / "child_run.stderr",
    )
    # run_dab_agent writes under child_ws/logs; find newest matching run.
    run_dirs = sorted((child_ws / "logs/dab_agent").glob(f"*{child_version}*"), key=lambda p: p.stat().st_mtime)
    if not run_dirs:
        return {"status": "child_run_failed_no_run_dir", "exit_code": proc.returncode, "workspace": str(child_ws)}
    child_run_dir = run_dirs[-1]
    child_analysis = analyze_run_quiet(
        child_run_dir,
        loop_dir / "child_analyze.stdout",
        loop_dir / "child_analyze.stderr",
    )
    child_signal = extract_primary_signal(child_run_dir / "agent_error_summary.json")
    child_eval_dir = candidate_dir / "child_eval"
    child_eval_dir.mkdir(parents=True, exist_ok=True)
    child_feedback = build_fine_grained_feedback_pack(
        child_run_dir,
        primary_signal=child_signal,
        max_trace_events=12,
    )
    child_feedback = adapt_feedback_for_repair_profile(child_feedback, "data_agent_tool_repair")
    child_helper_repair_plan = plan_helper_repair(child_feedback, "data_agent_tool_repair")
    child_feedback["helper_repair_plan"] = child_helper_repair_plan
    child_feedback_json_path = child_eval_dir / "child_fine_grained_evidence_pack.json"
    child_feedback_md_path = child_eval_dir / "child_fine_grained_evidence_pack.md"
    write_pack(child_feedback, child_feedback_json_path, child_feedback_md_path)
    next_repair_seed = {
        "seed_id": f"next_data_agent_repair_seed_iter{iteration:03d}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "child_eval_fine_grained_feedback",
        "parent_candidate_dir": str(candidate_dir),
        "child_run_dir": str(child_run_dir),
        "selected_stage": child_feedback.get("selected_stage"),
        "selected_signal": child_feedback.get("selected_signal"),
        "analysis_summary": {
            "passed": child_analysis.get("passed"),
            "validation_reason": child_analysis.get("validation_reason"),
        },
        "repair_profile": "data_agent_tool_repair",
        "repair_routing": child_feedback.get("repair_routing"),
        "helper_repair_plan": child_helper_repair_plan,
        "answer_delta": child_feedback.get("answer_delta"),
        "fine_grained_feedback": {
            "feedback_type": child_feedback.get("feedback_type"),
            "source_run_dir": child_feedback.get("source_run_dir"),
            "selected_stage": child_feedback.get("selected_stage"),
            "selected_signal": child_feedback.get("selected_signal"),
            "repair_routing": child_feedback.get("repair_routing"),
            "helper_repair_plan": child_helper_repair_plan,
            "parent_capabilities": child_feedback.get("parent_capabilities"),
            "answer_delta": child_feedback.get("answer_delta"),
            "runtime_trace_evidence": (child_feedback.get("runtime_trace_evidence") or [])[:8],
            "ranked_feedback_signals": (child_feedback.get("ranked_feedback_signals") or [])[:5],
            "repair_constraints": child_feedback.get("repair_constraints"),
            "next_repair_focus": child_feedback.get("next_repair_focus"),
            "full_evidence_pack_paths": {
                "json": str(child_feedback_json_path),
                "markdown": str(child_feedback_md_path),
            },
        },
    }
    next_repair_seed_path = child_eval_dir / "next_data_agent_repair_seed.json"
    write_json(next_repair_seed_path, next_repair_seed)
    helper_usage = generated_code_uses_helper(
        child_run_dir / "generated_solve.py",
        candidate_patents_helper_modules(candidate_dir),
    )
    child_failure_gates: list[str] = []
    if helper_usage.get("status") != "helper_called_by_child_generated_code" and helper_usage.get("required"):
        child_failure_gates.append(str(helper_usage.get("status") or "helper_not_used_by_child_generated_code"))
    final_answer_dependency = helper_usage.get("final_answer_dependency") if isinstance(helper_usage.get("final_answer_dependency"), dict) else {}
    if (
        final_answer_dependency.get("required")
        and final_answer_dependency.get("status") != "helper_output_used_for_final_answer"
    ):
        child_failure_gates.append(str(final_answer_dependency.get("status") or "helper_output_not_used_for_final_answer"))
    try:
        from experiments.meta_agent_cycle import compute_answer_metrics

        child_answer_metrics = compute_answer_metrics(child_analysis.get("validation_reason"))
    except Exception:
        child_answer_metrics = {"status": "unavailable"}
    parent_answer_metrics = {}
    evals = (parent_agent_card or {}).get("evals") if isinstance((parent_agent_card or {}).get("evals"), dict) else {}
    for item in evals.values() if isinstance(evals, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("answer_metrics"), dict):
            parent_answer_metrics = item.get("answer_metrics") or {}
            break
    try:
        child_f1 = float(child_answer_metrics.get("f1") or 0.0)
        parent_f1 = float(parent_answer_metrics.get("f1") or 0.0)
        child_pred = int(child_answer_metrics.get("predicted_count") or 0)
        parent_pred = int(parent_answer_metrics.get("predicted_count") or 0)
    except Exception:
        child_f1 = parent_f1 = 0.0
        child_pred = parent_pred = 0
    if parent_f1 > 0 and (child_f1 <= 0 or (parent_pred > 0 and child_pred > max(parent_pred * 5, parent_pred + 100))):
        child_failure_gates.append("severe_child_answer_regression")
    child_failure_gate = child_failure_gates[0] if child_failure_gates else None
    changed_files_for_open_diagnosis: list[str] = []
    patch_numstat = candidate_dir / "patch_numstat.txt"
    if patch_numstat.exists():
        for line in patch_numstat.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                changed_files_for_open_diagnosis.append(parts[2])
    open_diagnosis_evidence = build_open_diagnosis_evidence(
        candidate_dir=candidate_dir,
        parent_candidate_dir=Path(str(parent_agent_card.get("candidate_dir"))) if isinstance(parent_agent_card, dict) and parent_agent_card.get("candidate_dir") else None,
        child_run_dir=child_run_dir,
        child_analysis=child_analysis,
        child_signal=child_signal,
        child_feedback=child_feedback,
        child_answer_metrics=child_answer_metrics,
        parent_answer_metrics=parent_answer_metrics,
        helper_usage=helper_usage,
        child_failure_gates=child_failure_gates,
        changed_files=changed_files_for_open_diagnosis,
    )
    next_repair_seed["open_diagnosis_evidence"] = open_diagnosis_evidence
    if isinstance(next_repair_seed.get("fine_grained_feedback"), dict):
        next_repair_seed["fine_grained_feedback"]["open_diagnosis_evidence"] = compact_open_diagnosis_evidence(open_diagnosis_evidence)
    write_json(next_repair_seed_path, next_repair_seed)
    child_eval_passed = bool(child_analysis.get("passed")) and not child_failure_gates
    report = {
        "status": "completed",
        "final_status": "candidate_child_eval_passed" if child_eval_passed else "candidate_child_eval_failed",
        "workspace": str(child_ws),
        "parent_source_materialization": parent_source_materialization,
        "child_run_dir": str(child_run_dir),
        "child_run_exit_code": proc.returncode,
        "child_answer_metrics": child_answer_metrics,
        "parent_answer_metrics": parent_answer_metrics,
        "child_failure_gates": child_failure_gates,
        "child_passed": child_eval_passed,
        "child_original_dab_passed": child_analysis.get("passed"),
        "child_validation_reason": child_analysis.get("validation_reason"),
        "child_selected_stage": child_signal.get("selected_component"),
        "child_selected_signal": child_signal.get("selected_signal"),
        "child_fine_grained_feedback_pack": {
            "json": str(child_feedback_json_path),
            "markdown": str(child_feedback_md_path),
        },
        "next_data_agent_repair_seed": str(next_repair_seed_path),
        "child_helper_repair_plan": child_helper_repair_plan,
        "helper_usage": helper_usage,
        "open_diagnosis_evidence": open_diagnosis_evidence,
        "child_failure_gate": child_failure_gate,
        "child_status": {
            "status": "completed",
            "passed_original_dab_validation": child_analysis.get("passed"),
            "validation_reason": child_analysis.get("validation_reason"),
            "selected_stage": child_feedback.get("selected_stage"),
            "selected_signal": child_feedback.get("selected_signal"),
            "helper_usage_status": helper_usage.get("status"),
            "child_failure_gate": child_failure_gate,
        },
    }
    write_json(child_eval_dir / "generic_child_eval_report.json", report)
    write_json(child_eval_dir / "child_eval_report.json", report)
    return report


def scope_note_for_candidate_type(candidate_type: str) -> str:
    if candidate_type == "data_agent_repair":
        return "Data-agent prompt repair candidate; not feedback analyzer infrastructure repair."
    if candidate_type == "feedback_analyzer_repair":
        return "Feedback/error-analysis infrastructure repair only; not a PATENTS answer solver repair."
    return f"Candidate type: {candidate_type}."


def postprocess_candidate(
    *,
    candidate_dir: Path,
    archive_root: Path,
    parent_agent_id: str,
    candidate_type: str,
    case_id: str,
) -> int:
    proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            "experiments/meta_agent_cycle.py",
            "postprocess-candidate",
            "--candidate-dir",
            str(candidate_dir),
            "--archive-root",
            str(archive_root),
            "--parent-agent-id",
            parent_agent_id,
            "--candidate-type",
            candidate_type,
            "--scope-note",
            scope_note_for_candidate_type(candidate_type),
            "--case-id",
            case_id,
        ],
        cwd=ROOT,
    )
    return proc.returncode


def run_loop(args: argparse.Namespace) -> int:
    archive_root = Path(args.archive_root).resolve()
    loop_root = Path(args.loop_root).resolve()
    loop_root.mkdir(parents=True, exist_ok=True)
    loop_dir = loop_root / f"meta_agent_loop_{utc_now_slug()}"
    loop_dir.mkdir(parents=True, exist_ok=False)

    parent_history: list[str] = []
    parent = select_parent_agent(
        archive_root,
        args.parent_agent_id,
        max_age_hours=args.archive_max_parent_age_hours,
        repeated_parent_ids=parent_history,
        repeated_parent_penalty=args.repeated_parent_penalty,
        source_lineage_family=args.source_lineage_family or None,
    )
    parent_agent_id = parent["card"]["agent_id"]
    initial_parent_agent_id = parent_agent_id
    meta_agent = select_meta_agent(archive_root, args.meta_agent_id)
    meta_agent_id = meta_agent["card"]["agent_id"] if meta_agent else None
    prompt_path = prompt_for_parent(parent, Path(args.prompt) if args.prompt else None)
    case_dir = Path(args.case_dir).resolve()
    dab_root = Path(args.dab_root).resolve()
    parent_materialization_preflight = preflight_parent_materialization(parent["card"])
    plan = {
        "status": "planned",
        "mode": args.mode,
        "iterations": args.iterations,
        "loop_dir": str(loop_dir),
        "selected_parent_agent": parent_agent_id,
        "selected_meta_agent_protocol": meta_agent_id,
        "prompt_path": str(prompt_path),
        "case_dir": str(case_dir),
        "dab_root": str(dab_root),
        "candidate_launcher": args.candidate_launcher,
        "candidate_id_prefix": args.candidate_id_prefix,
        "repair_profile": args.repair_profile,
        "parent_materialization_preflight": parent_materialization_preflight,
        "parent_selection_policy": {
            "initial_parent_override": args.parent_agent_id,
            "subsequent_iterations": "select parent_pool via archive_selector after candidate postprocess",
            "archive_max_parent_age_hours": args.archive_max_parent_age_hours,
            "repeated_parent_penalty": args.repeated_parent_penalty,
            "source_lineage_family": args.source_lineage_family or None,
        },
        "stages": [
            "select_parent_pool_from_archive_selector",
            "select_evidence_pool_from_archive_selector",
            "select_meta_agent_protocol_from_archive",
            "run_or_reuse_parent_dab_tool_agent",
            "analyze_parent_tool_agent_trace_and_seed_repair",
            "invoke_candidate_launcher",
            "optional_dab_tool_agent_child_eval",
            "postprocess_candidate_archive",
            "select_next_parent_from_archive_top_ranked",
        ],
    }
    write_json(loop_dir / "loop_plan.json", plan)
    if parent_materialization_preflight.get("status") == "failed":
        raise RuntimeError(f"selected parent materialization preflight failed: {parent_materialization_preflight}")
    if args.mode == "dry-run":
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    parent_run = Path(args.parent_run).resolve() if args.parent_run else None
    results: list[dict[str, Any]] = []
    for iteration in range(1, args.iterations + 1):
        iteration_dir = loop_dir / f"iteration_{iteration:03d}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            iteration_dir / "selected_agents.json",
            {
                "data_parent_agent_id": parent_agent_id,
                "meta_agent_protocol_id": meta_agent_id,
                "data_parent_card": parent["card"],
                "meta_agent_card": meta_agent["card"] if meta_agent else None,
                "parent_selection_score": parent.get("selection_score"),
            },
        )
        if parent_run is None or args.rerun_parent_each_iteration:
            parent_run = run_parent_case(
                case_dir=case_dir,
                prompt_path=prompt_path,
                version=f"meta_loop_parent_iter{iteration:03d}_{utc_now_slug()}",
                dab_root=dab_root,
                timeout_sec=args.timeout_sec,
                parent_agent_card=parent["card"],
                loop_dir=iteration_dir,
            )
        if args.repair_seed:
            seed_path = Path(args.repair_seed).resolve()
            if not seed_path.exists():
                raise SystemExit(f"repair_seed not found: {seed_path}")
            seed = load_json(seed_path) or {}
            archive_selection = attach_archive_selection_to_seed(
                seed=seed,
                seed_path=seed_path,
                archive_root=archive_root,
                loop_dir=iteration_dir,
                repeated_parent_ids=parent_history,
            )
            attach_recent_loop_handoffs_to_seed(seed, seed_path, archive_root, iteration_dir)
            write_json(
                iteration_dir / "repair_seed_override.json",
                {
                    "status": "using_repair_seed_override_skip_parent_analysis",
                    "override_seed_path": str(seed_path),
                    "override_seed": seed,
                    "parent_analysis_seed_path": None,
                    "parent_run": str(parent_run),
                    "archive_selection_path": str(iteration_dir / "archive_selection.json"),
                    "reason": "Explicit repair_seed is authoritative; skip legacy parent analyzer so DAB tool-agent runs without result.json are supported.",
                },
            )
        else:
            seed, seed_path = analyze_and_seed(
                run_dir=parent_run,
                loop_dir=iteration_dir,
                candidate_context={"parent_agent_id": parent_agent_id, "iteration": iteration, "repair_profile": args.repair_profile},
            )
            archive_selection = attach_archive_selection_to_seed(
                seed=seed,
                seed_path=seed_path,
                archive_root=archive_root,
                loop_dir=iteration_dir,
                repeated_parent_ids=parent_history,
            )
            attach_recent_loop_handoffs_to_seed(seed, seed_path, archive_root, iteration_dir)
        candidate_id = candidate_id_for(args.candidate_id_prefix, iteration)
        candidate_dir = ROOT / "candidates/dab" / candidate_id
        launcher_exit = None
        if args.candidate_launcher:
            launcher_exit = run_candidate_launcher(
                launcher=Path(args.candidate_launcher).resolve(),
                candidate_id=candidate_id,
                candidate_dir=candidate_dir,
                seed_path=seed_path,
                parent_run=parent_run,
                parent_agent_id=parent_agent_id,
                parent_prompt=prompt_path,
                case_dir=case_dir,
                dab_root=dab_root,
                loop_dir=iteration_dir,
                env_candidate_id_name=args.candidate_id_env,
                repair_profile=args.repair_profile,
                repair_seed_override=bool(args.repair_seed),
            )
        else:
            write_json(
                iteration_dir / "awaiting_candidate_launcher.json",
                {
                    "status": "awaiting_candidate_launcher",
                    "candidate_id": candidate_id,
                    "seed_path": str(seed_path),
                    "message": "Provide --candidate-launcher to generate and validate a candidate.",
                },
            )
            results.append(
                {
                    "iteration": iteration,
                    "status": "awaiting_candidate_launcher",
                    "parent_run": str(parent_run),
                    "seed_path": str(seed_path),
                    "candidate_id": candidate_id,
                    "candidate_dir": str(candidate_dir),
                }
            )
            break

        child_eval = None
        if launcher_exit == 0 and args.run_generic_child_eval:
            if is_dab_tool_agent_workflow_seed(seed):
                child_eval = run_dab_tool_agent_child_eval(
                    candidate_dir=candidate_dir,
                    case_dir=case_dir,
                    dab_root=dab_root,
                    loop_dir=iteration_dir,
                    iteration=iteration,
                    parent_agent_card=parent["card"],
                    parent_prompt=prompt_path,
                    repair_seed=seed,
                )
            else:
                child_eval = run_generic_child_eval(
                    candidate_dir=candidate_dir,
                    case_dir=case_dir,
                    prompt_path=prompt_path,
                    dab_root=dab_root,
                    timeout_sec=args.timeout_sec,
                    loop_dir=iteration_dir,
                    iteration=iteration,
                    parent_agent_card=parent["card"],
                )

        postprocess_exit = None
        if candidate_dir.exists():
            postprocess_exit = postprocess_candidate(
                candidate_dir=candidate_dir,
                archive_root=archive_root,
                parent_agent_id=parent_agent_id,
                candidate_type=args.candidate_type,
                case_id=args.case_id,
            )

        handoff_path = None
        if candidate_dir.exists():
            handoff = build_iteration_handoff(
                archive_root=archive_root,
                loop_dir=loop_dir,
                iteration_dir=iteration_dir,
                iteration=iteration,
                candidate_dir=candidate_dir,
                candidate_id=candidate_id,
                parent_agent_id=parent_agent_id,
                meta_agent_id=meta_agent_id,
                parent_run=parent_run,
                seed_path=seed_path,
                launcher_exit=launcher_exit,
                child_eval=child_eval,
                postprocess_exit=postprocess_exit,
            )
            handoff_path = record_iteration_handoff(archive_root, handoff, iteration_dir)

        results.append(
            {
                "iteration": iteration,
                "candidate_id": candidate_id,
                "candidate_dir": str(candidate_dir),
                "data_parent_agent_id": parent_agent_id,
                "meta_agent_protocol_id": meta_agent_id,
                "parent_run": str(parent_run),
                "seed": seed,
                "archive_selection_path": str(iteration_dir / "archive_selection.json"),
                "launcher_exit_code": launcher_exit,
                "child_eval": child_eval,
                "postprocess_exit_code": postprocess_exit,
                "next_iteration_handoff": str(handoff_path) if handoff_path else None,
            }
        )

        parent_history.append(parent_agent_id)
        if iteration < args.iterations:
            next_parent = select_parent_agent(
                archive_root,
                None,
                max_age_hours=args.archive_max_parent_age_hours,
                repeated_parent_ids=parent_history,
                repeated_parent_penalty=args.repeated_parent_penalty,
            )
            write_json(
                iteration_dir / "next_parent_selection.json",
                {
                    "status": "selected_from_archive_selector_parent_pool",
                    "previous_parent_agent_id": parent_agent_id,
                    "next_parent_agent_id": next_parent["card"]["agent_id"],
                    "selection_score": next_parent.get("selection_score"),
                    "parent_history": parent_history,
                    "policy": "archive_selector_parent_pool_after_candidate_postprocess_with_repeated_parent_penalty",
                    "archive_max_parent_age_hours": args.archive_max_parent_age_hours,
                    "repeated_parent_penalty": args.repeated_parent_penalty,
                },
            )
            parent = next_parent
            parent_agent_id = parent["card"]["agent_id"]
            prompt_path = prompt_for_parent(parent, Path(args.prompt) if args.prompt else None)
            parent_run = None
        else:
            write_json(
                iteration_dir / "next_parent_selection.json",
                {
                    "status": "skipped_final_iteration",
                    "previous_parent_agent_id": parent_agent_id,
                    "next_parent_agent_id": None,
                    "parent_history": parent_history,
                    "policy": "next_parent_selection_only_required_before_a_following_iteration",
                    "archive_max_parent_age_hours": args.archive_max_parent_age_hours,
                    "repeated_parent_penalty": args.repeated_parent_penalty,
                },
            )

    summary = {
        "status": "completed",
        "loop_dir": str(loop_dir),
        "selected_initial_parent_agent": initial_parent_agent_id,
        "selected_next_parent_agent": parent_agent_id,
        "selected_meta_agent_protocol": meta_agent_id,
        "results": results,
    }
    summary_path = loop_dir / "loop_summary.json"
    write_json(summary_path, summary)
    terminal_summary = {
        "status": summary["status"],
        "loop_dir": str(loop_dir),
        "loop_summary": str(summary_path),
        "selected_initial_parent_agent": initial_parent_agent_id,
        "selected_next_parent_agent": parent_agent_id,
        "selected_meta_agent_protocol": meta_agent_id,
        "iterations": [
            {
                "iteration": item.get("iteration"),
                "candidate_id": item.get("candidate_id"),
                "candidate_dir": item.get("candidate_dir"),
                "parent_run": item.get("parent_run"),
                "seed_path": item.get("seed_path") or str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "repair_seed.json"),
                "launcher_exit_code": item.get("launcher_exit_code"),
                "child_eval_status": (item.get("child_eval") or {}).get("final_status") or (item.get("child_eval") or {}).get("status"),
                "child_selected_stage": (item.get("child_eval") or {}).get("child_selected_stage"),
                "postprocess_exit_code": item.get("postprocess_exit_code"),
                "logs": {
                    "candidate_launcher_stdout": str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "candidate_launcher.stdout"),
                    "candidate_launcher_stderr": str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "candidate_launcher.stderr"),
                    "parent_analyze_stdout": str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "parent_analyze.stdout"),
                    "child_run_stdout": str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "child_run.stdout"),
                    "child_analyze_stdout": str(loop_dir / f"iteration_{item.get('iteration', 0):03d}" / "child_analyze.stdout"),
                },
            }
            for item in results
        ],
    }
    print(json.dumps(terminal_summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["dry-run", "run"], default="dry-run")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--loop-root", default=str(ROOT / "trajectories/meta_agent_loops"))
    parser.add_argument("--parent-agent-id", help="Initial parent override for the first iteration only; later iterations reselect the current top-ranked archive parent.")
    parser.add_argument("--archive-max-parent-age-hours", type=float, default=24.0, help="Only auto-select data-agent parents whose archive agent_card was modified within this many hours; <=0 disables the freshness filter. Explicit --parent-agent-id bypasses this for the first iteration.")
    parser.add_argument("--repeated-parent-penalty", type=float, default=0.15, help="Subtract this score per prior use of the same parent inside the current loop when selecting the next parent.")
    parser.add_argument("--source-lineage-family", default=os.environ.get("META_LOOP_SOURCE_LINEAGE_FAMILY", "dab_tool_agent_workflow"), help="Restrict automatic parent selection to one source lineage family; use empty string to disable.")
    parser.add_argument("--meta-agent-id")
    parser.add_argument("--prompt")
    parser.add_argument("--case-id", default="PATENTS_query1")
    parser.add_argument("--case-dir", default=str(DEFAULT_CASE_DIR))
    parser.add_argument("--dab-root", default=str(DEFAULT_DAB_ROOT))
    parser.add_argument("--parent-run", help="Reuse an existing parent run instead of running the data agent.")
    parser.add_argument("--repair-seed", help="Use an existing repair seed for candidate generation instead of the parent-selected signal.")
    parser.add_argument("--rerun-parent-each-iteration", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--candidate-launcher", help="Single-candidate launcher invoked by the loop.")
    parser.add_argument("--candidate-id-prefix", default="codex_qwen_patents_iter004_data_agent_repair")
    parser.add_argument("--candidate-id-env", default="ITER004_CANDIDATE_ID")
    parser.add_argument("--candidate-type", default="data_agent_repair")
    parser.add_argument("--repair-profile", default="data_agent_prompt_repair", choices=["data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair", "analyzer_infra_repair"], help="Repair profile passed to the candidate launcher. Use data_agent_tool_repair to prefer reusable adapters/patents helper scripts, or data_agent_project_repair for broader safe project-source edits.")
    parser.add_argument("--run-generic-child-eval", action="store_true", help="Run child eval after candidate generation. For DAB tool-agent seeds this uses the DAB tool-agent child eval; legacy generated_solve eval is only used for legacy seeds.")
    parser.set_defaults(func=run_loop)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
