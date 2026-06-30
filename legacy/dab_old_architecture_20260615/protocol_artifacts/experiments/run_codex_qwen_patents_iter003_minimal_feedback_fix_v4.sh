#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
ID="${ITER003_CANDIDATE_ID:-codex_qwen_patents_iter003_v4_structured_patch_spec_retry1}"
OUT="$ROOT/candidates/dab/$ID"
WORK_ROOT="$(mktemp -d /tmp/${ID}.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
RUN_SOURCE="$ROOT/logs/dab_agent/run_demo_full_loop_20260619_200238_parent_query_PATENTS_query1_20260619_200238"
RUN_COPY="$WORK_ROOT/validation_run"
HELPER="$ROOT/experiments/structured_patch_spec_v4.py"
PROMPT_TEMPLATE="$ROOT/prompts/dab/meta_agent/codex_qwen_patents_iter003_minimal_feedback_fix_v4_structured_patch_spec.txt"
CONTEXT_PACK="$OUT/minimal_source_context_pack.md"
PATCH_SPEC_PROMPT="$OUT/patch_spec_prompt.txt"
PATCH_SPEC_RAW="$OUT/patch_spec_raw.txt"
PATCH_SPEC_VALIDATED="$OUT/patch_spec_validated.json"
ALLOWED=(adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py)

[[ ! -e "$OUT" ]] || { echo "candidate exists: $OUT" >&2; exit 3; }
mkdir -p "$WORKSPACE" "$OUT"
rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude=.codex \
  --exclude=__pycache__ --exclude=logs --exclude=candidates --exclude=reports \
  --exclude=trajectories "$ROOT/" "$WORKSPACE/"
git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "Codex Qwen Structured Patch Spec"
git -C "$WORKSPACE" config user.email codex-qwen-v4@localhost
git -C "$WORKSPACE" add .
git -C "$WORKSPACE" commit --quiet -m "Clean parent baseline for iter003 v4"

"$ROOT/.venv/bin/python" "$HELPER" build-context --workspace "$WORKSPACE" --output "$CONTEXT_PACK"
"$ROOT/.venv/bin/python" "$HELPER" build-prompt \
  --template "$PROMPT_TEMPLATE" --context "$CONTEXT_PACK" --output "$PATCH_SPEC_PROMPT"

export PYTHONPATH="$ROOT"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
export http_proxy=http://172.17.240.1:17891
export https_proxy="$http_proxy" HTTP_PROXY="$http_proxy" HTTPS_PROXY="$http_proxy"
export all_proxy="$http_proxy" ALL_PROXY="$http_proxy"
export no_proxy=localhost,127.0.0.1,::1 NO_PROXY=localhost,127.0.0.1,::1

cd "$ROOT"
source .venv/bin/activate
META_AGENT_MAX_TOKENS="${META_AGENT_MAX_TOKENS:-2048}" "$ROOT/.venv/bin/python" - "$PATCH_SPEC_PROMPT" "$PATCH_SPEC_RAW" >"$OUT/qwen_call.log" 2>&1 <<'PY'
import sys
from pathlib import Path
from llm_client import call_meta_llm, describe_llm_config

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
response = call_meta_llm(prompt)
Path(sys.argv[2]).write_text(response.strip() + "\n", encoding="utf-8")
print(describe_llm_config()["meta"])
PY

set +e
"$ROOT/.venv/bin/python" "$HELPER" validate-spec \
  --raw "$PATCH_SPEC_RAW" --validated "$PATCH_SPEC_VALIDATED" --result "$OUT/patch_spec_validation.json"
SPEC_EXIT=$?
set -e
if [[ "$SPEC_EXIT" -ne 0 ]]; then
  cp "$OUT/patch_spec_validation.json" "$OUT/manifest.json"
  exit "$SPEC_EXIT"
fi

set +e
"$ROOT/.venv/bin/python" "$HELPER" apply-spec \
  --workspace "$WORKSPACE" --spec "$PATCH_SPEC_VALIDATED" --result "$OUT/deterministic_apply.json"
APPLY_EXIT=$?
set -e
if [[ "$APPLY_EXIT" -ne 0 ]]; then
  cp "$OUT/deterministic_apply.json" "$OUT/manifest.json"
  exit "$APPLY_EXIT"
fi

git -C "$WORKSPACE" status --porcelain >"$OUT/git_status.txt"
git -C "$WORKSPACE" diff --binary -- "${ALLOWED[@]}" >"$OUT/patch.diff"
git -C "$WORKSPACE" diff --numstat -- "${ALLOWED[@]}" >"$OUT/patch_numstat.txt"

set +e
"$ROOT/.venv/bin/python" "$HELPER" post-apply-gate \
  --workspace "$WORKSPACE" --patch "$OUT/patch.diff" --git-status "$OUT/git_status.txt" \
  --numstat "$OUT/patch_numstat.txt" --max-changed-lines 80 --result "$OUT/post_apply_gate.json"
GATE_EXIT=$?
set -e
if [[ "$GATE_EXIT" -ne 0 ]]; then
  cp "$OUT/post_apply_gate.json" "$OUT/manifest.json"
  exit "$GATE_EXIT"
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
errors = extract_patents_trace_errors(no_years)
assert any(x.get("subtype") == "no_years_found" for x in errors), errors
print("NO_YEARS_FOUND_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" - <<'PY'
from adapters.feedback.dab_patents_checks import extract_patents_trace_errors
zero_patents = {"error": None, "trace": [{"event": "patent_aggregation_summary", "outputs": {"parsed_patents": 0}}]}
errors = extract_patents_trace_errors(zero_patents)
assert any(x.get("subtype") == "patent_aggregation_zero_parsed_patents" for x in errors), errors
print("PARSED_PATENTS_ZERO_OK")
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
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" - <<'PY'
import ast
from pathlib import Path
tree = ast.parse(Path("adapters/feedback/common_trace_checks.py").read_text(encoding="utf-8"))
funcs = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
required = {"extract_trace_based_errors", "extract_operation_event_errors"}
missing = required - funcs
assert not missing, missing
print("PUBLIC_FUNCTIONS_PRESERVED_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" experiments/analyze_agent_error.py --run-dir "$RUN_COPY"
  echo PATENTS_ANALYZER_OK
) >"$OUT/validation.log" 2>&1
VALIDATION_EXIT=$?
set -e

"$ROOT/.venv/bin/python" - "$OUT" "$WORK_ROOT" "$VALIDATION_EXIT" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
numstat = []
for line in (out / "patch_numstat.txt").read_text(encoding="utf-8").splitlines():
    added, deleted, path = line.split("\t", 2)
    numstat.append({"path": path, "added": int(added), "deleted": int(deleted)})
total_changed = sum(row["added"] + row["deleted"] for row in numstat)
valid = int(sys.argv[3]) == 0
manifest = {
    "candidate_id": out.name,
    "status": "valid_candidate_pending_child_eval" if valid else "failed_validation",
    "workspace": sys.argv[2],
    "validation_exit_code": int(sys.argv[3]),
    "patch_spec_status": json.loads((out / "patch_spec_validation.json").read_text())["status"],
    "deterministic_apply_status": json.loads((out / "deterministic_apply.json").read_text())["status"],
    "post_apply_gate_status": json.loads((out / "post_apply_gate.json").read_text())["status"],
    "project_changed_files": [row["path"] for row in numstat],
    "patch_numstat": numstat,
    "total_changed_lines": total_changed,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest))
raise SystemExit(0 if valid else 1)
PY

