#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
WORK_ROOT="$(mktemp -d /tmp/editor_protocol_negative_control_v2.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
TRANSCRIPT="$WORK_ROOT/transcript.jsonl"
RESULT="$WORK_ROOT/manifest.json"
VALIDATION_MARKER="$WORK_ROOT/validation_started"

mkdir -p "$WORKSPACE"
cp "$ROOT/experiments/fixtures/editor_protocol_negative_control/sample.py" "$WORKSPACE/sample.py"
git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "Editor Protocol Negative Control"
git -C "$WORKSPACE" config user.email editor-negative-control@localhost
git -C "$WORKSPACE" add sample.py
git -C "$WORKSPACE" commit --quiet -m init

(
  sleep 0.1
  cp "$ROOT/experiments/fixtures/editor_protocol_negative_control/read_only_completed.jsonl" "$TRANSCRIPT"
  sleep 30
) &
FAKE_EDITOR_PID=$!

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" first-action \
  --pid "$FAKE_EDITOR_PID" --transcript "$TRANSCRIPT" --workspace "$WORKSPACE" \
  --result "$RESULT" --allowed sample.py
GATE_EXIT=$?
wait "$FAKE_EDITOR_PID" 2>/dev/null
EDITOR_EXIT=$?
set -e

STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$RESULT")"
if [[ "$GATE_EXIT" -eq 41 && "$STATUS" == protocol_failed_first_action_no_diff \
      && "$EDITOR_EXIT" -ne 0 && ! -e "$VALIDATION_MARKER" ]]; then
  cp "$RESULT" "$ROOT/reports/protocol/editor_negative_control_v2_result.json"
  printf '%s\n' "$WORK_ROOT" >"$ROOT/reports/protocol/editor_negative_control_v2_path.txt"
  cat "$RESULT"
  exit 0
fi

touch "$VALIDATION_MARKER"
echo "negative control failed: gate=$GATE_EXIT editor=$EDITOR_EXIT status=$STATUS" >&2
exit 1
