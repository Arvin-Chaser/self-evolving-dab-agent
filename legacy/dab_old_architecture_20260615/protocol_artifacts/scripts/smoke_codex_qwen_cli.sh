#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d /tmp/codex-qwen-cli-smoke.XXXXXX)"
CODEX_HOME_DIR="$(mktemp -d /tmp/codex-qwen-home.XXXXXX)"
PROXY_LOG="${WORK_DIR}/proxy.log"
CODEX_LOG="${WORK_DIR}/codex.jsonl"

cleanup() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "${PROXY_PID}" 2>/dev/null || true
    wait "${PROXY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "${ROOT_DIR}"
source .venv/bin/activate
cp configs/codex_qwen_proxy.toml "${CODEX_HOME_DIR}/config.toml"
export CODEX_HOME="${CODEX_HOME_DIR}"
export CODEX_QWEN_PROXY_TOKEN="local-qwen-proxy"

python tools/codex_qwen_proxy.py --port 8787 >"${PROXY_LOG}" 2>&1 &
PROXY_PID=$!

for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:8787/health >/dev/null; then
    break
  fi
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

git -C "${WORK_DIR}" init --quiet
printf '%s\n' \
  'Use separate tool calls for every step. Create smoke.py that initially prints WRONG. Run it and observe the output. Edit smoke.py so it prints exactly TOOL_OK. Run it again and verify the output. Finish by replying exactly CODEX_QWEN_PROXY_OK.' \
  | codex exec \
      --strict-config \
      --ephemeral \
      --sandbox workspace-write \
      --json \
      -C "${WORK_DIR}" \
      - >"${CODEX_LOG}" 2>&1

ACTUAL_OUTPUT="$(python "${WORK_DIR}/smoke.py")"
if [[ "${ACTUAL_OUTPUT}" != "TOOL_OK" ]]; then
  echo "Unexpected smoke.py output: ${ACTUAL_OUTPUT}" >&2
  exit 1
fi
if ! grep -q 'CODEX_QWEN_PROXY_OK' "${CODEX_LOG}"; then
  echo "Codex did not emit the expected final marker." >&2
  exit 1
fi

printf '{"passed":true,"work_dir":"%s","codex_log":"%s","proxy_log":"%s"}\n' \
  "${WORK_DIR}" "${CODEX_LOG}" "${PROXY_LOG}"
