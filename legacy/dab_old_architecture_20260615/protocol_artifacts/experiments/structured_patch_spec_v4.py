#!/usr/bin/env python3
"""Structured patch-spec validator and deterministic executor for iter003 v4."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED = {
    "adapters/feedback/dab_patents_checks.py",
    "adapters/feedback/common_trace_checks.py",
}
REQUIRED_PUBLIC = {"extract_trace_based_errors", "extract_operation_event_errors"}
FINAL_STATUSES = {
    "valid_candidate_pending_child_eval",
    "no_op_failed",
    "protocol_failed_invalid_patch_spec",
    "patch_apply_failed",
    "rejected_large_rewrite",
    "failed_validation",
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def public_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def function_span(text: str, name: str) -> tuple[int, int] | None:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, getattr(node, "end_lineno", node.lineno)
    return None


def numbered_excerpt(text: str, start: int, end: int) -> str:
    lines = text.splitlines()
    return "\n".join(
        f"{idx:04d}: {lines[idx - 1]}"
        for idx in range(max(1, start), min(len(lines), end) + 1)
    )


def build_context(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    out = Path(args.output)
    dab_path = workspace / "adapters/feedback/dab_patents_checks.py"
    common_path = workspace / "adapters/feedback/common_trace_checks.py"
    dab = dab_path.read_text(encoding="utf-8")
    common = common_path.read_text(encoding="utf-8")

    common_funcs = sorted(public_functions(common_path))
    dab_funcs = sorted(public_functions(dab_path))
    patents_span = function_span(dab, "extract_patents_trace_errors")
    trace_span = function_span(common, "extract_trace_based_errors")
    operation_span = function_span(common, "extract_operation_event_errors")

    errors_lines = [
        f"{idx}: {line.strip()}"
        for idx, line in enumerate(dab.splitlines(), start=1)
        if "errors.append" in line
        or "errors:" in line
        or "extract_zero_mapping_and_year_errors" in line
    ]
    helper_refs = [
        f"{idx}: {line.strip()}"
        for idx, line in enumerate(dab.splitlines(), start=1)
        if "extract_zero_mapping_and_year_errors" in line
    ]
    helper_defs = [
        f"{idx}: {line.strip()}"
        for idx, line in enumerate(common.splitlines(), start=1)
        if "def extract_zero_mapping_and_year_errors" in line
    ]
    import_lines = [
        f"{idx}: {line}"
        for idx, line in enumerate(dab.splitlines(), start=1)
        if re.match(r"\s*(from|import)\s+", line)
    ]

    sections: list[str] = [
        "# Minimal source context pack for iter003_v4",
        "",
        "No PATENTS evidence package was read while constructing this pack.",
        "",
        "## Allowed files",
        "- adapters/feedback/dab_patents_checks.py",
        "- adapters/feedback/common_trace_checks.py",
        "",
        "## dab_patents_checks.py imports",
        "```text\n" + "\n".join(import_lines) + "\n```",
        "",
        "## dab_patents_checks.py public functions",
        "```text\n" + "\n".join(dab_funcs) + "\n```",
        "",
        "## extract_patents_trace_errors current body",
    ]
    if patents_span:
        sections.append("```python\n" + numbered_excerpt(dab, patents_span[0], patents_span[1]) + "\n```")
    sections.extend(
        [
            "",
            "## errors initialization / missing helper grep results",
            "```text\n" + "\n".join(errors_lines) + "\n```",
            "",
            "## missing extractor / import coherence grep",
            "```text",
            "dab_patents_checks.py references:",
            *(helper_refs or ["<none>"]),
            "common_trace_checks.py definitions:",
            *(helper_defs or ["<none>"]),
            "```",
            "",
            "## common_trace_checks.py public function list",
            "```text\n" + "\n".join(common_funcs) + "\n```",
            "",
            "## analyzer dependency checks",
            f"- extract_trace_based_errors exists: {'extract_trace_based_errors' in common_funcs}",
            f"- extract_operation_event_errors exists: {'extract_operation_event_errors' in common_funcs}",
            f"- extract_zero_mapping_and_year_errors exists: {'extract_zero_mapping_and_year_errors' in common_funcs}",
            "",
            "## common_trace_checks.py relevant public helper excerpts",
        ]
    )
    if operation_span:
        start, end = operation_span
        sections.append("### extract_operation_event_errors excerpt")
        sections.append("```python\n" + numbered_excerpt(common, start, min(end, start + 45)) + "\n```")
    if trace_span:
        start, end = trace_span
        sections.append("### extract_trace_based_errors excerpt")
        sections.append("```python\n" + numbered_excerpt(common, start, min(end, start + 35)) + "\n```")
    sections.extend(
        [
            "",
            "## Minimal patch-spec operations available to Qwen",
            "- move_errors_init_to_function_top",
            "- add_extract_zero_mapping_and_year_errors",
        ]
    )
    out.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return 0


def build_prompt(args: argparse.Namespace) -> int:
    template = Path(args.template).read_text(encoding="utf-8")
    context = Path(args.context).read_text(encoding="utf-8")
    Path(args.output).write_text(template.replace("<<<CONTEXT_PACK>>>", context), encoding="utf-8")
    return 0


def load_spec(raw_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    raw = raw_path.read_text(encoding="utf-8").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failed: {exc}"
    if not isinstance(parsed, dict):
        return None, "top-level JSON must be an object"
    return parsed, None


def invalid(result: Path, reason: str, **extra: Any) -> int:
    write_json(
        result,
        {
            "status": "protocol_failed_invalid_patch_spec",
            "reason": reason,
            "validation_allowed": False,
            **extra,
        },
    )
    return 61


def validate_spec(args: argparse.Namespace) -> int:
    raw_path = Path(args.raw)
    result = Path(args.result)
    validated = Path(args.validated)
    spec, err = load_spec(raw_path)
    if err:
        return invalid(result, err)

    assert spec is not None
    status = spec.get("status")
    if status == "no_op_failed":
        reason = str(spec.get("reason") or "").strip()
        if not reason:
            return invalid(result, "no_op_failed requires a non-empty reason")
        write_json(
            result,
            {"status": "no_op_failed", "reason": reason, "validation_allowed": False},
        )
        validated.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
        return 20
    if status != "patch_spec":
        return invalid(result, "status must be patch_spec or no_op_failed", observed_status=status)

    target_files = spec.get("target_files")
    if not isinstance(target_files, list) or not target_files:
        return invalid(result, "target_files must be a non-empty list")
    if any(path not in ALLOWED for path in target_files):
        return invalid(result, "target_files contains a non-whitelisted path", target_files=target_files)

    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        return invalid(result, "edits must be a non-empty list")
    for idx, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return invalid(result, f"edit {idx} must be an object")
        for key in ("file", "operation", "anchor", "intended_change", "rationale"):
            if not isinstance(edit.get(key), str) or not edit[key].strip():
                return invalid(result, f"edit {idx} missing non-empty {key}")
        if edit["file"] not in ALLOWED:
            return invalid(result, f"edit {idx} file is not whitelisted", file=edit["file"])
        if edit["file"] not in target_files:
            return invalid(result, f"edit {idx} file not declared in target_files", file=edit["file"])

    if spec.get("risk_scope") != "minimal/local/common_api_preserved":
        return invalid(result, "risk_scope must be minimal/local/common_api_preserved")
    preserve = spec.get("public_functions_to_preserve")
    if not isinstance(preserve, list) or not REQUIRED_PUBLIC.issubset(set(map(str, preserve))):
        return invalid(result, "public_functions_to_preserve must include analyzer dependencies")
    ack = spec.get("forbidden_actions_ack")
    if not isinstance(ack, dict):
        return invalid(result, "forbidden_actions_ack must be an object")
    required_ack = ("no_common_module_rewrite", "no_delete_analyzer_dependencies", "no_broad_refactor")
    if any(ack.get(key) is not True for key in required_ack):
        return invalid(result, "forbidden_actions_ack did not confirm all forbidden actions")

    validated.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    write_json(
        result,
        {
            "status": "patch_spec_valid",
            "target_files": target_files,
            "edit_count": len(edits),
            "validation_allowed": False,
        },
    )
    return 0


def move_errors_init_to_function_top(path: Path, anchor: str) -> None:
    text = path.read_text(encoding="utf-8")
    if anchor not in text:
        raise ValueError("anchor not found for move_errors_init_to_function_top")
    top_pattern = (
        anchor
        + "\n"
        + "    # Detect zero-parsed-patents signal from patent_aggregation_summary event\n"
    )
    if top_pattern not in text:
        raise ValueError("expected comment after extract_patents_trace_errors anchor not found")
    text = text.replace(
        top_pattern,
        anchor
        + "\n"
        + "    errors: list[dict[str, Any]] = []\n"
        + "    if stage_trace_info.get(\"error\"):\n"
        + "        return errors\n"
        + "\n"
        + "    # Detect zero-parsed-patents signal from patent_aggregation_summary event\n",
        1,
    )
    duplicate = (
        "\n"
        + "    errors: list[dict[str, Any]] = []\n"
        + "    if stage_trace_info.get(\"error\"):\n"
        + "        return errors\n"
    )
    if duplicate not in text:
        raise ValueError("later duplicate errors initialization block not found")
    text = text.replace(duplicate, "\n", 1)
    path.write_text(text, encoding="utf-8")


ZERO_MAPPING_HELPER = '''

def extract_zero_mapping_and_year_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract focused zero-output signals used by PATENTS feedback adapters."""
    errors: list[dict[str, Any]] = []
    if stage_trace_info.get("error"):
        return errors

    for item in stage_trace_info.get("trace") or []:
        event = str(item.get("event") or item.get("operation") or "").lower()
        reason = str(item.get("reason") or item.get("status") or item.get("summary") or "").lower()
        outputs = item.get("outputs") or {}
        joined = json.dumps(
            {
                "event": item.get("event"),
                "reason": item.get("reason"),
                "summary": item.get("summary"),
                "outputs": outputs,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).lower()

        if "no_years_found" in reason or "no_years_found" in joined:
            errors.append(
                {
                    "stage": "metadata_parser",
                    "type": "operation_zero_output_signal",
                    "subtype": "no_years_found",
                    "confidence": "high",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["metadata_parser", "year_extraction"],
                }
            )

        if ("mapping" in event or "year" in event or "extraction" in event) and any(
            value == 0 for _, value in numeric_values(outputs)
        ):
            errors.append(
                {
                    "stage": normalize_component(item.get("stage"), fallback="transformation_calculation"),
                    "type": "operation_zero_output_signal",
                    "subtype": "zero_mapping_or_year_extraction_output",
                    "confidence": "medium",
                    "evidence": json.dumps(item, ensure_ascii=False)[:1000],
                    "target_modules": ["metadata_parser", "granularity_mapping", "transformation_logic"],
                }
            )

    return errors
'''


def add_zero_mapping_helper(path: Path, anchor: str) -> None:
    text = path.read_text(encoding="utf-8")
    if "def extract_zero_mapping_and_year_errors" in text:
        return
    if anchor not in text:
        raise ValueError("anchor not found for add_extract_zero_mapping_and_year_errors")
    text = text.replace(anchor, ZERO_MAPPING_HELPER + "\n" + anchor, 1)
    path.write_text(text, encoding="utf-8")


def delete_function_for_control(path: Path, anchor: str) -> None:
    text = path.read_text(encoding="utf-8")
    name_match = re.match(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", anchor.strip())
    if not name_match:
        raise ValueError("control delete anchor must start with def")
    name = name_match.group(1)
    span = function_span(text, name)
    if not span:
        raise ValueError(f"function {name} not found for control deletion")
    lines = text.splitlines()
    start, end = span
    new_text = "\n".join(lines[: start - 1] + lines[end:]) + "\n"
    path.write_text(new_text, encoding="utf-8")


def apply_spec(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = Path(args.result)
    if spec.get("status") != "patch_spec":
        write_json(result, {"status": "patch_apply_failed", "reason": "spec status is not patch_spec"})
        return 71

    applied: list[dict[str, str]] = []
    try:
        for edit in spec["edits"]:
            rel = edit["file"]
            path = workspace / rel
            op = edit["operation"]
            if op == "move_errors_init_to_function_top":
                move_errors_init_to_function_top(path, edit["anchor"])
            elif op == "add_extract_zero_mapping_and_year_errors":
                add_zero_mapping_helper(path, edit["anchor"])
            elif op == "delete_function_for_control":
                delete_function_for_control(path, edit["anchor"])
            else:
                raise ValueError(f"unsupported deterministic operation: {op}")
            applied.append({"file": rel, "operation": op})
    except Exception as exc:
        write_json(
            result,
            {
                "status": "patch_apply_failed",
                "reason": str(exc),
                "applied_before_failure": applied,
                "validation_allowed": False,
            },
        )
        return 71

    write_json(result, {"status": "patch_apply_succeeded", "applied_edits": applied})
    return 0


def parse_git_status(path: Path) -> list[str]:
    changed: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if len(line) >= 4:
            changed.append(line[3:].split(" -> ")[-1])
    return changed


def post_apply_gate(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    result = Path(args.result)
    patch = Path(args.patch)
    status_path = Path(args.git_status)
    numstat_path = Path(args.numstat)
    patch_nonempty = patch.exists() and bool(patch.read_text(encoding="utf-8").strip())
    changed = parse_git_status(status_path)
    project_changed = [path for path in changed if path in ALLOWED]
    unexpected = [path for path in changed if path not in ALLOWED]

    total_changed = 0
    common_added = common_deleted = 0
    if numstat_path.exists():
        for line in numstat_path.read_text(encoding="utf-8").splitlines():
            added_s, deleted_s, path = line.split("\t", 2)
            added = int(added_s)
            deleted = int(deleted_s)
            total_changed += added + deleted
            if path == "adapters/feedback/common_trace_checks.py":
                common_added += added
                common_deleted += deleted

    details = {
        "patch_nonempty": patch_nonempty,
        "project_changed_files": project_changed,
        "unexpected_changed_files": unexpected,
        "total_changed_lines": total_changed,
        "validation_allowed": False,
    }
    if not patch_nonempty:
        write_json(result, {"status": "patch_apply_failed", "reason": "patch.diff is empty", **details})
        return 72
    if not project_changed:
        write_json(result, {"status": "patch_apply_failed", "reason": "project_changed_files is empty", **details})
        return 72
    if unexpected:
        write_json(result, {"status": "patch_apply_failed", "reason": "unexpected changed files", **details})
        return 72
    if total_changed > args.max_changed_lines:
        write_json(result, {"status": "rejected_large_rewrite", "reason": "diff too large", **details})
        return 73
    if common_deleted > 12 or common_added + common_deleted > args.max_changed_lines:
        write_json(result, {"status": "rejected_large_rewrite", "reason": "common trace checker diff too large", **details})
        return 73

    funcs = public_functions(workspace / "adapters/feedback/common_trace_checks.py")
    missing = sorted(REQUIRED_PUBLIC - funcs)
    if missing:
        write_json(
            result,
            {
                "status": "rejected_large_rewrite",
                "reason": "required public functions deleted",
                "missing_public_functions": missing,
                **details,
            },
        )
        return 73

    write_json(result, {"status": "post_apply_gate_passed", **{**details, "validation_allowed": True}})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    ctx = sub.add_parser("build-context")
    ctx.add_argument("--workspace", required=True)
    ctx.add_argument("--output", required=True)
    ctx.set_defaults(func=build_context)

    prompt = sub.add_parser("build-prompt")
    prompt.add_argument("--template", required=True)
    prompt.add_argument("--context", required=True)
    prompt.add_argument("--output", required=True)
    prompt.set_defaults(func=build_prompt)

    validate = sub.add_parser("validate-spec")
    validate.add_argument("--raw", required=True)
    validate.add_argument("--validated", required=True)
    validate.add_argument("--result", required=True)
    validate.set_defaults(func=validate_spec)

    apply = sub.add_parser("apply-spec")
    apply.add_argument("--workspace", required=True)
    apply.add_argument("--spec", required=True)
    apply.add_argument("--result", required=True)
    apply.set_defaults(func=apply_spec)

    gate = sub.add_parser("post-apply-gate")
    gate.add_argument("--workspace", required=True)
    gate.add_argument("--patch", required=True)
    gate.add_argument("--git-status", required=True)
    gate.add_argument("--numstat", required=True)
    gate.add_argument("--max-changed-lines", type=int, required=True)
    gate.add_argument("--result", required=True)
    gate.set_defaults(func=post_apply_gate)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

