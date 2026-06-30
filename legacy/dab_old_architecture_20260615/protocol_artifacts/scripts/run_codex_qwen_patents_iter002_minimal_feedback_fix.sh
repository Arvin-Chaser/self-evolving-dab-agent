#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
ID=codex_qwen_patents_iter002_minimal_feedback_fix
OUT="$ROOT/candidates/dab/$ID"
WORK_ROOT="$(mktemp -d /tmp/${ID}.XXXXXX)"
WORKSPACE="$WORK_ROOT/workspace"
CODEX_HOME_DIR="$WORK_ROOT/codex_home"
FINAL_MESSAGE="$WORKSPACE/.codex_final_message.md"

cleanup() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "$PROXY_PID" 2>/dev/null || true
    wait "$PROXY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[[ ! -e "$OUT" ]] || { echo "candidate exists: $OUT" >&2; exit 1; }
mkdir -p "$WORKSPACE/evidence/iter001_diagnosis" "$CODEX_HOME_DIR" "$OUT"
rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude=.codex \
  --exclude=__pycache__ --exclude=logs --exclude=candidates --exclude=reports \
  --exclude=trajectories "$ROOT/" "$WORKSPACE/"
cp "$ROOT/candidates/dab/codex_qwen_patents_iter001_child/evidence_task.md" \
  "$WORKSPACE/evidence/PATENTS_META_AGENT_TASK.md"
cp "$ROOT/candidates/dab/codex_qwen_patents_iter001_child/validation_report.md" \
  "$WORKSPACE/evidence/iter001_diagnosis/rejection_report.md"

git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "Codex Qwen Experiment"
git -C "$WORKSPACE" config user.email codex-qwen@localhost
git -C "$WORKSPACE" add .
git -C "$WORKSPACE" commit --quiet -m "Clean parent baseline for iter002"
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
  >"$OUT/proxy.log" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  curl --silent --fail http://127.0.0.1:8787/health >/dev/null && break
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:8787/health >/dev/null

set +e
codex exec --strict-config --ephemeral --sandbox workspace-write --json \
  --output-last-message "$FINAL_MESSAGE" -C "$WORKSPACE" \
  - <"$ROOT/prompts/dab/meta_agent/codex_qwen_patents_iter002_minimal_feedback_fix.txt" \
  >"$OUT/codex_transcript.jsonl" 2>"$OUT/codex_stderr.txt"
CODEX_EXIT=$?
set -e

[[ -f "$FINAL_MESSAGE" ]] && cp "$FINAL_MESSAGE" "$OUT/change_summary.md"
git -C "$WORKSPACE" status --porcelain >"$OUT/git_status.txt"
git -C "$WORKSPACE" diff --binary -- \
  adapters/feedback/dab_patents_checks.py \
  adapters/feedback/common_trace_checks.py >"$OUT/patch.diff"
git -C "$WORKSPACE" diff --numstat -- \
  adapters/feedback/dab_patents_checks.py \
  adapters/feedback/common_trace_checks.py >"$OUT/patch_numstat.txt"
printf '%s\n' "$WORK_ROOT" >"$OUT/work_root.txt"
printf '{"candidate_id":"%s","codex_exit_code":%s,"status":"generated_pending_validation"}\n' \
  "$ID" "$CODEX_EXIT" >"$OUT/manifest.json"

[[ "$CODEX_EXIT" -eq 0 && -s "$OUT/patch.diff" ]]
