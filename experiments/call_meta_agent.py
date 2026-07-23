"""Call a coding meta-agent and save a patch candidate bundle.

This is the first automated meta-agent interface. It reads a task package from
``build_evolution_task.py``, builds a bounded coding prompt, calls the local LLM,
and extracts a candidate ``patch.diff`` plus review metadata.

The script intentionally does not apply the patch. Use
``experiments/apply_candidate_patch.py`` for the guarded apply step.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report
from llm_client import call_meta_llm, describe_llm_config


DEFAULT_SCHEMA = BASE_DIR / "meta_agent" / "meta_agent_response_schema.md"
DEFAULT_PROJECT_PROMPT = BASE_DIR / "prompts" / "dab" / "meta_agent" / "project_evolve_prompt.txt"


def read_text_limited(path: Path, max_chars: int) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n[TRUNCATED]\n", True


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_fenced_blocks(text: str, language: str) -> list[str]:
    pattern = rf"```{re.escape(language)}\s*\n(.*?)\n```"
    return [match.strip() for match in re.findall(pattern, text, flags=re.DOTALL | re.IGNORECASE)]


def _decode_json_string_fragment(fragment: str) -> str:
    try:
        return json.loads(f'"{fragment}"')
    except json.JSONDecodeError:
        return fragment


def extract_partial_json_metadata(text: str) -> dict[str, Any]:
    """Recover top-level metadata when a long fenced JSON object is malformed.

    Meta-agent responses often put large code snippets in `edits[].content`.
    A small syntax error near the end should not erase earlier routing fields
    such as repair_target, which patch lint needs for grounded decisions.
    """
    recovered: dict[str, Any] = {}
    string_fields = [
        "candidate_id",
        "goal",
        "repair_target",
        "evidence_quality",
        "why_this_target",
        "why_not_prompt_only",
        "expected_effect",
    ]
    for field in string_fields:
        match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
        if match:
            recovered[field] = _decode_json_string_fragment(match.group(1))

    bool_match = re.search(r'"feedback_layer_sufficient"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    if bool_match:
        recovered["feedback_layer_sufficient"] = bool_match.group(1).lower() == "true"

    for field in ("changed_files", "validation_plan", "risks"):
        match = re.search(rf'"{re.escape(field)}"\s*:\s*\[(.*?)\]', text, flags=re.DOTALL)
        if not match:
            continue
        recovered[field] = [
            _decode_json_string_fragment(item)
            for item in re.findall(r'"((?:\\.|[^"\\])*)"', match.group(1), flags=re.DOTALL)
        ]

    if recovered:
        recovered.setdefault("parse_warning", "Recovered top-level metadata from malformed JSON.")
    return recovered


def extract_first_json(text: str) -> dict[str, Any]:
    for block in extract_fenced_blocks(text, "json"):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            recovered = extract_partial_json_metadata(block)
            if recovered:
                return recovered
            continue
        if isinstance(value, dict):
            return value

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return extract_partial_json_metadata(match.group(0))
        if isinstance(value, dict):
            return value
    return {}


def extract_markdown_summary(text: str) -> str:
    blocks = extract_fenced_blocks(text, "markdown") + extract_fenced_blocks(text, "md")
    if blocks:
        return blocks[0].strip() + "\n"
    return "# Change Summary\n\nNo fenced markdown summary was found in the meta-agent response.\n"


def extract_unified_diff(text: str) -> str:
    diff_blocks = extract_fenced_blocks(text, "diff")
    if diff_blocks:
        return diff_blocks[0].strip() + "\n"

    index = text.find("diff --git ")
    if index >= 0:
        return text[index:].strip() + "\n"

    return ""


def normalize_patch_path(path_text: str) -> str | None:
    path_text = path_text.strip()
    if not path_text or path_text == "/dev/null":
        return None
    if path_text.startswith("a/") or path_text.startswith("b/"):
        path_text = path_text[2:]
    return path_text


def touched_paths_from_patch(patch_text: str) -> list[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            for item in parts[2:4]:
                normalized = normalize_patch_path(item)
                if normalized:
                    paths.add(normalized)
        elif line.startswith("--- ") or line.startswith("+++ "):
            item = line[4:].split("\t", 1)[0]
            normalized = normalize_patch_path(item)
            if normalized:
                paths.add(normalized)
    return sorted(paths)


def git_apply_check(patch_path: Path, repo_root: Path = BASE_DIR) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "--check", str(patch_path)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "message": result.stderr.strip() or result.stdout.strip(),
    }


def build_patch_repair_prompt(
    invalid_patch: str,
    check_result: dict[str, Any],
    response_schema: Path,
    candidate_dir: Path,
    max_source_chars: int,
) -> str:
    schema_text = response_schema.read_text(encoding="utf-8", errors="replace")
    source_sections: list[str] = []

    for path_text in touched_paths_from_patch(invalid_patch):
        path = BASE_DIR / path_text
        if not path.exists() or not path.is_file():
            continue
        content, truncated = read_text_limited(path, max_source_chars)
        suffix = "\n[TRUNCATED]" if truncated else ""
        source_sections.append(
            "\n".join(
                [
                    f"## Current File: {path_text}",
                    "",
                    "```text",
                    content.rstrip(),
                    suffix,
                    "```",
                    "",
                ]
            )
        )

    return "\n".join(
        [
            "You previously generated an invalid unified diff for this meta-agent candidate.",
            "Repair only the diff. Do not introduce new behavior beyond the original intended change.",
            "",
            "Hard requirements:",
            "- Output exactly one fenced ```diff block and no prose.",
            "- The diff must pass `git apply --check` from the repository root.",
            "- Include valid hunk headers and exact context from the current files.",
            "- For markdown bullet lines, remember that a removed line begins with two minus characters: one diff marker plus the literal markdown '-'.",
            "- Do not edit validators, ground truth, legacy files, logs, .env, or llm_client.py.",
            "- Do not convert validator-only expected counts or missing-answer examples into data-agent rules.",
            "",
            "中文要求：",
            "- 只修复 unified diff 格式，不要扩展新的修改目标。",
            "- diff 必须能通过 `git apply --check`。",
            "- 不要把验证器里的 expected 数量或 missing 示例写成 agent 规则。",
            "",
            "# Response Schema Reminder",
            "",
            schema_text,
            "",
            "# git apply --check failure",
            "",
            "```text",
            json.dumps(check_result, indent=2, ensure_ascii=False),
            "```",
            "",
            "# Candidate Directory",
            "",
            str(candidate_dir),
            "",
            "# Invalid Patch",
            "",
            "```diff",
            invalid_patch.rstrip(),
            "```",
            "",
            "# Current Source Files",
            "",
            "\n".join(source_sections),
        ]
    )


def repair_patch_with_meta_llm(
    invalid_patch: str,
    check_result: dict[str, Any],
    response_schema: Path,
    candidate_dir: Path,
    attempt: int,
    max_source_chars: int,
) -> tuple[str, dict[str, Any]]:
    repair_prompt = build_patch_repair_prompt(
        invalid_patch=invalid_patch,
        check_result=check_result,
        response_schema=response_schema,
        candidate_dir=candidate_dir,
        max_source_chars=max_source_chars,
    )
    prompt_path = candidate_dir / f"meta_agent_patch_repair_prompt_{attempt:03d}.txt"
    raw_path = candidate_dir / f"meta_agent_patch_repair_raw_output_{attempt:03d}.txt"
    prompt_path.write_text(repair_prompt, encoding="utf-8")
    raw_text = call_meta_llm(repair_prompt)
    raw_path.write_text(raw_text, encoding="utf-8")
    repaired_patch = extract_unified_diff(raw_text)
    return repaired_patch, {
        "attempt": attempt,
        "strategy": "diff_repair",
        "prompt_path": str(prompt_path),
        "raw_output_path": str(raw_path),
        "patch_found": bool(repaired_patch),
    }


def safe_snapshot_path(candidate_dir: Path, path_text: str, suffix: str) -> Path:
    safe_name = path_text.replace("/", "__").replace("\\", "__")
    return candidate_dir / "replacement_files" / f"{safe_name}.{suffix}"


def build_replacement_repair_prompt(
    invalid_patch: str,
    check_result: dict[str, Any],
    response_schema: Path,
    candidate_dir: Path,
    max_source_chars: int,
) -> str:
    schema_text = response_schema.read_text(encoding="utf-8", errors="replace")
    source_sections: list[str] = []
    paths = touched_paths_from_patch(invalid_patch)

    for path_text in paths:
        path = BASE_DIR / path_text
        if not path.exists() or not path.is_file():
            continue
        content, truncated = read_text_limited(path, max_source_chars)
        suffix = "\n[TRUNCATED]" if truncated else ""
        source_sections.append(
            "\n".join(
                [
                    f"## Current File: {path_text}",
                    "",
                    "```text",
                    content.rstrip(),
                    suffix,
                    "```",
                    "",
                ]
            )
        )

    return "\n".join(
        [
            "Your unified diff repair did not pass git apply --check.",
            "Now output complete replacement content for the touched files as JSON.",
            "The local script will generate the unified diff from your replacement content.",
            "",
            "Hard requirements:",
            "- Output exactly one fenced ```json block and no prose.",
            "- Use this schema: {\"files\": [{\"path\": \"repo/relative/path\", \"content\": \"complete new file content\"}]}",
            "- Only include files already touched by the invalid patch.",
            "- Preserve all unrelated content exactly.",
            "- Do not edit validators, ground truth, legacy files, logs, .env, or llm_client.py.",
            "- Do not convert validator-only expected counts or missing-answer examples into data-agent rules.",
            "- If you cannot safely provide the complete file content, return {\"files\": []}.",
            "",
            "中文要求：",
            "- 这次不要输出 diff，只输出完整文件内容 JSON。",
            "- 本地脚本会用完整文件内容生成合法 unified diff。",
            "- 不要把 validator 的 expected 数量或 missing 示例写成 agent 规则。",
            "",
            "# Response Schema Reminder",
            "",
            schema_text,
            "",
            "# Touched Paths",
            "",
            "```json",
            json.dumps(paths, indent=2, ensure_ascii=False),
            "```",
            "",
            "# git apply --check failure",
            "",
            "```text",
            json.dumps(check_result, indent=2, ensure_ascii=False),
            "```",
            "",
            "# Invalid Patch",
            "",
            "```diff",
            invalid_patch.rstrip(),
            "```",
            "",
            "# Current Source Files",
            "",
            "\n".join(source_sections),
        ]
    )


def patch_from_replacements(replacements: list[dict[str, Any]], candidate_dir: Path) -> str:
    patch_parts: list[str] = []
    snapshot_dir = candidate_dir / "replacement_files"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for item in replacements:
        path_text = item.get("path")
        content = item.get("content")
        if not isinstance(path_text, str) or not isinstance(content, str):
            continue
        rel_path = normalize_patch_path(path_text)
        if not rel_path:
            continue
        path = BASE_DIR / rel_path
        if not path.exists() or not path.is_file():
            continue

        old_text = path.read_text(encoding="utf-8", errors="replace")
        old_lines = old_text.splitlines(keepends=True)
        new_text = content
        if old_text.endswith("\n") and not new_text.endswith("\n"):
            new_text += "\n"
        new_lines = new_text.splitlines(keepends=True)
        if old_lines == new_lines:
            continue

        snapshot_path = safe_snapshot_path(candidate_dir, rel_path, "txt")
        snapshot_path.write_text(new_text, encoding="utf-8")
        patch_parts.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            )
        )

    if not patch_parts:
        return ""

    return "".join(line if line.endswith("\n") else f"{line}\n" for line in patch_parts)


def patch_from_structured_edits(
    edits: list[dict[str, Any]],
    candidate_dir: Path,
) -> tuple[str, list[dict[str, Any]]]:
    """Build a local unified diff from constrained structured edits."""
    by_path: dict[str, str] = {}
    results: list[dict[str, Any]] = []

    for index, edit in enumerate(edits, start=1):
        path_text = edit.get("path")
        mode = str(edit.get("mode") or "exact_replace").strip()
        if not isinstance(path_text, str):
            results.append(
                {
                    "index": index,
                    "status": "rejected",
                    "reason": "Each edit must include a string path field.",
                }
            )
            continue

        rel_path = normalize_patch_path(path_text)
        if not rel_path:
            results.append({"index": index, "path": path_text, "status": "rejected", "reason": "Invalid path."})
            continue
        path = BASE_DIR / rel_path
        if not path.exists() or not path.is_file():
            results.append({"index": index, "path": rel_path, "status": "rejected", "reason": "File missing."})
            continue

        current_text = by_path.get(rel_path)
        if current_text is None:
            current_text = path.read_text(encoding="utf-8", errors="replace")

        if mode == "exact_replace":
            find_text = edit.get("find")
            replace_text = edit.get("replace")
            if not isinstance(find_text, str) or not isinstance(replace_text, str):
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "status": "rejected",
                        "reason": "exact_replace edits must include string find and replace fields.",
                    }
                )
                continue

            occurrence_count = current_text.count(find_text)
            if occurrence_count != 1:
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "status": "rejected",
                        "reason": f"Find text matched {occurrence_count} times; expected exactly 1.",
                    }
                )
                continue

            by_path[rel_path] = current_text.replace(find_text, replace_text, 1)
            results.append({"index": index, "path": rel_path, "mode": mode, "status": "applied_to_candidate"})
            continue

        if mode == "insert_after":
            anchor_text = edit.get("anchor") or edit.get("find")
            insert_text = edit.get("insert") or edit.get("replace")
            if not isinstance(anchor_text, str) or not isinstance(insert_text, str):
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "mode": mode,
                        "status": "rejected",
                        "reason": "insert_after edits must include string anchor and insert fields.",
                    }
                )
                continue

            occurrence_count = current_text.count(anchor_text)
            if occurrence_count != 1:
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "mode": mode,
                        "status": "rejected",
                        "reason": f"Anchor text matched {occurrence_count} times; expected exactly 1.",
                    }
                )
                continue
            if re.match(r"\s*(async\s+def|def|class)\s+", anchor_text.strip()) and re.search(
                r"^\s*(async\s+def|def|class)\s+",
                insert_text,
                flags=re.MULTILINE,
            ):
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "mode": mode,
                        "status": "rejected",
                        "reason": "Do not insert a new function/class directly after a function/class signature; use exact_replace for an existing function or append_to_file for a new top-level helper.",
                    }
                )
                continue

            prefix = "" if anchor_text.endswith("\n") or insert_text.startswith("\n") else "\n"
            suffix = "" if insert_text.endswith("\n") else "\n"
            by_path[rel_path] = current_text.replace(anchor_text, anchor_text + prefix + insert_text + suffix, 1)
            results.append({"index": index, "path": rel_path, "mode": mode, "status": "applied_to_candidate"})
            continue

        if mode == "append_to_file":
            content = edit.get("content") or edit.get("insert") or edit.get("replace")
            if not isinstance(content, str) or not content.strip():
                results.append(
                    {
                        "index": index,
                        "path": rel_path,
                        "mode": mode,
                        "status": "rejected",
                        "reason": "append_to_file edits must include non-empty string content.",
                    }
                )
                continue

            prefix = "" if current_text.endswith("\n\n") else "\n" if current_text.endswith("\n") else "\n\n"
            by_path[rel_path] = current_text + prefix + content.rstrip() + "\n"
            results.append({"index": index, "path": rel_path, "mode": mode, "status": "applied_to_candidate"})
            continue

        results.append(
            {
                "index": index,
                "path": rel_path,
                "mode": mode,
                "status": "rejected",
                "reason": "Unknown edit mode. Use exact_replace, insert_after, or append_to_file.",
            }
        )
        continue

    replacements = [{"path": path, "content": content} for path, content in by_path.items()]
    return patch_from_replacements(replacements, candidate_dir), results


def repair_patch_by_replacement(
    invalid_patch: str,
    check_result: dict[str, Any],
    response_schema: Path,
    candidate_dir: Path,
    max_source_chars: int,
) -> tuple[str, dict[str, Any]]:
    repair_prompt = build_replacement_repair_prompt(
        invalid_patch=invalid_patch,
        check_result=check_result,
        response_schema=response_schema,
        candidate_dir=candidate_dir,
        max_source_chars=max_source_chars,
    )
    prompt_path = candidate_dir / "meta_agent_replacement_repair_prompt.txt"
    raw_path = candidate_dir / "meta_agent_replacement_repair_raw_output.txt"
    prompt_path.write_text(repair_prompt, encoding="utf-8")
    raw_text = call_meta_llm(repair_prompt)
    raw_path.write_text(raw_text, encoding="utf-8")
    replacement_payload = extract_first_json(raw_text)
    replacements = replacement_payload.get("files") if isinstance(replacement_payload, dict) else []
    if not isinstance(replacements, list):
        replacements = []
    repaired_patch = patch_from_replacements(replacements, candidate_dir)
    return repaired_patch, {
        "attempt": 1,
        "strategy": "replacement_repair",
        "prompt_path": str(prompt_path),
        "raw_output_path": str(raw_path),
        "replacement_count": len(replacements),
        "patch_found": bool(repaired_patch),
    }


def collect_context_sections(
    manifest: dict[str, Any],
    max_source_chars: int,
    max_total_source_chars: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    sections: list[str] = []
    refs_read: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_chars = 0

    ref_groups = [
        ("analyzer_refs", "Analyzer Output"),
        ("source_refs", "Source Reference"),
        ("run_artifact_refs", "Run Artifact"),
        ("scope_refs", "Scope Reference"),
        ("script_report_refs", "Script Report"),
    ]

    artifact_priority = {
        "stage_trace.json": 0,
        "generated_solve.py": 1,
        "result.json": 2,
        "summary.json": 3,
        "final_answer.txt": 4,
        "execution_stderr.txt": 5,
        "execution_stdout.txt": 6,
        "prompt.txt": 7,
        "raw_llm_output.txt": 8,
    }
    source_priority = {
        "experiments/analyze_agent_error.py": 0,
        "adapters/feedback/dab_patents_checks.py": 1,
        "adapters/feedback/common_trace_checks.py": 2,
        "adapters/runtime_observer.py": 3,
        "prompts/dab/meta_agent/project_evolve_prompt.txt": 4,
        "meta_agent/agent_scope.md": 5,
        "experiments/run_dab_agent.py": 6,
        "experiments/build_evolution_task.py": 7,
        "experiments/run_meta_agent_loop.py": 8,
        "experiments/script_run_report.py": 9,
        "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt": 10,
        "prompts/dab/dab_code_agent_prompt_v004_operation_trace.txt": 11,
    }
    skipped_run_artifacts = {
        "final_answer.txt",
        "prompt.txt",
        "raw_llm_output.txt",
    }
    compact_artifact_limits = {
        "stage_trace.json": 12000,
        "generated_solve.py": 16000,
        "result.json": 6000,
        "summary.json": 4000,
        "execution_stdout.txt": 4000,
        "execution_stderr.txt": 4000,
    }
    compact_source_limits = {
        "adapters/feedback/common_trace_checks.py": 12000,
        "experiments/run_dab_agent.py": 6000,
        "experiments/build_evolution_task.py": 3000,
        "experiments/run_meta_agent_loop.py": 3000,
        "experiments/script_run_report.py": 3000,
        "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt": 6000,
        "prompts/dab/dab_code_agent_prompt_v004_operation_trace.txt": 3000,
    }

    def ordered_refs(group_name: str) -> list[dict[str, Any]]:
        refs = list(manifest.get(group_name) or [])
        if group_name == "run_artifact_refs":
            refs.sort(key=lambda ref: artifact_priority.get(Path(ref.get("path", "")).name, 100))
        if group_name == "source_refs":
            refs.sort(
                key=lambda ref: source_priority.get(
                    str(ref.get("repo_relative_path") or Path(ref.get("path", "")).as_posix()),
                    100,
                )
            )
        return refs

    def context_limit(group_name: str, path: Path, remaining: int) -> int:
        limit = min(max_source_chars, remaining)
        if group_name == "run_artifact_refs":
            limit = min(limit, compact_artifact_limits.get(path.name, max_source_chars))
        if group_name == "source_refs":
            try:
                rel_path = path.resolve().relative_to(BASE_DIR).as_posix()
            except ValueError:
                rel_path = path.as_posix()
            limit = min(limit, compact_source_limits.get(rel_path, max_source_chars))
        if group_name == "script_report_refs":
            limit = min(limit, 6000)
        return limit

    for group_name, label in ref_groups:
        for ref in ordered_refs(group_name):
            path_text = ref.get("path")
            if not path_text:
                continue
            path = Path(path_text)
            if group_name == "run_artifact_refs" and path.name in skipped_run_artifacts:
                warnings.append(f"Skipped large/duplicative run artifact: {path}")
                continue
            if not path.exists() or not path.is_file():
                warnings.append(f"Missing {group_name}: {path}")
                continue
            remaining = max_total_source_chars - total_chars
            if remaining <= 0:
                warnings.append("Context budget exhausted before all references were read.")
                break
            limit = context_limit(group_name, path, remaining)
            content, truncated = read_text_limited(path, limit)
            total_chars += len(content)
            refs_read.append(path_ref(path.name, path, role=group_name))
            if truncated:
                warnings.append(f"Truncated {path} to {limit} chars.")
            sections.append(
                "\n".join(
                    [
                        f"## {label}: {path}",
                        "",
                        "```text",
                        content.rstrip(),
                        "```",
                        "",
                    ]
                )
            )
        if total_chars >= max_total_source_chars:
            break

    return "\n".join(sections), refs_read, warnings


def build_meta_agent_prompt(
    task_md: Path,
    context_manifest: Path,
    response_schema: Path,
    max_source_chars: int,
    max_total_source_chars: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    task_text = task_md.read_text(encoding="utf-8", errors="replace")
    schema_text = response_schema.read_text(encoding="utf-8", errors="replace")
    project_prompt = (
        DEFAULT_PROJECT_PROMPT.read_text(encoding="utf-8", errors="replace")
        if DEFAULT_PROJECT_PROMPT.exists()
        else ""
    )
    manifest = load_json(context_manifest)
    context_text, refs_read, warnings = collect_context_sections(
        manifest=manifest,
        max_source_chars=max_source_chars,
        max_total_source_chars=max_total_source_chars,
    )

    prompt = "\n".join(
        [
            "You are the project-level meta-agent for a DAB data-agent.",
            "Your job is to propose small structured edits. The local script will turn them into a patch.",
            "",
            "Hard requirements:",
            "- Output exactly the required fenced json and markdown blocks.",
            "- In the json block, include an `edits` list of constrained structured operations.",
            "- Prefer `mode: \"append_to_file\"` for adding helper functions at the end of a file.",
            "- Prefer `mode: \"insert_after\"` with a short unique anchor for small insertions after an existing function or bullet.",
            "- Use `mode: \"exact_replace\"` only for short spans that you copied exactly from the current source.",
            "- When changing an existing Python function, use `exact_replace` on that function body or a short internal block; never insert a new `def` directly after an existing `def ...:` signature.",
            "- In the json block, include `repair_target`, `evidence_quality`, `why_this_target`, `why_not_prompt_only`, and `feedback_layer_sufficient`.",
            "- Use exactly one valid repair_target value from the response schema; `runtime_observer` is not valid, use `feedback_adapter` for adapters/runtime_observer.py.",
            "- Do not output a unified diff unless explicitly asked; local code will generate patch.diff.",
            "- Do not edit validators, ground truth, old logs, legacy code, .env, or llm_client.py.",
            "- Do not hard-code benchmark answers.",
            "- Do not convert validator-only expected counts, missing items, or extra items into agent rules unless the original natural-language task states them.",
            "- Prefer changes grounded in runtime logs, analyzer output, and script reports.",
            "- Do not default to editing the object-level data-agent prompt. First decide whether the failure is caused by weak feedback, missing runtime signals, analyzer misclassification, task packaging, runner/context injection, or loop guard behavior.",
            "- If evidence is coarse, contradictory, missing, or repeatedly causes prompt regressions, improve feedback/analyzer/runner/task-packaging before adding more prompt constraints.",
            "- Feedback/analyzer patches must affect the active analysis path: wire new helpers into an existing extractor, analyzer, or context builder in the same patch.",
            "- Do not add runtime-observer APIs or feedback helpers as standalone prerequisites; the same patch must make generated code call them via prompt/runner changes or make analyzer/context code consume them.",
            "- If the child failure is an infrastructure/API failure, say so and improve the loop only if useful.",
            "",
            "中文要求：",
            "- 你是项目级 meta-agent，不是只改 prompt 的 prompt engineer。",
            "- 输出必须包含 json、markdown 两个 fenced block。",
            "- json 里用 edits 数组表达结构化修改；不要自己写 unified diff。",
            "- 追加 helper 函数时优先用 `append_to_file`，小范围插入时优先用 `insert_after`，只有短文本替换才用 `exact_replace`。",
            "- 修改已有 Python 函数时，用 `exact_replace` 替换函数体或函数内部短片段；不要在已有 `def ...:` 签名后直接插入新的 `def`。",
            "- 修改必须基于 trajectory、runtime log、analyzer 或 script report 的证据。",
            "- 不要默认修改 object-level data-agent prompt；要先判断问题是不是 feedback、analyzer、runner、task packaging 或 loop guard 不够好。",
            "- 如果证据太粗、互相矛盾、缺失，或者反复诱导 prompt 回归，应优先演进反馈/分析/打包/护栏层。",
            "- feedback/analyzer patch 必须接入实际分析路径；不要只追加没有调用者的 helper 函数。",
            "- 不要只新增 runtime-observer API 或 feedback helper 作为未来前置工作；同一个 patch 必须让 generated code 通过 prompt/runner 调用它，或让 analyzer/context 消费它。",
            "- 不要把 validator 里的 expected 数量、missing 示例或 extra 示例写成 agent 规则，除非原始任务文本明确要求。",
            "",
            "# Project Meta-Agent Prompt",
            "",
            project_prompt,
            "",
            "# Response Schema",
            "",
            schema_text,
            "",
            "# Evolution Task",
            "",
            task_text,
            "",
            "# Context Manifest",
            "",
            "```json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
            "```",
            "",
            "# Referenced Context",
            "",
            context_text,
        ]
    )
    return prompt, refs_read, warnings


def call_meta_agent(
    task_md: Path,
    context_manifest: Path,
    candidate_dir: Path,
    response_schema: Path = DEFAULT_SCHEMA,
    max_source_chars: int = 12000,
    max_total_source_chars: int = 60000,
    patch_repair_attempts: int = 1,
    dry_run: bool = False,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    candidate_dir.mkdir(parents=True, exist_ok=True)

    prompt, refs_read, warnings = build_meta_agent_prompt(
        task_md=task_md,
        context_manifest=context_manifest,
        response_schema=response_schema,
        max_source_chars=max_source_chars,
        max_total_source_chars=max_total_source_chars,
    )

    prompt_path = candidate_dir / "meta_agent_prompt.txt"
    raw_output_path = candidate_dir / "meta_agent_raw_output.txt"
    proposal_path = candidate_dir / "proposal.json"
    summary_path = candidate_dir / "change_summary.md"
    patch_path = candidate_dir / "patch.diff"
    patch_check_path = candidate_dir / "patch_check.json"

    prompt_path.write_text(prompt, encoding="utf-8")

    operations: list[dict[str, Any]] = [
        {
            "name": "build_meta_agent_prompt",
            "status": "completed",
            "outputs": {
                "prompt_path": str(prompt_path),
                "refs_read": len(refs_read),
                "warnings": warnings,
                "llm_config": describe_llm_config()["meta"],
            },
        }
    ]

    error: dict[str, Any] | None = None
    patch_check_result: dict[str, Any] | None = None
    repair_records: list[dict[str, Any]] = []

    if dry_run:
        raw_text = ""
        proposal = {
            "candidate_id": candidate_dir.name,
            "goal": "dry_run_only",
            "changed_files": [],
            "validation_plan": ["Inspect meta_agent_prompt.txt before enabling LLM call."],
        }
        summary = "# Change Summary\n\nDry run only. No LLM call was made.\n"
        patch = ""
        status = "success"
        operations.append({"name": "call_llm", "status": "skipped", "outputs": {"dry_run": True}})
    else:
        try:
            raw_text = call_meta_llm(prompt)
            proposal = extract_first_json(raw_text)
            if not proposal:
                proposal = {"candidate_id": candidate_dir.name, "parse_warning": "No valid JSON block found."}
            summary = extract_markdown_summary(raw_text)
            edits = proposal.get("edits") if isinstance(proposal, dict) else []
            if isinstance(edits, list):
                patch, edit_results = patch_from_structured_edits(edits, candidate_dir)
            else:
                patch, edit_results = "", [
                    {
                        "status": "rejected",
                        "reason": "`edits` must be a list.",
                    }
                ]
            if not patch:
                patch = extract_unified_diff(raw_text)
            status = "success" if patch else "partial"
            operations.append(
                {
                    "name": "call_llm_and_extract_candidate",
                    "status": status,
                    "outputs": {
                        "raw_output_path": str(raw_output_path),
                        "patch_found": bool(patch),
                        "structured_edit_count": len(edits) if isinstance(edits, list) else 0,
                        "structured_edit_results": edit_results,
                        "proposal_found": bool(proposal),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - report LLM/API errors as artifacts.
            raw_text = ""
            proposal = {
                "candidate_id": candidate_dir.name,
                "error": type(exc).__name__,
                "message": str(exc),
            }
            summary = f"# Change Summary\n\nMeta-agent call failed: `{type(exc).__name__}: {exc}`\n"
            patch = ""
            status = "failed"
            error = {"type": type(exc).__name__, "message": str(exc)}
            operations.append({"name": "call_llm", "status": "failed", "outputs": error})

    proposal.setdefault("candidate_id", candidate_dir.name)
    proposal.setdefault("changed_files", [])

    raw_output_path.write_text(raw_text, encoding="utf-8")
    proposal_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(summary, encoding="utf-8")
    patch_path.write_text(patch, encoding="utf-8")

    if patch and not dry_run:
        patch_check_result = git_apply_check(patch_path)
        operations.append(
            {
                "name": "git_apply_check_candidate_patch",
                "status": "completed" if patch_check_result["passed"] else "failed",
                "outputs": patch_check_result,
            }
        )

        for attempt in range(1, patch_repair_attempts + 1):
            if patch_check_result["passed"]:
                break
            try:
                repaired_patch, repair_record = repair_patch_with_meta_llm(
                    invalid_patch=patch,
                    check_result=patch_check_result,
                    response_schema=response_schema,
                    candidate_dir=candidate_dir,
                    attempt=attempt,
                    max_source_chars=max_source_chars,
                )
                repair_records.append(repair_record)
                if not repaired_patch:
                    repair_record["check_result"] = {
                        "passed": False,
                        "message": "Repair response did not contain a diff block.",
                    }
                    continue
                patch = repaired_patch
                patch_path.write_text(patch, encoding="utf-8")
                patch_check_result = git_apply_check(patch_path)
                repair_record["check_result"] = patch_check_result
            except Exception as exc:  # noqa: BLE001 - keep repair failures as artifacts.
                repair_record = {
                    "attempt": attempt,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
                repair_records.append(repair_record)
                break

        if patch_check_result and not patch_check_result["passed"] and patch_repair_attempts > 0:
            try:
                repaired_patch, replacement_record = repair_patch_by_replacement(
                    invalid_patch=patch,
                    check_result=patch_check_result,
                    response_schema=response_schema,
                    candidate_dir=candidate_dir,
                    max_source_chars=max_source_chars,
                )
                repair_records.append(replacement_record)
                if repaired_patch:
                    patch = repaired_patch
                    patch_path.write_text(patch, encoding="utf-8")
                    patch_check_result = git_apply_check(patch_path)
                    replacement_record["check_result"] = patch_check_result
                else:
                    replacement_record["check_result"] = {
                        "passed": False,
                        "message": "Replacement repair did not produce a non-empty patch.",
                    }
            except Exception as exc:  # noqa: BLE001 - keep repair failures as artifacts.
                repair_records.append(
                    {
                        "attempt": 1,
                        "strategy": "replacement_repair",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )

        if repair_records:
            operations.append(
                {
                    "name": "repair_invalid_patch",
                    "status": "completed" if patch_check_result and patch_check_result["passed"] else "failed",
                    "outputs": {
                        "attempts": repair_records,
                    },
                }
            )

    if patch_check_result:
        patch_check_path.write_text(
            json.dumps(
                {
                    "patch_path": str(patch_path),
                    "repair_attempts": repair_records,
                    "final_check": patch_check_result,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    if not dry_run and patch:
        status = "success" if patch_check_result and patch_check_result["passed"] else "partial"

    checks = [
        {
            "name": "task_md_exists",
            "passed": task_md.exists(),
            "message": str(task_md),
        },
        {
            "name": "context_manifest_exists",
            "passed": context_manifest.exists(),
            "message": str(context_manifest),
        },
        {
            "name": "patch_diff_written",
            "passed": patch_path.exists(),
            "message": str(patch_path),
        },
        {
            "name": "patch_diff_nonempty",
            "passed": bool(patch),
            "message": "Dry-run or failed LLM calls may intentionally leave patch.diff empty.",
        },
        {
            "name": "patch_git_apply_check",
            "passed": bool(patch_check_result and patch_check_result["passed"]),
            "message": (
                patch_check_result["message"]
                if patch_check_result
                else "Skipped for dry-run, missing patch, or failed LLM call."
            ),
        },
    ]

    report_path, _ = write_script_run_report(
        output_dir=candidate_dir,
        script_name="experiments/call_meta_agent.py",
        script_role="coding_meta_agent_interface",
        started_at=started_at,
        status=status,
        inputs=[
            path_ref("task_md", task_md),
            path_ref("context_manifest", context_manifest),
            path_ref("response_schema", response_schema),
            *refs_read,
        ],
        operations=operations,
        outputs=[
            path_ref("meta_agent_prompt", prompt_path),
            path_ref("raw_output", raw_output_path),
            path_ref("proposal", proposal_path),
            path_ref("change_summary", summary_path),
            path_ref("patch", patch_path),
            path_ref("patch_check", patch_check_path),
        ],
        checks=checks,
        self_feedback={
            "confidence": "high" if patch_check_result and patch_check_result["passed"] else "medium",
            "uncertainties": warnings
            + ([] if patch else ["No non-empty patch was produced."])
            + (
                []
                if (dry_run or not patch or (patch_check_result and patch_check_result["passed"]))
                else ["Patch was generated but did not pass git apply --check."]
            ),
            "evolution_hints": [
                "If prompts are too long for the local model, reduce context refs or max source chars.",
                "Apply patches only through experiments/apply_candidate_patch.py.",
            ],
            "suggested_target_modules": [
                "experiments/call_meta_agent.py",
                "prompts/dab/meta_agent/project_evolve_prompt.txt",
                "meta_agent/meta_agent_response_schema.md",
            ],
        },
        error=error,
        report_stem="call_meta_agent",
    )

    return {
        "candidate_dir": str(candidate_dir),
        "status": status,
        "dry_run": dry_run,
        "meta_agent_prompt_path": str(prompt_path),
        "raw_output_path": str(raw_output_path),
        "proposal_path": str(proposal_path),
        "change_summary_path": str(summary_path),
        "patch_path": str(patch_path),
        "patch_check_path": str(patch_check_path) if patch_check_result else None,
        "script_run_report_path": str(report_path),
        "patch_found": bool(patch),
        "patch_apply_check_passed": bool(patch_check_result and patch_check_result["passed"]),
        "patch_repair_attempts": repair_records,
        "warnings": warnings,
        "error": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-md", required=True)
    parser.add_argument("--context-manifest", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--response-schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--max-source-chars", type=int, default=12000)
    parser.add_argument("--max-total-source-chars", type=int, default=60000)
    parser.add_argument("--patch-repair-attempts", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = call_meta_agent(
        task_md=Path(args.task_md).resolve(),
        context_manifest=Path(args.context_manifest).resolve(),
        candidate_dir=Path(args.candidate_dir).resolve(),
        response_schema=Path(args.response_schema).resolve(),
        max_source_chars=args.max_source_chars,
        max_total_source_chars=args.max_total_source_chars,
        patch_repair_attempts=args.patch_repair_attempts,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
