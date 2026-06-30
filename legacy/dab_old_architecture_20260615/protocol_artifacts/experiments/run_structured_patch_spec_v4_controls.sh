#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
HELPER="$ROOT/experiments/structured_patch_spec_v4.py"
REPORT_DIR="$ROOT/reports/protocol"
mkdir -p "$REPORT_DIR"
WORK_ROOT="$(mktemp -d /tmp/structured_patch_spec_v4_controls.XXXXXX)"

make_fixture() {
  local ws="$1"
  mkdir -p "$ws/adapters/feedback"
  cat >"$ws/adapters/feedback/dab_patents_checks.py" <<'PY'
from __future__ import annotations

import json
from typing import Any

from adapters.feedback.common_trace_checks import normalize_component


def extract_patents_trace_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    # Detect zero-parsed-patents signal from patent_aggregation_summary event
    for item in stage_trace_info.get("trace") or []:
        if item.get("event") == "patent_aggregation_summary":
            outputs = item.get("outputs") or {}
            parsed_patents = outputs.get("parsed_patents", 0)
            if parsed_patents == 0:
                errors.append({"subtype": "patent_aggregation_zero_parsed_patents"})
                break

    errors: list[dict[str, Any]] = []
    if stage_trace_info.get("error"):
        return errors

    from adapters.feedback.common_trace_checks import extract_zero_mapping_and_year_errors
    errors.extend(extract_zero_mapping_and_year_errors(stage_trace_info))
    return errors
PY
  cat >"$ws/adapters/feedback/common_trace_checks.py" <<'PY'
from __future__ import annotations

import json
from typing import Any


def normalize_component(value: Any, fallback: str = "unknown_component") -> str:
    return str(value or fallback)


def numeric_values(value: Any) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (int, float)) and not isinstance(child, bool):
                values.append((str(key), float(child)))
    return values


def extract_operation_event_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"subtype": "zero"}] if stage_trace_info.get("trace") else []


def extract_trace_based_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:
    return extract_operation_event_errors(stage_trace_info)


def extract_validation_errors(passed: bool, reason: str, strict_info: dict[str, Any]) -> list[dict[str, Any]]:
    return []
PY
  git -C "$ws" init --quiet
  git -C "$ws" config user.name "Structured Patch Spec V4 Control"
  git -C "$ws" config user.email structured-v4-control@localhost
  git -C "$ws" add .
  git -C "$ws" commit --quiet -m init
}

valid_spec() {
  local out="$1"
  cat >"$out" <<'JSON'
{
  "status": "patch_spec",
  "target_files": [
    "adapters/feedback/dab_patents_checks.py",
    "adapters/feedback/common_trace_checks.py"
  ],
  "edits": [
    {
      "file": "adapters/feedback/dab_patents_checks.py",
      "operation": "move_errors_init_to_function_top",
      "anchor": "def extract_patents_trace_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:",
      "intended_change": "Initialize errors before any append.",
      "rationale": "The first loop appends to errors before initialization."
    },
    {
      "file": "adapters/feedback/common_trace_checks.py",
      "operation": "add_extract_zero_mapping_and_year_errors",
      "anchor": "def extract_validation_errors(passed: bool, reason: str, strict_info: dict[str, Any]) -> list[dict[str, Any]]:",
      "intended_change": "Add the missing focused helper before validation checks.",
      "rationale": "PATENTS adapter imports this helper."
    }
  ],
  "risk_scope": "minimal/local/common_api_preserved",
  "public_functions_to_preserve": [
    "extract_trace_based_errors",
    "extract_operation_event_errors"
  ],
  "forbidden_actions_ack": {
    "no_common_module_rewrite": true,
    "no_delete_analyzer_dependencies": true,
    "no_broad_refactor": true
  }
}
JSON
}

run_validate_expect_fail() {
  local raw="$1"
  local dir="$2"
  set +e
  "$ROOT/.venv/bin/python" "$HELPER" validate-spec \
    --raw "$raw" --validated "$dir/validated.json" --result "$dir/result.json"
  local exit_code=$?
  set -e
  local status
  status="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$dir/result.json")"
  [[ "$exit_code" -ne 0 && "$status" == protocol_failed_invalid_patch_spec ]]
}

INVALID_JSON_DIR="$WORK_ROOT/invalid_json"
mkdir -p "$INVALID_JSON_DIR"
printf '{not json\n' >"$INVALID_JSON_DIR/raw.txt"
run_validate_expect_fail "$INVALID_JSON_DIR/raw.txt" "$INVALID_JSON_DIR"

INVALID_TARGET_DIR="$WORK_ROOT/invalid_target"
mkdir -p "$INVALID_TARGET_DIR"
cat >"$INVALID_TARGET_DIR/raw.json" <<'JSON'
{
  "status": "patch_spec",
  "target_files": ["README.md"],
  "edits": [
    {
      "file": "README.md",
      "operation": "replace_literal",
      "anchor": "x",
      "intended_change": "bad target",
      "rationale": "control"
    }
  ],
  "risk_scope": "minimal/local/common_api_preserved",
  "public_functions_to_preserve": ["extract_trace_based_errors", "extract_operation_event_errors"],
  "forbidden_actions_ack": {
    "no_common_module_rewrite": true,
    "no_delete_analyzer_dependencies": true,
    "no_broad_refactor": true
  }
}
JSON
run_validate_expect_fail "$INVALID_TARGET_DIR/raw.json" "$INVALID_TARGET_DIR"

VALID_DIR="$WORK_ROOT/valid_fixture"
VALID_WS="$VALID_DIR/workspace"
mkdir -p "$VALID_DIR" "$VALID_WS"
make_fixture "$VALID_WS"
valid_spec "$VALID_DIR/raw.json"
"$ROOT/.venv/bin/python" "$HELPER" validate-spec \
  --raw "$VALID_DIR/raw.json" --validated "$VALID_DIR/validated.json" --result "$VALID_DIR/validate_result.json"
"$ROOT/.venv/bin/python" "$HELPER" apply-spec \
  --workspace "$VALID_WS" --spec "$VALID_DIR/validated.json" --result "$VALID_DIR/apply_result.json"
git -C "$VALID_WS" status --porcelain >"$VALID_DIR/git_status.txt"
git -C "$VALID_WS" diff --binary -- adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py >"$VALID_DIR/patch.diff"
git -C "$VALID_WS" diff --numstat -- adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py >"$VALID_DIR/patch_numstat.txt"
"$ROOT/.venv/bin/python" "$HELPER" post-apply-gate \
  --workspace "$VALID_WS" --patch "$VALID_DIR/patch.diff" --git-status "$VALID_DIR/git_status.txt" \
  --numstat "$VALID_DIR/patch_numstat.txt" --max-changed-lines 80 --result "$VALID_DIR/gate_result.json"
VALID_GATE_STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$VALID_DIR/gate_result.json")"
[[ "$VALID_GATE_STATUS" == post_apply_gate_passed ]]

DELETE_DIR="$WORK_ROOT/public_delete"
DELETE_WS="$DELETE_DIR/workspace"
mkdir -p "$DELETE_DIR" "$DELETE_WS"
make_fixture "$DELETE_WS"
cat >"$DELETE_DIR/raw.json" <<'JSON'
{
  "status": "patch_spec",
  "target_files": ["adapters/feedback/common_trace_checks.py"],
  "edits": [
    {
      "file": "adapters/feedback/common_trace_checks.py",
      "operation": "delete_function_for_control",
      "anchor": "def extract_trace_based_errors(stage_trace_info: dict[str, Any]) -> list[dict[str, Any]]:",
      "intended_change": "Delete a public function for gate control.",
      "rationale": "This must be rejected by public API preservation gate."
    }
  ],
  "risk_scope": "minimal/local/common_api_preserved",
  "public_functions_to_preserve": ["extract_trace_based_errors", "extract_operation_event_errors"],
  "forbidden_actions_ack": {
    "no_common_module_rewrite": true,
    "no_delete_analyzer_dependencies": true,
    "no_broad_refactor": true
  }
}
JSON
"$ROOT/.venv/bin/python" "$HELPER" validate-spec \
  --raw "$DELETE_DIR/raw.json" --validated "$DELETE_DIR/validated.json" --result "$DELETE_DIR/validate_result.json"
"$ROOT/.venv/bin/python" "$HELPER" apply-spec \
  --workspace "$DELETE_WS" --spec "$DELETE_DIR/validated.json" --result "$DELETE_DIR/apply_result.json"
git -C "$DELETE_WS" status --porcelain >"$DELETE_DIR/git_status.txt"
git -C "$DELETE_WS" diff --binary -- adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py >"$DELETE_DIR/patch.diff"
git -C "$DELETE_WS" diff --numstat -- adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py >"$DELETE_DIR/patch_numstat.txt"
set +e
"$ROOT/.venv/bin/python" "$HELPER" post-apply-gate \
  --workspace "$DELETE_WS" --patch "$DELETE_DIR/patch.diff" --git-status "$DELETE_DIR/git_status.txt" \
  --numstat "$DELETE_DIR/patch_numstat.txt" --max-changed-lines 80 --result "$DELETE_DIR/gate_result.json"
DELETE_GATE_EXIT=$?
set -e
DELETE_GATE_STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$DELETE_DIR/gate_result.json")"
[[ "$DELETE_GATE_EXIT" -ne 0 && "$DELETE_GATE_STATUS" == rejected_large_rewrite ]]

"$ROOT/.venv/bin/python" - "$WORK_ROOT" "$REPORT_DIR/structured_patch_spec_v4_controls_result.json" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = {
    "v4_controls_status": "passed",
    "invalid_json_control": json.loads((root / "invalid_json/result.json").read_text()),
    "invalid_target_file_control": json.loads((root / "invalid_target/result.json").read_text()),
    "valid_fixture_patch_spec_control": {
        "validate": json.loads((root / "valid_fixture/validate_result.json").read_text()),
        "apply": json.loads((root / "valid_fixture/apply_result.json").read_text()),
        "gate": json.loads((root / "valid_fixture/gate_result.json").read_text()),
    },
    "public_function_deletion_control": {
        "validate": json.loads((root / "public_delete/validate_result.json").read_text()),
        "apply": json.loads((root / "public_delete/apply_result.json").read_text()),
        "gate": json.loads((root / "public_delete/gate_result.json").read_text()),
    },
}
Path(sys.argv[2]).write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
PY

