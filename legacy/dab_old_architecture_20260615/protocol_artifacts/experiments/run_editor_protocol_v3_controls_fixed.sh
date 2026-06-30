#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
REPORT_DIR="$ROOT/reports/protocol"
mkdir -p "$REPORT_DIR"

NEG_ROOT="$(mktemp -d /tmp/editor_protocol_v3_negative.XXXXXX)"
NEG_WS="$NEG_ROOT/workspace"
NEG_TRANSCRIPT="$NEG_ROOT/transcript.jsonl"
NEG_RESULT="$NEG_ROOT/manifest.json"
mkdir -p "$NEG_WS"
printf 'VALUE = 1\n' >"$NEG_WS/sample.py"
git -C "$NEG_WS" init --quiet
git -C "$NEG_WS" config user.name "Editor Protocol V3 Negative"
git -C "$NEG_WS" config user.email editor-v3-negative@localhost
git -C "$NEG_WS" add sample.py
git -C "$NEG_WS" commit --quiet -m init

(
  sleep 0.1
  printf '%s\n' '{"type":"item.completed","item":{"id":"v3_neg_1","type":"command_execution","command":"sed -n '\''1,20p'\'' sample.py","aggregated_output":"VALUE = 1\n","exit_code":0,"status":"completed"}}' >"$NEG_TRANSCRIPT"
  sleep 30
) &
NEG_EDITOR_PID=$!

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" first-action \
  --pid "$NEG_EDITOR_PID" --transcript "$NEG_TRANSCRIPT" --workspace "$NEG_WS" \
  --result "$NEG_RESULT" --allowed sample.py
NEG_GATE_EXIT=$?
wait "$NEG_EDITOR_PID" 2>/dev/null
NEG_EDITOR_EXIT=$?
set -e

NEG_STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$NEG_RESULT")"
if [[ "$NEG_GATE_EXIT" -ne 41 || "$NEG_STATUS" != protocol_failed_first_action_no_diff || "$NEG_EDITOR_EXIT" -eq 0 ]]; then
  echo "v3 negative control failed: gate=$NEG_GATE_EXIT editor=$NEG_EDITOR_EXIT status=$NEG_STATUS" >&2
  exit 1
fi

POS_ROOT="$(mktemp -d /tmp/editor_protocol_v3_positive.XXXXXX)"
POS_WS="$POS_ROOT/workspace"
POS_TRANSCRIPT="$POS_ROOT/transcript.jsonl"
POS_RESULT="$POS_ROOT/manifest.json"
mkdir -p "$POS_WS"
printf 'VALUE = 1\n' >"$POS_WS/sample.py"
git -C "$POS_WS" init --quiet
git -C "$POS_WS" config user.name "Editor Protocol V3 Positive"
git -C "$POS_WS" config user.email editor-v3-positive@localhost
git -C "$POS_WS" add sample.py
git -C "$POS_WS" commit --quiet -m init

(
  sleep 0.1
  "$ROOT/.venv/bin/python" - <<PY
from pathlib import Path
path = Path("$POS_WS/sample.py")
text = path.read_text(encoding="utf-8")
if text != "VALUE = 1\n":
    raise SystemExit("unexpected fixture content")
path.write_text("VALUE = 2\n", encoding="utf-8")
PY
  printf '%s\n' '{"type":"item.completed","item":{"id":"v3_pos_1","type":"command_execution","command":"python inline edit sample.py; git diff -- sample.py","aggregated_output":"diff present","exit_code":0,"status":"completed"}}' >"$POS_TRANSCRIPT"
  sleep 0.5
) &
POS_EDITOR_PID=$!

set +e
"$ROOT/.venv/bin/python" "$ROOT/experiments/editor_protocol_gate_v2.py" first-action \
  --pid "$POS_EDITOR_PID" --transcript "$POS_TRANSCRIPT" --workspace "$POS_WS" \
  --result "$POS_RESULT" --allowed sample.py
POS_GATE_EXIT=$?
wait "$POS_EDITOR_PID" 2>/dev/null
POS_EDITOR_EXIT=$?
set -e

POS_STATUS="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$POS_RESULT")"
POS_CONTENT="$(cat "$POS_WS/sample.py")"
if [[ "$POS_GATE_EXIT" -ne 0 || "$POS_STATUS" != first_action_gate_passed || "$POS_CONTENT" != "VALUE = 2" ]]; then
  echo "v3 positive control failed: gate=$POS_GATE_EXIT editor=$POS_EDITOR_EXIT status=$POS_STATUS content=$POS_CONTENT" >&2
  exit 1
fi

"$ROOT/.venv/bin/python" - "$NEG_RESULT" "$POS_RESULT" "$REPORT_DIR/editor_protocol_v3_controls_result.json" <<'PY'
import json
import sys
from pathlib import Path

neg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
pos = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
out = {
    "v3_negative_control_status": "passed",
    "v3_positive_control_status": "passed",
    "negative_gate": neg,
    "positive_gate": pos,
}
Path(sys.argv[3]).write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
PY

