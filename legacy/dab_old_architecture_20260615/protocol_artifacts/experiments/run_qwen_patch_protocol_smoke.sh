#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
SMOKE=/tmp/qwen_patch_smoke
ARTIFACTS=/tmp/qwen_patch_smoke_artifacts
CODEX_HOME_DIR="$ARTIFACTS/codex_home"
TRANSCRIPT="$ARTIFACTS/codex_transcript.jsonl"
STDERR_LOG="$ARTIFACTS/codex_stderr.txt"
PROXY_LOG="$ARTIFACTS/proxy.log"
FINAL_MESSAGE="$ARTIFACTS/final_message.md"

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

if [[ -e "$SMOKE" || -e "$ARTIFACTS" ]]; then
  echo "Smoke paths already exist; refusing to overwrite: $SMOKE $ARTIFACTS" >&2
  exit 3
fi

mkdir -p "$SMOKE" "$CODEX_HOME_DIR"
cp "$ROOT/experiments/fixtures/qwen_patch_smoke/sample.py" "$SMOKE/sample.py"
git -C "$SMOKE" init --quiet
git -C "$SMOKE" config user.name "Qwen Patch Smoke"
git -C "$SMOKE" config user.email qwen-patch-smoke@localhost
git -C "$SMOKE" add sample.py
git -C "$SMOKE" commit --quiet -m init
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
python tools/codex_qwen_bounded_proxy.py --port 8787 --max-upstream-rounds 4 \
  >"$PROXY_LOG" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  curl --silent --fail http://127.0.0.1:8787/health >/dev/null && break
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

set +e
codex exec --strict-config --ephemeral --sandbox workspace-write --json \
  --output-last-message "$FINAL_MESSAGE" -C "$SMOKE" \
  - <"$ROOT/prompts/dab/meta_agent/qwen_patch_protocol_smoke.txt" \
  >"$TRANSCRIPT" 2>"$STDERR_LOG" &
CODEX_PID=$!
set -e

FIRST_TOOL_SEEN=0
FIRST_TOOL_DIFF_NONEMPTY=0
FIRST_TOOL_EVIDENCE=""
while kill -0 "$CODEX_PID" 2>/dev/null; do
  FIRST_TOOL_EVIDENCE="$(grep -m1 -E '"type":"item.completed".*"type":"(command_execution|file_change)"' "$TRANSCRIPT" 2>/dev/null || true)"
  if [[ -n "$FIRST_TOOL_EVIDENCE" ]]; then
    FIRST_TOOL_SEEN=1
    if git -C "$SMOKE" diff --quiet -- sample.py; then
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

git -C "$SMOKE" diff -- sample.py >"$ARTIFACTS/patch.diff"
cp "$SMOKE/sample.py" "$ARTIFACTS/sample.py.final"

PATCH_NONEMPTY=0
VALUE_CHANGED=0
REAL_TOOL_EVIDENCE=0
TEXT_PATCH_NOT_EXECUTED=0
[[ -s "$ARTIFACTS/patch.diff" ]] && PATCH_NONEMPTY=1
grep -qx 'VALUE = 2' "$SMOKE/sample.py" && VALUE_CHANGED=1
grep -qE '"type":"item.completed".*"type":"(command_execution|file_change)"' "$TRANSCRIPT" \
  && REAL_TOOL_EVIDENCE=1
if [[ "$PATCH_NONEMPTY" -eq 0 ]] && grep -qE 'apply_patch|\*\*\* Begin Patch|"name"[[:space:]]*:[[:space:]]*"apply_patch"' "$TRANSCRIPT"; then
  TEXT_PATCH_NOT_EXECUTED=1
fi

STATUS=protocol_smoke_failed
if [[ "$FIRST_TOOL_SEEN" -eq 1 && "$FIRST_TOOL_DIFF_NONEMPTY" -eq 1 \
      && "$PATCH_NONEMPTY" -eq 1 && "$VALUE_CHANGED" -eq 1 \
      && "$REAL_TOOL_EVIDENCE" -eq 1 && "$TEXT_PATCH_NOT_EXECUTED" -eq 0 ]]; then
  STATUS=protocol_smoke_passed
fi

python - "$ARTIFACTS/protocol_result.json" <<PY
import json
import sys
from pathlib import Path

result = {
    "protocol_smoke_status": "$STATUS",
    "codex_exit_code": $CODEX_EXIT,
    "first_tool_seen": bool($FIRST_TOOL_SEEN),
    "first_tool_diff_nonempty": bool($FIRST_TOOL_DIFF_NONEMPTY),
    "patch_nonempty": bool($PATCH_NONEMPTY),
    "sample_value_changed": bool($VALUE_CHANGED),
    "real_tool_evidence": bool($REAL_TOOL_EVIDENCE),
    "text_patch_not_executed": bool($TEXT_PATCH_NOT_EXECUTED),
    "first_tool_evidence": r'''$FIRST_TOOL_EVIDENCE''',
}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
PY

[[ "$STATUS" == protocol_smoke_passed ]]
