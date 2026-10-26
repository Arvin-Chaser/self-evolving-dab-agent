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
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.archive_selector import select_from_archive
from experiments.evidence_sufficiency import assess_evidence_sufficiency
from experiments.open_diagnosis import build_open_diagnosis_evidence, compact_open_diagnosis_evidence
from experiments.near_miss_causal_diagnosis import build_near_miss_causal_diagnosis


DEFAULT_ARCHIVE = ROOT / "archive"
DEFAULT_CASE_DIR = Path("/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1")
DEFAULT_DAB_ROOT = Path("/home/m0st1ma/research/DataAgentBench")
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


DEFAULT_MULTI_QUERY_BATCH = ROOT / "dab_corpus/batches/multi_query_patents_stockindex_001.json"


def valid_multi_query_batch(batch: Any) -> bool:
    if not isinstance(batch, dict):
        return False
    query_ids = batch.get("query_ids")
    return isinstance(query_ids, list) and any(str(item).strip() for item in query_ids)


def load_multi_query_batch(path: Path) -> dict[str, Any]:
    batch = safe_load_json(path)
    if valid_multi_query_batch(batch):
        batch = dict(batch)
        batch.setdefault("recovered_from", str(path))
        return batch
    return {}


def read_text_tail(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def recover_multi_query_batch_from_seed(seed: dict[str, Any]) -> dict[str, Any]:
    """Return a runnable multi-query batch for child eval.

    Full child rerun requires query_ids.  Handoff seeds from failed candidates
    can be compact and may lose the original batch, so recover it from several
    lineage locations before falling back to the disk-safe local smoke batch.
    """
    batch = seed.get("batch") if isinstance(seed.get("batch"), dict) else {}
    if valid_multi_query_batch(batch):
        return batch

    batch_id = str(seed.get("batch_id") or "").strip()
    if batch_id:
        for candidate_path in (
            ROOT / "dab_corpus/batches" / f"{batch_id}.json",
            ROOT / "dab_corpus/batches" / batch_id,
        ):
            recovered_batch = load_multi_query_batch(candidate_path)
            if recovered_batch:
                return recovered_batch

    for key in ("source_candidate_dir", "parent_candidate_dir", "source_candidate"):
        candidate_dir = seed.get(key)
        if not candidate_dir:
            continue
        candidate_path = Path(str(candidate_dir))
        if not candidate_path.is_absolute():
            candidate_path = ROOT / candidate_path
        for seed_path in (
            candidate_path / "child_eval/next_data_agent_repair_seed.json",
            candidate_path / "next_data_agent_repair_seed.json",
            candidate_path / "child_eval/child_eval_report.json",
        ):
            report = safe_load_json(seed_path)
            recovered_batch = report.get("batch") if isinstance(report.get("batch"), dict) else {}
            if valid_multi_query_batch(recovered_batch):
                recovered_batch = dict(recovered_batch)
                recovered_batch.setdefault("recovered_from", str(seed_path))
                return recovered_batch
            recovered: list[str] = []
            for item in report.get("per_query_results") or report.get("per_query_feedback") or []:
                if not isinstance(item, dict):
                    continue
                query_id = str(item.get("query_id") or "").strip()
                if query_id and query_id not in recovered:
                    recovered.append(query_id)
            if recovered:
                return {
                    "schema_version": "dab_query_batch_v001",
                    "batch_id": str(seed.get("batch_id") or report.get("batch_id") or "recovered_child_eval_batch"),
                    "query_ids": recovered,
                    "recovered_from": str(seed_path),
                }

    default_batch = load_multi_query_batch(DEFAULT_MULTI_QUERY_BATCH)
    if default_batch:
        default_batch["recovery_reason"] = "seed_missing_batch_query_ids"
        return default_batch

    return {}


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


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def build_near_miss_refinement_mode(seed: dict[str, Any]) -> dict[str, Any]:
    """Describe whether the next repair should be a near-miss boundary refinement.

    This is intentionally a routing/evidence attribute, not a deterministic
    repair recipe.  The meta-agent should still infer the causal mechanism, but
    when the answer is already close it should focus on the observed boundary
    errors instead of broad prompt/helper rewrites.
    """
    quality = answer_quality_from_feedback(seed)
    f1 = _float_or_none(quality.get("f1"))
    missing_count = _int_or_none(quality.get("missing_count"))
    extra_count = _int_or_none(quality.get("extra_count"))
    strict_match_passed = quality.get("strict_match_passed")
    missing_codes = quality.get("missing_codes_sample") if isinstance(quality.get("missing_codes_sample"), list) else []
    extra_codes = quality.get("extra_codes_sample") if isinstance(quality.get("extra_codes_sample"), list) else []
    active = bool(
        strict_match_passed is False
        and f1 is not None
        and f1 >= 0.90
        and missing_count is not None
        and extra_count is not None
        and missing_count <= 5
        and extra_count <= 5
    )
    return {
        "schema_version": "near_miss_refinement_mode_v001",
        "mode": "near_miss_refinement" if active else "normal_repair",
        "active": active,
        "activation_criteria": {
            "strict_match_passed": False,
            "f1_min": 0.90,
            "missing_count_max": 5,
            "extra_count_max": 5,
        },
        "observed": {
            "strict_match_passed": strict_match_passed,
            "f1": f1,
            "precision": _float_or_none(quality.get("precision")),
            "recall": _float_or_none(quality.get("recall")),
            "expected_count": _int_or_none(quality.get("expected_count")),
            "predicted_count": _int_or_none(quality.get("predicted_count")),
            "true_positive_count": _int_or_none(quality.get("true_positive_count")),
            "missing_count": missing_count,
            "extra_count": extra_count,
            "boundary_error_count": (missing_count + extra_count) if missing_count is not None and extra_count is not None else None,
            "strict_match_reason_excerpt": str(quality.get("strict_match_reason") or quality.get("strict_match_reason_excerpt") or "")[:800],
        },
        "targeted_boundary_codes": {
            "missing_codes_sample": missing_codes[:12],
            "extra_codes_sample": extra_codes[:12],
        },
        "meta_agent_instructions": [
            "Treat this as a boundary-refinement repair, not a broad parser/prompt rewrite.",
            "First inspect why the current helper/workflow excludes the missing codes and includes the extra codes.",
            "Prefer a small reusable helper/filter/ranking/tie-breaker change plus minimal prompt glue.",
            "Do not hardcode the exact expected answer list or blindly append/remove the diagnostic missing/extra samples.",
            "Validate by rerunning the child workflow and comparing the new missing/extra counts against this near-miss baseline.",
        ] if active else [
            "Near-miss refinement is inactive; use the normal open diagnosis and repair loop.",
        ],
    }


def attach_repair_mode_to_seed(seed: dict[str, Any], seed_path: Path | None = None) -> dict[str, Any]:
    mode = build_near_miss_refinement_mode(seed)
    diagnosis = build_near_miss_causal_diagnosis(seed)
    seed["repair_mode"] = mode
    seed["near_miss_refinement"] = mode
    seed["near_miss_causal_diagnosis"] = diagnosis
    fine = seed.setdefault("fine_grained_feedback", {})
    if isinstance(fine, dict):
        fine["repair_mode"] = mode
        fine["near_miss_refinement"] = mode
        fine["near_miss_causal_diagnosis"] = diagnosis
    if isinstance(mode, dict):
        mode["causal_diagnosis_available"] = diagnosis.get("available")
        mode["causal_diagnosis_active"] = diagnosis.get("active")
    if seed_path is not None:
        write_json(seed_path, seed)
    return mode


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
    if stdout_path:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
    if stderr_path:
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout = stdout_path.open("w", encoding="utf-8") if stdout_path else subprocess.PIPE
    stderr = stderr_path.open("w", encoding="utf-8") if stderr_path else subprocess.PIPE
    try:
        return subprocess.run(args, cwd=cwd, env=env, text=True, stdout=stdout, stderr=stderr, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        if stderr_path:
            stderr.write(message + "\n")
            stderr_value = None
        else:
            stderr_value = message
        stdout_value = None if stdout_path else ""
        return subprocess.CompletedProcess(args, 127, stdout_value, stderr_value)
    finally:
        if stdout_path:
            stdout.close()
        if stderr_path:
            stderr.close()


LLM_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)


def normalize_llm_network_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    aliases = {
        "": "auto",
        "none": "direct",
        "no_proxy": "direct",
        "noproxy": "direct",
        "wsl_proxy": "proxy",
        "system": "inherited",
        "env": "inherited",
    }
    return aliases.get(mode, mode)


def llm_preflight_network_modes(env: dict[str, str]) -> list[str]:
    requested = normalize_llm_network_mode(env.get("META_LOOP_LLM_NETWORK_MODE", "auto"))
    if requested != "auto":
        return [requested]
    raw_order = env.get("META_LOOP_LLM_NETWORK_ORDER", "direct,proxy,inherited")
    modes: list[str] = []
    for item in raw_order.split(","):
        mode = normalize_llm_network_mode(item)
        if mode and mode != "auto" and mode not in modes:
            modes.append(mode)
    return modes or ["direct", "proxy", "inherited"]


def apply_llm_network_env(env: dict[str, str], mode: str | None = None) -> dict[str, str]:
    """Apply one explicit network mode for DashScope/OpenAI-compatible LLM calls."""

    resolved = normalize_llm_network_mode(
        mode
        or env.get("META_LOOP_SELECTED_LLM_NETWORK_MODE")
        or env.get("META_LOOP_LLM_NETWORK_MODE", "auto")
    )
    if resolved == "auto":
        resolved = "proxy" if not env.get("META_LOOP_DISABLE_WSL_PROXY") else "inherited"
    if resolved == "direct":
        for key in LLM_PROXY_ENV_KEYS:
            env.pop(key, None)
        env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
        env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    elif resolved == "proxy":
        proxy_url = env.get("META_LOOP_WSL_PROXY_URL", "http://172.17.240.1:17891")
        for key in LLM_PROXY_ENV_KEYS:
            env[key] = proxy_url
        env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
        env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    elif resolved == "inherited":
        pass
    else:
        raise ValueError(f"Unsupported META_LOOP_LLM_NETWORK_MODE={resolved!r}; expected auto/direct/proxy/inherited")
    env["META_LOOP_EFFECTIVE_LLM_NETWORK_MODE"] = resolved
    return env


def selected_llm_run_env() -> dict[str, str]:
    return apply_llm_network_env(os.environ.copy())


def run_dab_tool_agent_llm_preflight(loop_dir: Path, label: str) -> dict[str, Any]:
    """Check the DataAgent LLM endpoint before spending a full parent/child run.

    The DAB tool-agent can fail before the first tool action when the DashScope/
    OpenAI-compatible endpoint is temporarily unreachable. Without this gate,
    the downstream analyzer sees an empty final answer and produces a misleading
    `missing_final_answer` seed. Keep this tiny and independent of Docker,
    Postgres, and query files: it only verifies that the configured data-agent
    model can return one short completion.
    """

    stdout_path = loop_dir / f"{label}_llm_preflight.stdout"
    stderr_path = loop_dir / f"{label}_llm_preflight.stderr"
    report_path = loop_dir / f"{label}_llm_preflight.json"
    base_env = os.environ.copy()
    base_env.setdefault("META_LOOP_LLM_PREFLIGHT_TIMEOUT_SEC", "30")
    base_env.setdefault("META_LOOP_LLM_PREFLIGHT_MAX_RETRIES", "2")
    outer_attempts = max(1, int(base_env.get("META_LOOP_LLM_PREFLIGHT_ATTEMPTS", "4")))
    outer_sleep_sec = max(0.0, float(base_env.get("META_LOOP_LLM_PREFLIGHT_RETRY_SLEEP_SEC", "5")))
    network_modes = llm_preflight_network_modes(base_env)
    code = r"""
import json
import os
import sys
import time

from openai import OpenAI


def first_env(names):
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value:
            return name, value
    return None, None


def normalize_openai_base_url(value):
    default = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if not value:
        return default
    base_url = value.strip()
    if not base_url:
        return default
    if "://" not in base_url:
        base_url = "https://" + base_url
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1") or base_url.endswith("/compatible-mode/v1"):
        return base_url
    return base_url + "/compatible-mode/v1"


key_env, api_key = first_env([
    os.getenv("DAB_TOOL_AGENT_API_KEY_ENV"),
    "DASHSCOPE_API_KEY",
    "dashscope_api_key",
    "BAILIAN_API_KEY",
    "DAB_TOOL_AGENT_API_KEY",
    "TOGETHER_API_KEY",
])
base_env, base_from_env = first_env([
    "DAB_TOOL_AGENT_OPENAI_BASE_URL",
    "DAB_TOOL_AGENT_BASE_URL",
    "DASHSCOPE_BASE_URL",
    "BAILIAN_BASE_URL",
])
base_url = normalize_openai_base_url(base_from_env)
model = os.getenv("DAB_TOOL_AGENT_MODEL", "glm-5.3-flash")
timeout = float(os.getenv("META_LOOP_LLM_PREFLIGHT_TIMEOUT_SEC", "30"))
max_retries = int(os.getenv("META_LOOP_LLM_PREFLIGHT_MAX_RETRIES", "0"))
started = time.time()
report = {
    "schema_version": "dab_tool_agent_llm_preflight_v001",
    "status": "unknown",
    "model": model,
    "provider": "openai_compatible",
    "api_key_env": key_env,
    "api_key_present": bool(api_key),
    "base_url_env": base_env,
    "base_url": base_url,
    "timeout_sec": timeout,
    "max_retries": max_retries,
}
if not api_key:
    report.update({
        "status": "failed",
        "failure_type": "missing_api_key",
        "error": "No data-agent API key visible. Set DASHSCOPE_API_KEY or DAB_TOOL_AGENT_API_KEY.",
        "elapsed_sec": round(time.time() - started, 3),
    })
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(2)
try:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Return exactly: ok"}],
        temperature=0,
        max_tokens=8,
        timeout=timeout,
    )
    content = response.choices[0].message.content or ""
    report.update({
        "status": "passed",
        "content_preview": content[:80],
        "elapsed_sec": round(time.time() - started, 3),
    })
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0)
except Exception as exc:
    report.update({
        "status": "failed",
        "failure_type": type(exc).__name__,
        "error": str(exc),
        "elapsed_sec": round(time.time() - started, 3),
    })
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(1)
"""
    attempts: list[dict[str, Any]] = []
    proc: subprocess.CompletedProcess[str] | None = None
    report: dict[str, Any] = {}
    selected_env: dict[str, str] | None = None
    selected_mode: str | None = None
    for network_mode in network_modes:
        env = apply_llm_network_env(base_env.copy(), network_mode)
        for attempt in range(1, outer_attempts + 1):
            attempt_stdout_path = loop_dir / f"{label}_llm_preflight_{network_mode}_attempt{attempt:02d}.stdout"
            attempt_stderr_path = loop_dir / f"{label}_llm_preflight_{network_mode}_attempt{attempt:02d}.stderr"
            proc = run_cmd(
                [str(ROOT / ".venv/bin/python"), "-c", code],
                cwd=ROOT,
                env=env,
                stdout_path=attempt_stdout_path,
                stderr_path=attempt_stderr_path,
            )
            stdout_text = attempt_stdout_path.read_text(encoding="utf-8", errors="replace").strip() if attempt_stdout_path.exists() else ""
            try:
                attempt_report = json.loads(stdout_text.splitlines()[-1]) if stdout_text else {}
            except Exception:
                attempt_report = {
                    "schema_version": "dab_tool_agent_llm_preflight_v001",
                    "status": "failed",
                    "failure_type": "invalid_preflight_output",
                    "error": stdout_text[:1000],
                }
            attempt_report.setdefault("schema_version", "dab_tool_agent_llm_preflight_v001")
            attempt_report.setdefault("status", "passed" if proc.returncode == 0 else "failed")
            attempt_report["network_mode"] = network_mode
            attempt_report["attempt"] = attempt
            attempt_report["exit_code"] = proc.returncode
            attempt_report["stdout_path"] = str(attempt_stdout_path)
            attempt_report["stderr_path"] = str(attempt_stderr_path)
            attempts.append(attempt_report)
            report = dict(attempt_report)
            if proc.returncode == 0 and report.get("status") == "passed":
                selected_env = env
                selected_mode = network_mode
                break
            if attempt < outer_attempts and outer_sleep_sec > 0:
                time.sleep(outer_sleep_sec * attempt)
        if selected_mode:
            break
    stdout_path.write_text(json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    report.setdefault("schema_version", "dab_tool_agent_llm_preflight_v001")
    report["label"] = label
    report["attempts"] = attempts
    report["network_mode_order"] = network_modes
    if selected_mode:
        report["selected_network_mode"] = selected_mode
        os.environ["META_LOOP_SELECTED_LLM_NETWORK_MODE"] = selected_mode
    report["outer_attempt_count"] = len(attempts)
    report["outer_attempt_limit"] = outer_attempts
    report_env = selected_env if selected_env is not None else apply_llm_network_env(base_env.copy(), network_modes[-1] if network_modes else "inherited")
    report["proxy_env"] = {
        "http_proxy": report_env.get("http_proxy"),
        "https_proxy": report_env.get("https_proxy"),
        "no_proxy": report_env.get("no_proxy"),
    }
    if proc is not None:
        report["exit_code"] = proc.returncode
    report["stdout_path"] = str(stdout_path)
    report["stderr_path"] = str(stderr_path)
    if (proc is None or proc.returncode != 0) and report.get("status") == "passed":
        report["status"] = "failed"
    if report.get("status") != "passed":
        report.setdefault("final_status", "infra_failed_llm_connection")
    write_json(report_path, report)
    return report


def write_infra_failed_loop_summary(
    *,
    loop_dir: Path,
    results: list[dict[str, Any]],
    initial_parent_agent_id: str,
    parent_agent_id: str,
    meta_agent_id: str | None,
    preflight: dict[str, Any],
) -> int:
    summary = {
        "status": "infra_failed_llm_connection",
        "loop_dir": str(loop_dir),
        "selected_initial_parent_agent": initial_parent_agent_id,
        "selected_next_parent_agent": parent_agent_id,
        "selected_meta_agent_protocol": meta_agent_id,
        "llm_preflight": preflight,
        "results": results,
    }
    summary_path = loop_dir / "loop_summary.json"
    write_json(summary_path, summary)
    print(json.dumps({
        "status": summary["status"],
        "loop_dir": str(loop_dir),
        "loop_summary": str(summary_path),
        "llm_preflight": preflight,
    }, indent=2, ensure_ascii=False))
    return 2


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
    exclude_agent_ids: list[str] | None = None,
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
    exclude_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    excluded = set(exclude_agent_ids or [])
    if requested:
        if requested in excluded:
            raise SystemExit(f"requested parent is excluded by materialization preflight: {requested}")
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
        if card.get("agent_id") in excluded:
            continue
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

    if excluded:
        raise SystemExit(f"no selectable archive parent remains after excluding non-materializable parents: {sorted(excluded)}")
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
    env = selected_llm_run_env()
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
    if policy_path.exists() and not env.get("DAB_QUERY_WORKSPACE"):
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
    observer_feedback_path = loop_dir / "observer_fine_grained_feedback.json"
    observer_input_path = loop_dir / "observer_raw_behavior_input.json"
    observer_proc = run_cmd(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "experiments/run_fine_grained_observer_agent.py"),
            "--run-dir",
            str(run_dir),
            "--output",
            str(observer_feedback_path),
            "--behavior-input-output",
            str(observer_input_path),
        ],
        cwd=ROOT,
        env=selected_llm_run_env(),
        stdout_path=loop_dir / "parent_fine_grained_observer.stdout",
        stderr_path=loop_dir / "parent_fine_grained_observer.stderr",
    )
    observer_feedback = load_json(observer_feedback_path)
    evidence_sufficiency = assess_evidence_sufficiency(
        seed=meta_agent_seed if isinstance(meta_agent_seed, dict) else {},
        observer_feedback=observer_feedback if isinstance(observer_feedback, dict) else {},
    )
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
                "fine_grained_observer_exit_code": observer_proc.returncode,
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
                "observer_generated_feedback": observer_feedback,
                "observer_generated_feedback_path": str(observer_feedback_path),
                "observer_raw_behavior_input_path": str(observer_input_path),
                "evidence_sufficiency": evidence_sufficiency,
                "top_observations": obs_top,
                "structured_observations": evidence_pack.get("structured_observations"),
                "repair_guidance": evidence_pack.get("repair_guidance"),
                "artifact_paths": evidence_pack.get("artifact_paths"),
                "full_evidence_pack_paths": {
                    "json": str(fine_grained_json_path),
                    "markdown": str(fine_grained_md_path),
                },
            },
            "observer_generated_feedback": observer_feedback,
            "observer_generated_feedback_path": str(observer_feedback_path),
            "observer_raw_behavior_input_path": str(observer_input_path),
            "evidence_sufficiency": evidence_sufficiency,
            "feedback_evolution_opportunity": evidence_sufficiency.get("feedback_evolution_opportunity"),
            "recommended_evolution_target": evidence_sufficiency.get("recommended_evolution_target"),
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
    seed.setdefault("evidence_sufficiency", evidence_sufficiency)
    seed.setdefault("feedback_evolution_opportunity", evidence_sufficiency.get("feedback_evolution_opportunity"))
    seed.setdefault("recommended_evolution_target", evidence_sufficiency.get("recommended_evolution_target"))
    seed_path = loop_dir / "repair_seed.json"
    write_json(seed_path, seed)
    return seed, seed_path


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



FEEDBACK_EVIDENCE_FILE_MARKERS = (
    "near_miss_causal_diagnosis.py",
    "build_dab_tool_agent_evidence_pack.py",
    "analyze_dab_tool_agent_trace.py",
    "archive_observation.py",
    "open_diagnosis.py",
    "interpret_failure.py",
    "gate_policy.py",
    "adapters/feedback/",
)


def candidate_matches_query_scope(row: dict[str, Any], *, source_lineage_family: str | None, query_workspace: str | None) -> bool:
    if source_lineage_family and row.get("source_lineage_family") != source_lineage_family:
        return False
    if query_workspace and row.get("query_workspace") != query_workspace:
        return False
    return True


def feedback_evidence_candidate_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    """Score candidates that improve how future loops see/interpret evidence.

    This is separate from answer-parent scoring. A candidate can be useless as
    an answer parent while still being valuable as a feedback/evidence parent if
    it repairs analyzer, evidence-pack, near-miss, gate, or diagnostic plumbing.
    """
    reasons: list[str] = []
    changed = [str(item) for item in (row.get("changed_files") or row.get("project_changed_files") or [])]
    score = 0.0
    if row.get("can_seed_next_repair"):
        score += 0.25
        reasons.append("can_seed_next_repair")
    if row.get("status") in {"candidate_child_eval_failed", "candidate_child_eval_improved_but_failed"}:
        score += 0.05
        reasons.append("has_child_eval_outcome")
    marker_hits = [path for path in changed if any(marker in path for marker in FEEDBACK_EVIDENCE_FILE_MARKERS)]
    if marker_hits:
        score += 0.45 + min(0.15, 0.05 * len(marker_hits))
        reasons.append("feedback_evidence_file_changed:" + ",".join(marker_hits[:3]))
    if row.get("has_open_diagnosis"):
        score += 0.05
        reasons.append("has_open_diagnosis")
    status = str(row.get("contract_eval_status") or "")
    if status and status != "not_evaluated_no_proposed_contracts":
        score += 0.03
        reasons.append("contract_eval_available")
    if row.get("metric_delta_f1") is not None:
        try:
            if float(row.get("metric_delta_f1") or 0.0) < -0.05:
                score -= 0.2
                reasons.append("negative_answer_delta_penalty")
        except Exception:
            pass
    if not marker_hits:
        reasons.append("no_feedback_evidence_file_marker")
        return 0.0, reasons
    return round(score, 6), reasons


def select_feedback_evidence_parent(
    archive_root: Path,
    *,
    source_lineage_family: str | None = None,
    query_workspace: str | None = None,
) -> dict[str, Any] | None:
    rows = load_jsonl(archive_root / "indexes/candidates.jsonl")
    scored: list[dict[str, Any]] = []
    for row in rows:
        if not candidate_matches_query_scope(row, source_lineage_family=source_lineage_family, query_workspace=query_workspace):
            continue
        if not row.get("can_seed_next_repair"):
            continue
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        card_ref = row.get("card")
        card_path = Path(card_ref) if isinstance(card_ref, str) and card_ref else archive_root / "candidates" / str(candidate_id) / "candidate_card.json"
        if not card_path.is_absolute():
            card_path = ROOT / card_path
        card = load_json(card_path) if card_path.exists() else {}
        enriched_row = dict(row)
        if not enriched_row.get("changed_files") and isinstance(card.get("changed_files"), list):
            enriched_row["changed_files"] = card.get("changed_files")
        if not enriched_row.get("project_changed_files") and isinstance(card.get("project_changed_files"), list):
            enriched_row["project_changed_files"] = card.get("project_changed_files")
        score, reasons = feedback_evidence_candidate_score(enriched_row)
        if score <= 0:
            continue
        artifacts = card.get("artifacts") if isinstance(card.get("artifacts"), dict) else {}
        patch_ref = artifacts.get("patch") or artifacts.get("candidate_patch") or str(Path(enriched_row.get("query_workspace") or "") / "candidates" / str(candidate_id) / "patch.diff")
        scored.append({
            "schema_version": "feedback_evidence_parent_v001",
            "candidate_id": candidate_id,
            "status": row.get("status"),
            "candidate_type": row.get("candidate_type"),
            "selection_role": "feedback_evidence_parent",
            "selection_score": score,
            "selection_reasons": reasons,
            "source_lineage_family": enriched_row.get("source_lineage_family"),
            "query_workspace": enriched_row.get("query_workspace"),
            "changed_files": enriched_row.get("changed_files") or enriched_row.get("project_changed_files") or [],
            "card": str(card_path.relative_to(ROOT)) if card_path.exists() and card_path.is_relative_to(ROOT) else str(card_path),
            "patch": patch_ref,
            "reward": row.get("reward"),
            "metric_delta_f1": row.get("metric_delta_f1"),
            "promotion_score": row.get("promotion_score"),
            "promotion_reason": row.get("promotion_reason"),
            "failure_observation_tags": row.get("failure_observation_tags") or [],
            "contract_eval_status": row.get("contract_eval_status"),
            "reuse_policy": {
                "can_seed_next_repair": row.get("can_seed_next_repair"),
                "use_as_negative_example": row.get("use_as_negative_example"),
                "do_not_replace_answer_parent": True,
            },
            "usage": "Use this candidate as feedback/evidence plumbing context for the next meta-agent repair. It does not replace the selected answer parent unless a later repair explicitly applies or merges it.",
        })
    scored.sort(key=lambda item: (item.get("selection_score") or 0.0, str(item.get("candidate_id") or "")), reverse=True)
    return scored[0] if scored else None

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
    source_lineage_family: str | None = None,
    query_workspace: str | None = None,
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
        source_lineage_family=source_lineage_family,
    )
    feedback_evidence_parent = select_feedback_evidence_parent(
        archive_root,
        source_lineage_family=source_lineage_family,
        query_workspace=query_workspace,
    )
    if feedback_evidence_parent:
        selection["feedback_evidence_parent"] = feedback_evidence_parent
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
        "feedback_evidence_parent": selection.get("feedback_evidence_parent"),
    }
    seed["archive_evidence_priority_observations"] = priority_observations
    seed["dual_parent_context"] = {
        "schema_version": "dual_parent_context_v001",
        "answer_parent_agent_id": seed.get("candidate_context", {}).get("parent_agent_id") or seed.get("parent_agent_id"),
        "answer_parent_policy": "Selected data-agent parent remains the source of answer behavior and materialized child workspace patches.",
        "feedback_evidence_parent": selection.get("feedback_evidence_parent"),
        "feedback_evidence_parent_policy": "Selected evidence/plumbing candidate is injected as context for meta-agent diagnosis; it does not replace the answer parent unless a later repair explicitly applies or merges it.",
    }
    seed.setdefault("fine_grained_feedback", {})["archive_evidence_pool"] = seed["archive_selection"]["evidence_pool"]
    seed["fine_grained_feedback"]["archive_evidence_priority_observations"] = priority_observations
    seed["fine_grained_feedback"]["dual_parent_context"] = seed["dual_parent_context"]
    write_json(loop_dir / "feedback_evidence_parent_selection.json", {"feedback_evidence_parent": selection.get("feedback_evidence_parent")})
    write_json(seed_path, seed)
    return selection


def analyze_and_seed(
    *,
    run_dir: Path,
    loop_dir: Path,
    candidate_context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Analyze a parent run and build the meta-agent repair seed.

    Current mainline supports only DAB tool-agent run artifacts.  The old
    one-shot generated_solve.py analyzer path has been archived to legacy so
    active evolution cannot silently fall back to a different feedback format.
    """
    if is_dab_tool_agent_run_dir(run_dir):
        return analyze_dab_tool_agent_and_seed(
            run_dir=run_dir,
            loop_dir=loop_dir,
            candidate_context=candidate_context,
        )

    raise SystemExit(
        "Unsupported parent run format for current DAB tool-agent mainline: "
        f"{run_dir}. Expected a run directory containing summary.json with "
        "schema_version=dab_tool_agent_run_v001, workflow_trace.jsonl, or "
        "tool_calls.jsonl. The legacy generated_solve.py analyzer path has "
        "been archived under legacy/ and is no longer used by the active loop."
    )

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
    if os.environ.get("META_LOOP_APPLY_LLM_NETWORK_TO_LAUNCHER"):
        env = selected_llm_run_env()
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
            "META_LOOP_QUERY_WORKSPACE": os.environ.get("DAB_QUERY_WORKSPACE", ""),
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
    workspace_ref = os.environ.get("DAB_QUERY_WORKSPACE")
    if workspace_ref:
        workspace = Path(workspace_ref)
        if not workspace.is_absolute():
            workspace = ROOT / workspace
        config = load_json(workspace / "workspace.json") or {}
        declared = config.get("inherited_candidate_patches")
        if isinstance(declared, list) and declared:
            return [
                path if path.is_absolute() else workspace / path
                for item in declared
                if isinstance(item, str) and item.strip()
                for path in [Path(item)]
            ]

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
        if not patch_path.exists():
            return {
                "status": "failed",
                "reason": "parent candidate patch missing",
                "patch_path": str(patch_path),
                "applied_patches": applied_patches,
            }
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


def is_multi_query_workflow_seed(seed: dict[str, Any]) -> bool:
    if not isinstance(seed, dict):
        return False
    if seed.get("schema_version") == "dab_multi_query_repair_seed_v001":
        return True
    if seed.get("feedback_type") == "dab_multi_query_workflow_feedback":
        return True
    batch = seed.get("batch") if isinstance(seed.get("batch"), dict) else {}
    return bool(seed.get("per_query_feedback")) and str(batch.get("schema_version") or "").startswith("dab_query_batch")


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
    env = selected_llm_run_env()
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
    attach_repair_mode_to_seed(next_seed, next_seed_path)

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


OBSERVER_INFRASTRUCTURE_EVAL_FILES = {
    "experiments/run_meta_agent_evolution_loop.py",
    "experiments/evidence_sufficiency.py",
    "experiments/run_fine_grained_observer_agent.py",
    "experiments/run_direct_failure_observer_agent.py",
    "experiments/analyze_dab_tool_agent_trace.py",
    "experiments/build_dab_tool_agent_evidence_pack.py",
}


def is_observer_infrastructure_candidate(changed_files: list[str]) -> bool:
    if not changed_files:
        return False
    return all(path in OBSERVER_INFRASTRUCTURE_EVAL_FILES for path in changed_files)


def run_observer_infrastructure_child_eval(*, child_ws: Path, child_eval_dir: Path, loop_dir: Path) -> dict[str, Any]:
    """Evaluate observer/harness patches with the patched workspace itself."""
    eval_dir = child_eval_dir / "observer_infrastructure_eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    loop_dir.mkdir(parents=True, exist_ok=True)
    smoke_script = eval_dir / "observer_infra_smoke.py"
    smoke_report = eval_dir / "observer_infra_smoke_report.json"
    smoke_work = eval_dir / "smoke_work"
    smoke_script.write_text('\nimport json\nimport sys\nfrom pathlib import Path\n\nchild_ws = Path(sys.argv[1])\nwork = Path(sys.argv[2])\nreport_path = Path(sys.argv[3])\nwork.mkdir(parents=True, exist_ok=True)\nsys.path.insert(0, str(child_ws))\n\nreport = {"status": "failed", "checks": {}}\ntry:\n    from experiments.run_meta_agent_evolution_loop import run_cmd, read_text_tail\n    from experiments.evidence_sufficiency import assess_evidence_sufficiency\n\n    stdout_path = work / "startup_failure.stdout"\n    stderr_path = work / "startup_failure.stderr"\n    proc = run_cmd(\n        [str(work / "definitely_missing_command_for_observer_infra_smoke")],\n        cwd=work,\n        stdout_path=stdout_path,\n        stderr_path=stderr_path,\n    )\n    stderr_tail = read_text_tail(stderr_path)\n    child_eval = {\n        "child_selected_signal": "multi_query_child_eval_failed",\n        "query_count": 0,\n        "final_answer_nonempty_count": 0,\n        "full_child_rerun": {\n            "required": True,\n            "status": "failed",\n            "exit_code": proc.returncode,\n            "stdout_path": str(stdout_path),\n            "stderr_path": str(stderr_path),\n            "artifact_paths": {"stdout": str(stdout_path), "stderr": str(stderr_path)},\n            "stderr_tail": stderr_tail,\n            "failure_mechanism": "full_child_rerun_command_failed",\n        },\n        "parent_child_delta": {\n            "comparison_available": False,\n            "reason": "observer_infra_smoke_failed_before_multi_query_summary",\n        },\n    }\n    sufficiency = assess_evidence_sufficiency(child_eval=child_eval)\n    missing = sufficiency.get("missing_evidence") or []\n    checks = {\n        "run_cmd_returned_failed_process": proc.returncode != 0,\n        "stderr_path_exists": stderr_path.exists(),\n        "stderr_tail_nonempty": bool(stderr_tail.strip()),\n        "sufficiency_sees_full_child_traceback": bool((sufficiency.get("available_evidence") or {}).get("has_full_child_traceback")),\n        "missing_full_child_stderr_resolved": "full_child_rerun_stderr_or_traceback" not in missing,\n        "parent_child_delta_preserved": bool(child_eval.get("parent_child_delta")),\n    }\n    passed = all(checks.values())\n    report = {\n        "status": "passed" if passed else "failed",\n        "checks": checks,\n        "completed_process": {"returncode": proc.returncode},\n        "stderr_tail": stderr_tail,\n        "synthetic_child_eval": child_eval,\n        "sufficiency_probe": sufficiency,\n    }\nexcept Exception as exc:\n    report = {\n        "status": "failed",\n        "exception_type": type(exc).__name__,\n        "exception_message": str(exc),\n        "checks": report.get("checks", {}),\n    }\n\nreport_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")\nsys.exit(0 if report.get("status") == "passed" else 1)\n', encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(child_ws)
    proc = run_cmd(
        [str(ROOT / ".venv/bin/python"), str(smoke_script), str(child_ws), str(smoke_work), str(smoke_report)],
        cwd=child_ws,
        env=env,
        stdout_path=loop_dir / "observer_infra_child_eval.stdout",
        stderr_path=loop_dir / "observer_infra_child_eval.stderr",
    )
    report = safe_load_json(smoke_report)
    report.update(
        {
            "eval_kind": "observer_infrastructure_child_eval",
            "exit_code": proc.returncode,
            "report_path": str(smoke_report),
            "stdout_path": str(loop_dir / "observer_infra_child_eval.stdout"),
            "stderr_path": str(loop_dir / "observer_infra_child_eval.stderr"),
        }
    )
    return report


def run_multi_query_architecture_child_eval(
    *,
    candidate_dir: Path,
    seed: dict[str, Any],
    loop_dir: Path,
    iteration: int,
    parent_agent_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a multi-query architecture/observer candidate without hand repair.

    This child eval is deliberately evidence-path oriented: apply the candidate
    patch in an isolated lightweight workspace, then rerun the patched analyzer
    and evidence-pack builder over the parent multi-query run directories
    recorded in the seed.  It avoids reloading DB dumps in /tmp, which can add
    Docker/PostgreSQL noise unrelated to observer/evidence-plumbing patches.
    """
    patch_path = candidate_dir / "patch.diff"
    child_eval_dir = candidate_dir / "child_eval"
    child_eval_dir.mkdir(parents=True, exist_ok=True)
    if not patch_path.exists() or not patch_path.read_text(encoding="utf-8", errors="replace").strip():
        report = {
            "status": "skipped",
            "final_status": "candidate_child_eval_failed",
            "eval_kind": "multi_query_architecture_reanalysis",
            "reason": "candidate patch.diff missing or empty",
        }
        write_json(child_eval_dir / "child_eval_report.json", report)
        write_json(child_eval_dir / "generic_child_eval_report.json", report)
        return report

    child_root = Path(tempfile.mkdtemp(prefix="meta_loop_multi_query_child_eval."))
    child_ws = child_root / "workspace"

    def ignore_lightweight_workspace(_: str, names: list[str]) -> list[str]:
        ignored = set(ignore_workspace("", names))
        ignored |= {"external", "dab_corpus"}
        return [name for name in names if name in ignored]

    shutil.copytree(ROOT, child_ws, ignore=ignore_lightweight_workspace, symlinks=True)
    for linked_name in (".venv", "external", "dab_corpus"):
        source = ROOT / linked_name
        target = child_ws / linked_name
        if source.exists() and not target.exists():
            try:
                target.symlink_to(source, target_is_directory=source.is_dir())
            except OSError:
                if source.is_dir():
                    shutil.copytree(source, target, symlinks=True)
                else:
                    shutil.copy2(source, target)
    run_cmd(["git", "init", "--quiet"], cwd=child_ws)
    run_cmd(["git", "config", "user.name", "meta-loop-multi-query-child-eval"], cwd=child_ws)
    run_cmd(["git", "config", "user.email", "meta-loop-multi-query-child-eval@localhost"], cwd=child_ws)
    run_cmd(["git", "add", "."], cwd=child_ws)
    run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=child_ws)

    parent_source_materialization = materialize_child_parent_source(child_ws, parent_agent_card)
    if parent_source_materialization.get("status") == "failed":
        report = {
            "status": "parent_source_materialization_failed",
            "final_status": "candidate_child_eval_failed",
            "eval_kind": "multi_query_architecture_reanalysis",
            "workspace": str(child_ws),
            "parent_source_materialization": parent_source_materialization,
            "child_failure_gates": ["parent_source_materialization_failed"],
        }
        write_json(child_eval_dir / "child_eval_report.json", report)
        write_json(child_eval_dir / "generic_child_eval_report.json", report)
        return report
    if parent_source_materialization.get("status") == "applied":
        run_cmd(["git", "add", "."], cwd=child_ws)
        run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=child_ws)

    apply_proc = run_cmd(["git", "apply", str(patch_path)], cwd=child_ws)
    patch_apply_mode = "strict"
    if apply_proc.returncode != 0:
        relaxed_apply_proc = run_cmd(["git", "apply", "--ignore-space-change", str(patch_path)], cwd=child_ws)
        if relaxed_apply_proc.returncode == 0:
            apply_proc = relaxed_apply_proc
            patch_apply_mode = "ignore_space_change"

    manifest = safe_load_json(candidate_dir / "manifest.json")
    changed_files = [str(path) for path in manifest.get("project_changed_files") or []]
    observer_infra_eval_applicable = is_observer_infrastructure_candidate(changed_files)
    observer_infrastructure_eval: dict[str, Any] = {
        "required": observer_infra_eval_applicable,
        "status": "not_required" if not observer_infra_eval_applicable else "pending",
    }
    child_failure_gates: list[str] = []
    if apply_proc.returncode != 0:
        child_failure_gates.append("patch_apply_failed")
        report = {
            "status": "patch_apply_failed",
            "final_status": "candidate_child_eval_failed",
            "eval_kind": "multi_query_architecture_reanalysis",
            "workspace": str(child_ws),
            "stderr": apply_proc.stderr,
            "patch_apply_mode": patch_apply_mode,
            "parent_source_materialization": parent_source_materialization,
            "child_failure_gates": child_failure_gates,
        }
        write_json(child_eval_dir / "child_eval_report.json", report)
        write_json(child_eval_dir / "generic_child_eval_report.json", report)
        return report

    env = os.environ.copy()
    env["PYTHONPATH"] = str(child_ws)
    changed_python_files = [child_ws / path for path in changed_files if path.endswith(".py")]
    compile_exit_code = 0
    if changed_python_files:
        compile_proc = run_cmd(
            [str(ROOT / ".venv/bin/python"), "-m", "py_compile", *[str(path) for path in changed_python_files]],
            cwd=child_ws,
            env=env,
            stdout_path=loop_dir / "multi_query_child_py_compile.stdout",
            stderr_path=loop_dir / "multi_query_child_py_compile.stderr",
        )
        compile_exit_code = compile_proc.returncode
        if compile_proc.returncode != 0:
            child_failure_gates.append("child_py_compile_failed")

    if observer_infra_eval_applicable and compile_exit_code == 0 and not any(g in {"patch_apply_failed", "child_py_compile_failed"} for g in child_failure_gates):
        observer_infrastructure_eval = run_observer_infrastructure_child_eval(
            child_ws=child_ws,
            child_eval_dir=child_eval_dir,
            loop_dir=loop_dir,
        )
        if observer_infrastructure_eval.get("status") != "passed":
            child_failure_gates.append("observer_infrastructure_child_eval_failed")

    reanalysis_root = child_eval_dir / "patched_reanalysis"
    reanalysis_root.mkdir(parents=True, exist_ok=True)
    per_query_results: list[dict[str, Any]] = []
    selected_stage_counts: dict[str, int] = {}
    selected_problem_type_counts: dict[str, int] = {}
    helper_dependency_counts: dict[str, int] = {}
    helper_usage_status_counts: dict[str, int] = {}
    successful_reanalysis_count = 0
    final_answer_nonempty_count = 0
    per_query_feedback = seed.get("per_query_feedback") if isinstance(seed.get("per_query_feedback"), list) else []

    for item in per_query_feedback:
        if not isinstance(item, dict):
            continue
        query_id = str(item.get("query_id") or "unknown_query")
        safe_query_id = re.sub(r"[^A-Za-z0-9_.-]+", "__", query_id).strip("_") or "unknown_query"
        run_dir_raw = item.get("run_dir")
        run_dir = Path(str(run_dir_raw)) if run_dir_raw else None
        output_dir = reanalysis_root / safe_query_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result: dict[str, Any] = {
            "query_id": query_id,
            "parent_run_dir": str(run_dir) if run_dir else None,
            "output_dir": str(output_dir),
        }
        if not run_dir or not run_dir.exists():
            result.update({"status": "failed", "exit_code": None, "reason": "parent_run_dir_missing"})
            child_failure_gates.append(f"parent_run_dir_missing:{query_id}")
            per_query_results.append(result)
            continue
        analyzer_proc = run_cmd(
            [
                str(ROOT / ".venv/bin/python"),
                str(child_ws / "experiments/analyze_dab_tool_agent_trace.py"),
                "--run-dir",
                str(run_dir),
                "--output-dir",
                str(output_dir),
            ],
            cwd=child_ws,
            env=env,
            stdout_path=output_dir / "analyzer.stdout",
            stderr_path=output_dir / "analyzer.stderr",
        )
        feedback_summary = safe_load_json(output_dir / "feedback_summary.json")
        observations = safe_load_json(output_dir / "observations.json")
        evidence_json = output_dir / "child_dab_tool_agent_evidence_pack.json"
        evidence_md = output_dir / "child_dab_tool_agent_evidence_pack.md"
        evidence_proc = run_cmd(
            [
                str(ROOT / ".venv/bin/python"),
                str(child_ws / "experiments/build_dab_tool_agent_evidence_pack.py"),
                "--run-dir",
                str(run_dir),
                "--output-json",
                str(evidence_json),
                "--output-md",
                str(evidence_md),
            ],
            cwd=child_ws,
            env=env,
            stdout_path=output_dir / "evidence.stdout",
            stderr_path=output_dir / "evidence.stderr",
        )
        if analyzer_proc.returncode == 0 and evidence_proc.returncode == 0:
            successful_reanalysis_count += 1
        else:
            child_failure_gates.append(f"reanalysis_failed:{query_id}")
        selected_stage = feedback_summary.get("selected_stage")
        selected_signal = feedback_summary.get("selected_signal")
        selected_problem_type = feedback_summary.get("selected_problem_type")
        if selected_stage:
            selected_stage_counts[str(selected_stage)] = selected_stage_counts.get(str(selected_stage), 0) + 1
        if selected_problem_type:
            selected_problem_type_counts[str(selected_problem_type)] = selected_problem_type_counts.get(str(selected_problem_type), 0) + 1
        helper_usage = feedback_summary.get("helper_usage_summary") if isinstance(feedback_summary.get("helper_usage_summary"), dict) else {}
        helper_dep = str(helper_usage.get("final_answer_dependency_status") or "unknown")
        helper_status = str(helper_usage.get("status") or "unknown")
        helper_dependency_counts[helper_dep] = helper_dependency_counts.get(helper_dep, 0) + 1
        helper_usage_status_counts[helper_status] = helper_usage_status_counts.get(helper_status, 0) + 1
        if feedback_summary.get("final_answer_nonempty"):
            final_answer_nonempty_count += 1
        result.update(
            {
                "status": "completed" if analyzer_proc.returncode == 0 and evidence_proc.returncode == 0 else "failed",
                "analyzer_exit_code": analyzer_proc.returncode,
                "evidence_exit_code": evidence_proc.returncode,
                "selected_stage": selected_stage,
                "selected_signal": selected_signal,
                "selected_problem_type": selected_problem_type,
                "final_answer_nonempty": feedback_summary.get("final_answer_nonempty"),
                "helper_dependency_status": helper_dep,
                "helper_usage_status": helper_status,
                "helper_tool_called": helper_usage.get("helper_tool_called"),
                "feedback_summary_path": str(output_dir / "feedback_summary.json"),
                "observations_path": str(output_dir / "observations.json") if (output_dir / "observations.json").exists() else None,
                "evidence_pack_paths": {"json": str(evidence_json), "markdown": str(evidence_md)},
                "observation_count": len(observations) if isinstance(observations, list) else None,
            }
        )
        per_query_results.append(result)

    query_count = len(per_query_results)
    reanalysis_only_safe_files = {
        "experiments/analyze_dab_tool_agent_trace.py",
        "experiments/build_dab_tool_agent_evidence_pack.py",
        "experiments/archive_observation.py",
        "experiments/gate_policy.py",
        "experiments/contract_eval.py",
    }
    full_rerun_required_files = [] if observer_infra_eval_applicable else [path for path in changed_files if path not in reanalysis_only_safe_files]
    reanalysis_only_applicable = not full_rerun_required_files and not observer_infra_eval_applicable
    recovered_batch_for_next_seed = recover_multi_query_batch_from_seed(seed)

    full_child_rerun: dict[str, Any] = {
        "required": bool(full_rerun_required_files),
        "status": "not_required" if not full_rerun_required_files else "pending",
    }
    full_child_summary: dict[str, Any] = {}
    parent_child_delta: dict[str, Any] = {}
    if full_rerun_required_files and compile_exit_code == 0 and not any(g in {"patch_apply_failed", "child_py_compile_failed"} for g in child_failure_gates):
        batch = recovered_batch_for_next_seed
        batch_id = str(seed.get("batch_id") or batch.get("batch_id") or f"multi_query_child_iter{iteration:03d}")
        child_batch_path = child_ws / "dab_corpus" / "batches" / f"{batch_id}.json"
        if not child_batch_path.exists():
            child_batch_path = child_ws / f"_child_eval_batch_iter{iteration:03d}.json"
            write_json(child_batch_path, batch)
        child_output_root = child_eval_dir / "full_child_rerun"
        child_run_id = f"full_child_iter{iteration:03d}_{utc_now_slug()}"
        env_full = selected_llm_run_env()
        env_full["PYTHONPATH"] = str(child_ws)
        env_full.setdefault("DAB_TOOL_AGENT_API_KEY_ENV", "DASHSCOPE_API_KEY")
        max_iterations = str(env_full.get("DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS") or env_full.get("DAB_MULTI_QUERY_MAX_ITERATIONS") or "10")
        full_child_stdout_path = loop_dir / "multi_query_full_child_run.stdout"
        full_child_stderr_path = loop_dir / "multi_query_full_child_run.stderr"
        full_child_command = [
            str(ROOT / ".venv/bin/python"),
            str(child_ws / "experiments/run_multi_query_baseline.py"),
            "--batch",
            str(child_batch_path),
            "--registry",
            str(child_ws / "dab_corpus/registry.json"),
            "--dab-root",
            str(child_ws / "external/DataAgentBench_sparse"),
            "--output-root",
            str(child_output_root),
            "--run-id",
            child_run_id,
            "--max-iterations",
            max_iterations,
        ]
        full_proc = run_cmd(
            full_child_command,
            cwd=child_ws,
            env=env_full,
            stdout_path=full_child_stdout_path,
            stderr_path=full_child_stderr_path,
        )
        child_summary_path = child_output_root / child_run_id / "multi_query_summary.json"
        full_child_summary = safe_load_json(child_summary_path)
        full_child_artifacts = {
            "stdout": str(full_child_stdout_path),
            "stderr": str(full_child_stderr_path),
            "batch": str(child_batch_path),
            "summary": str(child_summary_path),
            "output_dir": str(child_output_root / child_run_id),
        }
        failure_mechanism = None
        if full_proc.returncode != 0:
            failure_mechanism = "full_child_rerun_command_failed"
        elif not full_child_summary:
            failure_mechanism = "full_child_rerun_missing_multi_query_summary"
        full_child_rerun = {
            "required": True,
            "status": "completed" if full_proc.returncode == 0 and full_child_summary else "failed",
            "exit_code": full_proc.returncode,
            "command": full_child_command,
            "run_id": child_run_id,
            "output_dir": str(child_output_root / child_run_id),
            "summary_path": str(child_summary_path),
            "stdout_path": str(full_child_stdout_path),
            "stderr_path": str(full_child_stderr_path),
            "artifact_paths": full_child_artifacts,
            "stdout_tail": read_text_tail(full_child_stdout_path),
            "stderr_tail": read_text_tail(full_child_stderr_path),
            "failure_mechanism": failure_mechanism,
            "max_iterations": max_iterations,
        }
        if full_proc.returncode != 0 or not full_child_summary:
            child_failure_gates.append("multi_query_full_child_rerun_failed")
            parent_child_delta = {
                "comparison_available": False,
                "reason": "full_child_rerun_failed_before_multi_query_summary",
                "blocked_by": failure_mechanism,
                "full_child_exit_code": full_proc.returncode,
                "full_child_stdout_path": str(full_child_stdout_path),
                "full_child_stderr_path": str(full_child_stderr_path),
                "full_child_output_dir": str(child_output_root / child_run_id),
            }
        else:
            def as_int(value: Any) -> int:
                try:
                    return int(value or 0)
                except Exception:
                    return 0

            def as_float_or_none(value: Any) -> float | None:
                try:
                    if value is None:
                        return None
                    return float(value)
                except Exception:
                    return None

            parent_success = as_int(seed.get("successful_run_count"))
            child_success = as_int(full_child_summary.get("successful_run_count"))
            parent_answer_count = as_int(seed.get("final_answer_nonempty_count"))
            child_answer_count = as_int(full_child_summary.get("final_answer_nonempty_count"))
            parent_avg_f1 = as_float_or_none(seed.get("average_f1"))
            child_avg_f1 = as_float_or_none(full_child_summary.get("average_f1"))
            parent_tool_failures = as_int((seed.get("selected_problem_type_counts") or {}).get("tool_failure") if isinstance(seed.get("selected_problem_type_counts"), dict) else 0)
            child_tool_failures = as_int((full_child_summary.get("selected_problem_type_counts") or {}).get("tool_failure") if isinstance(full_child_summary.get("selected_problem_type_counts"), dict) else 0)
            parent_helper_not_called = as_int(seed.get("helper_registered_but_not_called_count"))
            child_helper_not_called = as_int(full_child_summary.get("helper_registered_but_not_called_count"))
            improved_f1 = child_avg_f1 is not None and (parent_avg_f1 is None or child_avg_f1 > parent_avg_f1)
            improved_answer = child_answer_count > parent_answer_count
            improved_success = child_success > parent_success and child_answer_count >= parent_answer_count
            reduced_tool_failures = child_tool_failures < parent_tool_failures and child_success >= parent_success
            reduced_helper_not_called = child_helper_not_called < parent_helper_not_called if parent_helper_not_called else False
            severe_regression = child_success < parent_success or child_answer_count < parent_answer_count
            parent_child_delta = {
                "parent_successful_run_count": parent_success,
                "child_successful_run_count": child_success,
                "delta_successful_run_count": child_success - parent_success,
                "parent_final_answer_nonempty_count": parent_answer_count,
                "child_final_answer_nonempty_count": child_answer_count,
                "delta_final_answer_nonempty_count": child_answer_count - parent_answer_count,
                "parent_average_f1": parent_avg_f1,
                "child_average_f1": child_avg_f1,
                "delta_average_f1": (child_avg_f1 - parent_avg_f1) if child_avg_f1 is not None and parent_avg_f1 is not None else None,
                "parent_tool_failure_count": parent_tool_failures,
                "child_tool_failure_count": child_tool_failures,
                "delta_tool_failure_count": child_tool_failures - parent_tool_failures,
                "parent_helper_registered_but_not_called_count": parent_helper_not_called,
                "child_helper_registered_but_not_called_count": child_helper_not_called,
                "delta_helper_registered_but_not_called_count": child_helper_not_called - parent_helper_not_called,
                "improved_f1": improved_f1,
                "improved_answer_count": improved_answer,
                "improved_success_count": improved_success,
                "reduced_tool_failures": reduced_tool_failures,
                "reduced_helper_registered_but_not_called": reduced_helper_not_called,
                "severe_regression": severe_regression,
            }
            if severe_regression:
                child_failure_gates.append("multi_query_full_child_severe_regression")
            if not (improved_f1 or improved_answer or improved_success or reduced_tool_failures):
                child_failure_gates.append("multi_query_full_child_no_measured_improvement")

    full_child_strict_mismatch_count = 0
    if isinstance(full_child_summary.get("per_query_feedback"), list):
        for row in full_child_summary.get("per_query_feedback") or []:
            if not isinstance(row, dict):
                continue
            quality = row.get("answer_quality") if isinstance(row.get("answer_quality"), dict) else {}
            if quality.get("strict_match_passed") is False:
                full_child_strict_mismatch_count += 1
    full_child_has_measured_improvement = bool(
        parent_child_delta.get("improved_f1")
        or parent_child_delta.get("improved_answer_count")
        or parent_child_delta.get("improved_success_count")
        or parent_child_delta.get("reduced_tool_failures")
        or parent_child_delta.get("reduced_helper_registered_but_not_called")
    )
    if observer_infra_eval_applicable:
        child_passed = bool(
            observer_infrastructure_eval.get("status") == "passed"
            and compile_exit_code == 0
            and not child_failure_gates
        )
        child_improved_but_failed = False
    elif reanalysis_only_applicable:
        child_passed = bool(
            query_count
            and successful_reanalysis_count == query_count
            and compile_exit_code == 0
            and not child_failure_gates
        )
        child_improved_but_failed = False
    else:
        child_passed = bool(
            full_child_rerun.get("status") == "completed"
            and not child_failure_gates
            and bool(parent_child_delta)
            and full_child_strict_mismatch_count == 0
        )
        child_improved_but_failed = bool(
            full_child_rerun.get("status") == "completed"
            and full_child_has_measured_improvement
            and not parent_child_delta.get("severe_regression")
            and full_child_strict_mismatch_count > 0
            and not any(g in {"patch_apply_failed", "child_py_compile_failed", "multi_query_full_child_rerun_failed", "multi_query_full_child_severe_regression", "multi_query_full_child_no_measured_improvement"} for g in child_failure_gates)
        )
    child_final_status = "candidate_child_eval_passed" if child_passed else ("candidate_child_eval_improved_but_failed" if child_improved_but_failed else "candidate_child_eval_failed")
    effective_query_count = int(full_child_summary.get("query_count") or query_count or 0) if isinstance(full_child_summary, dict) else query_count
    effective_successful_count = int(full_child_summary.get("successful_run_count") or successful_reanalysis_count or 0) if isinstance(full_child_summary, dict) else successful_reanalysis_count
    effective_final_answer_count = int(full_child_summary.get("final_answer_nonempty_count") or final_answer_nonempty_count or 0) if isinstance(full_child_summary, dict) else final_answer_nonempty_count
    effective_stage_counts = full_child_summary.get("selected_stage_counts") if isinstance(full_child_summary.get("selected_stage_counts"), dict) else selected_stage_counts
    effective_problem_counts = full_child_summary.get("selected_problem_type_counts") if isinstance(full_child_summary.get("selected_problem_type_counts"), dict) else selected_problem_type_counts
    effective_helper_status_counts = full_child_summary.get("helper_usage_status_counts") if isinstance(full_child_summary.get("helper_usage_status_counts"), dict) else helper_usage_status_counts
    effective_helper_not_called_count = full_child_summary.get("helper_registered_but_not_called_count", effective_helper_status_counts.get("helper_tool_registered_but_not_called", 0))
    effective_per_query_feedback = full_child_summary.get("per_query_feedback") if isinstance(full_child_summary.get("per_query_feedback"), list) else per_query_results
    if observer_infra_eval_applicable and isinstance(observer_infrastructure_eval.get("sufficiency_probe"), dict):
        child_evidence_sufficiency = observer_infrastructure_eval["sufficiency_probe"]
    else:
        child_evidence_sufficiency = assess_evidence_sufficiency(
            seed=seed if isinstance(seed, dict) else {},
            child_eval={
                "query_count": effective_query_count,
                "final_answer_nonempty_count": effective_final_answer_count,
                "selected_stage_counts": effective_stage_counts,
                "selected_problem_type_counts": effective_problem_counts,
                "helper_usage_status_counts": effective_helper_status_counts,
                "full_child_rerun": full_child_rerun,
                "parent_child_delta": parent_child_delta,
                "child_selected_stage": next(iter(effective_stage_counts), None) if isinstance(effective_stage_counts, dict) else None,
                "child_selected_signal": "multi_query_full_child_rerun_passed" if child_passed and full_child_rerun.get("required") else ("multi_query_reanalysis_passed" if child_passed else "multi_query_child_eval_failed"),
            },
        )
    next_seed = dict(seed)
    next_seed.update(
        {
            "seed_id": f"next_multi_query_architecture_repair_seed_iter{iteration:03d}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "child_eval_multi_query_architecture_reanalysis",
            "parent_candidate_dir": str(candidate_dir),
            "repair_profile": "multi_query_architecture_evolution",
            "batch": recovered_batch_for_next_seed,
            "batch_id": recovered_batch_for_next_seed.get("batch_id") if isinstance(recovered_batch_for_next_seed, dict) else None,
            "query_count": effective_query_count,
            "successful_run_count": effective_successful_count,
            "successful_reanalysis_count": successful_reanalysis_count,
            "final_answer_nonempty_count": effective_final_answer_count,
            "selected_stage_counts": effective_stage_counts,
            "selected_problem_type_counts": effective_problem_counts,
            "helper_dependency_counts": helper_dependency_counts,
            "helper_usage_status_counts": effective_helper_status_counts,
            "helper_registered_but_not_called_count": effective_helper_not_called_count,
            "per_query_feedback": effective_per_query_feedback,
            "full_evidence_pack_paths": {"reanalysis_root": str(reanalysis_root)},
            "full_child_rerun": full_child_rerun,
            "parent_child_delta": parent_child_delta,
            "child_multi_query_summary": full_child_summary,
            "observer_infrastructure_eval": observer_infrastructure_eval,
            "evidence_sufficiency": child_evidence_sufficiency,
            "feedback_evolution_opportunity": child_evidence_sufficiency.get("feedback_evolution_opportunity"),
            "recommended_evolution_target": child_evidence_sufficiency.get("recommended_evolution_target"),
            "recommended_observer_subtarget": child_evidence_sufficiency.get("recommended_observer_subtarget"),
        }
    )
    next_seed_path = child_eval_dir / "next_data_agent_repair_seed.json"
    attach_repair_mode_to_seed(next_seed, next_seed_path)

    report = {
        "status": "completed",
        "final_status": child_final_status,
        "eval_kind": "multi_query_architecture_reanalysis",
        "workspace": str(child_ws),
        "candidate_structure_type": (safe_load_json(candidate_dir / "validated_patch_spec.json").get("codex_native") or {}).get("candidate_structure_type") or "unknown",
        "project_changed_files": changed_files,
        "total_changed_lines": manifest.get("total_changed_lines"),
        "patch_apply_mode": patch_apply_mode,
        "child_py_compile_exit_code": compile_exit_code,
        "reanalysis_only_applicable": reanalysis_only_applicable,
        "observer_infra_eval_applicable": observer_infra_eval_applicable,
        "observer_infrastructure_eval": observer_infrastructure_eval,
        "batch": recovered_batch_for_next_seed,
        "batch_id": recovered_batch_for_next_seed.get("batch_id") if isinstance(recovered_batch_for_next_seed, dict) else None,
        "full_rerun_required_files": full_rerun_required_files,
        "full_child_rerun": full_child_rerun,
        "parent_child_delta": parent_child_delta,
        "child_multi_query_summary": full_child_summary,
        "evidence_sufficiency": child_evidence_sufficiency,
        "feedback_evolution_opportunity": child_evidence_sufficiency.get("feedback_evolution_opportunity"),
        "recommended_evolution_target": child_evidence_sufficiency.get("recommended_evolution_target"),
        "recommended_observer_subtarget": child_evidence_sufficiency.get("recommended_observer_subtarget"),
        "full_child_strict_mismatch_count": full_child_strict_mismatch_count,
        "child_improved_but_failed": child_improved_but_failed,
        "query_count": effective_query_count,
        "successful_reanalysis_count": successful_reanalysis_count,
        "final_answer_nonempty_count": effective_final_answer_count,
        "selected_stage_counts": effective_stage_counts,
        "selected_problem_type_counts": effective_problem_counts,
        "helper_dependency_counts": helper_dependency_counts,
        "helper_usage_status_counts": effective_helper_status_counts,
        "helper_registered_but_not_called_count": effective_helper_not_called_count,
        "per_query_results": per_query_results,
        "child_failure_gates": child_failure_gates,
        "child_passed": child_passed,
        "child_selected_stage": next(iter((full_child_summary.get("selected_stage_counts") if isinstance(full_child_summary.get("selected_stage_counts"), dict) else selected_stage_counts)), None),
        "child_selected_signal": "multi_query_full_child_rerun_passed" if child_passed and full_child_rerun.get("required") else ("multi_query_reanalysis_passed" if child_passed else "multi_query_child_eval_failed"),
        "next_data_agent_repair_seed": str(next_seed_path),
        "child_status": {
            "status": "completed",
            "passed_original_dab_validation": None,
            "validation_reason": "multi-query observer/evidence reanalysis; DataAgent/prompt/helper patches require full child rerun",
            "selected_stage": next(iter((full_child_summary.get("selected_stage_counts") if isinstance(full_child_summary.get("selected_stage_counts"), dict) else selected_stage_counts)), None),
            "selected_signal": "multi_query_full_child_rerun_passed" if child_passed and full_child_rerun.get("required") else ("multi_query_reanalysis_passed" if child_passed else "multi_query_child_eval_failed"),
            "selected_stage_counts": full_child_summary.get("selected_stage_counts") if isinstance(full_child_summary.get("selected_stage_counts"), dict) else selected_stage_counts,
            "selected_problem_type_counts": full_child_summary.get("selected_problem_type_counts") if isinstance(full_child_summary.get("selected_problem_type_counts"), dict) else selected_problem_type_counts,
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
    """Reject the archived generated_solve.py child-eval path.

    Generic child eval used to execute experiments/run_dab_agent.py and analyze
    generated_solve.py artifacts.  The active research mainline now evaluates
    DAB tool-agent workflows through run_dab_tool_agent_child_eval or
    run_multi_query_architecture_child_eval, both of which preserve full
    execution traces for the observer-feedback architecture.
    """
    return {
        "status": "legacy_generated_solve_child_eval_disabled",
        "reason": "Use DAB tool-agent child eval; the generated_solve.py child eval path is archived and intentionally not run by the active loop.",
        "candidate_dir": str(candidate_dir),
        "case_dir": str(case_dir),
        "prompt_path": str(prompt_path),
        "dab_root": str(dab_root),
        "loop_dir": str(loop_dir),
        "iteration": iteration,
        "parent_agent_id": (parent_agent_card or {}).get("agent_id") if isinstance(parent_agent_card, dict) else None,
    }


def scope_note_for_candidate_type(candidate_type: str) -> str:
    """Human-readable archive scope note for candidate postprocessing."""
    if candidate_type == "data_agent_multi_query_architecture_repair":
        return (
            "Multi-query DataAgent architecture repair candidate. Evaluate through "
            "batch child eval and archive observations; do not treat helper creation "
            "alone as answer success."
        )
    if candidate_type == "data_agent_project_repair":
        return "DataAgent project-source repair candidate; child eval decides parent eligibility."
    if candidate_type == "data_agent_tool_repair":
        return "DataAgent helper/tool repair candidate; verify helper is registered, called, and used in final answer behavior."
    return "Meta-agent repair candidate; child eval and archive scoring decide promotion, not candidate text alone."
def postprocess_candidate(
    *,
    candidate_dir: Path,
    archive_root: Path,
    parent_agent_id: str,
    candidate_type: str,
    case_id: str,
    query_workspace: str | None = None,
    source_lineage_family: str | None = None,
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
            "--query-workspace",
            query_workspace or "",
            "--source-lineage-family",
            source_lineage_family or "",
            "--recommended-goal",
            f"Repair the data-agent side for {case_id} using the current child-eval feedback; improve answer quality while preserving benchmark integrity, query-local isolation, and helper/output wiring.",
        ],
        cwd=ROOT,
    )
    return proc.returncode


def run_loop(args: argparse.Namespace) -> int:
    query_workspace: Path | None = None
    query_workspace_config: dict[str, Any] = {}
    if args.query_workspace:
        query_workspace = Path(args.query_workspace).resolve()
        config_path = query_workspace / "workspace.json"
        if not config_path.exists():
            raise SystemExit(f"query workspace config not found: {config_path}")
        query_workspace_config = load_json(config_path) or {}
        try:
            query_workspace_rel = query_workspace.relative_to(ROOT)
        except ValueError as exc:
            raise SystemExit("query workspace must live inside the project root") from exc
        os.environ["DAB_QUERY_WORKSPACE"] = query_workspace_rel.as_posix()
        configured_case_dir = query_workspace_config.get("query_dir")
        if configured_case_dir:
            args.case_dir = str(configured_case_dir)
        args.case_id = f"{query_workspace_config.get('benchmark_family', 'DAB')}_{query_workspace_config.get('query_id', query_workspace.name)}"
        query_initial_parent_agent_id = query_workspace_config.get("initial_parent_agent_id")
        if args.query_parent_mode == "initial":
            args.parent_agent_id = args.parent_agent_id or query_initial_parent_agent_id
        args.source_lineage_family = query_workspace_config.get("source_lineage_family") or args.source_lineage_family
        os.environ["META_LOOP_SOURCE_LINEAGE_FAMILY"] = str(args.source_lineage_family or "")
        artifact_config = query_workspace_config.get("artifacts") if isinstance(query_workspace_config.get("artifacts"), dict) else {}
        loop_rel = artifact_config.get("meta_agent_loops") or "runs/meta_agent_evolution"
        args.loop_root = str((query_workspace / loop_rel).resolve())
        candidate_rel = artifact_config.get("candidates") or "candidates"
        args.candidate_root = str((query_workspace / candidate_rel).resolve())
        if args.candidate_id_prefix == "codex_qwen_patents_iter004_data_agent_repair":
            args.candidate_id_prefix = f"codex_native_{query_workspace_config.get('workspace_id', query_workspace.name)}"

    archive_root = Path(args.archive_root).resolve()
    loop_root = Path(args.loop_root).resolve()
    loop_root.mkdir(parents=True, exist_ok=True)
    loop_dir = loop_root / f"meta_agent_loop_{utc_now_slug()}"
    loop_dir.mkdir(parents=True, exist_ok=False)

    parent_history: list[str] = []
    try:
        parent = select_parent_agent(
            archive_root,
            args.parent_agent_id,
            max_age_hours=args.archive_max_parent_age_hours,
            repeated_parent_ids=parent_history,
            repeated_parent_penalty=args.repeated_parent_penalty,
            source_lineage_family=args.source_lineage_family or None,
        )
    except SystemExit:
        if not query_workspace or args.query_parent_mode != "best-archive" or not query_initial_parent_agent_id:
            raise
        parent = select_parent_agent(
            archive_root,
            query_initial_parent_agent_id,
            max_age_hours=args.archive_max_parent_age_hours,
            repeated_parent_ids=parent_history,
            repeated_parent_penalty=args.repeated_parent_penalty,
            source_lineage_family=args.source_lineage_family or None,
        )
    parent_agent_id = parent["card"]["agent_id"]
    initial_parent_agent_id = parent_agent_id
    meta_agent = select_meta_agent(archive_root, args.meta_agent_id)
    meta_agent_id = meta_agent["card"]["agent_id"] if meta_agent else None
    prompt_override = Path(args.prompt).resolve() if args.prompt else None
    if query_workspace and prompt_override is None:
        agent_config = query_workspace_config.get("agent") if isinstance(query_workspace_config.get("agent"), dict) else {}
        prompt_override = (query_workspace / str(agent_config.get("policy") or "agent/policy.txt")).resolve()
    prompt_path = prompt_for_parent(parent, prompt_override)
    case_dir = Path(args.case_dir).resolve()
    dab_root = Path(args.dab_root).resolve()
    skipped_parent_materialization_failures: list[dict[str, Any]] = []
    max_parent_preflight_skips = max(0, int(getattr(args, "parent_materialization_preflight_max_skips", 3)))
    parent_materialization_preflight = preflight_parent_materialization(parent["card"])
    while (
        parent_materialization_preflight.get("status") == "failed"
        and not args.parent_agent_id
        and len(skipped_parent_materialization_failures) < max_parent_preflight_skips
    ):
        skipped_parent_materialization_failures.append(
            {
                "agent_id": parent.get("card", {}).get("agent_id"),
                "reason": parent_materialization_preflight.get("reason"),
                "patch_path": parent_materialization_preflight.get("patch_path"),
                "stderr": parent_materialization_preflight.get("stderr"),
            }
        )
        parent = select_parent_agent(
            archive_root,
            None,
            max_age_hours=args.archive_max_parent_age_hours,
            repeated_parent_ids=parent_history,
            repeated_parent_penalty=args.repeated_parent_penalty,
            source_lineage_family=args.source_lineage_family or None,
            exclude_agent_ids=[str(row.get("agent_id")) for row in skipped_parent_materialization_failures if row.get("agent_id")],
        )
        parent_agent_id = parent["card"]["agent_id"]
        initial_parent_agent_id = parent_agent_id
        if query_workspace and prompt_override is None:
            agent_config = query_workspace_config.get("agent") if isinstance(query_workspace_config.get("agent"), dict) else {}
            prompt_override = (query_workspace / str(agent_config.get("policy") or "agent/policy.txt")).resolve()
        prompt_path = prompt_for_parent(parent, prompt_override)
        parent_materialization_preflight = preflight_parent_materialization(parent["card"])
    if parent_materialization_preflight.get("status") == "failed" and not args.parent_agent_id and args.repair_seed:
        try:
            clean_parent = select_parent_agent(
                archive_root,
                "dab_tool_agent_zero_start_current",
                max_age_hours=None,
                repeated_parent_ids=parent_history,
                repeated_parent_penalty=args.repeated_parent_penalty,
                source_lineage_family=args.source_lineage_family or None,
            )
            skipped_parent_materialization_failures.append(
                {
                    "agent_id": parent.get("card", {}).get("agent_id"),
                    "reason": parent_materialization_preflight.get("reason"),
                    "patch_path": parent_materialization_preflight.get("patch_path"),
                    "stderr": parent_materialization_preflight.get("stderr"),
                    "fallback": "dab_tool_agent_zero_start_current",
                }
            )
            parent = clean_parent
            parent_agent_id = parent["card"]["agent_id"]
            initial_parent_agent_id = parent_agent_id
            prompt_path = prompt_for_parent(parent, prompt_override)
            parent_materialization_preflight = preflight_parent_materialization(parent["card"])
        except SystemExit:
            pass
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
        "candidate_root": str(Path(args.candidate_root).resolve()),
        "repair_profile": args.repair_profile,
        "query_parent_mode": args.query_parent_mode if query_workspace else None,
        "query_workspace": str(query_workspace) if query_workspace else None,
        "query_workspace_id": query_workspace_config.get("workspace_id"),
        "parent_materialization_preflight": parent_materialization_preflight,
        "skipped_parent_materialization_failures": skipped_parent_materialization_failures,
        "parent_materialization_preflight_max_skips": max_parent_preflight_skips,
        "parent_selection_policy": {
            "initial_parent_override": args.parent_agent_id,
            "subsequent_iterations": "select parent_pool via archive_selector after candidate postprocess",
            "archive_max_parent_age_hours": args.archive_max_parent_age_hours,
            "repeated_parent_penalty": args.repeated_parent_penalty,
            "source_lineage_family": args.source_lineage_family or None,
            "query_parent_mode": args.query_parent_mode if query_workspace else None,
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
    if parent_run is None and args.repair_seed:
        seed_preload_path = Path(args.repair_seed).resolve()
        seed_preload = safe_load_json(seed_preload_path)
        if args.repair_profile == "multi_query_architecture_evolution" or is_multi_query_workflow_seed(seed_preload):
            parent_run = seed_preload_path.parent
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
            parent_llm_preflight = run_dab_tool_agent_llm_preflight(iteration_dir, "parent")
            if parent_llm_preflight.get("status") != "passed":
                results.append(
                    {
                        "iteration": iteration,
                        "status": "infra_failed_llm_connection",
                        "data_parent_agent_id": parent_agent_id,
                        "meta_agent_protocol_id": meta_agent_id,
                        "llm_preflight": parent_llm_preflight,
                        "reason": "DataAgent LLM preflight failed before parent run; skipped parent analysis and candidate generation to avoid misleading missing_final_answer feedback.",
                    }
                )
                return write_infra_failed_loop_summary(
                    loop_dir=loop_dir,
                    results=results,
                    initial_parent_agent_id=initial_parent_agent_id,
                    parent_agent_id=parent_agent_id,
                    meta_agent_id=meta_agent_id,
                    preflight=parent_llm_preflight,
                )
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
                source_lineage_family=args.source_lineage_family or None,
                query_workspace=os.environ.get("DAB_QUERY_WORKSPACE"),
            )
            attach_recent_loop_handoffs_to_seed(seed, seed_path, archive_root, iteration_dir)
            attach_repair_mode_to_seed(seed, seed_path)
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
                source_lineage_family=args.source_lineage_family or None,
                query_workspace=os.environ.get("DAB_QUERY_WORKSPACE"),
            )
            attach_recent_loop_handoffs_to_seed(seed, seed_path, archive_root, iteration_dir)
            attach_repair_mode_to_seed(seed, seed_path)
        candidate_id = candidate_id_for(args.candidate_id_prefix, iteration)
        candidate_dir = Path(args.candidate_root).resolve() / candidate_id
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
            if args.repair_profile == "multi_query_architecture_evolution" or is_multi_query_workflow_seed(seed):
                child_eval = run_multi_query_architecture_child_eval(
                    candidate_dir=candidate_dir,
                    seed=seed,
                    loop_dir=iteration_dir,
                    iteration=iteration,
                    parent_agent_card=parent["card"],
                )
            else:
                child_llm_preflight = run_dab_tool_agent_llm_preflight(iteration_dir, "child")
                if child_llm_preflight.get("status") != "passed":
                    child_eval = {
                        "status": "skipped",
                        "final_status": "infra_failed_llm_connection",
                        "eval_kind": "dab_tool_agent" if is_dab_tool_agent_workflow_seed(seed) else "generic",
                        "llm_preflight": child_llm_preflight,
                        "reason": "DataAgent LLM preflight failed before child eval; skipped answer-quality evaluation to avoid misleading missing_final_answer feedback.",
                    }
                    if candidate_dir.exists():
                        child_eval_dir = candidate_dir / "child_eval"
                        child_eval_dir.mkdir(parents=True, exist_ok=True)
                        write_json(child_eval_dir / "child_eval_report.json", child_eval)
                        write_json(child_eval_dir / "generic_child_eval_report.json", child_eval)
                elif is_dab_tool_agent_workflow_seed(seed):
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
                query_workspace=os.environ.get("DAB_QUERY_WORKSPACE"),
                source_lineage_family=args.source_lineage_family or None,
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
            next_parent_status = "selected_from_archive_selector_parent_pool"
            try:
                next_parent = select_parent_agent(
                    archive_root,
                    None,
                    max_age_hours=args.archive_max_parent_age_hours,
                    repeated_parent_ids=parent_history,
                    repeated_parent_penalty=args.repeated_parent_penalty,
                    source_lineage_family=args.source_lineage_family or None,
                )
            except SystemExit:
                if not query_workspace:
                    raise
                next_parent = parent
                next_parent_status = "retained_current_parent_no_eligible_query_child"
            write_json(
                iteration_dir / "next_parent_selection.json",
                {
                    "status": next_parent_status,
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
            if query_workspace:
                agent_config = query_workspace_config.get("agent") if isinstance(query_workspace_config.get("agent"), dict) else {}
                prompt_path = (query_workspace / str(agent_config.get("policy") or "agent/policy.txt")).resolve()
            else:
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
    parser.add_argument("--query-workspace", default=os.environ.get("DAB_QUERY_WORKSPACE"), help="Query-local workspace.json plus isolated policy/helper registry.")
    parser.add_argument("--query-parent-mode", choices=["initial", "best-archive"], default="initial", help="For query workspaces, choose the initial parent or the best eligible archive parent for the first iteration.")
    parser.add_argument("--candidate-root", default=str(ROOT / "candidates/dab"), help="Candidate output root; query workspace candidates directory is used automatically.")
    parser.add_argument("--loop-root", default=str(ROOT / "trajectories/meta_agent_loops"))
    parser.add_argument("--parent-agent-id", help="Initial parent override for the first iteration only; later iterations reselect the current top-ranked archive parent.")
    parser.add_argument("--archive-max-parent-age-hours", type=float, default=24.0, help="Only auto-select data-agent parents whose archive agent_card was modified within this many hours; <=0 disables the freshness filter. Explicit --parent-agent-id bypasses this for the first iteration.")
    parser.add_argument("--parent-materialization-preflight-max-skips", type=int, default=int(os.environ.get("META_LOOP_PARENT_PREFLIGHT_MAX_SKIPS", "3")), help="Maximum stale/unmaterializable archive parents to skip before falling back or failing.")
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
    parser.add_argument("--repair-profile", default="data_agent_prompt_repair", choices=["data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair", "analyzer_infra_repair", "multi_query_architecture_evolution"], help="Repair profile passed to the candidate launcher. Use data_agent_tool_repair to prefer reusable adapters/patents helper scripts, or data_agent_project_repair for broader safe project-source edits.")
    parser.add_argument("--run-generic-child-eval", action="store_true", help="Run child eval after candidate generation. For DAB tool-agent seeds this uses the DAB tool-agent child eval; legacy generated_solve eval is only used for legacy seeds.")
    parser.set_defaults(func=run_loop)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
