#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 /tmp/candidate-work-root" >&2
  exit 2
fi

ROOT_DIR="/home/m0st1ma/research/text2sql"
WORK_ROOT="$1"
WORKSPACE="${WORK_ROOT}/workspace"
CODEX_HOME_DIR="${WORK_ROOT}/codex_home"
CANDIDATE_DIR="${ROOT_DIR}/candidates/dab/codex_qwen_patents_iter001_child"
FINAL_MESSAGE="${WORKSPACE}/.codex_phase3_final_message.md"

cleanup() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "${PROXY_PID}" 2>/dev/null || true
    wait "${PROXY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

test -d "${WORKSPACE}/.git"
export CODEX_HOME="${CODEX_HOME_DIR}"
export CODEX_QWEN_PROXY_TOKEN="local-qwen-proxy"
export PYTHONPATH="${ROOT_DIR}"

cd "${ROOT_DIR}"
source .venv/bin/activate
python tools/codex_qwen_bounded_proxy.py \
  --port 8787 \
  --max-upstream-rounds 5 \
  >"${CANDIDATE_DIR}/proxy_phase3.log" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:8787/health >/dev/null; then
    break
  fi
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

set +e
codex exec \
  --strict-config \
  --ephemeral \
  --sandbox workspace-write \
  --json \
  --output-last-message "${FINAL_MESSAGE}" \
  -C "${WORKSPACE}" \
  - <"${ROOT_DIR}/prompts/dab/meta_agent/codex_qwen_first_candidate_apply.txt" \
  >"${CANDIDATE_DIR}/codex_phase3_transcript.jsonl" \
  2>"${CANDIDATE_DIR}/codex_phase3_stderr.txt"
CODEX_EXIT_CODE=$?
set -e

if [[ -f "${FINAL_MESSAGE}" ]]; then
  cp "${FINAL_MESSAGE}" "${CANDIDATE_DIR}/change_summary.md"
  rm -f "${FINAL_MESSAGE}"
fi

rm -f "${WORKSPACE}/prompts/dab/meta_agent/codex_qwen_first_candidate_edit.txt"
git -C "${WORKSPACE}" status --porcelain >"${CANDIDATE_DIR}/git_status.txt"
git -C "${WORKSPACE}" add -N .
git -C "${WORKSPACE}" diff --binary -- . >"${CANDIDATE_DIR}/patch.diff"

python - "${CANDIDATE_DIR}" "${CODEX_EXIT_CODE}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

candidate_dir = Path(sys.argv[1])
manifest_path = candidate_dir / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
status_lines = (candidate_dir / "git_status.txt").read_text(encoding="utf-8").splitlines()
changed_files = [line[3:].split(" -> ")[-1] for line in status_lines if len(line) >= 4]
patch_nonempty = bool((candidate_dir / "patch.diff").read_text(encoding="utf-8").strip())
exit_code = int(sys.argv[2])
manifest.update(
    {
        "phase3_completed_at": datetime.now(timezone.utc).isoformat(),
        "phase3_codex_exit_code": exit_code,
        "phase3_hard_upstream_round_limit": 5,
        "changed_files": changed_files,
        "patch_nonempty": patch_nonempty,
        "status": "candidate_generated" if exit_code == 0 and patch_nonempty else "candidate_failed",
    }
)
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False))
PY

if [[ "${CODEX_EXIT_CODE}" -ne 0 ]] || [[ ! -s "${CANDIDATE_DIR}/patch.diff" ]]; then
  exit 1
fi
