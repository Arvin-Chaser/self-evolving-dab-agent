#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
ID=codex_qwen_patents_iter003_minimal_feedback_fix
OUT="$ROOT/candidates/dab/$ID"
WORK_ROOT="$(mktemp -d /tmp/${ID}.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
CODEX_HOME_DIR="$WORK_ROOT/codex_home"
TRANSCRIPT="$OUT/codex_transcript.jsonl"
RUN_SOURCE="$ROOT/logs/dab_agent/run_demo_full_loop_20260619_200238_parent_query_PATENTS_query1_20260619_200238"
RUN_COPY="$WORK_ROOT/validation_run"

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
git -C "$WORKSPACE" commit --quiet -m "Clean parent baseline for iter003"
cp "$ROOT/configs/codex_qwen_proxy.toml" "$CODEX_HOME_DIR/config.toml"

export CODEX_HOME="$CODEX_HOME_DIR"
export CODEX_QWEN_PROXY_TOKEN=local-qwen-proxy
export PYTHONPATH="$ROOT"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
export http_proxy=http://172.17.240.1:17891
export https_proxy="$http_proxy" HTTP_PROXY="$http_proxy" HTTPS_PROXY="$http_proxy"
export all_proxy="$http_proxy" ALL_PROXY="$http_proxy"
export no_proxy=localhost,127.0.0.1,::1 NO_PROXY=localhost,127.0.0.1,::1

cd "$ROOT"
source .venv/bin/activate
python tools/codex_qwen_bounded_proxy.py --port 8787 --max-upstream-rounds 6 \
  >"$OUT/proxy.log" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  curl --silent --fail http://127.0.0.1:8787/health >/dev/null && break
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

set +e
codex exec --strict-config --ephemeral --sandbox workspace-write --json \
  --output-last-message "$OUT/change_summary.md" -C "$WORKSPACE" \
  - <"$ROOT/prompts/dab/meta_agent/codex_qwen_patents_iter003_minimal_feedback_fix.txt" \
  >"$TRANSCRIPT" 2>"$OUT/codex_stderr.txt" &
CODEX_PID=$!
set -e

FIRST_TOOL_SEEN=0
FIRST_TOOL_DIFF_NONEMPTY=0
while kill -0 "$CODEX_PID" 2>/dev/null; do
  if grep -qE '"type":"item.completed".*"type":"(command_execution|file_change)"' "$TRANSCRIPT" 2>/dev/null; then
    FIRST_TOOL_SEEN=1
    if git -C "$WORKSPACE" diff --quiet -- \
      adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py; then
      kill "$CODEX_PID" 2>/dev/null || true
    else
      FIRST_TOOL_DIFF_NONEMPTY=1
    fi
    break
  fi
  sleep 0.05
done

set +e
wait "$CODEX_PID"
CODEX_EXIT=$?
set -e
CODEX_PID=""

git -C "$WORKSPACE" status --porcelain >"$OUT/git_status.txt"
git -C "$WORKSPACE" diff --binary -- \
  adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py \
  >"$OUT/patch.diff"
git -C "$WORKSPACE" diff --numstat -- \
  adapters/feedback/dab_patents_checks.py adapters/feedback/common_trace_checks.py \
  >"$OUT/patch_numstat.txt"

cp -a "$RUN_SOURCE" "$RUN_COPY"
set +e
cd "$WORKSPACE"
{
  "$ROOT/.venv/bin/python" -m py_compile \
    adapters/feedback/common_trace_checks.py adapters/feedback/dab_patents_checks.py
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
no_years = {"error": None, "trace": [{"stage": "answer_synthesis", "event": "year_extraction", "reason": "no_years_found"}]}
zero_patents = {"error": None, "trace": [{"event": "patent_aggregation_summary", "outputs": {"parsed_patents": 0}}]}
a = extract_patents_trace_errors(no_years)
b = extract_patents_trace_errors(zero_patents)
assert any(x.get("subtype") == "no_years_found" for x in a), a
assert any(x.get("subtype") == "patent_aggregation_zero_parsed_patents" for x in b), b
print("FOCUSED_BEHAVIOR_OK")
PY
  PYTHONPATH="$WORKSPACE" "$ROOT/.venv/bin/python" \
    experiments/analyze_agent_error.py --run-dir "$RUN_COPY"
  echo PATENTS_ANALYZER_OK
} >"$OUT/validation.log" 2>&1
VALIDATION_EXIT=$?
set -e

python - "$OUT" "$WORK_ROOT" "$CODEX_EXIT" "$VALIDATION_EXIT" \
  "$FIRST_TOOL_SEEN" "$FIRST_TOOL_DIFF_NONEMPTY" <<'PY'
import json, sys
from pathlib import Path

out = Path(sys.argv[1])
allowed = {
    "adapters/feedback/dab_patents_checks.py",
    "adapters/feedback/common_trace_checks.py",
}
status_lines = (out / "git_status.txt").read_text(encoding="utf-8").splitlines()
changed = [line[3:].split(" -> ")[-1] for line in status_lines if len(line) >= 4]
unexpected = [p for p in changed if p not in allowed]
numstat = []
for line in (out / "patch_numstat.txt").read_text(encoding="utf-8").splitlines():
    a, d, path = line.split("\t", 2)
    numstat.append({"path": path, "added": int(a), "deleted": int(d)})
total_changed = sum(x["added"] + x["deleted"] for x in numstat)
patch_nonempty = bool((out / "patch.diff").read_text(encoding="utf-8").strip())
transcript = (out / "codex_transcript.jsonl").read_text(encoding="utf-8")
text_patch_not_executed = not patch_nonempty and "apply_patch" in transcript
valid = all([
    int(sys.argv[3]) == 0,
    int(sys.argv[4]) == 0,
    int(sys.argv[5]) == 1,
    int(sys.argv[6]) == 1,
    patch_nonempty,
    not unexpected,
    0 < len(numstat) <= 2,
    total_changed <= 80,
    not text_patch_not_executed,
])
manifest = {
    "candidate_id": "codex_qwen_patents_iter003_minimal_feedback_fix",
    "status": "valid_candidate_pending_child_eval" if valid else "protocol_or_validation_failed",
    "workspace": sys.argv[2],
    "codex_exit_code": int(sys.argv[3]),
    "validation_exit_code": int(sys.argv[4]),
    "first_tool_seen": bool(int(sys.argv[5])),
    "first_tool_diff_nonempty": bool(int(sys.argv[6])),
    "project_changed_files": [x["path"] for x in numstat],
    "unexpected_changed_files": unexpected,
    "patch_numstat": numstat,
    "total_changed_lines": total_changed,
    "text_patch_not_executed": text_patch_not_executed,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest))
sys.exit(0 if valid else 1)
PY
