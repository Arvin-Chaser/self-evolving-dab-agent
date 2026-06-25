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

PROFILE_SKILLS = {
    "data_agent_prompt_repair": ROOT / "skills/dab-data-agent-prompt-repair/SKILL.md",
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
}

FINAL_STATUSES = {
    "valid_candidate_pending_child_eval",
    "no_op_failed",
    "protocol_failed_invalid_patch_spec",
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
    if profile.name != "data_agent_prompt_repair" or parent_prompt is None:
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


def build_context_pack(
    *,
    profile: RepairProfile,
    workspace: Path,
    candidate_dir: Path,
    repair_seed: Path | None,
    parent_run: Path | None,
    parent_prompt: Path | None,
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
    skill_path = PROFILE_SKILLS.get(profile.name)
    if skill_path and skill_path.exists():
        lines += [
            "## Active repair skill",
            f"Path: `{skill_path.relative_to(ROOT)}`",
            "Follow this skill before proposing a patch_spec.",
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
            "If evidence shows `cpc_mapping_summary` with `mapped_to_level5 = 0` or all publication CPC entries unmapped, prioritize prompt instructions for CPC symbol normalization and metadata lookup before EMA/year logic.",
            "Future generated code should normalize raw publication CPC codes to the CPC definition `symbol` format before lookup, and should log coverage/sample unmatched codes when mapping coverage is zero.",
            "",
        ]
    if repair_seed and repair_seed.exists():
        lines += ["## Repair seed", "```json", read_text(repair_seed, 16000).strip(), "```", ""]
    if parent_prompt:
        prompt_path = parent_prompt if parent_prompt.is_absolute() else workspace / parent_prompt
        if prompt_path.exists():
            lines += ["## Parent data-agent prompt", f"Path: `{normalize_rel(parent_prompt)}`", "```text", read_text(prompt_path, 24000), "```", ""]
    if parent_run and parent_run.exists():
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
    out = candidate_dir / "minimal_source_context_pack.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def profile_prompt_instructions(profile: RepairProfile) -> str:
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
8. If the parent prompt contains an older contradictory runtime signature such as log_exception(exc) or "one positional argument", prefer replace_text_once on that stale prompt sentence/block instead of appending a new conflicting instruction.
9. Output strict JSON only: no markdown fences, no comments, no raw multiline strings. Use valid JSON escaping for all quote and newline characters inside JSON strings.
10. If the repair would require editing generated_solve.py or project source instead of the prompt, output no_op_failed.
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


def load_or_call_patch_spec(args: argparse.Namespace, prompt_path: Path, candidate_dir: Path) -> tuple[dict[str, Any] | None, str]:
    raw_path = candidate_dir / "patch_spec_raw.txt"
    patch_spec_file = args.patch_spec_file or os.environ.get("PATCH_SPEC_FILE")
    no_call_meta_llm = args.no_call_meta_llm or os.environ.get("NO_CALL_META_LLM") == "1"
    if patch_spec_file:
        raw = read_text(Path(patch_spec_file))
    elif no_call_meta_llm:
        raw = json.dumps({"status": "no_op_failed", "reason": "--no-call-meta-llm set and no --patch-spec-file provided"}, ensure_ascii=False)
    elif call_meta_llm is None:
        raw = json.dumps({"status": "no_op_failed", "reason": "llm_client.call_meta_llm unavailable"}, ensure_ascii=False)
    else:
        raw = call_meta_llm(read_text(prompt_path))
        if describe_llm_config:
            write_json(candidate_dir / "llm_config.json", describe_llm_config())
    raw_path.write_text(raw, encoding="utf-8")
    return extract_first_json(raw), raw



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
    return True, "ok"

def validate_spec(spec: dict[str, Any] | None, profile: RepairProfile, candidate_dir: Path) -> tuple[bool, str, str]:
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
        if profile.name == "data_agent_prompt_repair":
            code_markers = ("def ", "import ", "json.loads", "sqlite3", "FINAL_ANSWER_PATH", "STAGE_TRACE_PATH")
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
    return True, "post_apply_gate_passed", "ok"


def run_validation(profile: RepairProfile, workspace: Path, candidate_dir: Path) -> tuple[bool, list[dict[str, Any]]]:
    out = candidate_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
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
        spec = json.loads((candidate_dir / "validated_patch_spec.json").read_text(encoding="utf-8"))
        suspicious = ("final answer is", "answer:", "hardcode", "expected output")
        for edit in spec["edits"]:
            low = edit["intended_change"].lower()
            if any(marker in low for marker in suspicious):
                results.append({"name": "no_obvious_answer_hardcoding", "exit_code": 1})
                return False, results
        results.append({"name": "static_prompt_repair_checks", "exit_code": 0})
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
    parent_run = Path(args.parent_run or os.environ.get("META_LOOP_PARENT_RUN", "")) if (args.parent_run or os.environ.get("META_LOOP_PARENT_RUN")) else None
    parent_prompt = Path(args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT", "")) if (args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT")) else None
    if parent_prompt is None and profile.name == "data_agent_prompt_repair":
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
    )
    prompt = build_prompt(profile, context, candidate_dir)
    spec, _ = load_or_call_patch_spec(args, prompt, candidate_dir)

    spec_ok, spec_status, spec_reason = validate_spec(spec, profile, candidate_dir)
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
            "scope_note": "feedback/error-analysis infrastructure repair" if profile.name == "analyzer_infra_repair" else "data-agent prompt repair; not feedback analyzer repair",
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
