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
from experiments.build_meta_agent_evidence_pack import build_fine_grained_feedback_pack, write_pack
from experiments.extract_primary_signal import extract_primary_signal
from experiments.helper_repair_planner import plan_helper_repair
from experiments.run_dab_agent import run_dab_agent


DEFAULT_ARCHIVE = ROOT / "archive"
DEFAULT_CASE_DIR = Path("/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1")
DEFAULT_DAB_ROOT = Path("/home/m0st1ma/research/DataAgentBench")
DATA_AGENT_CANONICAL_PROMPT = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")


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


def generated_code_uses_helper(generated_code_path: Path, helpers: list[dict[str, str]]) -> dict[str, Any]:
    if not helpers:
        return {"required": False, "status": "not_required", "helpers": []}
    code = generated_code_path.read_text(encoding="utf-8", errors="replace") if generated_code_path.exists() else ""
    code_low = code.lower()
    observed: list[str] = []
    missing: list[str] = []
    for helper in helpers:
        full = helper["module"].lower()
        stem = helper["stem"].lower()
        used = (
            full in code_low
            or f"from adapters.patents import {stem}" in code_low
            or f"import adapters.patents.{stem}" in code_low
            or f"from {stem} import" in code_low
            or f"import {stem}" in code_low
        )
        if used:
            observed.append(helper["module"])
        else:
            missing.append(helper["module"])
    status = "helper_used_by_child_generated_code" if observed else "helper_not_used_by_child_generated_code"
    return {
        "required": True,
        "status": status,
        "helpers": helpers,
        "observed_modules": observed,
        "missing_modules": missing,
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
) -> dict[str, Any]:
    return select_archive_agent(
        archive_root,
        requested=requested,
        agent_type="data_agent",
        require_prompt=True,
        max_age_hours=max_age_hours,
        repeated_parent_ids=repeated_parent_ids,
        repeated_parent_penalty=repeated_parent_penalty,
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


def run_parent_case(
    *,
    case_dir: Path,
    prompt_path: Path,
    version: str,
    dab_root: Path,
    timeout_sec: int,
) -> Path:
    result = run_dab_agent(
        case_dir=case_dir,
        prompt_path=prompt_path,
        version=version,
        dab_root=dab_root,
        timeout_sec=timeout_sec,
    )
    return Path(result["run_dir"])


def analyze_run_quiet(run_dir: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return analyze_run(run_dir)
    finally:
        stdout_path.write_text(stdout.getvalue(), encoding="utf-8")
        stderr_path.write_text(stderr.getvalue(), encoding="utf-8")


def analyze_and_seed(
    *,
    run_dir: Path,
    loop_dir: Path,
    candidate_context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
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
        "selected_stage": signal.get("selected_component"),
        "selected_signal": signal.get("selected_signal"),
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
    changed = run_cmd(["git", "diff", "--name-only"], cwd=child_ws)
    return {
        "status": "applied",
        "patch_paths": applied_patches,
        "excluded_prompt": DATA_AGENT_CANONICAL_PROMPT.as_posix(),
        "changed_files": [line for line in changed.stdout.splitlines() if line.strip()],
    }


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
        "selected_stage": child_signal.get("selected_component"),
        "selected_signal": child_signal.get("selected_signal"),
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
    child_failure_gate = None
    if helper_usage.get("status") == "helper_not_used_by_child_generated_code":
        child_failure_gate = "helper_not_used_by_child_generated_code"
    report = {
        "status": "completed",
        "final_status": "candidate_child_eval_passed" if child_analysis.get("passed") else "candidate_child_eval_failed",
        "workspace": str(child_ws),
        "parent_source_materialization": parent_source_materialization,
        "child_run_dir": str(child_run_dir),
        "child_run_exit_code": proc.returncode,
        "child_passed": child_analysis.get("passed"),
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
        "child_failure_gate": child_failure_gate,
        "child_status": {
            "status": "completed",
            "passed_original_dab_validation": child_analysis.get("passed"),
            "validation_reason": child_analysis.get("validation_reason"),
            "selected_stage": child_signal.get("selected_component"),
            "selected_signal": child_signal.get("selected_signal"),
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
    )
    parent_agent_id = parent["card"]["agent_id"]
    initial_parent_agent_id = parent_agent_id
    meta_agent = select_meta_agent(archive_root, args.meta_agent_id)
    meta_agent_id = meta_agent["card"]["agent_id"] if meta_agent else None
    prompt_path = prompt_for_parent(parent, Path(args.prompt) if args.prompt else None)
    case_dir = Path(args.case_dir).resolve()
    dab_root = Path(args.dab_root).resolve()
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
        "parent_selection_policy": {
            "initial_parent_override": args.parent_agent_id,
            "subsequent_iterations": "select current top-ranked recent data_agent from archive after candidate postprocess",
            "archive_max_parent_age_hours": args.archive_max_parent_age_hours,
            "repeated_parent_penalty": args.repeated_parent_penalty,
        },
        "stages": [
            "select_parent_from_archive",
            "select_meta_agent_protocol_from_archive",
            "run_or_reuse_parent_data_agent",
            "analyze_parent_and_seed_repair",
            "invoke_candidate_launcher",
            "optional_generic_child_eval",
            "postprocess_candidate_archive",
            "select_next_parent_from_archive_top_ranked",
        ],
    }
    write_json(loop_dir / "loop_plan.json", plan)
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
            },
        )
        if parent_run is None or args.rerun_parent_each_iteration:
            parent_run = run_parent_case(
                case_dir=case_dir,
                prompt_path=prompt_path,
                version=f"meta_loop_parent_iter{iteration:03d}_{utc_now_slug()}",
                dab_root=dab_root,
                timeout_sec=args.timeout_sec,
            )
        seed, seed_path = analyze_and_seed(
            run_dir=parent_run,
            loop_dir=iteration_dir,
            candidate_context={"parent_agent_id": parent_agent_id, "iteration": iteration, "repair_profile": args.repair_profile},
        )
        if args.repair_seed:
            seed_path = Path(args.repair_seed).resolve()
            if not seed_path.exists():
                raise SystemExit(f"repair_seed not found: {seed_path}")
            seed = load_json(seed_path) or {}
            write_json(
                iteration_dir / "repair_seed_override.json",
                {
                    "status": "using_repair_seed_override",
                    "override_seed_path": str(seed_path),
                    "override_seed": seed,
                    "parent_analysis_seed_path": str(iteration_dir / "repair_seed.json"),
                },
            )
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

        results.append(
            {
                "iteration": iteration,
                "candidate_id": candidate_id,
                "candidate_dir": str(candidate_dir),
                "data_parent_agent_id": parent_agent_id,
                "meta_agent_protocol_id": meta_agent_id,
                "parent_run": str(parent_run),
                "seed": seed,
                "launcher_exit_code": launcher_exit,
                "child_eval": child_eval,
                "postprocess_exit_code": postprocess_exit,
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
                    "status": "selected_from_archive_top_ranked_recent_with_repeated_penalty",
                    "previous_parent_agent_id": parent_agent_id,
                    "next_parent_agent_id": next_parent["card"]["agent_id"],
                    "selection_score": next_parent.get("selection_score"),
                    "parent_history": parent_history,
                    "policy": "archive_top_ranked_recent_after_candidate_postprocess_with_repeated_parent_penalty",
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
    parser.add_argument("--run-generic-child-eval", action="store_true")
    parser.set_defaults(func=run_loop)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

