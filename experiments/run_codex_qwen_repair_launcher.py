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


def extract_first_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE):
        try:
            value = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
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


def is_prompt_path(path: str) -> bool:
    rel = normalize_rel(path)
    return rel.startswith("prompts/") and rel.endswith(".txt")


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
    if repair_seed and repair_seed.exists():
        lines += ["## Repair seed", "```json", read_text(repair_seed, 32000).strip(), "```", ""]
    if parent_prompt:
        prompt_path = parent_prompt if parent_prompt.is_absolute() else workspace / parent_prompt
        if prompt_path.exists():
            lines += ["## Parent data-agent prompt", f"Path: `{normalize_rel(parent_prompt)}`", "```text", read_text(prompt_path, 24000), "```", ""]
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
                    fence = "json" if artifact.suffix == ".json" else "text"
                    max_chars = 16000 if name == "agent_error_summary.json" else 12000
                    lines += [f"## Parent run artifact: {name}", f"Path: `{artifact}`", f"```{fence}", read_text(artifact, max_chars), "```", ""]
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
        source_excerpts = [
            "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
            "adapters/patents/__init__.py",
            "adapters/patents/cpc_definition.py",
            "adapters/patents/cpc_mapping.py",
            "adapters/patents/ema.py",
            "adapters/patents/patent_query_utils.py",
            "adapters/runtime_observer.py",
            "adapters/dab_validator.py",
            "adapters/feedback/common_trace_checks.py",
            "adapters/feedback/dab_patents_checks.py",
            "experiments/run_dab_agent.py",
            "experiments/analyze_agent_error.py",
            "experiments/extract_primary_signal.py",
            "experiments/build_meta_agent_evidence_pack.py",
        ]
        for rel in source_excerpts:
            source = workspace / rel
            if source.exists():
                fence = "python" if source.suffix == ".py" else "text"
                lines += [f"## Project source excerpt: {rel}", f"```{fence}", read_text(source, 12000), "```", ""]
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
10. If creating a new helper module, use operation create_file and include import-safe, py_compile-clean Python.
11. Do not modify feedback analyzer code, logs, candidates, archive, trajectories, reports, benchmarks, legacy code, data files, virtualenvs, pycache, or generated run artifacts.
12. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Use valid JSON escaping for all quote and newline characters inside JSON strings.
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
        for key in ("file", "operation", "anchor", "intended_change", "rationale"):
            if key not in edit or not isinstance(edit[key], str):
                return False, "protocol_failed_invalid_patch_spec", f"edit {idx} missing string {key}"
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
            code_markers = ("def ", "import ", "json.loads", "sqlite3")
            intended_only = edit["intended_change"].lower()
            if any(marker.lower() in intended_only for marker in code_markers):
                return False, "protocol_failed_invalid_patch_spec", f"edit {idx} appears to patch generated code instead of prompt instructions"
            change_ok, change_reason = validate_data_agent_prompt_change(edit, idx)
            if not change_ok:
                return False, "protocol_failed_invalid_patch_spec", change_reason
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


def apply_edit(workspace: Path, edit: dict[str, str]) -> None:
    path = workspace / edit["file"]
    op = edit["operation"]
    anchor = edit["anchor"]
    change = edit["intended_change"]
    if op == "create_file":
        if path.exists():
            raise ValueError(f"create_file target already exists: {edit['file']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(change, encoding="utf-8")
        return
    if not path.exists():
        raise ValueError(f"target file does not exist: {edit['file']}")
    text = path.read_text(encoding="utf-8")
    if op == "append_text":
        path.write_text(text + ("" if text.endswith("\n") else "\n") + change, encoding="utf-8")
        return
    if anchor not in text:
        raise ValueError(f"anchor not found in {edit['file']}")
    if op == "replace_text_once":
        path.write_text(text.replace(anchor, change, 1), encoding="utf-8")
    elif op == "insert_after_anchor":
        path.write_text(text.replace(anchor, anchor + change, 1), encoding="utf-8")
    elif op == "insert_before_anchor":
        path.write_text(text.replace(anchor, change + anchor, 1), encoding="utf-8")
    else:
        raise ValueError(f"unsupported operation: {op}")


def apply_spec(spec: dict[str, Any], workspace: Path, candidate_dir: Path) -> tuple[bool, str]:
    applied: list[dict[str, str]] = []
    try:
        for edit in spec["edits"]:
            apply_edit(workspace, edit)
            applied.append({"file": edit["file"], "operation": edit["operation"]})
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


def hardcode_marker_is_negated(text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 96): min(len(text), end + 96)]
    negators = r"(?:no|not|never|without|avoid(?:s|ing)?|prevent(?:s|ing)?|forbid(?:s|den)?|must not|do not|does not)"
    hardcode = r"hardcod\w*"
    if re.search(negators + r"(?:\W+\w+){0,8}\W+" + hardcode, context):
        return True
    if re.search(hardcode + r"(?:\W+\w+){0,8}\W+" + negators, context):
        return True
    return False


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
            if start >= 0 and not hardcode_marker_is_negated(low, start, start + len(marker)):
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
    if any(path in integration_targets for path in targets):
        return True, "ok"
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

def run_validation(profile: RepairProfile, workspace: Path, candidate_dir: Path) -> tuple[bool, list[dict[str, Any]]]:
    out = candidate_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    spec = json.loads((candidate_dir / "validated_patch_spec.json").read_text(encoding="utf-8"))

    if profile.name in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair"}:
        hardcode_ok, hardcode_reason = no_hardcoded_answer_check(spec)
        results.append({"name": "no_obvious_answer_hardcoding", "exit_code": 0 if hardcode_ok else 1, "reason": hardcode_reason})
        if not hardcode_ok:
            return False, results

    if profile.name == "data_agent_tool_repair":
        integration_ok, integration_reason = data_agent_tool_helper_integration_check(spec)
        results.append({"name": "data_agent_tool_helper_integration", "exit_code": 0 if integration_ok else 1, "reason": integration_reason})
        if not integration_ok:
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
            results.append({"name": name, "file": rel, "exit_code": proc.returncode})
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
        results.append({"name": name, "exit_code": proc.returncode})
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
        results.append({"name": name, "exit_code": proc.returncode})
        if proc.returncode != 0:
            return False, results
    if profile.name == "data_agent_prompt_repair":
        results.append({"name": "static_prompt_repair_checks", "exit_code": 0})
    if profile.name == "data_agent_project_repair":
        results.append({"name": "static_project_repair_checks", "exit_code": 0})
    if profile.name == "data_agent_tool_repair":
        results.append({"name": "static_data_agent_tool_repair_checks", "exit_code": 0})
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

    repair_seed = Path(args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED", "")) if (args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED")) else None
    repair_seed_override = os.environ.get("META_LOOP_REPAIR_SEED_OVERRIDE") == "1"
    parent_run = Path(args.parent_run or os.environ.get("META_LOOP_PARENT_RUN", "")) if (args.parent_run or os.environ.get("META_LOOP_PARENT_RUN")) else None
    parent_prompt = Path(args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT", "")) if (args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT")) else None
    if parent_prompt is None and profile.name in {"data_agent_prompt_repair", "data_agent_project_repair"}:
        parent_prompt = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")

    workspace = make_workspace(candidate_dir)
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
                "workspace": str(workspace),
            },
        )
        return 20 if spec_status == "no_op_failed" else 61

    assert spec is not None
    apply_ok, apply_reason = apply_spec(spec, workspace, candidate_dir)
    if not apply_ok:
        write_manifest(candidate_dir, {"candidate_id": candidate_id, "status": "patch_apply_failed", "reason": apply_reason, "repair_profile": profile.name, "workspace": str(workspace)})
        return 71

    diff_info = diff_artifacts(workspace, candidate_dir)
    gate_ok, gate_status, gate_reason = post_apply_gate(profile, workspace, candidate_dir, diff_info)
    if not gate_ok:
        write_manifest(candidate_dir, {"candidate_id": candidate_id, "status": gate_status, "reason": gate_reason, "repair_profile": profile.name, "workspace": str(workspace), **diff_info})
        return 72

    validation_ok, validation_results = run_validation(profile, workspace, candidate_dir)
    final_status = "valid_candidate_pending_child_eval" if validation_ok else "failed_validation"
    write_manifest(
        candidate_dir,
        {
            "candidate_id": candidate_id,
            "status": final_status,
            "repair_profile": profile.name,
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
