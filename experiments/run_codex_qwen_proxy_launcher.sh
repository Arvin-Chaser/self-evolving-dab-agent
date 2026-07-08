#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/m0st1ma/research/text2sql}"
cd "$ROOT"

MODE="${1:-exec}"
if [[ "$MODE" == "smoke" || "$MODE" == "exec" ]]; then
  shift || true
else
  MODE="exec"
fi

MODEL="${CODEX_QWEN_MODEL:-${META_AGENT_MODEL:-qwen-plus}}"
HOST="${CODEX_QWEN_PROXY_HOST:-127.0.0.1}"
PORT="${CODEX_QWEN_PROXY_PORT:-8787}"
TOKEN="${CODEX_QWEN_PROXY_TOKEN:-local-qwen-proxy}"
UPSTREAM_BASE_URL="${DASHSCOPE_BASE_URL:-https://ws-dn1a11fa08pmh39q.cn-beijing.maas.aliyuncs.com/compatible-mode/v1}"
TIMEOUT_SEC="${META_AGENT_TIMEOUT_SEC:-180}"
MAX_UPSTREAM_ROUNDS="${CODEX_QWEN_MAX_UPSTREAM_ROUNDS:-8}"
OUTPUT_ROOT="${CODEX_QWEN_PROXY_OUTPUT_ROOT:-$ROOT/logs/meta_agent/codex_qwen_proxy_runs}"
RUN_ID="${CODEX_QWEN_PROXY_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
mkdir -p "$RUN_DIR"

export http_proxy="${http_proxy:-http://172.17.240.1:17891}"
export https_proxy="${https_proxy:-http://172.17.240.1:17891}"
export HTTP_PROXY="${HTTP_PROXY:-$http_proxy}"
export HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}"
export all_proxy="${all_proxy:-http://172.17.240.1:17891}"
export ALL_PROXY="${ALL_PROXY:-$all_proxy}"
export no_proxy="${no_proxy:-localhost,127.0.0.1,::1}"
export NO_PROXY="${NO_PROXY:-$no_proxy}"

export DASHSCOPE_BASE_URL="$UPSTREAM_BASE_URL"
export META_AGENT_MODEL="$MODEL"
export CODEX_QWEN_MODEL="$MODEL"
export CODEX_QWEN_PROFILE="${CODEX_QWEN_PROFILE:-qwen-proxy}"
export CODEX_QWEN_PROXY_TOKEN="$TOKEN"
export META_AGENT_PATCH_SPEC_BACKEND="${META_AGENT_PATCH_SPEC_BACKEND:-codex_cli}"
export CODEX_QWEN_EXEC_TIMEOUT_SEC="${CODEX_QWEN_EXEC_TIMEOUT_SEC:-300}"

PROXY_LOG="$RUN_DIR/proxy.log"
MANIFEST="$RUN_DIR/launcher_manifest.json"

write_manifest() {
  local status="$1"
  local exit_code="$2"
  python3 - "$MANIFEST" <<PY
import json, os, sys
path=sys.argv[1]
manifest={
  "status": "$status",
  "mode": "$MODE",
  "exit_code": int("$exit_code"),
  "run_dir": "$RUN_DIR",
  "proxy_log": "$PROXY_LOG",
  "model": "$MODEL",
  "profile": os.environ.get("CODEX_QWEN_PROFILE"),
  "upstream_base_url": "$UPSTREAM_BASE_URL",
  "port": int("$PORT"),
  "meta_agent_patch_spec_backend": os.environ.get("META_AGENT_PATCH_SPEC_BACKEND"),
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

"$ROOT/.venv/bin/python" "$ROOT/tools/codex_qwen_bounded_proxy.py" \
  --host "$HOST" \
  --port "$PORT" \
  --model "$MODEL" \
  --upstream-base-url "$UPSTREAM_BASE_URL" \
  --timeout-sec "$TIMEOUT_SEC" \
  --max-upstream-rounds "$MAX_UPSTREAM_ROUNDS" \
  > "$PROXY_LOG" 2>&1 &
PROXY_PID=$!

cleanup() {
  kill "$PROXY_PID" >/dev/null 2>&1 || true
  wait "$PROXY_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 80); do
  if [[ -f "$PROXY_LOG" ]] && grep -q '"status": "listening"' "$PROXY_LOG"; then
    break
  fi
  if ! kill -0 "$PROXY_PID" >/dev/null 2>&1; then
    echo "proxy failed to start; see $PROXY_LOG" >&2
    write_manifest "proxy_start_failed" 2
    exit 2
  fi
  sleep 0.25
done

if [[ ! -f "$PROXY_LOG" ]] || ! grep -q '"status": "listening"' "$PROXY_LOG"; then
  echo "proxy did not become ready; see $PROXY_LOG" >&2
  write_manifest "proxy_start_timeout" 2
  exit 2
fi

if [[ "$MODE" == "smoke" ]]; then
  SMOKE_ROOT="$RUN_DIR/protocol_smoke"
  set +e
  "$ROOT/.venv/bin/python" "$ROOT/experiments/codex_qwen_protocol_smoke.py" \
    --profile "$CODEX_QWEN_PROFILE" \
    --model "$MODEL" \
    --output-root "$SMOKE_ROOT" \
    > "$RUN_DIR/smoke.stdout" 2> "$RUN_DIR/smoke.stderr"
  CODE=$?
  set -e
  if [[ "$CODE" -eq 0 ]]; then
    write_manifest "smoke_passed" 0
  else
    write_manifest "smoke_failed" "$CODE"
  fi
  echo "$RUN_DIR"
  exit "$CODE"
fi

if [[ "$#" -gt 0 ]]; then
  COMMAND=("$@")
elif [[ -n "${CODEX_QWEN_PROXY_EXEC_CMD:-}" ]]; then
  # shellcheck disable=SC2206
  COMMAND=(${CODEX_QWEN_PROXY_EXEC_CMD})
else
  COMMAND=("$ROOT/experiments/run_codex_qwen_repair_launcher.sh")
fi

# In direct_qwen mode the child process uses llm_client/OpenAI Chat
# Completions. Route only the child process to this already-started local
# proxy. The proxy process itself has already captured the real upstream
# DashScope key before these exports, so the local token does not replace the
# upstream API key.
if [[ "${META_AGENT_PATCH_SPEC_BACKEND:-}" == "direct_qwen" ]]; then
  export META_AGENT_BASE_URL="http://$HOST:$PORT/v1"
  export META_AGENT_API_KEY="$TOKEN"
  export META_AGENT_MODEL="$MODEL"
fi

set +e
"${COMMAND[@]}" > "$RUN_DIR/exec.stdout" 2> "$RUN_DIR/exec.stderr"
CODE=$?
set -e
if [[ "$CODE" -eq 0 ]]; then
  write_manifest "exec_passed" 0
else
  write_manifest "exec_failed" "$CODE"
fi

echo "$RUN_DIR"
exit "$CODE"