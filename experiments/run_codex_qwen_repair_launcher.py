#!/usr/bin/env python3
"""Unified Codex-Qwen repair launcher.

This is the reusable candidate-generation step used by the higher-level
meta-agent loop.  It replaces one-off repair launchers with profile-driven
behavior:

- ``analyzer_infra_repair``: feedback/error-analysis infrastructure repair.
- ``data_agent_prompt_repair``: DAB data-agent prompt repair.

The launcher never merges into the main workspace.  It creates an isolated
workspace, asks for or reads a structured JSON ``patch_spec``, applies it
deterministically, runs gates/validation, and writes a candidate bundle.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

META_AGENT_PROJECT_MEMORY_SKILL = ROOT / "skills/dab-meta-agent-project-memory/SKILL.md"

PROFILE_SKILLS = {
    "data_agent_prompt_repair": ROOT / "skills/dab-data-agent-prompt-repair/SKILL.md",
    "data_agent_project_repair": ROOT / "skills/dab-patents-project-repair/SKILL.md",
    "data_agent_tool_repair": ROOT / "skills/dab-patents-project-repair/SKILL.md",
}

try:
    from experiments.helper_repair_planner import plan_helper_repair
except Exception:  # pragma: no cover
    plan_helper_repair = None  # type: ignore[assignment]

try:
    from experiments.open_diagnosis import compact_open_diagnosis_evidence
except Exception:  # pragma: no cover
    compact_open_diagnosis_evidence = None  # type: ignore[assignment]

try:
    from experiments.gate_policy import GATE_POLICY_SCHEMA_VERSION, decorate_validation_gate, should_block_validation
except Exception:  # pragma: no cover
    GATE_POLICY_SCHEMA_VERSION = "gate_policy_unavailable"

    def decorate_validation_gate(result: dict[str, Any]) -> dict[str, Any]:
        return result

    def should_block_validation(result: dict[str, Any]) -> bool:
        return result.get("hard_fail", True) and result.get("exit_code") not in (None, 0)

try:
    from llm_client import call_meta_llm, describe_llm_config
except Exception:  # pragma: no cover
    call_meta_llm = None  # type: ignore[assignment]
    describe_llm_config = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RepairProfile:
    name: str
    allowed_patterns: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    operations: tuple[str, ...]
    risk_scope: str
    required_ack: tuple[str, ...]
    max_changed_lines: int
    required_public_functions: tuple[str, ...] = ()
    py_compile_files: tuple[str, ...] = ()
    import_modules: tuple[str, ...] = ()


PROFILES: dict[str, RepairProfile] = {
    "analyzer_infra_repair": RepairProfile(
        name="analyzer_infra_repair",
        allowed_patterns=(
            "adapters/feedback/common_trace_checks.py",
            "adapters/feedback/dab_patents_checks.py",
        ),
        forbidden_patterns=("prompts/**", "logs/**", "candidates/**", "archive/**", "trajectories/**"),
        operations=("replace_text_once", "insert_after_anchor", "insert_before_anchor", "append_text", "create_file"),
        risk_scope="minimal/local/common_api_preserved",
        required_ack=("no_common_module_rewrite", "no_delete_analyzer_dependencies", "no_broad_refactor"),
        max_changed_lines=80,
        required_public_functions=("extract_trace_based_errors", "extract_operation_event_errors"),
        py_compile_files=(
            "adapters/feedback/common_trace_checks.py",
            "adapters/feedback/dab_patents_checks.py",
        ),
        import_modules=(
            "adapters.feedback.common_trace_checks",
            "adapters.feedback.dab_patents_checks",
        ),
    ),
    "data_agent_prompt_repair": RepairProfile(
        name="data_agent_prompt_repair",
        allowed_patterns=(
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        ),
        forbidden_patterns=(
            "adapters/feedback/**",
            "experiments/analyze_agent_error.py",
            "experiments/extract_primary_signal.py",
            "logs/**",
            "candidates/**",
            "archive/**",
            "trajectories/**",
        ),
        operations=("replace_text_once", "insert_after_anchor", "insert_before_anchor", "append_text"),
        risk_scope="minimal/local/data_agent_prompt_only",
        required_ack=("no_feedback_analyzer_changes", "no_hardcoded_answer", "no_broad_refactor"),
        max_changed_lines=140,
    ),
    "data_agent_tool_repair": RepairProfile(
        name="data_agent_tool_repair",
        allowed_patterns=(
            "adapters/patents/**/*.py",
            "adapters/patents/*.py",
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "experiments/run_dab_agent.py",
            "adapters/runtime_observer.py",
            "experiments/build_meta_agent_evidence_pack.py",
        ),
        forbidden_patterns=(
            "logs/**",
            "candidates/**",
            "archive/**",
            "trajectories/**",
            "reports/**",
            "benchmarks/**",
            "legacy/**",
            "data/**",
            "adapters/feedback/**",
            "**/__pycache__/**",
            "*.pyc",
            ".git/**",
            ".venv/**",
            ".codex/**",
        ),
        operations=("replace_text_once", "insert_after_anchor", "insert_before_anchor", "append_text", "create_file"),
        risk_scope="minimal/local/data_agent_tool_repair",
        required_ack=("no_control_artifact_changes", "no_benchmark_data_changes", "no_hardcoded_answer", "no_broad_refactor"),
        max_changed_lines=220,
    ),
    "data_agent_project_repair": RepairProfile(
        name="data_agent_project_repair",
        allowed_patterns=(
            "prompts/dab/**/*.txt",
            "prompts/dab/*.txt",
            "adapters/**/*.py",
            "adapters/*.py",
            "experiments/*.py",
            "llm_client.py",
        ),
        forbidden_patterns=(
            "logs/**",
            "candidates/**",
            "archive/**",
            "trajectories/**",
            "reports/**",
            "benchmarks/**",
            "legacy/**",
            "data/**",
            "**/__pycache__/**",
            "*.pyc",
            ".git/**",
            ".venv/**",
            ".codex/**",
        ),
        operations=("replace_text_once", "insert_after_anchor", "insert_before_anchor", "append_text"),
        risk_scope="minimal/local/project_repair",
        required_ack=("no_control_artifact_changes", "no_benchmark_data_changes", "no_hardcoded_answer", "no_broad_refactor"),
        max_changed_lines=180,
    ),
}

GATE_SCHEMA_VERSION = "profile_gate_schema_v001"

PROFILE_GATE_VERSIONS = {
    "analyzer_infra_repair": "analyzer_infra_repair_gate_v001",
    "data_agent_prompt_repair": "data_agent_prompt_repair_gate_v002",
    "data_agent_project_repair": "data_agent_project_repair_gate_v003",
    "data_agent_tool_repair": "data_agent_tool_repair_gate_v006",
}

VALIDATION_GATE_CATALOG: dict[str, dict[str, str]] = {
    "no_obvious_answer_hardcoding": {
        "gate_layer": "hard_safety",
        "gate_type": "anti_cheating",
        "purpose": "Reject patch specs that hardcode expected answers, ground truth, or answer-count shortcuts.",
    },
    "data_agent_tool_helper_plan_alignment": {
        "gate_layer": "task_contract",
        "gate_type": "fine_grained_feedback_alignment",
        "purpose": "Require helper targets to match the deterministic helper plan derived from fine-grained feedback.",
    },
    "data_agent_tool_helper_integration": {
        "gate_layer": "task_contract",
        "gate_type": "runtime_integration",
        "purpose": "Require reusable helper changes to be discoverable by generated_solve.py via prompt glue or runner integration.",
    },
    "data_agent_tool_helper_quality": {
        "gate_layer": "task_contract",
        "gate_type": "no_op_or_metric_gaming_guard",
        "purpose": "Reject helper implementations that merely restate the old rule, sort without filtering, or game answer cardinality.",
    },
    "static_prompt_repair_checks": {
        "gate_layer": "validation",
        "gate_type": "static_prompt_contract",
        "purpose": "Record that prompt-only static checks passed.",
    },
    "static_project_repair_checks": {
        "gate_layer": "validation",
        "gate_type": "static_project_contract",
        "purpose": "Record that project-source static checks passed.",
    },
    "static_data_agent_tool_repair_checks": {
        "gate_layer": "validation",
        "gate_type": "static_tool_contract",
        "purpose": "Record that data-agent tool repair static checks passed.",
    },
}


def profile_gate_version(profile: RepairProfile) -> str:
    return PROFILE_GATE_VERSIONS.get(profile.name, f"{profile.name}_gate_v001")


def profile_gate_protocol(profile: RepairProfile) -> dict[str, Any]:
    """Describe the gate contract used for this candidate.

    The protocol is intentionally data-only so archive/selector code can later
    compare candidates by gate version instead of treating all failures as
    equivalent.
    """
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "gate_policy_schema_version": GATE_POLICY_SCHEMA_VERSION,
        "repair_profile": profile.name,
        "profile_gate_version": profile_gate_version(profile),
        "gate_policy": {
            "hard_gate": "Safety, protocol, benchmark integrity, non-empty real patch, and executable syntax/import checks can block candidate validation.",
            "soft_observation": "Semantic/interface/tool-contract checks are recorded for archive evidence and next-iteration meta-agent learning rather than used as human-coded repair vetoes.",
            "promotion_gate": "Child eval and parent-child metrics decide parent eligibility; failed candidates can still seed future repair as evidence.",
        },
        "hard_gates": [
            {
                "name": "patch_spec_schema",
                "gate_layer": "protocol",
                "gate_type": "structured_patch_spec",
                "purpose": "Qwen must output parseable JSON patch_spec/no_op_failed, not free-form patches.",
            },
            {
                "name": "allowed_source_scope",
                "gate_layer": "hard_safety",
                "gate_type": "scope_control",
                "purpose": "Changed files must match the profile allowlist and avoid control artifacts.",
                "allowed_patterns": list(profile.allowed_patterns),
                "forbidden_patterns": list(profile.forbidden_patterns),
            },
            {
                "name": "non_empty_patch",
                "gate_layer": "protocol",
                "gate_type": "real_diff_required",
                "purpose": "patch.diff and project_changed_files must be non-empty before validation.",
            },
            {
                "name": "diff_size_limit",
                "gate_layer": "hard_safety",
                "gate_type": "minimality",
                "purpose": "Reject large rewrites for a local repair task.",
                "max_changed_lines": profile.max_changed_lines,
            },
        ],
        "task_contract_gates": [
            {"name": name, **meta}
            for name, meta in VALIDATION_GATE_CATALOG.items()
            if (
                name.startswith("data_agent_tool_helper")
                and profile.name == "data_agent_tool_repair"
            )
            or name == "no_obvious_answer_hardcoding"
        ],
        "validation_gates": [
            {
                "name": "py_compile_changed_python_files",
                "gate_layer": "validation",
                "gate_type": "syntax",
                "purpose": "Every changed Python file must compile.",
            },
            *[
                {
                    "name": f"import_{module.replace('.', '_')}",
                    "gate_layer": "validation",
                    "gate_type": "module_import",
                    "purpose": "Required public modules must remain importable.",
                    "module": module,
                }
                for module in profile.import_modules
            ],
        ],
        "soft_score_inputs": [
            "answer_delta",
            "parent_child_delta_f1",
            "selected_stage",
            "selected_signal",
            "fine_grained_feedback_alignment",
            "helper_usage_observed_in_child",
            "new_stage_errors",
        ],
        "notes": [
            "Hard gates decide candidate validity before child eval.",
            "Task contract gates encode the repair profile's causal hypothesis.",
            "Soft score inputs are for archive selection and future bandit-style parent selection, not immediate patch validity.",
        ],
    }


def gate_result(
    profile: RepairProfile,
    name: str,
    *,
    exit_code: int = 0,
    reason: str | None = None,
    file: str | None = None,
    gate_layer: str | None = None,
    gate_type: str | None = None,
    hard_fail: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    catalog = VALIDATION_GATE_CATALOG.get(name, {})
    result: dict[str, Any] = {
        "name": name,
        "exit_code": exit_code,
        "gate_layer": gate_layer or catalog.get("gate_layer", "validation"),
        "gate_type": gate_type or catalog.get("gate_type", "runtime_check"),
        "profile_gate_version": profile_gate_version(profile),
        "hard_fail": hard_fail,
    }
    if reason is not None:
        result["reason"] = reason
    if file is not None:
        result["file"] = file
    if catalog.get("purpose"):
        result["purpose"] = catalog["purpose"]
    result.update(extra)
    return decorate_validation_gate(result)


FINAL_STATUSES = {
    "valid_candidate_pending_child_eval",
    "no_op_failed",
    "protocol_failed_invalid_patch_spec",
    "protocol_failed_seed_mismatch",
    "patch_apply_failed",
    "protocol_failed_empty_patch",
    "rejected_large_rewrite",
    "failed_validation",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n\n[TRUNCATED]\n"
    return text


def run_cmd(
    args: list[str],
    *,
    cwd: Path,
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


def normalize_rel(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def is_allowed_file(path: str, profile: RepairProfile) -> bool:
    rel = normalize_rel(path)
    return matches_any(rel, profile.allowed_patterns) and not matches_any(rel, profile.forbidden_patterns)


def ignore_workspace(_: str, names: list[str]) -> list[str]:
    ignored = {".git", ".venv", ".env", ".codex", "__pycache__", "logs", "candidates", "archive", "reports", "trajectories"}
    return [name for name in names if name in ignored]


DATA_AGENT_CANONICAL_PROMPT = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")


def resolve_prompt_source(prompt: Path, workspace: Path) -> Path:
    if prompt.is_absolute():
        return prompt
    root_candidate = ROOT / prompt
    if root_candidate.exists():
        return root_candidate
    return workspace / prompt


def materialize_parent_prompt(
    *,
    profile: RepairProfile,
    workspace: Path,
    candidate_dir: Path,
    parent_prompt: Path | None,
) -> Path | None:
    if profile.name not in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair"} or parent_prompt is None:
        return parent_prompt
    source = resolve_prompt_source(parent_prompt, workspace)
    if not source.exists():
        raise FileNotFoundError(f"parent prompt not found: {parent_prompt}")
    target = workspace / DATA_AGENT_CANONICAL_PROMPT
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    write_json(
        candidate_dir / "materialized_parent_prompt.json",
        {
            "status": "materialized_parent_prompt",
            "source_prompt": str(source),
            "canonical_target": str(DATA_AGENT_CANONICAL_PROMPT),
        },
    )
    amend = run_cmd(["git", "add", str(DATA_AGENT_CANONICAL_PROMPT)], cwd=workspace)
    if amend.returncode != 0:
        raise RuntimeError(f"failed to stage materialized parent prompt: {amend.stderr}")
    amend = run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=workspace)
    if amend.returncode != 0:
        raise RuntimeError(f"failed to amend materialized parent prompt into baseline: {amend.stderr}")
    return DATA_AGENT_CANONICAL_PROMPT

def load_parent_agent_card(parent_agent_id: str | None) -> dict[str, Any] | None:
    if not parent_agent_id:
        return None
    card_path = ROOT / "archive" / "agents" / parent_agent_id / "agent_card.json"
    if not card_path.exists():
        return None
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return card if isinstance(card, dict) else None


def resolve_parent_candidate_patches(parent_agent_id: str | None) -> list[Path]:
    patches: list[Path] = []
    seen: set[str] = set()

    def collect(agent_id: str | None) -> None:
        if not agent_id or agent_id in seen:
            return
        seen.add(agent_id)
        card = load_parent_agent_card(agent_id)
        if not card:
            return
        lineage = card.get("lineage") if isinstance(card.get("lineage"), dict) else {}
        collect(str(lineage.get("parent_agent_id") or ""))
        source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
        patch_ref = source_refs.get("candidate_patch")
        if not patch_ref:
            return
        patch_path = Path(str(patch_ref))
        if not patch_path.is_absolute():
            patch_path = ROOT / patch_path
        if patch_path.exists() and patch_path not in patches:
            patches.append(patch_path)

    collect(parent_agent_id)
    return patches


def materialize_parent_source_patch(
    *,
    profile: RepairProfile,
    workspace: Path,
    candidate_dir: Path,
    parent_agent_id: str | None,
) -> dict[str, Any]:
    if profile.name not in {"data_agent_project_repair", "data_agent_tool_repair"}:
        return {"status": "skipped", "reason": f"profile {profile.name} does not materialize parent source"}
    patch_paths = resolve_parent_candidate_patches(parent_agent_id)
    if not patch_paths:
        result = {"status": "skipped", "reason": "parent candidate patch missing or not declared", "parent_agent_id": parent_agent_id}
        write_json(candidate_dir / "materialized_parent_source.json", result)
        return result
    applied_patches: list[str] = []
    for patch_path in patch_paths:
        if not patch_path.read_text(encoding="utf-8", errors="replace").strip():
            continue
        apply_proc = run_cmd(
            [
                "git",
                "apply",
                f"--exclude={DATA_AGENT_CANONICAL_PROMPT.as_posix()}",
                str(patch_path),
            ],
            cwd=workspace,
        )
        if apply_proc.returncode != 0:
            result = {
                "status": "failed",
                "reason": "parent source patch apply failed",
                "parent_agent_id": parent_agent_id,
                "patch_path": str(patch_path),
                "applied_patches": applied_patches,
                "stderr": apply_proc.stderr,
            }
            write_json(candidate_dir / "materialized_parent_source.json", result)
            raise RuntimeError(result["reason"] + ": " + apply_proc.stderr)
        applied_patches.append(str(patch_path))
    if not applied_patches:
        result = {"status": "skipped", "reason": "parent candidate patches empty", "parent_agent_id": parent_agent_id, "patch_paths": [str(path) for path in patch_paths]}
        write_json(candidate_dir / "materialized_parent_source.json", result)
        return result
    changed = run_cmd(["git", "diff", "--name-only"], cwd=workspace)
    changed_files = [line for line in changed.stdout.splitlines() if line.strip()]
    amend = run_cmd(["git", "add", "."], cwd=workspace)
    if amend.returncode != 0:
        raise RuntimeError(f"failed to stage materialized parent source: {amend.stderr}")
    amend = run_cmd(["git", "commit", "--quiet", "--amend", "--no-edit"], cwd=workspace)
    if amend.returncode != 0:
        raise RuntimeError(f"failed to amend materialized parent source into baseline: {amend.stderr}")
    result = {
        "status": "applied",
        "parent_agent_id": parent_agent_id,
        "patch_paths": applied_patches,
        "excluded_prompt": DATA_AGENT_CANONICAL_PROMPT.as_posix(),
        "changed_files": changed_files,
    }
    write_json(candidate_dir / "materialized_parent_source.json", result)
    return result


def make_workspace(candidate_dir: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="codex_qwen_repair."))
    workspace = root / "workspace"
    shutil.copytree(ROOT, workspace, ignore=ignore_workspace, symlinks=True)
    run_cmd(["git", "init", "--quiet"], cwd=workspace)
    run_cmd(["git", "config", "user.name", "codex-qwen-repair-launcher"], cwd=workspace)
    run_cmd(["git", "config", "user.email", "codex-qwen-repair-launcher@localhost"], cwd=workspace)
    run_cmd(["git", "add", "."], cwd=workspace)
    commit = run_cmd(["git", "commit", "--quiet", "-m", "baseline"], cwd=workspace)
    if commit.returncode != 0:
        raise RuntimeError(f"failed to create isolated baseline: {commit.stderr}")
    write_json(candidate_dir / "workspace.json", {"workspace": str(workspace), "created_at": utc_now()})
    return workspace


def escape_invalid_json_backslashes(raw: str) -> str:
    valid_json_escapes = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}
    out: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] != "\\":
            out.append(raw[index])
            index += 1
            continue
        end = index
        while end < len(raw) and raw[end] == "\\":
            end += 1
        run_length = end - index
        next_char = raw[end] if end < len(raw) else ""
        if run_length % 2 == 1 and next_char and next_char not in valid_json_escapes:
            out.append("\\" * (run_length + 1))
        else:
            out.append("\\" * run_length)
        index = end
    return "".join(out)


def json_loads_lenient_model_output(raw: str) -> Any:
    r"""Parse model-emitted JSON with one conservative repair.

    Qwen occasionally emits Python code inside JSON strings with Python-style
    escapes such as ``\'`` or ``\.``.  These are invalid JSON escapes.  When
    a run of backslashes is followed by a non-JSON escape character, preserve
    the intended backslash by adding one more backslash before JSON parsing.
    All other JSON syntax remains strict.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repaired = escape_invalid_json_backslashes(raw)
        if repaired == raw:
            raise
        return json.loads(repaired)

def extract_first_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    try:
        value = json_loads_lenient_model_output(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE):
        try:
            value = json_loads_lenient_model_output(block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json_loads_lenient_model_output(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None



def load_repair_seed_json(repair_seed: Path | None) -> dict[str, Any]:
    if repair_seed is None or not repair_seed.exists():
        return {}
    try:
        value = json.loads(repair_seed.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def load_repair_routing(repair_seed: Path | None) -> dict[str, Any]:
    seed = load_repair_seed_json(repair_seed)
    routing = seed.get("repair_routing")
    if not isinstance(routing, dict):
        fine = seed.get("fine_grained_feedback") if isinstance(seed.get("fine_grained_feedback"), dict) else {}
        routing = fine.get("repair_routing") if isinstance(fine, dict) else None
    return routing if isinstance(routing, dict) else {}


def repair_seed_feedback_for_planner(seed: dict[str, Any]) -> dict[str, Any]:
    fine = seed.get("fine_grained_feedback") if isinstance(seed.get("fine_grained_feedback"), dict) else None
    if isinstance(fine, dict) and (fine.get("selected_stage") or fine.get("selected_signal")):
        feedback = dict(fine)
        for key in (
            "selected_stage",
            "selected_signal",
            "answer_delta",
            "analysis_summary",
            "repair_routing",
            "runtime_trace_evidence",
            "ranked_feedback_signals",
            "parent_capabilities",
            "patch_generation_feedback",
        ):
            if key not in feedback and key in seed:
                feedback[key] = seed.get(key)
        return feedback
    return seed


def cached_helper_repair_plan_from_seed(seed: dict[str, Any]) -> dict[str, Any]:
    plan = seed.get("helper_repair_plan")
    if not isinstance(plan, dict):
        fine = seed.get("fine_grained_feedback") if isinstance(seed.get("fine_grained_feedback"), dict) else {}
        plan = fine.get("helper_repair_plan") if isinstance(fine, dict) else None
    return plan if isinstance(plan, dict) else {}


def load_helper_repair_plan(repair_seed: Path | None) -> dict[str, Any]:
    seed = load_repair_seed_json(repair_seed)
    if not seed:
        return {}
    cached_plan = cached_helper_repair_plan_from_seed(seed)
    feedback = repair_seed_feedback_for_planner(seed)
    repair_profile = str(seed.get("repair_profile") or feedback.get("repair_profile") or "data_agent_tool_repair")
    if plan_helper_repair is not None and isinstance(feedback, dict) and (feedback.get("selected_stage") or feedback.get("selected_signal")):
        try:
            recomputed = plan_helper_repair(feedback, repair_profile)
        except Exception:
            recomputed = {}
        if isinstance(recomputed, dict) and recomputed.get("status") == "planned":
            recomputed = dict(recomputed)
            recomputed["plan_source"] = "recomputed_from_repair_seed_with_current_planner"
            if cached_plan:
                recomputed["cached_helper_repair_plan_ignored"] = True
                recomputed["cached_helper_repair_plan_ignore_reason"] = (
                    "Repair seed helper_repair_plan was recomputed with the current planner to avoid stale cached routing."
                )
            return recomputed
    if cached_plan:
        cached_plan = dict(cached_plan)
        cached_plan.setdefault("plan_source", "cached_in_repair_seed")
        return cached_plan
    return {}


def is_prompt_path(path: str) -> bool:
    rel = normalize_rel(path)
    return rel.startswith("prompts/") and rel.endswith(".txt")


def prompt_edit_looks_like_code_payload(text: str) -> bool:
    low = text.lower()
    if "json.loads" in low or "sqlite3" in low:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^def\s+\w+\s*\(", stripped):
            return True
        if re.match(r"^(from\s+\S+\s+import\s+\S+|import\s+\S+)", stripped):
            helper_import_instruction = "adapters.patents" in stripped and any(
                marker in low
                for marker in ("must import", "must use", "reusable helper", "do not reimplement", "instead of reimplementing")
            )
            if helper_import_instruction:
                continue
            return True
    return False


def prompt_edit_is_helper_glue(text: str) -> bool:
    low = text.lower()
    return "adapters.patents" in text and any(
        marker in low
        for marker in (
            "must import",
            "must use",
            "reusable helper",
            "do not reimplement",
            "instead of reimplementing",
        )
    )


def validate_project_repair_routing(
    spec: dict[str, Any],
    *,
    profile: RepairProfile,
    repair_seed: Path | None,
    candidate_dir: Path,
) -> tuple[bool, str]:
    if profile.name != "data_agent_project_repair":
        return True, "ok"
    routing = load_repair_routing(repair_seed)
    if not routing:
        return True, "ok"

    target_files = [str(path) for path in spec.get("target_files") or []]
    prompt_only = bool(target_files) and all(is_prompt_path(path) for path in target_files)
    policy = routing.get("prompt_only_policy") if isinstance(routing.get("prompt_only_policy"), dict) else {}
    policy_status = str(policy.get("status") or "")
    source_required = bool(policy.get("source_change_required")) or policy_status == "reject"

    write_json(
        candidate_dir / "repair_routing_used.json",
        {
            "status": "loaded",
            "routing": routing,
            "target_files": target_files,
            "prompt_only": prompt_only,
        },
    )

    if prompt_only and source_required:
        return False, f"repair_routing rejects prompt-only patch for layer {routing.get('recommended_repair_layer')}"

    combined = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    ).lower()
    routing_text = "\n".join(
        str(routing.get(key) or "")
        for key in ("recommended_repair_layer", "routing_reason")
    ).lower()
    concrete_terms = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{4,}", routing_text):
        if token not in {"repair", "layer", "target", "failure", "active", "generated", "source", "prompt", "files"} and token not in concrete_terms:
            concrete_terms.append(token)
    matched = [term for term in concrete_terms[:12] if term in combined]

    if prompt_only and policy_status in {"weak_allowed", "allowed_if_specific"} and len(matched) == 0:
        return False, "prompt-only project repair does not mention the repair_routing layer/reason in rationale"
    return True, "ok"


def compact_repair_seed_summary(seed: dict[str, Any]) -> dict[str, Any]:
    """Keep only cross-project seed fields that guide patch generation.

    Full repair_seed can duplicate patch_generation_feedback, helper plan, and
    fine_grained_feedback.  The context pack should expose a compact index and
    artifact paths, not the entire nested seed.
    """
    keys = (
        "seed_id",
        "created_at",
        "parent_run_dir",
        "selected_stage",
        "selected_signal",
        "repair_profile",
        "analysis_summary",
        "parent_capabilities",
        "answer_delta",
        "candidate_context",
    )
    summary = {key: seed.get(key) for key in keys if seed.get(key) is not None}
    open_diag = seed.get("open_diagnosis_evidence")
    if isinstance(open_diag, dict):
        summary["open_diagnosis_evidence"] = compact_open_diagnosis_evidence(open_diag) if compact_open_diagnosis_evidence else open_diag
    fine = seed.get("fine_grained_feedback") if isinstance(seed.get("fine_grained_feedback"), dict) else {}
    paths = fine.get("full_evidence_pack_paths") if isinstance(fine.get("full_evidence_pack_paths"), dict) else None
    if paths:
        summary["full_evidence_pack_paths"] = paths
    archive_selection = seed.get("archive_selection") if isinstance(seed.get("archive_selection"), dict) else {}
    if archive_selection:
        summary["archive_selection"] = {
            "schema_version": archive_selection.get("schema_version"),
            "selection_path": archive_selection.get("selection_path"),
            "current_failure_tags": archive_selection.get("current_failure_tags"),
            "parent_pool_preview": (archive_selection.get("parent_pool_preview") or [])[:3],
            "evidence_pool": (archive_selection.get("evidence_pool") or [])[:5],
        }
    priority = seed.get("archive_evidence_priority_observations")
    if priority:
        summary["archive_evidence_priority_observations"] = priority
    return summary


def compact_parent_artifact(name: str, artifact: Path) -> tuple[str, str]:
    fence = "json" if artifact.suffix == ".json" else "text"
    if name == "agent_error_summary.json":
        data = load_repair_seed_json(artifact)
        if data:
            compact = {
                "passed": data.get("passed"),
                "validation_reason": data.get("validation_reason"),
                "selected_signal": data.get("selected_signal"),
                "localized_errors_sample": (data.get("localized_errors") or [])[:5] if isinstance(data.get("localized_errors"), list) else None,
                "preserved_invariants": data.get("preserved_invariants"),
            }
            return "json", json.dumps(compact, indent=2, ensure_ascii=False)
        return fence, read_text(artifact, 3000)
    if name == "stage_trace.json":
        data = load_repair_seed_json(artifact)
        if isinstance(data, list):
            interesting = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                event = str(item.get("event") or "")
                severity = str(item.get("severity") or "")
                trigger = str(item.get("trigger") or "")
                if event in {"candidate_decision_summary", "final_answer_written", "ema_best_years_computed", "cpc_mapping_summary", "cpc_level5_mapping_summary", "granularity_mapping_fallback_used", "no_years_found"} or severity in {"warning", "error"} or trigger in {"runtime_check_failed", "runtime_anomaly"}:
                    interesting.append(item)
                if len(interesting) >= 8:
                    break
            return "json", json.dumps(interesting, indent=2, ensure_ascii=False)
        return fence, read_text(artifact, 2500)
    if name == "generated_solve.py":
        text = read_text(artifact)
        keywords = ("candidate", "best_year", "ema", "final_answer", "level", "mapping", "helper", "diagnostic")
        snippets: list[str] = []
        lines = text.splitlines()
        used: set[int] = set()
        for idx, line in enumerate(lines):
            if not any(key in line.lower() for key in keywords):
                continue
            start = max(0, idx - 4)
            end = min(len(lines), idx + 10)
            if any(i in used for i in range(start, end)):
                continue
            used.update(range(start, end))
            snippets.append("\n".join(f"{i+1}: {lines[i]}" for i in range(start, end)))
            if sum(len(item) for item in snippets) > 5000:
                break
        return "python", "\n\n# ... snippet ...\n".join(snippets) if snippets else read_text(artifact, 3000)
    if name == "final_answer.txt":
        return "text", read_text(artifact, 1500)
    return fence, read_text(artifact, 2500)


def recommended_context_source_files(profile: RepairProfile, repair_seed: Path | None) -> list[str]:
    seed = load_repair_seed_json(repair_seed)
    routing = load_repair_routing(repair_seed)
    helper_plan = load_helper_repair_plan(repair_seed)
    recommended: list[str] = []

    def add(path: Any) -> None:
        rel = normalize_rel(str(path or ""))
        if rel and rel not in recommended:
            recommended.append(rel)

    if isinstance(helper_plan, dict):
        add(helper_plan.get("recommended_helper_file"))
        add(helper_plan.get("recommended_prompt_glue_file"))
    for item in (routing.get("recommended_target_files") if isinstance(routing, dict) else []) or []:
        add(item)

    if profile.name == "data_agent_tool_repair":
        # Tool repair needs helper targets and thin prompt glue, not analyzer or
        # meta-agent implementation internals by default.
        defaults = [
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "adapters/patents/__init__.py",
            "adapters/patents/cpc_mapping.py",
            "adapters/patents/ema.py",
            "adapters/patents/patent_query_utils.py",
        ]
    elif profile.name == "data_agent_project_repair":
        defaults = [
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "experiments/run_dab_agent.py",
            "adapters/runtime_observer.py",
            "adapters/patents/cpc_mapping.py",
            "adapters/patents/ema.py",
            "adapters/patents/patent_query_utils.py",
        ]
    elif profile.name == "analyzer_infra_repair":
        defaults = list(profile.allowed_patterns)
    else:
        defaults = ["prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt"]
    for item in defaults:
        add(item)
    return [path for path in recommended if "*" not in path][:8]


def source_excerpt_limit(profile: RepairProfile, rel: str) -> int:
    if is_prompt_path(rel):
        return 6000 if profile.name == "data_agent_prompt_repair" else 4500
    if rel.startswith("adapters/patents/"):
        return 6500
    if rel in {"experiments/run_dab_agent.py", "adapters/runtime_observer.py"}:
        return 4500
    return 3000


def build_context_pack(
    *,
    profile: RepairProfile,
    workspace: Path,
    candidate_dir: Path,
    repair_seed: Path | None,
    parent_run: Path | None,
    parent_prompt: Path | None,
    repair_seed_override: bool = False,
) -> Path:
    lines: list[str] = [
        f"# Minimal source context pack: {profile.name}",
        "",
        "The meta-agent must output strict JSON patch_spec only.",
        "",
        "## Profile",
        f"- risk_scope: `{profile.risk_scope}`",
        f"- max_changed_lines: `{profile.max_changed_lines}`",
        "- allowed patterns:",
        *[f"  - `{item}`" for item in profile.allowed_patterns],
        "- forbidden patterns:",
        *[f"  - `{item}`" for item in profile.forbidden_patterns],
        "- deterministic operations:",
        *[f"  - `{item}`" for item in profile.operations],
        "",
    ]
    if repair_seed_override:
        lines += [
            "## Repair seed override policy",
            "The Repair seed below is the PRIMARY objective for this candidate.",
            "Parent run artifacts are background context only; do not repair an unrelated parent traceback or runtime API issue unless it directly supports the override seed.",
            "The patch_spec rationale and intended_change must explicitly address the override seed selected_stage/selected_signal.",
            "If no minimal prompt repair can address the override seed, output no_op_failed instead of repairing a different issue.",
            "",
        ]
    if META_AGENT_PROJECT_MEMORY_SKILL.exists():
        lines += [
            "## Active project memory skill",
            f"Path: `{META_AGENT_PROJECT_MEMORY_SKILL.relative_to(ROOT)}`",
            "This project memory skill has priority over generic repair heuristics when they conflict.",
            "```markdown",
            read_text(META_AGENT_PROJECT_MEMORY_SKILL, 12000),
            "```",
            "",
        ]
    skill_path = PROFILE_SKILLS.get(profile.name)
    if skill_path and skill_path.exists():
        lines += [
            "## Active repair skill",
            f"Path: `{skill_path.relative_to(ROOT)}`",
            "Follow this skill before proposing a patch_spec, subject to the project memory skill above.",
            "```markdown",
            read_text(skill_path, 12000),
            "```",
            "",
        ]
    if profile.name == "data_agent_prompt_repair":
        lines += [
            "## Runtime observer API contract",
            "These signatures are authoritative for generated DAB code. Do not infer alternate signatures from stack traces.",
            "```python",
            "def log_exception(event: str, exc: BaseException, *, evidence: dict | None = None, suggested_target: str | None = None) -> None: ...",
            "def log_event(event: str, *, trigger: str = 'runtime_observation', severity: str = 'info', status: str | None = None, purpose: str | None = None, inputs: dict | None = None, outputs: dict | None = None, checks: list | dict | None = None, evidence: dict | None = None, error: object = None, suggested_target: str | None = None, **extra) -> dict: ...",
            "def check_and_log(name: str, passed: bool, *, observed=None, expected=None, message: str | None = None, event: str | None = None, severity: str | None = None, evidence: dict | None = None, suggested_target: str | None = None) -> bool: ...",
            "def write_runtime_log() -> None: ...",
            "```",
            "Correct exception logging examples:",
            "- `log_exception(\"task_failed_with_exception\", exc)`",
            "- `log_exception(\"cpc_definition_parsing_failed\", e, suggested_target=\"metadata_parser\")`",
            "Incorrect examples that must not appear in prompt repair instructions:",
            "- `log_exception(e)`",
            "- `log_exception(exc)`",
            "- `log_exception(exc=e)`",
            "- text claiming log_exception takes exactly one positional argument",
            "",
            "## PATENTS mapping failure priority hints",
            "If evidence shows `cpc_mapping_summary` with `mapped_to_level5 = 0` or all publication CPC entries unmapped, prioritize prompt instructions for metadata-grounded CPC lookup before EMA/year logic.",
            "Observed PATENTS CPCDefinition COPY headers mix quoted and unquoted column names, for example quoted applicationReferences/titleFull plus unquoted level/parents/symbol; generated code must strip surrounding double quotes from header column names before required-column checks.",
            "The CPCDefinition COPY header columns are inside parentheses on the same `COPY public.cpc_definition (...) FROM stdin;` line; generated code must not treat the next data row as the header.",
            "For CPCDefinition COPY data blocks, generated code should scan line-by-line after the COPY header until a line whose stripped content is exactly backslash-dot; do not rely on one fragile whole-file substring for the terminator.",
            "Future generated code should parse CPCDefinition `parents` robustly; if the COPY field contains escaped newlines such as `\\n`, decode them before JSON/list parsing and verify that symbols_with_parents is non-zero.",
            "Future generated code should try exact raw publication CPC code lookup against CPCDefinition `symbol` first, then apply only metadata-confirmed normalization/aliasing.",
            "Do not blindly strip trailing classification zeros, slash groups, or decimal-like parts from CPC symbols; transformations such as `C01B33/00 -> C01B33` can destroy valid metadata keys unless the transformed symbol is proven present.",
            "If normalization is used, generated code should compare mapping coverage before/after, log sample raw->matched mappings, and treat zero mapped coverage as a hard evidence event instead of silently writing an empty answer.",
            "Do not repair mapped_to_level5=0 by merely ensuring FINAL_ANSWER_PATH is an empty file; the repair target is CPCDefinition parsing / symbol-parent mapping coverage.",
            "For EMA, generated code must build the year axis from filing years, not from CPC-code dictionary keys.",
            "If the parent evidence already has a non-empty partially correct answer, do not propose a broad parser rewrite or generic stricter-filtering instruction. Preserve the working parser path and target the observed missing/extra set, EMA best-year calculation, and fallback/filtering logic.",
            "When validation shows the expected and generated counts are close but items differ, prefer instructions for comparing candidate best-year decisions and avoiding fallback-derived extras, not instructions that change COPY parsing mechanics.",
            "",
        ]
    seed_for_open_diagnosis = load_repair_seed_json(repair_seed)
    open_diag = seed_for_open_diagnosis.get("open_diagnosis_evidence") if isinstance(seed_for_open_diagnosis.get("open_diagnosis_evidence"), dict) else None
    if open_diag:
        compact_open_diag = compact_open_diagnosis_evidence(open_diag) if compact_open_diagnosis_evidence else open_diag
        lines += [
            "## Open diagnosis evidence",
            "Use this section to form your own open-vocabulary diagnosis before choosing target_files. Do not treat selected_stage or helper_repair_plan as a closed failure taxonomy.",
            "Your patch_spec should include a top-level `open_diagnosis` object with diagnosis_label, causal_hypothesis, supporting_evidence, ruled_out_or_deprioritized_hypotheses, next_repair_strategy, not_to_repeat, and uncertainties.",
            "If your diagnosis disagrees with deterministic routing/helper_plan, explain the disagreement in open_diagnosis and still obey safety/scope gates.",
            "```json",
            json.dumps(compact_open_diag, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    routing = load_repair_routing(repair_seed)
    if routing:
        lines += [
            "## Repair routing",
            "Use this routing before selecting target_files. If it conflicts with generic instincts, follow the routing.",
            "```json",
            json.dumps(routing, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    helper_plan = load_helper_repair_plan(repair_seed)
    if helper_plan:
        lines += [
            "## Helper repair plan from fine-grained feedback",
            "This deterministic plan is an advisory/fallback proposal derived from selected_stage, selected_signal, runtime trace events, ranked feedback, and answer_delta.",
            "Use the Open diagnosis evidence first. If you choose a different safe target than this plan, justify the disagreement in top-level open_diagnosis; otherwise implement the recommended helper file/API or output no_op_failed.",
            "```json",
            json.dumps(helper_plan, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    seed_for_patch_generation = load_repair_seed_json(repair_seed)
    patch_feedback = seed_for_patch_generation.get("patch_generation_feedback") if isinstance(seed_for_patch_generation.get("patch_generation_feedback"), dict) else None
    if patch_feedback:
        lines += [
            "## Patch-generation fine-grained feedback",
            "This section is the primary action evidence for patch_spec generation. The patch_spec must explicitly address required_patch_behavior and must avoid forbidden_patch_shortcuts.",
            "Use evidence_to_use to choose target files and helper APIs; do not hardcode diagnostic-only missing/extra samples as answers.",
            "```json",
            json.dumps(patch_feedback, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    if repair_seed and repair_seed.exists():
        seed_data_for_context = load_repair_seed_json(repair_seed)
        seed_summary = compact_repair_seed_summary(seed_data_for_context)
        lines += ["## Repair seed summary", "This compact summary avoids repeating patch_generation_feedback/helper_repair_plan already shown above.", "```json", json.dumps(seed_summary, indent=2, ensure_ascii=False), "```", ""]
        archive_priority = seed_data_for_context.get("archive_evidence_priority_observations")
        archive_evidence_pool = ((seed_data_for_context.get("fine_grained_feedback") or {}).get("archive_evidence_pool") if isinstance(seed_data_for_context.get("fine_grained_feedback"), dict) else None)
        if archive_priority or archive_evidence_pool:
            lines += [
                "## Archive evidence from prior candidates",
                "These are failed/non-parent candidates selected by archive_selector. Treat them as high-value negative examples and do not repeat their observed failure modes.",
                "The patch_spec proposed_contracts must explicitly address any relevant high_priority_observations.",
                "```json",
                json.dumps({
                    "archive_evidence_priority_observations": archive_priority or [],
                    "archive_evidence_pool": archive_evidence_pool or [],
                }, indent=2, ensure_ascii=False),
                "```",
                "",
            ]
    if parent_prompt:
        prompt_path = parent_prompt if parent_prompt.is_absolute() else workspace / parent_prompt
        if prompt_path.exists() and profile.name == "data_agent_prompt_repair":
            lines += ["## Parent data-agent prompt", f"Path: `{normalize_rel(parent_prompt)}`", "```text", read_text(prompt_path, 9000), "```", ""]
    if parent_run and parent_run.exists():
        if profile.name == "data_agent_prompt_repair" and repair_seed_override:
            lines += [
                "## Parent run artifact policy for repair-seed override",
                f"Parent run artifacts exist at `{parent_run}` but are intentionally omitted because the override Repair seed is the primary objective.",
                "Do not repair unrelated parent-run tracebacks or runtime API issues unless they directly support the override seed evidence.",
                "",
            ]
        else:
            artifact_names = ["agent_error_summary.json", "stage_trace.json", "final_answer.txt"]
            if profile.name != "data_agent_prompt_repair":
                artifact_names.insert(2, "generated_solve.py")
            for name in artifact_names:
                artifact = parent_run / name
                if artifact.exists():
                    fence, compact_text = compact_parent_artifact(name, artifact)
                    lines += [f"## Parent run artifact summary: {name}", f"Path: `{artifact}`", f"```{fence}", compact_text, "```", ""]
            if profile.name == "data_agent_prompt_repair" and (parent_run / "generated_solve.py").exists():
                lines += [
                    "## Generated code evidence policy",
                    f"Generated code exists at `{parent_run / 'generated_solve.py'}` but is intentionally not included as editable context.",
                    "For this profile, generated_solve.py is evidence only. Do not use generated code as a patch target, anchor, or intended_change.",
                    "Translate any code-level diagnosis into a durable instruction for the parent data-agent prompt.",
                    "",
                ]
    if profile.name == "analyzer_infra_repair":
        for pattern in profile.allowed_patterns:
            if "*" in pattern:
                continue
            source = workspace / pattern
            if source.exists():
                lines += [f"## Source excerpt: {pattern}", "```python", read_text(source, 24000), "```", ""]
    if profile.name in {"data_agent_project_repair", "data_agent_tool_repair"}:
        source_excerpts = recommended_context_source_files(profile, repair_seed)
        lines += [
            "## Project source excerpt policy",
            "Only profile-relevant recommended target/helper files are included. Analyzer/meta-agent internals are omitted unless this repair profile targets them.",
            "```json",
            json.dumps({"included_source_excerpts": source_excerpts}, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
        for rel in source_excerpts:
            source = workspace / rel
            if source.exists():
                fence = "python" if source.suffix == ".py" else "text"
                lines += [f"## Project source excerpt: {rel}", f"```{fence}", read_text(source, source_excerpt_limit(profile, rel)), "```", ""]
    out = candidate_dir / "minimal_source_context_pack.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def profile_prompt_instructions(profile: RepairProfile) -> str:
    if profile.name == "data_agent_tool_repair":
        return """
Profile-specific hard rules for data_agent_tool_repair:

1. Prefer creating or updating reusable Python helper modules under adapters/patents/*.py instead of adding more prompt text.
2. The helper must be general and benchmark-safe: no hardcoded expected CPC answers, exact answer counts, or case-specific output lists.
3. Good helper targets include CPCDefinition COPY parsing, symbol/level/parents mapping, raw CPC to target-level ancestor mapping, filing-year extraction, EMA calculation, and answer diagnostics.
4. Prompt edits are allowed only as thin glue that instructs future generated_solve.py to import/use the helper. Keep prompt edits small and avoid duplicating existing bullets.
5. If no safe reusable helper can be created, output no_op_failed or explicitly justify a prompt-only fallback in the rationale using the phrase `prompt-only fallback` and the evidence reason.
6. generated_solve.py is evidence, not a patch target. Translate repeated generated-code failures into reusable helpers or minimal prompt glue.
7. Include at least one adapters/patents/*.py target unless using the explicit prompt-only fallback described above.
8. If repair_routing recommends adapters/patents/*.py helper targets, select one of those helper targets before adding any prompt glue.
9. A helper-only patch is not enough: also add minimal prompt glue or run_dab_agent integration so future generated_solve.py can discover and use the helper.
10. Prompt glue must be mandatory, not advisory: use wording such as `MUST import/use from adapters.patents.<module>` and `do not reimplement this helper logic inline`; avoid weak wording such as `prefer` or `when available`.
11. If creating a new helper module, use operation create_file and include import-safe, py_compile-clean Python.
12. Do not modify feedback analyzer code, logs, candidates, archive, trajectories, reports, benchmarks, legacy code, data files, virtualenvs, pycache, or generated run artifacts.
13. Treat the Open diagnosis evidence and Patch-generation fine-grained feedback as the primary action evidence. First produce your own top-level open_diagnosis object; diagnosis_label is open vocabulary and must not be limited to selected_stage.
14. The patch_spec rationale must cite the selected_stage/selected_signal, at least one concrete evidence item, and how the patch changes child behavior.
15. If helper_repair_plan.patch_generation_contract.schema_version is helper_patch_generation_contract_v002 and behavior_change_contract.required is true, your JSON patch_spec MUST include a top-level behavior_change_contract object with before, after, decision_path_change, child_observable_effect, and why_not_diagnostics_only.
16. For action helpers such as candidate_filtering.py/rank_or_filter_candidates, diagnostics-only or logging-only helpers are insufficient. The helper must affect final answer selection/ranking/filtering, and prompt glue must require generated_solve.py to use the helper output for final_answer.txt.
17. Prompt glue for any helper must include a concrete data-flow requirement, not only `import/use`: name the helper call, name the runtime inputs, name the returned variable(s), and state where the returned value must be consumed. Examples: `metadata = parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH); symbol_to_level = metadata.get("symbol_to_level", {}); symbol_to_parents = metadata.get("symbol_to_parents", {})` before CPC mapping; `selected_symbols = rank_or_filter_candidates(candidate_rows, target_year=2022)` and write `selected_symbols` to final_answer.txt.
18. For every helper-facing patch, declare a local interface contract: identify the generated_solve.py/prompt caller, the helper callee, the exact expected call pattern, the runtime argument types likely passed by generated_solve.py, and the helper-side compatibility behavior. The helper must be robust to the actual local call contract, e.g. if prompt glue passes a path constant string, the helper should accept str/path-like inputs or the prompt glue must explicitly convert to Path before calling.
19. The proposed validation must exercise the local interface contract, not only the helper's ideal type signature. If the expected call pattern is `parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH)` and CPC_DEFINITION_SQL_PATH is a string, validation_hint must include a string-path call test.
20. If the selected signal says CPCDefinition metadata was not read, prioritize a CPCDefinition metadata reader/parser helper and require generated_solve.py to call it before raw CPC mapping. Do not repair this as candidate filtering first.
21. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Use valid JSON escaping for all quote and newline characters inside JSON strings.
"""
    if profile.name == "data_agent_project_repair":
        return """
Profile-specific hard rules for data_agent_project_repair:

1. You may modify project source files in the isolated candidate workspace only, within allowed_patterns.
2. You may target prompts/dab, adapters, experiments, and llm_client.py when the repair seed proves that layer is causal.
3. Do NOT modify logs, candidates, archive, trajectories, reports, benchmarks, legacy code, data files, virtualenvs, pycache, or generated run artifacts.
4. Prefer at most 1-3 files and a small diff. If a fix requires broad refactor, output no_op_failed.
5. generated_solve.py is evidence, not a patch target; translate its failure into a durable project-source or prompt repair.
6. Read `repair_routing` before choosing target_files. Prefer its recommended_target_files and avoid anti_targets.
7. If `repair_routing.prompt_only_policy.status` is `reject`, do not output a prompt-only patch.
8. If `repair_routing.prompt_only_policy.status` is `weak_allowed`, a prompt-only patch must explicitly explain why it prevents the concrete traceback/signal; otherwise prefer a project-source guardrail.
9. Do not hardcode expected CPC answers, exact expected counts, or benchmark ground-truth lists.
10. If editing Python, preserve public APIs used by existing callers and keep imports coherent.
11. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Use valid JSON escaping for all quote and newline characters inside JSON strings.
"""
    if profile.name == "data_agent_prompt_repair":
        return """
Profile-specific hard rules for data_agent_prompt_repair:

1. You may modify ONLY the parent prompt file listed in target_files.
2. The anchor MUST be exact text copied from the Parent data-agent prompt section of the context pack.
3. Do NOT use generated_solve.py, runtime logs, stage_trace, or error-summary text as an anchor. They are evidence only.
4. Do NOT write Python implementation code into the prompt. Translate code-level failures into concise prompt instructions that guide future generated code.
5. Prefer insert_after_anchor or append_text with a short instruction paragraph. Avoid replacing large prompt blocks.
6. For insert_after_anchor or insert_before_anchor, intended_change must start with a newline so prompt bullets are not merged onto one line.
7. Use the Runtime observer API contract from the context pack as authoritative. In particular, log_exception requires two positional arguments: log_exception("event_name", exc).
8. Repair an older contradictory runtime signature such as log_exception(exc) only when the active repair seed/runtime evidence is about the runtime observer API; otherwise do not prioritize it over the seed focus.
9. If the failure involves an unclear domain concept, hierarchy term, level, or granularity requirement, propose a generic local-grounding instruction. Do not name a dataset-specific concept unless it already appears in the target prompt/evidence; do not add web access or external search to generated code.
10. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Use valid JSON escaping for all quote and newline characters inside JSON strings.
11. If the repair would require editing generated_solve.py or project source instead of the prompt, output no_op_failed.
"""
    return """
Profile-specific hard rules:

1. Use only files allowed by the selected profile.
2. Anchors must be exact text from the allowed target file.
3. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Escape quotes and newlines inside JSON strings.
"""


def build_prompt(profile: RepairProfile, context_path: Path, candidate_dir: Path) -> Path:
    profile_rules = profile_prompt_instructions(profile)
    prompt = f"""You are Codex-Qwen acting as a structured meta-agent repair proposer.

You are not allowed to run tools, read additional files, or emit free-form patches. Output exactly one strict JSON object.
Do not wrap the JSON in markdown fences.
{profile_rules}

If no safe minimal repair is possible, output:
{{"status": "no_op_failed", "reason": "..."}}

Otherwise output this schema:
{{
  "status": "patch_spec",
  "repair_profile": "{profile.name}",
  "open_diagnosis": {{
    "diagnosis_label": "free-form concise label, not a fixed enum",
    "causal_hypothesis": "why the child/parent evidence points to this repair",
    "supporting_evidence": ["specific evidence references"],
    "ruled_out_or_deprioritized_hypotheses": ["what the evidence makes less likely"],
    "next_repair_strategy": {{
      "target_layer": "free-form layer description",
      "target_files": ["..."],
      "expected_child_observable_effect": "what should change in child eval"
    }},
    "not_to_repeat": ["patch shapes or assumptions to avoid"],
    "uncertainties": ["unknowns and validation checks"]
  }},
  "target_files": ["..."],
  "edits": [
    {{
      "file": "...",
      "operation": "{" | ".join(profile.operations)}",
      "anchor": "exact source text to match; empty only for append_text if that operation is allowed",
      "intended_change": "exact text to write/insert",
      "rationale": "why this is minimal and within scope"
    }}
  ],
  "risk_scope": "{profile.risk_scope}",
  "behavior_change_contract": {{
    "before": "what parent generated_solve.py did before, from the evidence",
    "after": "what child generated_solve.py should do after applying this patch",
    "decision_path_change": "which selection/ranking/filtering or parser decision path changes; say no_op_failed if no behavior change is safe",
    "child_observable_effect": "what child_eval should observe, e.g. helper output used for final_answer.txt or selected signal moves",
    "why_not_diagnostics_only": "why this is not merely logging/summarization when action repair is required"
  }},
  "proposed_contracts": [
    {{
      "contract_id": "short_snake_case_id",
      "statement": "specific behavior contract this patch claims to satisfy",
      "target_files": ["files whose behavior should satisfy the contract"],
      "expected_observable_effect": "child-eval or trace/log/answer effect that should be observed",
      "validation_hint": "how child eval or focused validation should check it"
    }}
  ],
  "local_interface_contracts": [
    {{
      "contract_id": "short_snake_case_id",
      "caller_context": "where the local project will call this behavior, e.g. generated_solve.py via prompt glue",
      "callee": "module.function or prompt/API surface being introduced or changed",
      "expected_call_pattern": "the exact or representative local call pattern the patch expects",
      "argument_contract": "string or object describing runtime argument names and types/shapes the callee must accept, based on local evidence",
      "compatibility_behavior": "how the patch handles those actual local inputs without crashing or becoming a no-op",
      "target_files": ["files whose code/prompt must satisfy this local interface contract"],
      "validation_hint": "focused validation that exercises the local call pattern and argument types, not only an idealized unit call"
    }}
  ],
  "public_functions_to_preserve": {json.dumps(list(profile.required_public_functions), ensure_ascii=False)},
  "forbidden_actions_ack": {{
{chr(10).join(f'    "{key}": true,' for key in profile.required_ack).rstrip(',')}
  }}
}}

Context pack:

{read_text(context_path)}
"""
    out = candidate_dir / "patch_spec_prompt.txt"
    out.write_text(prompt, encoding="utf-8")
    return out


def call_codex_cli_patch_spec(prompt_path: Path, candidate_dir: Path) -> str:
    """Generate patch_spec text through Codex CLI using the configured Qwen proxy."""
    profile = os.environ.get("CODEX_QWEN_PROFILE", "qwen-proxy")
    model = os.environ.get("CODEX_QWEN_MODEL", os.environ.get("META_AGENT_MODEL", "qwen-plus"))
    sandbox = os.environ.get("CODEX_QWEN_SANDBOX", "read-only")
    timeout = int(os.environ.get("CODEX_QWEN_EXEC_TIMEOUT_SEC", "300"))
    raw_path = candidate_dir / "patch_spec_raw.txt"
    stdout_path = candidate_dir / "codex_patch_spec.stdout"
    stderr_path = candidate_dir / "codex_patch_spec.stderr"
    prompt = read_text(prompt_path)
    command = [
        "codex",
        "--profile",
        profile,
        "--model",
        model,
        "--sandbox",
        sandbox,
        "-a",
        "never",
        "exec",
        "--skip-git-repo-check",
        "--output-last-message",
        str(raw_path),
        "-",
    ]
    started = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            command,
            cwd=candidate_dir,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
        write_json(
            candidate_dir / "codex_patch_spec_run.json",
            {
                "backend": "codex_cli",
                "profile": profile,
                "model": model,
                "sandbox": sandbox,
                "started_at": started,
                "exit_code": proc.returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "raw_path": str(raw_path),
            },
        )
        if proc.returncode != 0 and not raw.strip():
            return json.dumps(
                {
                    "status": "no_op_failed",
                    "reason": f"codex cli patch_spec generation failed with exit code {proc.returncode}",
                },
                ensure_ascii=False,
            )
        return raw
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8", errors="replace")
        return json.dumps(
            {"status": "no_op_failed", "reason": f"codex cli patch_spec generation timed out after {timeout}s"},
            ensure_ascii=False,
        )


def load_or_call_patch_spec(args: argparse.Namespace, prompt_path: Path, candidate_dir: Path) -> tuple[dict[str, Any] | None, str]:
    raw_path = candidate_dir / "patch_spec_raw.txt"
    patch_spec_file = args.patch_spec_file or os.environ.get("PATCH_SPEC_FILE")
    no_call_meta_llm = args.no_call_meta_llm or os.environ.get("NO_CALL_META_LLM") == "1"
    backend = os.environ.get("META_AGENT_PATCH_SPEC_BACKEND", "direct_qwen")
    if patch_spec_file:
        raw = read_text(Path(patch_spec_file))
    elif no_call_meta_llm:
        raw = json.dumps({"status": "no_op_failed", "reason": "--no-call-meta-llm set and no --patch-spec-file provided"}, ensure_ascii=False)
    elif backend == "codex_cli":
        raw = call_codex_cli_patch_spec(prompt_path, candidate_dir)
    elif call_meta_llm is None:
        raw = json.dumps({"status": "no_op_failed", "reason": "llm_client.call_meta_llm unavailable"}, ensure_ascii=False)
    else:
        raw = call_meta_llm(read_text(prompt_path))
        if describe_llm_config:
            write_json(candidate_dir / "llm_config.json", describe_llm_config())
    raw_path.write_text(raw, encoding="utf-8")
    return extract_first_json(raw), raw



def active_seed_supports_strict_granularity_filter(repair_seed: Path | None) -> bool:
    if repair_seed is None or not repair_seed.exists():
        return False
    raw = read_text(repair_seed, max_chars=60000).lower()
    required_problem_markers = (
        "non-level-5",
        "not level 5",
        "fallback-derived",
        "fallback derived",
        "deep cpc",
        "extra deep",
        "invalid level",
        "wrong level",
        "granularity_mapping_fallback_used",
    )
    return any(marker in raw for marker in required_problem_markers)


def validate_anti_regression_project_memory(
    spec: dict[str, Any],
    *,
    profile: RepairProfile,
    repair_seed: Path | None,
) -> tuple[bool, str]:
    if profile.name != "data_agent_prompt_repair":
        return True, "ok"
    combined = "\n".join(
        str(edit.get("intended_change", "")) + "\n" + str(edit.get("rationale", ""))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    ).lower()
    vague_strict_markers = (
        "only symbols explicitly present",
        "explicitly present in the cpc definition metadata with `level == 5`",
        "level == 5",
        "strictly filter",
        "strict filter",
        "fallback-derived",
        "fallback derived",
        "do not include symbols derived solely from string-based fallbacks",
        "do not treat fallback-derived symbols as canonical",
    )
    if not any(marker in combined for marker in vague_strict_markers):
        return True, "ok"
    if active_seed_supports_strict_granularity_filter(repair_seed):
        preserve_markers = (
            "preserve",
            "already parses",
            "parent already",
            "non-empty",
            "partial answer",
            "current parent",
        )
        if any(marker in combined for marker in preserve_markers):
            return True, "ok"
    return (
        False,
        "project memory gate rejected vague strict level/filtering patch without active evidence that parent outputs non-level-5 or fallback-derived extras",
    )


def validate_data_agent_prompt_change(edit: dict[str, str], idx: int) -> tuple[bool, str]:
    intended = edit["intended_change"]
    low = intended.lower()
    anchor_low = edit["anchor"].lower()
    stale_log_exception_anchor = "log_exception(exc)" in anchor_low or "one positional argument" in anchor_low
    if stale_log_exception_anchor and "log_exception" in low and edit["operation"] != "replace_text_once":
        return False, f"edit {idx} must use replace_text_once to replace stale log_exception signature guidance instead of appending a conflicting instruction"
    if edit["operation"] in ("insert_after_anchor", "insert_before_anchor") and not intended.startswith("\n"):
        return False, f"edit {idx} intended_change must start with newline for prompt formatting"
    bad_runtime_api_patterns = [
        r"log_exception\s*\(\s*(?:e|exc)\s*\)",
        r"log_exception\s*\(\s*exc\s*=",
    ]
    for pattern in bad_runtime_api_patterns:
        for match in re.finditer(pattern, intended):
            prefix = intended[max(0, match.start() - 48):match.start()].lower()
            if any(marker in prefix for marker in ("do not", "don't", "never", "avoid", "instead of")):
                continue
            return False, f"edit {idx} contains invalid runtime_observer log_exception API usage"
    if "log_exception" in low and any(
        phrase in low
        for phrase in (
            "exactly one positional argument",
            "one positional argument",
            "single positional argument",
            "only one positional argument",
            "takes one argument",
        )
    ):
        return False, f"edit {idx} gives incorrect log_exception signature guidance"
    if any(phrase in low for phrase in ("write final_answer_path with an empty", "empty final answer", "empty answer file", "write an empty file")):
        return False, f"edit {idx} proposes an empty-answer contract instead of repairing parser/mapping coverage"
    return True, "ok"


def _seed_focus_terms(repair_seed: Path | None) -> tuple[str | None, list[str], list[str], dict[str, Any]]:
    if not repair_seed or not repair_seed.exists():
        return None, [], [], {}
    try:
        seed = json.loads(repair_seed.read_text(encoding="utf-8"))
    except Exception:
        return None, [], [], {}
    stage = seed.get("selected_stage")
    signal = seed.get("selected_signal")
    runtime_evidence = seed.get("runtime_repair_evidence") or {}
    raw = " ".join(str(item or "") for item in (stage, signal, (seed.get("selected_signal_evidence") or {}).get("raw")))
    runtime_raw = json.dumps(runtime_evidence, ensure_ascii=False) if runtime_evidence else ""
    stop = {
        "generated", "appears", "example", "instead", "repair", "failure", "selected",
        "signal", "stage", "code", "codes", "from", "with", "that", "this", "have",
        "into", "only", "using", "used", "must", "should", "would", "could",
    }
    terms = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{4,}", raw.lower()):
        if token not in stop and token not in terms:
            terms.append(token)
    runtime_terms = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{4,}", runtime_raw.lower()):
        if token not in stop and token not in runtime_terms:
            runtime_terms.append(token)
    return str(stage) if stage else None, terms[:16], runtime_terms[:24], runtime_evidence


def validate_seed_alignment(
    spec: dict[str, Any],
    *,
    profile: RepairProfile,
    repair_seed: Path | None,
    repair_seed_override: bool,
) -> tuple[bool, str]:
    if not repair_seed_override or profile.name != "data_agent_prompt_repair":
        return True, "ok"
    stage, terms, runtime_terms, runtime_evidence = _seed_focus_terms(repair_seed)
    if not stage and not terms and not runtime_terms:
        return True, "ok"
    combined = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("anchor", "intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    ).lower()
    stage_variants = []
    if stage:
        stage_low = stage.lower()
        stage_variants = [stage_low, stage_low.replace("_", " "), stage_low.replace("_", "-")]
    matched_terms = [term for term in terms if term in combined]
    matched_runtime_terms = [term for term in runtime_terms if term in combined]
    runtime_raw = json.dumps(runtime_evidence, ensure_ascii=False).lower() if runtime_evidence else ""
    if ("symbols_with_parents" in runtime_raw or "parents may parse as empty" in runtime_raw) and not any(
        marker in combined
        for marker in (
            "symbols_with_parents",
            "escaped",
            "decode",
            "decoded",
            "parents parsing",
            "parse parents",
            "parse `parents`",
            "empty parents",
            "usable parents",
        )
    ):
        return False, "patch_spec does not address runtime evidence: CPCDefinition parents parsing produced zero usable parents"
    if ("failed to parse column names" in runtime_raw or "quoted column names" in runtime_raw or "missing required columns" in runtime_raw) and not any(
        marker in combined
        for marker in (
            "strip surrounding double quotes",
            "strip quotes",
            "quoted column",
            "copy header",
            "header column",
            "titlefull",
        )
    ):
        return False, "patch_spec does not address runtime evidence: CPCDefinition COPY header has quoted column names"
    if runtime_terms and len(matched_runtime_terms) >= 2:
        return True, "ok"
    if any(variant in combined for variant in stage_variants) or len(matched_terms) >= 3:
        return True, "ok"
    focus = stage or ", ".join((runtime_terms or terms)[:5])
    return False, f"patch_spec does not address override repair seed focus: {focus}"




def validate_tool_repair_policy(spec: dict[str, Any], profile: RepairProfile) -> tuple[bool, str]:
    if profile.name != "data_agent_tool_repair":
        return True, "ok"
    targets = [normalize_rel(str(path)) for path in spec.get("target_files") or []]
    has_patents_helper = any(path.startswith("adapters/patents/") and path.endswith(".py") for path in targets)
    if has_patents_helper:
        return True, "ok"
    prompt_only = bool(targets) and all(is_prompt_path(path) for path in targets)
    combined = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    ).lower()
    fallback_markers = (
        "prompt-only fallback",
        "no safe reusable helper",
        "existing helper already",
        "existing project source already",
    )
    if prompt_only and any(marker in combined for marker in fallback_markers):
        return True, "ok"
    return False, "data_agent_tool_repair must include at least one adapters/patents/*.py helper target or explicitly justify a prompt-only fallback"

def validate_spec(spec: dict[str, Any] | None, profile: RepairProfile, candidate_dir: Path, repair_seed: Path | None = None, repair_seed_override: bool = False) -> tuple[bool, str, str]:
    if spec is None:
        return False, "protocol_failed_invalid_patch_spec", "patch_spec JSON could not be parsed"
    if spec.get("status") == "no_op_failed":
        write_json(candidate_dir / "validated_patch_spec.json", spec)
        return False, "no_op_failed", str(spec.get("reason") or "no reason")
    if spec.get("status") != "patch_spec":
        return False, "protocol_failed_invalid_patch_spec", "status must be patch_spec or no_op_failed"
    if spec.get("repair_profile") not in (None, profile.name):
        return False, "protocol_failed_invalid_patch_spec", f"repair_profile must be {profile.name}"
    targets = spec.get("target_files")
    if not isinstance(targets, list) or not targets:
        return False, "protocol_failed_invalid_patch_spec", "target_files must be a non-empty list"
    for target in targets:
        if not isinstance(target, str) or not is_allowed_file(target, profile):
            return False, "protocol_failed_invalid_patch_spec", f"target file not allowed: {target}"
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        return False, "protocol_failed_invalid_patch_spec", "edits must be a non-empty list"
    for idx, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} must be object"
        for key in ("file", "operation", "anchor", "intended_change"):
            if key not in edit or not isinstance(edit[key], str):
                return False, "protocol_failed_invalid_patch_spec", f"edit {idx} missing string {key}"
        if "rationale" not in edit:
            edit["rationale"] = ""
        elif not isinstance(edit["rationale"], str):
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} rationale must be string when present"
        if not is_allowed_file(edit["file"], profile):
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} file not allowed: {edit['file']}"
        if edit["file"] not in targets:
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} file not declared in target_files"
        if edit["operation"] not in profile.operations:
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} unsupported operation: {edit['operation']}"
        if edit["operation"] not in ("append_text", "create_file") and not edit["anchor"]:
            return False, "protocol_failed_invalid_patch_spec", f"edit {idx} requires non-empty anchor"
        prompt_edit = profile.name == "data_agent_prompt_repair" or (profile.name in {"data_agent_project_repair", "data_agent_tool_repair"} and is_prompt_path(edit["file"]))
        if prompt_edit:
            intended_only = edit["intended_change"]
            if prompt_edit_looks_like_code_payload(intended_only):
                return False, "protocol_failed_invalid_patch_spec", f"edit {idx} appears to patch generated code instead of prompt instructions"
            change_ok, change_reason = validate_data_agent_prompt_change(edit, idx)
            if not change_ok:
                return False, "protocol_failed_invalid_patch_spec", change_reason
    contracts = spec.get("proposed_contracts")
    if not isinstance(contracts, list) or not contracts:
        return False, "protocol_failed_invalid_patch_spec", "proposed_contracts must be a non-empty list; output no_op_failed if no behavior contract is safe"
    for idx, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            return False, "protocol_failed_invalid_patch_spec", f"proposed_contracts[{idx}] must be object"
        statement = contract.get("statement") or contract.get("contract") or contract.get("contract_statement")
        if not isinstance(statement, str) or not statement.strip():
            return False, "protocol_failed_invalid_patch_spec", f"proposed_contracts[{idx}] missing non-empty statement"
        effect = contract.get("expected_observable_effect") or contract.get("success_condition") or contract.get("validation_hint")
        if not isinstance(effect, str) or not effect.strip():
            return False, "protocol_failed_invalid_patch_spec", f"proposed_contracts[{idx}] missing expected_observable_effect or validation_hint"
        files = contract.get("target_files") or contract.get("files") or []
        if isinstance(files, str):
            files = [files]
        if not isinstance(files, list) or not files:
            return False, "protocol_failed_invalid_patch_spec", f"proposed_contracts[{idx}] missing target_files"
        for file in files:
            if not isinstance(file, str) or not is_allowed_file(file, profile):
                return False, "protocol_failed_invalid_patch_spec", f"proposed_contracts[{idx}] target file not allowed: {file}"
    if profile.name == "data_agent_tool_repair":
        interface_contracts = spec.get("local_interface_contracts")
        if not isinstance(interface_contracts, list) or not interface_contracts:
            return False, "protocol_failed_invalid_patch_spec", "data_agent_tool_repair patch_spec must include non-empty local_interface_contracts for helper/prompt call compatibility"
        for idx, contract in enumerate(interface_contracts):
            if not isinstance(contract, dict):
                return False, "protocol_failed_invalid_patch_spec", f"local_interface_contracts[{idx}] must be object"
            for key in (
                "caller_context",
                "callee",
                "expected_call_pattern",
                "compatibility_behavior",
                "validation_hint",
            ):
                value = contract.get(key)
                if not isinstance(value, str) or not value.strip():
                    return False, "protocol_failed_invalid_patch_spec", f"local_interface_contracts[{idx}] missing non-empty {key}"
            argument_contract = contract.get("argument_contract")
            if isinstance(argument_contract, str):
                argument_contract_ok = bool(argument_contract.strip())
            elif isinstance(argument_contract, dict):
                argument_contract_ok = bool(argument_contract)
            elif isinstance(argument_contract, list):
                argument_contract_ok = bool(argument_contract)
            else:
                argument_contract_ok = False
            if not argument_contract_ok:
                return False, "protocol_failed_invalid_patch_spec", f"local_interface_contracts[{idx}] missing non-empty argument_contract"
            files = contract.get("target_files") or contract.get("files") or []
            if isinstance(files, str):
                files = [files]
            if not isinstance(files, list) or not files:
                return False, "protocol_failed_invalid_patch_spec", f"local_interface_contracts[{idx}] missing target_files"
            for file in files:
                if not isinstance(file, str) or not is_allowed_file(file, profile):
                    return False, "protocol_failed_invalid_patch_spec", f"local_interface_contracts[{idx}] target file not allowed: {file}"
    if spec.get("risk_scope") != profile.risk_scope:
        return False, "protocol_failed_invalid_patch_spec", f"risk_scope must be {profile.risk_scope}"
    ack = spec.get("forbidden_actions_ack")
    if not isinstance(ack, dict):
        return False, "protocol_failed_invalid_patch_spec", "forbidden_actions_ack must be object"
    for key in profile.required_ack:
        if ack.get(key) is not True:
            return False, "protocol_failed_invalid_patch_spec", f"forbidden_actions_ack missing {key}=true"
    preserve = set(map(str, spec.get("public_functions_to_preserve") or []))
    for name in profile.required_public_functions:
        if name not in preserve:
            return False, "protocol_failed_invalid_patch_spec", f"public_functions_to_preserve missing {name}"
    project_memory_ok, project_memory_reason = validate_anti_regression_project_memory(spec, profile=profile, repair_seed=repair_seed)
    if not project_memory_ok:
        return False, "protocol_failed_seed_mismatch", project_memory_reason
    aligned, align_reason = validate_seed_alignment(spec, profile=profile, repair_seed=repair_seed, repair_seed_override=repair_seed_override)
    if not aligned:
        return False, "protocol_failed_seed_mismatch", align_reason
    routed, route_reason = validate_project_repair_routing(
        spec,
        profile=profile,
        repair_seed=repair_seed,
        candidate_dir=candidate_dir,
    )
    if not routed:
        return False, "protocol_failed_seed_mismatch", route_reason
    tool_ok, tool_reason = validate_tool_repair_policy(spec, profile)
    if not tool_ok:
        return False, "protocol_failed_seed_mismatch", tool_reason
    write_json(candidate_dir / "validated_patch_spec.json", spec)
    return True, "patch_spec_valid", "ok"


def apply_edit(workspace: Path, edit: dict[str, str]) -> dict[str, Any]:
    path = workspace / edit["file"]
    op = edit["operation"]
    anchor = edit["anchor"]
    change = edit["intended_change"]
    if op == "create_file":
        if path.exists():
            raise ValueError(f"create_file target already exists: {edit['file']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(change, encoding="utf-8")
        return {}
    if not path.exists():
        raise ValueError(f"target file does not exist: {edit['file']}")
    text = path.read_text(encoding="utf-8")
    if op == "append_text":
        path.write_text(text + ("" if text.endswith("\n") else "\n") + change, encoding="utf-8")
        return {}
    if anchor not in text:
        if op in {"insert_after_anchor", "insert_before_anchor"} and is_prompt_path(edit["file"]) and prompt_edit_is_helper_glue(change):
            appended = (
                text
                + ("" if text.endswith("\n") else "\n")
                + "\nAdditional helper contract for reusable PATENTS helpers:\n"
                + change.strip()
                + "\n"
            )
            path.write_text(appended, encoding="utf-8")
            return {
                "anchor_fallback": "append_prompt_helper_glue",
                "reason": "prompt helper glue anchor not found; appended under restricted helper-glue fallback",
            }
        raise ValueError(f"anchor not found in {edit['file']}")
    if op == "replace_text_once":
        path.write_text(text.replace(anchor, change, 1), encoding="utf-8")
    elif op == "insert_after_anchor":
        path.write_text(text.replace(anchor, anchor + change, 1), encoding="utf-8")
    elif op == "insert_before_anchor":
        path.write_text(text.replace(anchor, change + anchor, 1), encoding="utf-8")
    else:
        raise ValueError(f"unsupported operation: {op}")
    return {}


def apply_spec(spec: dict[str, Any], workspace: Path, candidate_dir: Path) -> tuple[bool, str]:
    applied: list[dict[str, str]] = []
    try:
        for edit in spec["edits"]:
            apply_meta = apply_edit(workspace, edit)
            applied.append({"file": edit["file"], "operation": edit["operation"], **apply_meta})
    except Exception as exc:
        write_json(candidate_dir / "apply_result.json", {"status": "patch_apply_failed", "reason": str(exc), "applied_before_failure": applied})
        return False, str(exc)
    write_json(candidate_dir / "apply_result.json", {"status": "patch_apply_succeeded", "applied_edits": applied})
    return True, "patch_apply_succeeded"


def status_files(text: str) -> list[str]:
    files: list[str] = []
    for line in text.splitlines():
        if len(line) >= 4:
            files.append(line[3:].split(" -> ")[-1])
    return sorted(set(files))


def numstat(text: str) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        added_s, deleted_s, path = line.split("\t", 2)
        added = 0 if added_s == "-" else int(added_s)
        deleted = 0 if deleted_s == "-" else int(deleted_s)
        total += added + deleted
        rows.append({"path": path, "added": added, "deleted": deleted})
    return total, rows


def diff_artifacts(workspace: Path, candidate_dir: Path) -> dict[str, Any]:
    # Include newly created helper files in git diff without staging content.
    run_cmd(["git", "add", "-N", "."], cwd=workspace)
    diff = run_cmd(["git", "diff", "--binary"], cwd=workspace)
    status = run_cmd(["git", "status", "--short"], cwd=workspace)
    stat = run_cmd(["git", "diff", "--numstat"], cwd=workspace)
    (candidate_dir / "patch.diff").write_text(diff.stdout or "", encoding="utf-8")
    (candidate_dir / "git_status.txt").write_text(status.stdout or "", encoding="utf-8")
    (candidate_dir / "patch_numstat.txt").write_text(stat.stdout or "", encoding="utf-8")
    total, rows = numstat(stat.stdout or "")
    return {"changed_files": status_files(status.stdout or ""), "total_changed_lines": total, "patch_numstat": rows}


def public_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def normalized_prompt_instruction(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[-*]\s+", "", text)
    text = re.sub(r"^\d+[.)]\s+", "", text)
    text = text.replace("`", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def baseline_file_text(workspace: Path, rel: str) -> tuple[str, str]:
    proc = run_cmd(["git", "show", f"HEAD:{normalize_rel(rel)}"], cwd=workspace)
    if proc.returncode == 0:
        return proc.stdout or "", "git"
    path = workspace / rel
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return text, "post_apply_fallback"


def anchor_line_indent(baseline: str, anchor: str) -> str | None:
    if not anchor:
        return None
    for line in baseline.splitlines():
        if anchor in line:
            stripped = line.lstrip(" ")
            if stripped.startswith("- "):
                return line[: len(line) - len(stripped)]
            return ""
    return None


def prompt_static_post_apply_gate(profile: RepairProfile, workspace: Path, candidate_dir: Path) -> tuple[bool, str]:
    if profile.name not in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair"}:
        return True, "ok"
    spec_path = candidate_dir / "validated_patch_spec.json"
    if not spec_path.exists():
        return True, "ok"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    failures: list[dict[str, Any]] = []
    for edit_index, edit in enumerate(spec.get("edits") or []):
        if not isinstance(edit, dict):
            continue
        rel = str(edit.get("file") or "")
        if not rel:
            continue
        if not is_prompt_path(rel):
            continue
        intended = str(edit.get("intended_change") or "")
        baseline, baseline_source = baseline_file_text(workspace, rel)
        normalized_baseline_lines = [
            normalized_prompt_instruction(line)
            for line in baseline.splitlines()
            if normalized_prompt_instruction(line)
        ]
        for line in intended.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            normalized_line = normalized_prompt_instruction(stripped)
            if len(normalized_line) < 80:
                continue
            occurrence_count = sum(1 for item in normalized_baseline_lines if item == normalized_line)
            duplicate = occurrence_count >= 1 if baseline_source == "git" else occurrence_count >= 2
            if duplicate:
                failures.append(
                    {
                        "edit_index": edit_index,
                        "file": rel,
                        "reason": "duplicate_prompt_instruction",
                        "line": stripped[:240],
                        "baseline_source": baseline_source,
                        "occurrence_count": occurrence_count,
                    }
                )
        if edit.get("operation") in {"insert_after_anchor", "insert_before_anchor"}:
            indent = anchor_line_indent(baseline, str(edit.get("anchor") or ""))
            if indent is not None and indent:
                for line in intended.splitlines():
                    if line.strip().startswith("- ") and not line.startswith(f"{indent}- "):
                        failures.append(
                            {
                                "edit_index": edit_index,
                                "file": rel,
                                "reason": "malformed_prompt_bullet_indentation",
                                "expected_prefix": f"{indent}- ",
                                "line": line[:240],
                            }
                        )
    out = candidate_dir / "validation" / "prompt_static_post_apply_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, {"status": "failed" if failures else "passed", "failures": failures})
    if failures:
        reasons = sorted({str(item.get("reason")) for item in failures})
        return False, f"prompt static post-apply gate failed: {', '.join(reasons)}"
    return True, "ok"


def post_apply_gate(profile: RepairProfile, workspace: Path, candidate_dir: Path, info: dict[str, Any]) -> tuple[bool, str, str]:
    if not read_text(candidate_dir / "patch.diff").strip():
        return False, "protocol_failed_empty_patch", "patch.diff is empty"
    project_changed = [path for path in info["changed_files"] if is_allowed_file(path, profile)]
    unexpected = [path for path in info["changed_files"] if not is_allowed_file(path, profile)]
    if not project_changed:
        return False, "patch_apply_failed", "project_changed_files is empty"
    if unexpected:
        return False, "rejected_large_rewrite", f"unexpected changed files: {unexpected}"
    if info["total_changed_lines"] > profile.max_changed_lines:
        return False, "rejected_large_rewrite", f"diff too large: {info['total_changed_lines']} > {profile.max_changed_lines}"
    if profile.required_public_functions:
        for rel in profile.py_compile_files:
            path = workspace / rel
            if path.exists():
                funcs = public_functions(path)
                missing = [name for name in profile.required_public_functions if name not in funcs]
                if missing:
                    return False, "rejected_large_rewrite", f"required public functions missing: {missing}"
    prompt_gate_ok, prompt_gate_reason = prompt_static_post_apply_gate(profile, workspace, candidate_dir)
    if not prompt_gate_ok:
        return False, "failed_validation", prompt_gate_reason
    return True, "post_apply_gate_passed", "ok"


def changed_project_files_from_numstat(candidate_dir: Path) -> list[str]:
    rows: list[str] = []
    path = candidate_dir / "patch_numstat.txt"
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            rows.append(parts[2])
    return rows


def text_marker_is_negated(text: str, start: int, end: int, marker_regex: str) -> bool:
    context = text[max(0, start - 96): min(len(text), end + 96)]
    negators = r"(?:no|not|never|without|avoid(?:s|ing)?|prevent(?:s|ing)?|forbid(?:s|den)?|must not|do not|does not)"
    if re.search(negators + r"(?:\W+\w+){0,8}\W+" + marker_regex, context):
        return True
    if re.search(marker_regex + r"(?:\W+\w+){0,8}\W+" + negators, context):
        return True
    return False


def hardcode_marker_is_negated(text: str, start: int, end: int) -> bool:
    return text_marker_is_negated(text, start, end, r"hardcod\w*")


def no_hardcoded_answer_check(spec: dict[str, Any]) -> tuple[bool, str]:
    suspicious = ("final answer is", "answer:", "expected output", "ground truth", "expected cpc")
    for edit in spec.get("edits") or []:
        if not isinstance(edit, dict):
            continue
        low = (str(edit.get("intended_change") or "") + "\n" + str(edit.get("rationale") or "")).lower()
        for match in re.finditer(r"hardcod\w*", low):
            if not hardcode_marker_is_negated(low, match.start(), match.end()):
                return False, "obvious answer hardcoding marker found in patch_spec"
        for marker in suspicious:
            start = low.find(marker)
            if start >= 0 and not text_marker_is_negated(low, start, start + len(marker), re.escape(marker)):
                return False, "obvious answer hardcoding marker found in patch_spec"
    return True, "ok"


def data_agent_tool_helper_integration_check(spec: dict[str, Any]) -> tuple[bool, str]:
    targets = [normalize_rel(str(path)) for path in spec.get("target_files") or []]
    helper_targets = [path for path in targets if path.startswith("adapters/patents/") and path.endswith(".py")]
    if not helper_targets:
        return True, "ok"
    integration_targets = {
        "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
        "experiments/run_dab_agent.py",
    }
    if not any(path in integration_targets for path in targets):
        combined = "\n".join(
            "\n".join(str(edit.get(key, "")) for key in ("intended_change", "rationale"))
            for edit in spec.get("edits") or []
            if isinstance(edit, dict)
        ).lower()
        explicit_existing_integration = (
            "existing prompt already imports" in combined
            or "existing generated_solve already imports" in combined
            or "existing runner already injects" in combined
            or "existing integration already" in combined
        )
        if explicit_existing_integration:
            return True, "ok"
        return (
            False,
            "helper_not_integrated: adapters/patents helper changes require prompt glue or run_dab_agent integration so future generated_solve.py can use the helper",
        )

    prompt_glue = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("anchor", "intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict) and normalize_rel(str(edit.get("file") or "")) == "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt"
    ).lower()
    if "experiments/run_dab_agent.py" in targets and not prompt_glue:
        return True, "ok"
    helper_modules = [Path(path).stem for path in helper_targets]
    mentions_helper = "adapters.patents" in prompt_glue or any(module in prompt_glue for module in helper_modules)
    mandatory = any(marker in prompt_glue for marker in ("must import", "must use", "must call", "always import", "always use", "required to import", "required to use"))
    weak_only = any(marker in prompt_glue for marker in ("prefer importing", "prefer using", "when available", "may import", "can import")) and not mandatory
    anti_inline = any(marker in prompt_glue for marker in ("do not reimplement", "do not duplicate", "instead of duplicating", "instead of reimplementing"))
    if not mentions_helper or not mandatory or weak_only:
        return (
            False,
            "helper_glue_too_weak: prompt glue for adapters/patents helpers must require generated_solve.py to import/use the helper, not merely prefer it",
        )
    if not anti_inline:
        return (
            False,
            "helper_glue_missing_no_inline_rule: prompt glue should tell generated_solve.py not to reimplement helper logic inline",
        )
    if "candidate_filtering" in prompt_glue or "rank_or_filter_candidates" in prompt_glue:
        mentions_prefiltered = "pre-filtered" in prompt_glue or "prefiltered" in prompt_glue
        negates_prefiltered = (
            "not pre-filtered" in prompt_glue
            or "not prefiltered" in prompt_glue
            or "not a pre-filtered" in prompt_glue
            or "not pass pre-filtered" in prompt_glue
            or "do not pass pre-filtered" in prompt_glue
        )
        uses_prefiltered_input = (
            "candidates_2022" in prompt_glue
            or "already filtered" in prompt_glue
            or (mentions_prefiltered and not negates_prefiltered)
        )
        if uses_prefiltered_input:
            return (
                False,
                "weak_filtering_no_op: prompt glue must require rank_or_filter_candidates(candidate_rows, target_year=2022), not a pre-filtered candidates_2022 list",
            )
        full_candidate_rows_glue = (
            "candidate_rows" in prompt_glue
            or "full list of unfiltered candidate rows" in prompt_glue
            or "full unfiltered candidate rows" in prompt_glue
            or "unfiltered candidate rows" in prompt_glue
        )
        if not full_candidate_rows_glue:
            return (
                False,
                "candidate_filtering_glue_missing_full_candidate_rows: prompt glue must tell generated_solve.py to pass full candidate_rows / full unfiltered candidate rows to rank_or_filter_candidates",
            )
    return True, "ok"


def helper_plan_requires_behavior_change(plan: dict[str, Any]) -> bool:
    if not isinstance(plan, dict) or plan.get("status") != "planned":
        return False
    contract = plan.get("patch_generation_contract") if isinstance(plan.get("patch_generation_contract"), dict) else {}
    behavior = contract.get("behavior_change_contract") if isinstance(contract.get("behavior_change_contract"), dict) else {}
    if behavior.get("required") is True:
        return True
    helper = normalize_rel(str(plan.get("recommended_helper_file") or ""))
    if helper.endswith("candidate_filtering.py"):
        return True
    for func in plan.get("required_functions") or []:
        if isinstance(func, dict) and str(func.get("name") or "") == "rank_or_filter_candidates":
            return True
    return False


def data_agent_tool_behavior_change_contract_check(spec: dict[str, Any], plan: dict[str, Any]) -> tuple[bool, str]:
    if not helper_plan_requires_behavior_change(plan):
        return True, "ok"
    behavior = spec.get("behavior_change_contract")
    if not isinstance(behavior, dict):
        return False, "behavior_change_contract_missing: v002 action-helper repairs must declare before/after/decision_path_change/child_observable_effect/why_not_diagnostics_only"
    required_fields = (
        "before",
        "after",
        "decision_path_change",
        "child_observable_effect",
        "why_not_diagnostics_only",
    )
    for field in required_fields:
        value = behavior.get(field)
        if not isinstance(value, str) or len(value.strip()) < 8:
            return False, f"behavior_change_contract_incomplete: missing non-empty {field}"
    edit_text = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    )
    combined = (json.dumps(behavior, ensure_ascii=False) + "\n" + edit_text).lower()
    action_markers = (
        "final_answer",
        "final answer",
        "selected_symbols",
        "construct final",
        "write final",
        "rank_or_filter_candidates",
        "ranking",
        "filtering",
        "selection",
        "select final",
        "exclude",
        "exclusion",
    )
    if not any(marker in combined for marker in action_markers):
        return False, "behavior_change_contract_no_decision_path: action helper must affect final answer selection/ranking/filtering, not only diagnostics"
    diagnostic_markers = ("diagnostic", "diagnostics", "summarize", "summary", "logging", "log only", "observation-only")
    final_answer_markers = ("final_answer", "final answer", "selected_symbols", "use its output", "helper output", "construct final", "write final")
    if any(marker in combined for marker in diagnostic_markers) and not any(marker in combined for marker in final_answer_markers):
        return False, "diagnostics_only_patch_rejected: v002 action-helper repair must use helper output to change final_answer construction"
    why = str(behavior.get("why_not_diagnostics_only") or "").lower()
    bad_why = ("diagnostics are sufficient", "logging is sufficient", "only log", "only summarize", "observation only")
    if any(marker in why for marker in bad_why):
        return False, "diagnostics_only_patch_rejected: why_not_diagnostics_only admits the patch is observation-only"
    return True, "ok"


def data_agent_tool_helper_plan_check(spec: dict[str, Any], repair_seed: Path | None, candidate_dir: Path | None = None) -> tuple[bool, str]:
    targets = [normalize_rel(str(path)) for path in spec.get("target_files") or []]
    helper_targets = [path for path in targets if path.startswith("adapters/patents/") and path.endswith(".py")]
    changed_files = set(changed_project_files_from_numstat(candidate_dir)) if candidate_dir else set()
    if candidate_dir is not None and helper_targets:
        unchanged_helper_targets = [path for path in helper_targets if path not in changed_files]
        if unchanged_helper_targets:
            return (
                False,
                f"declared_helper_target_no_effect: patch_spec targets helper file(s) {unchanged_helper_targets}, but final patch.diff changes {sorted(changed_files)}",
            )

    plan = load_helper_repair_plan(repair_seed)
    if plan.get("status") != "planned":
        return True, "ok"
    required_helper = normalize_rel(str(plan.get("recommended_helper_file") or ""))
    if not required_helper:
        return True, "ok"
    if required_helper not in targets:
        return (
            False,
            f"helper_plan_target_mismatch: fine-grained helper_repair_plan requires {required_helper}, but patch_spec targets {targets}",
        )
    if candidate_dir is not None and required_helper not in changed_files:
        return (
            False,
            f"helper_plan_target_no_effect: fine-grained helper_repair_plan requires {required_helper}, but final patch.diff changes {sorted(changed_files)}",
        )
    combined = "\n".join(
        "\n".join(str(edit.get(key, "")) for key in ("intended_change", "rationale"))
        for edit in spec.get("edits") or []
        if isinstance(edit, dict)
    ).lower()
    required_functions = [
        str(item.get("name") or "").lower()
        for item in plan.get("required_functions") or []
        if isinstance(item, dict) and item.get("name")
    ]
    if required_functions and not any(name in combined for name in required_functions):
        return (
            False,
            "helper_plan_api_missing: patch_spec targets the planned helper file but does not implement or mention the required helper API names",
        )
    behavior_ok, behavior_reason = data_agent_tool_behavior_change_contract_check(spec, plan)
    if not behavior_ok:
        return False, behavior_reason
    return True, "ok"


def data_agent_tool_helper_quality_check(spec: dict[str, Any]) -> tuple[bool, str]:
    for edit in spec.get("edits") or []:
        if not isinstance(edit, dict):
            continue
        rel = normalize_rel(str(edit.get("file") or ""))
        if not (rel.startswith("adapters/patents/") and rel.endswith(".py")):
            continue
        helper_text = (str(edit.get("intended_change") or "") + "\n" + str(edit.get("rationale") or "")).lower()
        diagnostics_helper_markers = (
            "answer_diagnostics.py",
            "summarize_candidate_decisions",
            "diagnostic helper",
            "candidate diagnostics",
            "diagnostics-only",
            "observation-only",
            "only logs",
            "log_event(event=\'candidate_decision_summary\'",
            'log_event(event="candidate_decision_summary"',
        )
        if rel.endswith("answer_diagnostics.py") or any(marker in helper_text for marker in diagnostics_helper_markers):
            return (
                False,
                "diagnostics_only_action_helper_rejected: data_agent_tool_repair must generate a helper that changes final answer ranking/filtering, not only candidate diagnostics/logging",
            )
        if rel.endswith("candidate_filtering.py"):
            cardinality_gaming_markers = (
                "expected_count",
                "expected count",
                "expected answer count",
                "match expected",
                "matches expected",
                "top 50",
                "[:50]",
                "at most 50",
                "exactly 50",
            )
            cardinality_check_text = helper_text
            negated_cardinality_phrases = (
                "no hardcoded answers or expected counts",
                "no hardcoded answer or expected count",
                "no hardcoded expected counts",
                "no hardcoded expected count",
                "without using expected counts",
                "without using expected count",
                "does not use expected counts",
                "does not use expected count",
                "do not use expected counts",
                "do not use expected count",
                "must not use expected counts",
                "must not use expected count",
                "no expected counts",
                "no expected count",
            )
            for phrase in negated_cardinality_phrases:
                cardinality_check_text = cardinality_check_text.replace(phrase, "")
            if any(marker in cardinality_check_text for marker in cardinality_gaming_markers):
                return False, "metric_gaming_guard: candidate_filtering helper must not use expected answer count/top-k truncation as the repair mechanism"
            if re.search(r"best_year\W*==\W*target_year", helper_text) and "return [row['symbol']" in helper_text:
                return False, "weak_filtering_no_op: candidate_filtering helper must not merely repeat best_year == target_year filtering and return all remaining symbols"
            if "sort" in helper_text and "filter" not in helper_text and "exclude" not in helper_text:
                return False, "weak_filtering_no_op: candidate_filtering helper only sorts candidates, which cannot improve set-valued answer validation"
        if rel.endswith("cpc_definition_parser.py"):
            tuple_return_markers = (
                "-> tuple",
                "-> tuple[",
                "-> tuple[dict",
                "tuple[dict",
                "tuple[dict[str",
                "return symbol_to_level, symbol_to_parents",
                "return (symbol_to_level, symbol_to_parents)",
            )
            if any(marker in helper_text for marker in tuple_return_markers):
                return (
                    False,
                    "cpc_definition_parser_return_contract_violation: parse_cpc_definition_sql must return a dict with symbol_to_level and symbol_to_parents, not a bare tuple",
                )
            has_symbol_to_level_key = '"symbol_to_level"' in helper_text or "'symbol_to_level'" in helper_text
            has_symbol_to_parents_key = '"symbol_to_parents"' in helper_text or "'symbol_to_parents'" in helper_text
            if not (has_symbol_to_level_key and has_symbol_to_parents_key):
                return (
                    False,
                    "cpc_definition_parser_return_contract_violation: helper text must expose symbol_to_level and symbol_to_parents dict keys",
                )
        if rel.endswith("cpc_mapping.py"):
            forbidden_patterns = (
                "fallback to prefix",
                "prefix fallback",
                "conservative prefix",
                "fallback-derived",
                "fallback derived",
                "return symbol  # fallback",
                "return symbol  #",
            )
            if any(pattern in helper_text for pattern in forbidden_patterns):
                return False, "metadata_grounding_violation: cpc_mapping helper must not encode prefix/string-shape fallback logic"
            if re.search(r"\.split\(\s*['\"]/[ '\"]*\)", helper_text) or "split('/')" in helper_text or 'split("/")' in helper_text:
                return False, "metadata_grounding_violation: cpc_mapping helper must not infer CPC level from slash/prefix shape"
            if "missing from metadata" in helper_text and "return symbol" in helper_text:
                return False, "metadata_grounding_violation: helper must return None or log failure when metadata is missing, not return raw symbols as mapped answers"
    return True, "ok"


def data_agent_tool_gate_soft_warning(reason: str | None) -> bool:
    """Return True for heuristic tool-repair gates that should not block child eval.

    These checks are useful signals, but we have repeatedly seen keyword-level
    false positives.  Keep protocol/safety/syntax gates hard; let child eval and
    parent-vs-child metrics decide semantic usefulness.
    """
    if not reason or reason == "ok":
        return False
    lowered = reason.lower()
    soft_markers = (
        "helper_plan_target_mismatch",
        "helper_plan_api_missing",
        "behavior_change_contract_no_decision_path",
        "diagnostics_only_patch_rejected",
        "diagnostics_only_action_helper_rejected",
        "helper_not_integrated",
        "helper_glue_too_weak",
        "helper_glue_missing_no_inline_rule",
        "candidate_filtering_glue_missing_full_candidate_rows",
        "weak_filtering_no_op",
        "metric_gaming_guard",
        "declared_helper_target_no_effect",
        "helper_plan_target_no_effect",
        "behavior_change_contract_missing",
        "behavior_change_contract_incomplete",
        "metadata_grounding_violation",
        "cpc_definition_parser_return_contract_violation",
    )
    # In the evolvable meta-agent setup, semantic/interface repair checks are
    # observations for the next iteration, not human-coded hard vetoes.  Safety,
    # protocol, forbidden-file, empty-patch, and syntax gates remain hard in
    # other layers.
    return any(marker in lowered for marker in soft_markers)



def cpc_definition_sql_validation_path() -> Path | None:
    """Return the real PATENTS CPCDefinition SQL path when available locally."""
    candidates = [
        os.environ.get("META_AGENT_CPC_DEFINITION_SQL_PATH"),
        os.environ.get("CPC_DEFINITION_SQL_PATH"),
        "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql",
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            return path
    return None


def run_cpc_definition_parser_real_sql_smoke(
    profile: RepairProfile,
    workspace: Path,
    candidate_dir: Path,
) -> dict[str, Any] | None:
    """Validate changed CPCDefinition parser helpers against the real PATENTS SQL dump."""
    rel = "adapters/patents/cpc_definition_parser.py"
    if profile.name != "data_agent_tool_repair":
        return None
    if rel not in set(changed_project_files_from_numstat(candidate_dir)):
        return None
    parser_path = workspace / rel
    if not parser_path.exists():
        return gate_result(
            profile,
            "real_cpc_definition_parser_smoke",
            exit_code=1,
            reason="changed cpc_definition_parser.py does not exist after apply",
            file=rel,
            gate_layer="validation",
            gate_type="real_data_parser_smoke",
        )
    sql_path = cpc_definition_sql_validation_path()
    if sql_path is None:
        return gate_result(
            profile,
            "real_cpc_definition_parser_smoke",
            exit_code=0,
            reason="skipped: real patent_CPCDefinition.sql not available in this environment",
            file=rel,
            gate_layer="validation",
            gate_type="real_data_parser_smoke",
            hard_fail=False,
        )
    out = candidate_dir / "validation"
    script = r'''
import json
import os
from pathlib import Path
from adapters.patents.cpc_definition_parser import parse_cpc_definition_sql

sql_path = Path(os.environ["META_AGENT_CPC_DEFINITION_SQL_PATH"])
metadata = parse_cpc_definition_sql(sql_path)
if not isinstance(metadata, dict):
    raise AssertionError(f"parse_cpc_definition_sql must return dict, got {type(metadata).__name__}")
for key in ("symbol_to_level", "symbol_to_parents"):
    if key not in metadata:
        raise AssertionError(f"metadata missing key: {key}")
symbol_to_level = metadata.get("symbol_to_level")
symbol_to_parents = metadata.get("symbol_to_parents")
if not isinstance(symbol_to_level, dict) or not symbol_to_level:
    raise AssertionError("symbol_to_level must be a non-empty dict for real patent_CPCDefinition.sql")
if not isinstance(symbol_to_parents, dict) or not symbol_to_parents:
    raise AssertionError("symbol_to_parents must be a non-empty dict for real patent_CPCDefinition.sql")
print(json.dumps({
    "status": "ok",
    "sql_path": str(sql_path),
    "symbol_to_level_count": len(symbol_to_level),
    "symbol_to_parents_count": len(symbol_to_parents),
}, ensure_ascii=False))
'''
    proc = run_cmd(
        [str(ROOT / ".venv/bin/python"), "-c", script],
        cwd=workspace,
        env={**os.environ, "PYTHONPATH": str(workspace), "META_AGENT_CPC_DEFINITION_SQL_PATH": str(sql_path)},
        stdout_path=out / "real_cpc_definition_parser_smoke.stdout",
        stderr_path=out / "real_cpc_definition_parser_smoke.stderr",
    )
    return gate_result(
        profile,
        "real_cpc_definition_parser_smoke",
        exit_code=proc.returncode,
        reason="ok" if proc.returncode == 0 else "parse real patent_CPCDefinition.sql failed",
        file=rel,
        gate_layer="validation",
        gate_type="real_data_parser_smoke",
        hard_fail=False,
        warning=proc.returncode != 0,
        sql_path=str(sql_path),
    )
def run_validation(profile: RepairProfile, workspace: Path, candidate_dir: Path, repair_seed: Path | None = None) -> tuple[bool, list[dict[str, Any]]]:
    out = candidate_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    spec = json.loads((candidate_dir / "validated_patch_spec.json").read_text(encoding="utf-8"))

    if profile.name in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair"}:
        hardcode_ok, hardcode_reason = no_hardcoded_answer_check(spec)
        results.append(gate_result(profile, "no_obvious_answer_hardcoding", exit_code=0 if hardcode_ok else 1, reason=hardcode_reason))
        if not hardcode_ok:
            return False, results

    if profile.name == "data_agent_tool_repair":
        plan_ok, plan_reason = data_agent_tool_helper_plan_check(spec, repair_seed, candidate_dir)
        plan_soft = (not plan_ok) and data_agent_tool_gate_soft_warning(plan_reason)
        results.append(
            gate_result(
                profile,
                "data_agent_tool_helper_plan_alignment",
                exit_code=0 if (plan_ok or plan_soft) else 1,
                reason=plan_reason,
                hard_fail=not plan_soft,
                warning=plan_soft,
            )
        )
        if not plan_ok and not plan_soft:
            return False, results
        integration_ok, integration_reason = data_agent_tool_helper_integration_check(spec)
        integration_soft = (not integration_ok) and data_agent_tool_gate_soft_warning(integration_reason)
        results.append(
            gate_result(
                profile,
                "data_agent_tool_helper_integration",
                exit_code=0 if (integration_ok or integration_soft) else 1,
                reason=integration_reason,
                hard_fail=not integration_soft,
                warning=integration_soft,
            )
        )
        if not integration_ok and not integration_soft:
            return False, results
        quality_ok, quality_reason = data_agent_tool_helper_quality_check(spec)
        quality_soft = (not quality_ok) and data_agent_tool_gate_soft_warning(quality_reason)
        results.append(
            gate_result(
                profile,
                "data_agent_tool_helper_quality",
                exit_code=0 if (quality_ok or quality_soft) else 1,
                reason=quality_reason,
                hard_fail=not quality_soft,
                warning=quality_soft,
            )
        )
        if not quality_ok and not quality_soft:
            return False, results

    if profile.name in {"data_agent_project_repair", "data_agent_tool_repair"}:
        for rel in changed_project_files_from_numstat(candidate_dir):
            if not rel.endswith(".py"):
                continue
            path = workspace / rel
            if not path.exists():
                continue
            name = f"py_compile_changed_{Path(rel).name}"
            proc = run_cmd(
                [str(ROOT / ".venv/bin/python"), "-m", "py_compile", str(path)],
                cwd=workspace,
                stdout_path=out / f"{name}.stdout",
                stderr_path=out / f"{name}.stderr",
            )
            results.append(gate_result(profile, name, file=rel, exit_code=proc.returncode, gate_layer="validation", gate_type="syntax"))
            if proc.returncode != 0:
                return False, results

    for rel in profile.py_compile_files:
        path = workspace / rel
        if not path.exists():
            continue
        name = f"py_compile_{Path(rel).name}"
        proc = run_cmd(
            [str(ROOT / ".venv/bin/python"), "-m", "py_compile", str(path)],
            cwd=workspace,
            stdout_path=out / f"{name}.stdout",
            stderr_path=out / f"{name}.stderr",
        )
        results.append(gate_result(profile, name, exit_code=proc.returncode, gate_layer="validation", gate_type="syntax"))
        if proc.returncode != 0:
            return False, results
    for module in profile.import_modules:
        name = f"import_{module.replace('.', '_')}"
        proc = run_cmd(
            [str(ROOT / ".venv/bin/python"), "-c", f"import {module}; print('ok')"],
            cwd=workspace,
            env={**os.environ, "PYTHONPATH": str(workspace)},
            stdout_path=out / f"{name}.stdout",
            stderr_path=out / f"{name}.stderr",
        )
        results.append(gate_result(profile, name, exit_code=proc.returncode, gate_layer="validation", gate_type="module_import"))
        if proc.returncode != 0:
            return False, results
    cpc_smoke = run_cpc_definition_parser_real_sql_smoke(profile, workspace, candidate_dir)
    if cpc_smoke is not None:
        results.append(cpc_smoke)
        if should_block_validation(cpc_smoke):
            return False, results

    if profile.name == "data_agent_prompt_repair":
        results.append(gate_result(profile, "static_prompt_repair_checks", exit_code=0))
    if profile.name == "data_agent_project_repair":
        results.append(gate_result(profile, "static_project_repair_checks", exit_code=0))
    if profile.name == "data_agent_tool_repair":
        results.append(gate_result(profile, "static_data_agent_tool_repair_checks", exit_code=0))
    return True, results


def write_manifest(candidate_dir: Path, payload: dict[str, Any]) -> None:
    status = payload.get("status")
    if status not in FINAL_STATUSES:
        raise ValueError(f"invalid final status: {status}")
    write_json(candidate_dir / "manifest.json", {"created_at": utc_now(), **payload})


def run_launcher(args: argparse.Namespace) -> int:
    profile = PROFILES[args.repair_profile]
    candidate_id = args.candidate_id or os.environ.get("META_LOOP_CANDIDATE_ID") or f"{profile.name}_{utc_slug()}"
    candidate_dir = Path(args.candidate_dir or os.environ.get("META_LOOP_CANDIDATE_DIR") or ROOT / "candidates/dab" / candidate_id)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    gate_protocol = profile_gate_protocol(profile)
    write_json(candidate_dir / "gate_protocol.json", gate_protocol)

    repair_seed = Path(args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED", "")) if (args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED")) else None
    repair_seed_override = os.environ.get("META_LOOP_REPAIR_SEED_OVERRIDE") == "1"
    parent_run = Path(args.parent_run or os.environ.get("META_LOOP_PARENT_RUN", "")) if (args.parent_run or os.environ.get("META_LOOP_PARENT_RUN")) else None
    parent_prompt = Path(args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT", "")) if (args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT")) else None
    parent_agent_id = os.environ.get("META_LOOP_PARENT_AGENT_ID")
    if parent_prompt is None and profile.name in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair"}:
        parent_prompt = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")

    workspace = make_workspace(candidate_dir)
    materialize_parent_source_patch(profile=profile, workspace=workspace, candidate_dir=candidate_dir, parent_agent_id=parent_agent_id)
    parent_prompt = materialize_parent_prompt(profile=profile, workspace=workspace, candidate_dir=candidate_dir, parent_prompt=parent_prompt)
    context = build_context_pack(
        profile=profile,
        workspace=workspace,
        candidate_dir=candidate_dir,
        repair_seed=repair_seed,
        parent_run=parent_run,
        parent_prompt=parent_prompt,
        repair_seed_override=repair_seed_override,
    )
    prompt = build_prompt(profile, context, candidate_dir)
    spec, _ = load_or_call_patch_spec(args, prompt, candidate_dir)

    spec_ok, spec_status, spec_reason = validate_spec(spec, profile, candidate_dir, repair_seed=repair_seed, repair_seed_override=repair_seed_override)
    if not spec_ok:
        write_manifest(
            candidate_dir,
            {
                "candidate_id": candidate_id,
                "status": spec_status,
                "reason": spec_reason,
                "repair_profile": profile.name,
                "profile_gate_version": gate_protocol["profile_gate_version"],
                "gate_protocol": gate_protocol,
                "workspace": str(workspace),
            },
        )
        return 20 if spec_status == "no_op_failed" else 61

    assert spec is not None
    apply_ok, apply_reason = apply_spec(spec, workspace, candidate_dir)
    if not apply_ok:
        write_manifest(candidate_dir, {"candidate_id": candidate_id, "status": "patch_apply_failed", "reason": apply_reason, "repair_profile": profile.name, "profile_gate_version": gate_protocol["profile_gate_version"], "gate_protocol": gate_protocol, "workspace": str(workspace)})
        return 71

    diff_info = diff_artifacts(workspace, candidate_dir)
    gate_ok, gate_status, gate_reason = post_apply_gate(profile, workspace, candidate_dir, diff_info)
    if not gate_ok:
        write_manifest(candidate_dir, {"candidate_id": candidate_id, "status": gate_status, "reason": gate_reason, "repair_profile": profile.name, "profile_gate_version": gate_protocol["profile_gate_version"], "gate_protocol": gate_protocol, "workspace": str(workspace), **diff_info})
        return 72

    validation_ok, validation_results = run_validation(profile, workspace, candidate_dir, repair_seed=repair_seed)
    final_status = "valid_candidate_pending_child_eval" if validation_ok else "failed_validation"
    write_manifest(
        candidate_dir,
        {
            "candidate_id": candidate_id,
            "status": final_status,
            "repair_profile": profile.name,
            "profile_gate_version": gate_protocol["profile_gate_version"],
            "gate_protocol": gate_protocol,
            "workspace": str(workspace),
            "project_changed_files": [path for path in diff_info["changed_files"] if is_allowed_file(path, profile)],
            "total_changed_lines": diff_info["total_changed_lines"],
            "patch_numstat": diff_info["patch_numstat"],
            "post_apply_gate_status": gate_status,
            "validation_results": validation_results,
            "scope_note": ("feedback/error-analysis infrastructure repair" if profile.name == "analyzer_infra_repair" else "data-agent tool repair; prefer reusable adapters/patents helpers with minimal prompt glue" if profile.name == "data_agent_tool_repair" else "data-agent project repair; may modify project source in isolated candidate workspace" if profile.name == "data_agent_project_repair" else "data-agent prompt repair; not feedback analyzer repair"),
        },
    )
    return 0 if validation_ok else 80


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-profile", choices=sorted(PROFILES), default=os.environ.get("REPAIR_PROFILE", "data_agent_prompt_repair"))
    parser.add_argument("--candidate-id")
    parser.add_argument("--candidate-dir")
    parser.add_argument("--repair-seed")
    parser.add_argument("--parent-run")
    parser.add_argument("--parent-prompt")
    parser.add_argument("--patch-spec-file")
    parser.add_argument("--no-call-meta-llm", action="store_true")
    parser.set_defaults(func=run_launcher)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
