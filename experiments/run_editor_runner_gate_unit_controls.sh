#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
WORK_ROOT="$(mktemp -d /tmp/editor_runner_gate_controls.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
PATCH="$WORK_ROOT/patch.diff"
STATUS_FILE="$WORK_ROOT/git_status.txt"
NUMSTAT="$WORK_ROOT/patch_numstat.txt"
EMPTY_RESULT="$WORK_ROOT/empty_patch_result.json"
AFTER_FAILURE_MARKER="$WORK_ROOT/validation_continued_after_failure"

mkdir -p "$WORKSPACE"
cp "$ROOT/experiments/fixtures/editor_protocol_negative_control/sample.py" "$WORKSPACE/sample.py"
git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "Editor Gate Controls"
git -C "$WORKSPACE" config user.email editor-gates@localhost
git -C "$WORKSPACE" add sample.py
git -C "$WORKSPACE" commit --quiet -m init
git -C "$WORKSPACE" status --porcelain >"$STATUS_FILE"
git -C "$WORKSPACE" diff -- sample.py >"$PATCH"
git -C "$WORKSPACE" diff --numstat -- sample.py >"$NUMSTAT"

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" prevalidation \
  --patch "$PATCH" --git-status "$STATUS_FILE" --numstat "$NUMSTAT" \
  --max-changed-lines 80 --result "$EMPTY_RESULT" --allowed sample.py
EMPTY_GATE_EXIT=$?
set -e
EMPTY_STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$EMPTY_RESULT")"

set +e
(
  set -e
  true
  false
  touch "$AFTER_FAILURE_MARKER"
  echo SHOULD_NOT_RUN
)
FAIL_FAST_EXIT=$?
set -e

if [[ "$EMPTY_GATE_EXIT" -eq 51 && "$EMPTY_STATUS" == protocol_failed_empty_patch \
      && "$FAIL_FAST_EXIT" -ne 0 && ! -e "$AFTER_FAILURE_MARKER" ]]; then
  cp "$EMPTY_RESULT" "$ROOT/reports/protocol/editor_empty_patch_gate_result.json"
  printf '{"empty_patch_gate":"passed","validation_fail_fast":"passed"}\n'
  exit 0
fi

echo "gate controls failed: empty_exit=$EMPTY_GATE_EXIT empty_status=$EMPTY_STATUS fail_fast_exit=$FAIL_FAST_EXIT" >&2
exit 1
