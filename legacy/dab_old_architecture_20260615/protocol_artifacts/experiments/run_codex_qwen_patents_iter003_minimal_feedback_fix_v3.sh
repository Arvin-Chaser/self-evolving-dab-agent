#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
ID="${ITER003_CANDIDATE_ID:-codex_qwen_patents_iter003_v3_minimal_feedback_fix_retry1}"
OUT="$ROOT/candidates/dab/$ID"
WORK_ROOT="$(mktemp -d /tmp/${ID}.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
CODEX_HOME_DIR="$WORK_ROOT/codex_home"
TRANSCRIPT="$OUT/codex_transcript.jsonl"
RUN_SOURCE="$ROOT/logs/dab_agent/run_demo_full_loop_20260619_200238_parent_query_PATENTS_query1_20260619_200238"
RUN_COPY="$WORK_ROOT/validation_run"
PROMPT_TEMPLATE="$ROOT/prompts/dab/meta_agent/codex_qwen_patents_iter003_minimal_feedback_fix_v3.txt"
CONTEXT_PACK="$OUT/minimal_source_context_pack.md"
EDITOR_PROMPT="$OUT/editor_prompt.txt"
ALLOWED=(adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py)

cleanup() {
  if [[ -n "${CODEX_PID:-}" ]] && kill -0 "$CODEX_PID" 2>/dev/null; then
    kill "$CODEX_PID" 2>/dev/null || true
    wait "$CODEX_PID" 2>/dev/null || true
  fi
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "$PROXY_PID" 2>/dev/null || true
    wait "$PROXY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[[ ! -e "$OUT" ]] || { echo "candidate exists: $OUT" >&2; exit 3; }
mkdir -p "$WORKSPACE" "$CODEX_HOME_DIR" "$OUT"
rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude=.codex \
  --exclude=__pycache__ --exclude=logs --exclude=candidates --exclude=reports \
  --exclude=trajectories "$ROOT/" "$WORKSPACE/"
git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "Codex Qwen Experiment"
git -C "$WORKSPACE" config user.email codex-qwen@localhost
git -C "$WORKSPACE" add .
git -C "$WORKSPACE" commit --quiet -m "Clean parent baseline for iter003 v3"
cp "$ROOT/configs/codex_qwen_proxy.toml" "$CODEX_HOME_DIR/config.toml"

"$ROOT/.venv/bin/python" - "$WORKSPACE" "$CONTEXT_PACK" <<'PY'
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
out = Path(sys.argv[2])
dab_path = workspace / "adapters/feedback/dab_patents_checks.py"
common_path = workspace / "adapters/feedback/common_trace_checks.py"
dab = dab_path.read_text(encoding="utf-8")
common = common_path.read_text(encoding="utf-8")


def numbered_excerpt(text: str, start: int, end: int) -> str:
    lines = text.splitlines()
    return "\n".join(
        f"{idx:04d}: {lines[idx - 1]}"
        for idx in range(max(1, start), min(len(lines), end) + 1)
    )


def function_span(text: str, name: str) -> tuple[int, int] | None:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, getattr(node, "end_lineno", node.lineno)
    return None


public_funcs = [
    node.name
    for node in ast.parse(common).body
    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
]
dab_funcs = [
    node.name
    for node in ast.parse(dab).body
    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
]
patents_span = function_span(dab, "extract_patents_trace_errors")
trace_span = function_span(common, "extract_trace_based_errors")
operation_span = function_span(common, "extract_operation_event_errors")

errors_append_lines = [
    f"{idx}: {line.strip()}"
    for idx, line in enumerate(dab.splitlines(), start=1)
    if "errors.append" in line or "errors:" in line or "extract_zero_mapping_and_year_errors" in line
]
missing_helper_refs = [
    f"{idx}: {line.strip()}"
    for idx, line in enumerate(dab.splitlines(), start=1)
    if "extract_zero_mapping_and_year_errors" in line
]
common_helper_defs = [
    f"{idx}: {line.strip()}"
    for idx, line in enumerate(common.splitlines(), start=1)
    if "def extract_zero_mapping_and_year_errors" in line
]
import_lines = [
    f"{idx}: {line}"
    for idx, line in enumerate(dab.splitlines(), start=1)
    if re.match(r"\s*(from|import)\s+", line)
]

sections: list[str] = []
sections.append("# Minimal source context pack for iter003_v3")
sections.append("")
sections.append("No PATENTS evidence package was read while constructing this pack.")
sections.append("")
sections.append("## Allowed files")
sections.append("- adapters/feedback/dab_patents_checks.py")
sections.append("- adapters/feedback/common_trace_checks.py")
sections.append("")
sections.append("## dab_patents_checks.py imports")
sections.append("```text\n" + "\n".join(import_lines) + "\n```")
sections.append("")
sections.append("## dab_patents_checks.py public functions")
sections.append("```text\n" + "\n".join(dab_funcs) + "\n```")
sections.append("")
sections.append("## extract_patents_trace_errors current body")
if patents_span:
    sections.append("```python\n" + numbered_excerpt(dab, patents_span[0], patents_span[1]) + "\n```")
sections.append("")
sections.append("## errors initialization / missing helper grep results")
sections.append("```text\n" + "\n".join(errors_append_lines) + "\n```")
sections.append("")
sections.append("## missing extractor / import coherence grep")
sections.append("```text")
sections.append("dab_patents_checks.py references:")
sections.extend(missing_helper_refs or ["<none>"])
sections.append("common_trace_checks.py definitions:")
sections.extend(common_helper_defs or ["<none>"])
sections.append("```")
sections.append("")
sections.append("## common_trace_checks.py public function list")
sections.append("```text\n" + "\n".join(public_funcs) + "\n```")
sections.append("")
sections.append("## analyzer dependency checks")
sections.append(f"- extract_trace_based_errors exists: {'extract_trace_based_errors' in public_funcs}")
sections.append(f"- extract_operation_event_errors exists: {'extract_operation_event_errors' in public_funcs}")
sections.append(f"- extract_zero_mapping_and_year_errors exists: {'extract_zero_mapping_and_year_errors' in public_funcs}")
sections.append("")
sections.append("## common_trace_checks.py relevant public helper excerpts")
if operation_span:
    start, end = operation_span
    sections.append("### extract_operation_event_errors excerpt")
    sections.append("```python\n" + numbered_excerpt(common, start, min(end, start + 45)) + "\n```")
if trace_span:
    start, end = trace_span
    sections.append("### extract_trace_based_errors excerpt")
    sections.append("```python\n" + numbered_excerpt(common, start, min(end, start + 35)) + "\n```")
sections.append("")
sections.append("## Minimal edit guidance derived from context")
sections.append("- Move/add `errors: list[dict[str, Any]] = []` to the top of `extract_patents_trace_errors`, before the `patent_aggregation_summary` loop.")
sections.append("- Remove the later duplicate initialization if present, so earlier appended errors are preserved.")
sections.append("- Add a small `extract_zero_mapping_and_year_errors(stage_trace_info)` helper in common_trace_checks.py, without touching existing helpers.")
sections.append("- The helper should detect `no_years_found` and generic zero mapping/year extraction count events, then return a list of error dictionaries.")
out.write_text("\n".join(sections) + "\n", encoding="utf-8")
PY

"$ROOT/.venv/bin/python" - "$PROMPT_TEMPLATE" "$CONTEXT_PACK" "$EDITOR_PROMPT" <<'PY'
import sys
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8")
context = Path(sys.argv[2]).read_text(encoding="utf-8")
Path(sys.argv[3]).write_text(template.replace("<<<CONTEXT_PACK>>>", context), encoding="utf-8")
PY

export CODEX_HOME="$CODEX_HOME_DIR" CODEX_QWEN_PROXY_TOKEN=local-qwen-proxy PYTHONPATH="$ROOT"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
export http_proxy=http://172.17.240.1:17891
export https_proxy="$http_proxy" HTTP_PROXY="$http_proxy" HTTPS_PROXY="$http_proxy"
export all_proxy="$http_proxy" ALL_PROXY="$http_proxy"
export no_proxy=localhost,127.0.0.1,::1 NO_PROXY=localhost,127.0.0.1,::1

cd "$ROOT"
source .venv/bin/activate
python tools/codex_qwen_bounded_proxy.py --port 8787 --max-upstream-rounds 6 >"$OUT/proxy.log" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  curl --silent --fail http://127.0.0.1:8787/health >/dev/null && break
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

codex exec --strict-config --ephemeral --sandbox workspace-write --json \
  --output-last-message "$OUT/change_summary.md" -C "$WORKSPACE" \
  - <"$EDITOR_PROMPT" >"$TRANSCRIPT" 2>"$OUT/codex_stderr.txt" &
CODEX_PID=$!

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" first-action \
  --pid "$CODEX_PID" --transcript "$TRANSCRIPT" --workspace "$WORKSPACE" \
  --result "$OUT/first_action_gate.json" --allowed "${ALLOWED[@]}"
FIRST_GATE_EXIT=$?
wait "$CODEX_PID"
CODEX_EXIT=$?
set -e
CODEX_PID=""

git -C "$WORKSPACE" status --porcelain >"$OUT/git_status.txt"
git -C "$WORKSPACE" diff --binary -- "${ALLOWED[@]}" >"$OUT/patch.diff"
git -C "$WORKSPACE" diff --numstat -- "${ALLOWED[@]}" >"$OUT/patch_numstat.txt"

if [[ "$FIRST_GATE_EXIT" -ne 0 ]]; then
  cp "$OUT/first_action_gate.json" "$OUT/manifest.json"
  exit "$FIRST_GATE_EXIT"
fi

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" prevalidation \
  --patch "$OUT/patch.diff" --git-status "$OUT/git_status.txt" \
  --numstat "$OUT/patch_numstat.txt" --max-changed-lines 80 \
  --result "$OUT/prevalidation_gate.json" --allowed "${ALLOWED[@]}"
PREVALIDATION_EXIT=$?
set -e
if [[ "$PREVALIDATION_EXIT" -ne 0 ]]; then
  cp "$OUT/prevalidation_gate.json" "$OUT/manifest.json"
  exit "$PREVALIDATION_EXIT"
fi

cp -a "$RUN_SOURCE" "$RUN_COPY"
set +e
(
  set -e
  cd "$WORKSPACE"
  "$ROOT/.venv/bin/python" -m py_compile "${ALLOWED[@]}"
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" - <<'PY'
import adapters.feedback.common_trace_checks as common
import adapters.feedback.dab_patents_checks as patents
assert callable(common.extract_operation_event_errors)
assert callable(common.extract_trace_based_errors)
assert callable(common.extract_zero_mapping_and_year_errors)
assert callable(patents.extract_patents_trace_errors)
print("IMPORT_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" - <<'PY'
from adapters.feedback.dab_patents_checks import extract_patents_trace_errors
no_years = {"error": None, "trace": [{"event": "year_extraction", "reason": "no_years_found"}]}
zero_patents = {"error": None, "trace": [{"event": "patent_aggregation_summary", "outputs": {"parsed_patents": 0}}]}
assert any(x.get("subtype") == "no_years_found" for x in extract_patents_trace_errors(no_years))
assert any(x.get("subtype") == "patent_aggregation_zero_parsed_patents" for x in extract_patents_trace_errors(zero_patents))
print("PATENTS_FOCUSED_BEHAVIOR_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" - <<'PY'
from adapters.feedback.common_trace_checks import extract_operation_event_errors
trace = {
    "error": None,
    "trace": [
        {
            "event": "operation_summary",
            "stage": "transformation_calculation",
            "operation": "mapping",
            "outputs": {"mapped_rows": 0},
        }
    ],
}
errors = extract_operation_event_errors(trace)
assert errors, errors
print("GENERIC_OPERATION_EVENT_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" experiments/analyze_agent_error.py --run-dir "$RUN_COPY"
  echo PATENTS_ANALYZER_OK
) >"$OUT/validation.log" 2>&1
VALIDATION_EXIT=$?
set -e

python - "$OUT" "$WORK_ROOT" "$CODEX_EXIT" "$VALIDATION_EXIT" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
numstat = []
for line in (out / "patch_numstat.txt").read_text(encoding="utf-8").splitlines():
    added, deleted, path = line.split("\t", 2)
    numstat.append({"path": path, "added": int(added), "deleted": int(deleted)})
total_changed = sum(row["added"] + row["deleted"] for row in numstat)
valid = int(sys.argv[3]) == 0 and int(sys.argv[4]) == 0
manifest = {
    "candidate_id": out.name,
    "status": "valid_candidate_pending_child_eval" if valid else "failed_validation",
    "workspace": sys.argv[2],
    "codex_exit_code": int(sys.argv[3]),
    "validation_exit_code": int(sys.argv[4]),
    "first_action_gate_status": "passed",
    "empty_patch_gate_status": "passed",
    "prevalidation_gate_status": "passed",
    "project_changed_files": [row["path"] for row in numstat],
    "patch_numstat": numstat,
    "total_changed_lines": total_changed,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest))
raise SystemExit(0 if valid else 1)
PY

