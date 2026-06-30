#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/m0st1ma/research/text2sql"
CANDIDATE_ID="codex_qwen_patents_iter001_child"
CANDIDATE_DIR="${ROOT_DIR}/candidates/dab/${CANDIDATE_ID}"
TASK_PATH="${ROOT_DIR}/logs/meta_agent/demo_full_loop_20260619_200238/demo_full_loop_20260619_200238_iter001_meta/tasks/task_20260619_200503/task.md"
PARENT_RUN="${ROOT_DIR}/logs/dab_agent/run_demo_full_loop_20260619_200238_parent_query_PATENTS_query1_20260619_200238"
FILTERED_CONTEXT="${ROOT_DIR}/logs/meta_agent/demo_full_loop_20260619_200238/iter_001/filtered_meta_agent_context.json"
WORK_ROOT="$(mktemp -d /tmp/${CANDIDATE_ID}.XXXXXX)"
WORKSPACE="${WORK_ROOT}/workspace"
CODEX_HOME_DIR="${WORK_ROOT}/codex_home"
FINAL_MESSAGE="${WORKSPACE}/.codex_final_message.md"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cleanup() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "${PROXY_PID}" 2>/dev/null || true
    wait "${PROXY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ -e "${CANDIDATE_DIR}" ]]; then
  echo "Candidate already exists: ${CANDIDATE_DIR}" >&2
  exit 1
fi

mkdir -p "${WORKSPACE}" "${CODEX_HOME_DIR}" "${CANDIDATE_DIR}"
rsync -a \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='.codex' \
  --exclude='__pycache__' \
  --exclude='logs' \
  --exclude='candidates' \
  --exclude='reports' \
  --exclude='trajectories' \
  "${ROOT_DIR}/" "${WORKSPACE}/"

mkdir -p "${WORKSPACE}/evidence/parent_run"
cp "${TASK_PATH}" "${WORKSPACE}/evidence/PATENTS_META_AGENT_TASK.md"
cp "${FILTERED_CONTEXT}" "${WORKSPACE}/evidence/filtered_meta_agent_context.json"
for name in result.json summary.json generated_solve.py execution_stdout.txt execution_stderr.txt stage_trace.json; do
  cp "${PARENT_RUN}/${name}" "${WORKSPACE}/evidence/parent_run/${name}"
done

git -C "${WORKSPACE}" init --quiet
git -C "${WORKSPACE}" config user.name "Codex Qwen Experiment"
git -C "${WORKSPACE}" config user.email "codex-qwen@localhost"
git -C "${WORKSPACE}" add .
git -C "${WORKSPACE}" commit --quiet -m "Isolated candidate baseline"

cp "${ROOT_DIR}/configs/codex_qwen_proxy.toml" "${CODEX_HOME_DIR}/config.toml"
export CODEX_HOME="${CODEX_HOME_DIR}"
export CODEX_QWEN_PROXY_TOKEN="local-qwen-proxy"

cd "${ROOT_DIR}"
source .venv/bin/activate
python tools/codex_qwen_bounded_proxy.py \
  --port 8787 \
  --max-upstream-rounds 12 \
  >"${CANDIDATE_DIR}/proxy.log" 2>&1 &
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
  - <"${WORKSPACE}/prompts/dab/meta_agent/codex_qwen_first_candidate.txt" \
  >"${CANDIDATE_DIR}/codex_transcript.jsonl" \
  2>"${CANDIDATE_DIR}/codex_stderr.txt"
CODEX_EXIT_CODE=$?
set -e

if [[ -f "${FINAL_MESSAGE}" ]]; then
  cp "${FINAL_MESSAGE}" "${CANDIDATE_DIR}/change_summary.md"
  rm -f "${FINAL_MESSAGE}"
else
  printf '%s\n' '# Candidate generation failed' >"${CANDIDATE_DIR}/change_summary.md"
fi

git -C "${WORKSPACE}" status --porcelain >"${CANDIDATE_DIR}/git_status.txt"
git -C "${WORKSPACE}" add -N .
git -C "${WORKSPACE}" diff --binary -- . >"${CANDIDATE_DIR}/patch.diff"
cp "${TASK_PATH}" "${CANDIDATE_DIR}/evidence_task.md"

python - "${CANDIDATE_DIR}" "${CANDIDATE_ID}" "${CODEX_EXIT_CODE}" "${STARTED_AT}" "${WORK_ROOT}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

candidate_dir = Path(sys.argv[1])
status_lines = (candidate_dir / "git_status.txt").read_text(encoding="utf-8").splitlines()
changed_files = [line[3:].split(" -> ")[-1] for line in status_lines if len(line) >= 4]
patch_nonempty = bool((candidate_dir / "patch.diff").read_text(encoding="utf-8").strip())
exit_code = int(sys.argv[3])
manifest = {
    "candidate_id": sys.argv[2],
    "parent_candidate_id": "iter_000_parent",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "started_at": sys.argv[4],
    "framework": "codex_cli",
    "model_provider": "local_qwen_responses_proxy",
    "model": "qwen-plus",
    "task_source": "task_20260619_200503",
    "codex_exit_code": exit_code,
    "changed_files": changed_files,
    "patch_nonempty": patch_nonempty,
    "hard_upstream_round_limit": 12,
    "workspace": sys.argv[5],
    "status": "candidate_generated" if exit_code == 0 and patch_nonempty else "candidate_failed",
}
(candidate_dir / "manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(json.dumps(manifest, ensure_ascii=False))
PY

if [[ "${CODEX_EXIT_CODE}" -ne 0 ]] || [[ ! -s "${CANDIDATE_DIR}/patch.diff" ]]; then
  exit 1
fi
