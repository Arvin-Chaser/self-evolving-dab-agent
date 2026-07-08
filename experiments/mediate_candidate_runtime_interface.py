#!/usr/bin/env python3
"""Mediate candidate/runtime interface mismatches without changing task semantics.

This phase sits between deterministic candidate apply and child eval.  It may
ask an LLM to propose an interface-only adapter spec, but the runner applies
only a narrow deterministic operation set.  It is not allowed to repair SQL,
domain reasoning, answer selection, or helper algorithm content.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from llm_client import call_meta_llm
except Exception:  # pragma: no cover
    call_meta_llm = None  # type: ignore[assignment]


ALLOWED_SCOPE = "interface_only"
ALLOWED_OPERATIONS = {
    "normalize_dab_helper_registry_schema",
    "replace_text_once",
    "insert_after_anchor",
    "insert_before_anchor",
}
ALLOWED_PREFIXES = (
    "adapters/dab_tool_agent_helpers/",
)
NON_RECOVERABLE_CHECKS = {
    "mock_runtime_output_pattern",
}
INTERFACE_RECOVERABLE_CHECKS = {
    "dab_tool_agent_helper_entry_required_keys",
    "dab_tool_agent_helper_function_import",
    "dab_tool_agent_helper_function_signature",
    "dab_tool_agent_helper_registry_import",
}
SEMANTIC_RISK_MARKERS = (
    "select ",
    "from patents",
    "expected_count",
    "ground truth",
    "final_answer",
    "answer list",
    "hardcode",
    "mock_",
    "simulate query execution",
    "in real use this would",
    "return mock",
    "dummy result",
)


def read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if max_chars is None else text[:max_chars]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(stripped[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def read_changed_files(path: Path | None) -> list[str]:
    if not path or not path.exists():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            rows.append(parts[2].strip())
    return [row for row in rows if row]


def changed_files_from_args(args: argparse.Namespace) -> list[str]:
    if args.changed_files_json:
        value = json.loads(args.changed_files_json)
        if not isinstance(value, list):
            raise SystemExit("--changed-files-json must be a JSON list")
        return [str(item) for item in value]
    return read_changed_files(args.patch_numstat)


def failed_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    return [item for item in checks if isinstance(item, dict) and item.get("status") == "failed"]


def classify_recoverability(report: dict[str, Any]) -> tuple[bool, str]:
    failures = failed_checks(report)
    if not failures:
        return False, "no failed local contract checks to mediate"
    names = {str(item.get("name") or "") for item in failures}
    if names & NON_RECOVERABLE_CHECKS:
        return False, "non-interface semantic/mock failure is not recoverable by mediation"
    unknown = sorted(name for name in names if name not in INTERFACE_RECOVERABLE_CHECKS)
    if unknown:
        return False, f"unsupported local contract failure(s): {unknown}"
    return True, "interface-only mismatch appears recoverable"


def changed_source_excerpt(workspace: Path, rel: str) -> dict[str, str]:
    path = workspace / rel
    if not path.exists() or not rel.endswith(".py"):
        return {"file": rel, "excerpt": ""}
    return {"file": rel, "excerpt": read_text(path, 5000)}


def build_prompt(workspace: Path, candidate_dir: Path, report: dict[str, Any], changed_files: list[str]) -> str:
    excerpts = [changed_source_excerpt(workspace, rel) for rel in changed_files if rel.startswith(ALLOWED_PREFIXES)]
    registry_contract = read_text(ROOT / "adapters/dab_tool_agent_helpers/README.md", 4000) if (ROOT / "adapters/dab_tool_agent_helpers/README.md").exists() else ""
    patch_summary = read_text(candidate_dir / "patch_numstat.txt", 2000) if (candidate_dir / "patch_numstat.txt").exists() else ""
    return f"""You are an interface mediator for a self-evolving DataAgent candidate.

Your task is NOT to fix the benchmark answer, SQL, domain reasoning, ranking, or helper algorithm.
Your only task is to propose an interface-only mediation spec when a candidate patch has a local runtime contract mismatch.

Allowed mediation scope:
- normalize DAB helper registry schema;
- fix import path / module:function wiring;
- add thin call-signature compatibility only when helper logic remains unchanged.

Forbidden:
- do not change SQL/domain/answer logic;
- do not invent task outputs;
- do not remove or rewrite helper algorithm content;
- do not add mock/simulated runtime behavior;
- do not hardcode expected counts or answers.

If the failure is not interface-only, output:
{{"status":"no_op_failed","reason":"..."}}

Otherwise output strict JSON:
{{
  "status": "adapter_spec",
  "scope": "interface_only",
  "interface_problem": "short label",
  "target_files": ["..."],
  "semantic_change_ack": false,
  "content_preservation_claim": {{
    "helper_logic_unchanged": true,
    "sql_logic_unchanged": true,
    "answer_logic_unchanged": true
  }},
  "edits": [
    {{
      "file": "adapters/dab_tool_agent_helpers/registry.py",
      "operation": "normalize_dab_helper_registry_schema",
      "anchor": "HELPERS",
      "intended_change": "normalize legacy helper_name/module_path/function_name into name/function/description/input_contract",
      "rationale": "interface-only registry schema compatibility"
    }}
  ]
}}

Supported deterministic operations: {sorted(ALLOWED_OPERATIONS)}

DAB helper runtime contract:
```markdown
{registry_contract}
```

Local contract check report:
```json
{json.dumps(report, indent=2, ensure_ascii=False)}
```

Patch numstat:
```text
{patch_summary}
```

Changed source excerpts:
```json
{json.dumps(excerpts, indent=2, ensure_ascii=False)}
```
"""


def semantic_risk(text: str) -> str | None:
    low = text.lower()
    for marker in SEMANTIC_RISK_MARKERS:
        if marker in low:
            return marker
    return None


def validate_spec(spec: dict[str, Any] | None, changed_files: list[str]) -> tuple[bool, str]:
    if not isinstance(spec, dict):
        return False, "interface_mediation_spec JSON could not be parsed"
    status = spec.get("status")
    if status == "no_op_failed":
        return True, "no_op_failed"
    if status != "adapter_spec":
        return False, "status must be adapter_spec or no_op_failed"
    if spec.get("scope") != ALLOWED_SCOPE:
        return False, "scope must be interface_only"
    if spec.get("semantic_change_ack") is not False:
        return False, "semantic_change_ack must be false"
    claim = spec.get("content_preservation_claim")
    if not isinstance(claim, dict):
        return False, "content_preservation_claim is required"
    for key in ("helper_logic_unchanged", "sql_logic_unchanged", "answer_logic_unchanged"):
        if claim.get(key) is not True:
            return False, f"content_preservation_claim.{key} must be true"
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        return False, "edits must be non-empty"
    target_files = spec.get("target_files")
    if not isinstance(target_files, list) or not target_files:
        return False, "target_files must be non-empty"
    changed = set(changed_files)
    for rel in target_files:
        if not isinstance(rel, str) or not rel.startswith(ALLOWED_PREFIXES):
            return False, f"target file outside interface mediation scope: {rel}"
        if changed and rel not in changed:
            return False, f"target file was not part of candidate patch: {rel}"
    for idx, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return False, f"edits[{idx}] must be object"
        rel = str(edit.get("file") or "")
        op = str(edit.get("operation") or "")
        if op not in ALLOWED_OPERATIONS:
            return False, f"unsupported mediation operation: {op}"
        if not rel.startswith(ALLOWED_PREFIXES):
            return False, f"edit file outside interface mediation scope: {rel}"
        if changed and rel not in changed:
            return False, f"edit file was not part of candidate patch: {rel}"
        combined = "\n".join(str(edit.get(key) or "") for key in ("anchor", "intended_change", "rationale"))
        risk = semantic_risk(combined)
        if risk:
            return False, f"semantic-risk marker found in mediation edit: {risk}"
    return True, "ok"


def dict_literal_value(node: ast.AST) -> dict[str, Any] | None:
    if not isinstance(node, ast.Dict):
        return None
    out: dict[str, Any] = {}
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            return None
        try:
            out[key_node.value] = ast.literal_eval(value_node)
        except Exception:
            return None
    return out


def normalize_registry_schema(workspace: Path, rel: str) -> dict[str, Any]:
    path = workspace / rel
    if not path.exists():
        raise ValueError(f"registry file missing: {rel}")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    helpers_value: list[dict[str, Any]] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "HELPERS" in names and isinstance(node.value, ast.List):
                helpers_value = []
                for item in node.value.elts:
                    literal = dict_literal_value(item)
                    if literal is None:
                        raise ValueError("HELPERS entries must be simple dict literals for deterministic normalization")
                    helpers_value.append(literal)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "HELPERS" and isinstance(node.value, ast.List):
            helpers_value = []
            for item in node.value.elts:
                literal = dict_literal_value(item)
                if literal is None:
                    raise ValueError("HELPERS entries must be simple dict literals for deterministic normalization")
                helpers_value.append(literal)
    if helpers_value is None:
        raise ValueError("HELPERS assignment not found")
    normalized: list[dict[str, str]] = []
    changed = False
    for helper in helpers_value:
        name = str(helper.get("name") or helper.get("helper_name") or "").strip()
        function = str(helper.get("function") or "").strip()
        module_path = str(helper.get("module_path") or "").strip()
        function_name = str(helper.get("function_name") or "").strip()
        if not function and module_path and function_name:
            function = f"{module_path}:{function_name}"
            changed = True
        description = str(helper.get("description") or f"Evolved helper {name}.").strip()
        input_contract = str(helper.get("input_contract") or "payload dict and inputs dict").strip()
        if not name or not function:
            raise ValueError(f"cannot normalize helper without name/function: {helper}")
        new_helper = {
            "name": name,
            "function": function,
            "description": description,
            "input_contract": input_contract,
        }
        if set(helper.keys()) != set(new_helper.keys()) or any(str(helper.get(k) or "") != v for k, v in new_helper.items()):
            changed = True
        normalized.append(new_helper)
    rendered = "HELPERS = " + repr(normalized).replace("}, {", "},\n    {") + "\n"
    if "HELPERS" not in text:
        raise ValueError("HELPERS marker not found")
    new_text = re.sub(r"(?ms)^HELPERS\s*(?::[^=]+)?=\s*\[.*?\]\s*$", rendered, text, count=1)
    if new_text == text and changed:
        raise ValueError("failed to replace HELPERS assignment")
    path.write_text(new_text, encoding="utf-8")
    return {"operation": "normalize_dab_helper_registry_schema", "file": rel, "normalized_entries": len(normalized), "changed": changed}


def apply_text_edit(workspace: Path, edit: dict[str, Any]) -> dict[str, Any]:
    rel = str(edit.get("file") or "")
    path = workspace / rel
    if not path.exists():
        raise ValueError(f"target file missing: {rel}")
    text = path.read_text(encoding="utf-8")
    op = str(edit.get("operation") or "")
    anchor = str(edit.get("anchor") or "")
    change = str(edit.get("intended_change") or "")
    if not anchor or anchor not in text:
        raise ValueError(f"anchor not found in {rel}")
    if op == "replace_text_once":
        new_text = text.replace(anchor, change, 1)
    elif op == "insert_after_anchor":
        new_text = text.replace(anchor, anchor + change, 1)
    elif op == "insert_before_anchor":
        new_text = text.replace(anchor, change + anchor, 1)
    else:
        raise ValueError(f"unsupported text op: {op}")
    path.write_text(new_text, encoding="utf-8")
    return {"operation": op, "file": rel}


def apply_spec(spec: dict[str, Any], workspace: Path) -> tuple[bool, list[dict[str, Any]], str]:
    applied: list[dict[str, Any]] = []
    if spec.get("status") == "no_op_failed":
        return False, applied, str(spec.get("reason") or "no-op")
    try:
        for edit in spec.get("edits") or []:
            op = str(edit.get("operation") or "")
            if op == "normalize_dab_helper_registry_schema":
                applied.append(normalize_registry_schema(workspace, str(edit.get("file") or "")))
            else:
                applied.append(apply_text_edit(workspace, edit))
    except Exception as exc:
        return False, applied, f"{type(exc).__name__}: {exc}"
    return True, applied, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--contract-report", type=Path)
    parser.add_argument("--patch-numstat", type=Path)
    parser.add_argument("--changed-files-json")
    parser.add_argument("--spec-file", type=Path, help="Use an existing mediation spec instead of calling LLM.")
    parser.add_argument("--call-llm", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    candidate_dir = args.candidate_dir.resolve()
    report = load_json(args.contract_report)
    changed_files = changed_files_from_args(args)
    recoverable, recover_reason = classify_recoverability(report)

    prompt = build_prompt(workspace, candidate_dir, report, changed_files)
    (candidate_dir / "interface_mediation_prompt.md").write_text(prompt, encoding="utf-8")

    spec: dict[str, Any] | None = None
    raw = ""
    if args.spec_file:
        raw = args.spec_file.read_text(encoding="utf-8")
        spec = extract_json_object(raw)
    elif recoverable and args.call_llm:
        if call_meta_llm is None:
            raw = ""
            spec = {"status": "no_op_failed", "reason": "call_meta_llm unavailable"}
        else:
            raw = call_meta_llm(prompt)
            spec = extract_json_object(raw)
    else:
        spec = {"status": "no_op_failed", "reason": recover_reason if not recoverable else "LLM call disabled"}
        raw = json.dumps(spec, ensure_ascii=False)

    (candidate_dir / "interface_mediation_raw.txt").write_text(raw or "", encoding="utf-8")
    if spec is not None:
        write_json(candidate_dir / "interface_mediation_spec.json", spec)

    valid, valid_reason = validate_spec(spec, changed_files)
    applied_ok = False
    applied: list[dict[str, Any]] = []
    apply_reason = "not_applied"
    if valid and spec and spec.get("status") == "adapter_spec":
        applied_ok, applied, apply_reason = apply_spec(spec, workspace)
    elif valid and spec and spec.get("status") == "no_op_failed":
        apply_reason = str(spec.get("reason") or "no-op")

    status = "mediation_applied" if applied_ok else ("mediation_no_op" if valid and spec and spec.get("status") == "no_op_failed" else "mediation_failed")
    payload = {
        "schema_version": "interface_mediation_report_v001",
        "status": status,
        "recoverable": recoverable,
        "recoverability_reason": recover_reason,
        "spec_valid": valid,
        "spec_validation_reason": valid_reason,
        "applied": applied,
        "apply_reason": apply_reason,
        "changed_files": changed_files,
        "contract_report": str(args.contract_report) if args.contract_report else None,
        "semantic_patch_changed": False,
    }
    out = args.output or candidate_dir / "interface_mediation_report.json"
    write_json(out, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if applied_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
