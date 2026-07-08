#!/usr/bin/env python3
"""Check whether a candidate patch connects to local project runtime contracts.

This is intentionally narrower than unit tests: it catches integration-shape
mismatches that pass py_compile but fail when the local runner tries to consume
new project files.  It is safe to run inside an isolated candidate workspace.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_changed_files(path: Path | None) -> list[str]:
    if not path or not path.exists():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(parts[2].strip())
        else:
            rows.append(parts[-1].strip())
    return [row for row in rows if row]


def result(name: str, status: str, *, severity: str = "error", details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "severity": severity, "details": details or {}}


def import_object(spec: str) -> Any:
    module_name, sep, object_name = spec.partition(":")
    if not sep or not module_name or not object_name:
        raise ValueError("function must use 'module.path:function_name' format")
    module = importlib.import_module(module_name)
    obj = module
    for part in object_name.split("."):
        obj = getattr(obj, part)
    return obj


def function_accepts_payload_inputs(func: Any) -> tuple[bool, str]:
    try:
        sig = inspect.signature(func)
    except Exception as exc:
        return False, f"signature unavailable: {type(exc).__name__}: {exc}"
    params = list(sig.parameters.values())
    positional = [
        param for param in params
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(param.kind == param.VAR_POSITIONAL for param in params)
    has_kwargs = any(param.kind == param.VAR_KEYWORD for param in params)
    if len(positional) >= 2 or has_varargs or has_kwargs:
        return True, str(sig)
    return False, f"helper function should accept at least (payload, inputs); got {sig}"


def check_dab_tool_agent_helper_registry(workspace: Path, changed_files: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    helper_changed = any(path.startswith("adapters/dab_tool_agent_helpers/") and path.endswith(".py") for path in changed_files)
    registry_path = workspace / "adapters/dab_tool_agent_helpers/registry.py"
    if not helper_changed and not registry_path.exists():
        return findings
    if not registry_path.exists():
        return [result("dab_tool_agent_helper_registry_exists", "failed", details={"path": str(registry_path)})]

    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
    try:
        if "adapters.dab_tool_agent_helpers.registry" in sys.modules:
            del sys.modules["adapters.dab_tool_agent_helpers.registry"]
        registry = importlib.import_module("adapters.dab_tool_agent_helpers.registry")
    except Exception as exc:
        return [
            result(
                "dab_tool_agent_helper_registry_import",
                "failed",
                details={"error_type": type(exc).__name__, "error": str(exc)},
            )
        ]

    helpers = getattr(registry, "HELPERS", None)
    if not isinstance(helpers, list):
        findings.append(result("dab_tool_agent_helper_registry_shape", "failed", details={"reason": "HELPERS must be a list"}))
        return findings

    required = {"name", "function", "description", "input_contract"}
    legacy_keys = {"helper_name", "module_path", "function_name"}
    for idx, helper in enumerate(helpers):
        if not isinstance(helper, dict):
            findings.append(result("dab_tool_agent_helper_entry_shape", "failed", details={"index": idx, "reason": "entry must be dict"}))
            continue
        missing = sorted(key for key in required if not str(helper.get(key) or "").strip())
        present_legacy = sorted(key for key in legacy_keys if key in helper)
        if missing:
            findings.append(
                result(
                    "dab_tool_agent_helper_entry_required_keys",
                    "failed",
                    details={
                        "index": idx,
                        "missing": missing,
                        "present_keys": sorted(helper.keys()),
                        "legacy_keys_present": present_legacy,
                        "expected_schema": {
                            "name": "helper_name_visible_to_tool",
                            "function": "module.path:function_name",
                            "description": "short tool-facing description",
                            "input_contract": "payload/input schema description",
                        },
                    },
                )
            )
            continue
        function_spec = str(helper.get("function"))
        try:
            func = import_object(function_spec)
        except Exception as exc:
            findings.append(
                result(
                    "dab_tool_agent_helper_function_import",
                    "failed",
                    details={"index": idx, "function": function_spec, "error_type": type(exc).__name__, "error": str(exc)},
                )
            )
            continue
        ok, reason = function_accepts_payload_inputs(func)
        if not ok:
            findings.append(
                result(
                    "dab_tool_agent_helper_function_signature",
                    "failed",
                    details={"index": idx, "function": function_spec, "reason": reason},
                )
            )
        else:
            findings.append(
                result(
                    "dab_tool_agent_helper_function_contract",
                    "passed",
                    severity="info",
                    details={"index": idx, "name": helper.get("name"), "function": function_spec, "signature": reason},
                )
            )
    if not helpers and helper_changed:
        findings.append(result("dab_tool_agent_helper_registry_nonempty", "failed", details={"reason": "helper files changed but HELPERS is empty"}))
    return findings


def check_mock_runtime_outputs(workspace: Path, changed_files: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    suspicious_patterns = [
        r"mock_[a-zA-Z0-9_]*_value",
        r"simulate query execution",
        r"in real use this would",
        r"return mock",
        r"dummy result",
    ]
    for rel in changed_files:
        if not rel.endswith(".py"):
            continue
        path = workspace / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = []
        for pattern in suspicious_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches.append(pattern)
        if matches:
            findings.append(
                result(
                    "mock_runtime_output_pattern",
                    "failed",
                    details={
                        "file": rel,
                        "patterns": matches,
                        "reason": "candidate helper appears to fabricate runtime data instead of connecting to local tool/input contracts",
                    },
                )
            )
    return findings


def run_checks(workspace: Path, changed_files: list[str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.extend(check_dab_tool_agent_helper_registry(workspace, changed_files))
    checks.extend(check_mock_runtime_outputs(workspace, changed_files))
    failed = [item for item in checks if item.get("status") == "failed" and item.get("severity") == "error"]
    return {
        "schema_version": "patch_local_contract_check_v001",
        "status": "failed" if failed else "passed",
        "changed_files": changed_files,
        "checks": checks,
        "failed_count": len(failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--changed-files-json", help="JSON list of changed files.")
    parser.add_argument("--patch-numstat", type=Path, help="Fallback git numstat file.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    changed_files: list[str] = []
    if args.changed_files_json:
        value = json.loads(args.changed_files_json)
        if not isinstance(value, list):
            raise SystemExit("--changed-files-json must be a JSON list")
        changed_files = [str(item) for item in value]
    if not changed_files:
        changed_files = read_changed_files(args.patch_numstat)
    report = run_checks(workspace, changed_files)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
