#!/usr/bin/env bash
# CT104: run a DAB baseline batch with the already-installed local services.
set -euo pipefail
umask 077

root=/srv/text2sql
dab_root="$root/external/DataAgentBench_official"
key_file=/root/.config/dab/school_api.env
test -r "$key_file" || { echo "Missing $key_file" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$key_file"
set +a
test -n "${DAB_TOOL_AGENT_API_KEY:-}" || { echo "DAB_TOOL_AGENT_API_KEY is empty" >&2; exit 1; }

export DAB_TOOL_AGENT_MODEL="glm-5.3-flash"
export DAB_TOOL_AGENT_OPENAI_BASE_URL="http://127.0.0.1:13001/v1"
export DAB_TOOL_AGENT_LLM_TIMEOUT="${DAB_TOOL_AGENT_LLM_TIMEOUT:-60}"
export DAB_TOOL_AGENT_LLM_RETRIES="${DAB_TOOL_AGENT_LLM_RETRIES:-1}"
export DAB_TOOL_AGENT_CLIENT_MAX_RETRIES="${DAB_TOOL_AGENT_CLIENT_MAX_RETRIES:-0}"
export DATA_AGENT_MODEL="$DAB_TOOL_AGENT_MODEL"
export DATA_AGENT_BASE_URL="$DAB_TOOL_AGENT_OPENAI_BASE_URL"
export DATA_AGENT_API_KEY="$DAB_TOOL_AGENT_API_KEY"
export META_AGENT_MODEL="$DAB_TOOL_AGENT_MODEL"
export META_AGENT_BASE_URL="$DAB_TOOL_AGENT_OPENAI_BASE_URL"
export META_AGENT_API_KEY="$DAB_TOOL_AGENT_API_KEY"
export CODEX_NATIVE_MODEL="$DAB_TOOL_AGENT_MODEL"
export PG_CLIENT=/usr/local/bin/dab-psql
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"

cd "$root"
exec .venv/bin/python experiments/run_multi_query_baseline.py \
  --dab-root "$dab_root" \
  --dab-upstream-root "$dab_root" \
  --registry "$root/dab_corpus/registry.json" \
  --use-base-db-description \
  --skip-observer \
  --max-iterations 0 \
  "$@"
