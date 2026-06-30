#!/usr/bin/env bash
set -euo pipefail

# Demo entrypoint for the full DAB evolution loop:
# parent data-agent -> failure analysis -> meta-agent patch -> apply/lint -> child data-agent.
#
# Common usage:
#   scripts/run_demo_full_loop.sh
#
# Useful overrides:
#   DEMO_ITERATIONS=2 scripts/run_demo_full_loop.sh
#   DEMO_PATCH_LINT=0 scripts/run_demo_full_loop.sh   # demo-only: force child run past patch lint
#   DEMO_INTERPRETER_LLM=1 scripts/run_demo_full_loop.sh   # use LLM for failure interpretation
#   DEMO_MODEL_TAG=prof_demo scripts/run_demo_full_loop.sh

cd /home/m0st1ma/research/text2sql

RUN_ID="${DEMO_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
MODEL_TAG="${DEMO_MODEL_TAG:-demo_full_loop}"

CASE_DIR="${DEMO_CASE_DIR:-/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1}"
DAB_ROOT="${DEMO_DAB_ROOT:-/home/m0st1ma/research/DataAgentBench}"
PROMPT_PATH="${DEMO_PROMPT_PATH:-prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt}"
OUTPUT_DIR="${DEMO_OUTPUT_DIR:-logs/meta_agent/${MODEL_TAG}_${RUN_ID}}"

ITERATIONS="${DEMO_ITERATIONS:-1}"
TIMEOUT_SEC="${DEMO_TIMEOUT_SEC:-300}"
STOP_CONDITION="${DEMO_STOP_CONDITION:-pass}"
PATCH_LINT="${DEMO_PATCH_LINT:-1}"
INTERPRETER_LLM="${DEMO_INTERPRETER_LLM:-0}"

PROXY_URL="${DEMO_PROXY_URL:-http://172.17.240.1:17891}"
export http_proxy="${http_proxy:-$PROXY_URL}"
export https_proxy="${https_proxy:-$PROXY_URL}"
export all_proxy="${all_proxy:-$PROXY_URL}"
export HTTP_PROXY="${HTTP_PROXY:-$PROXY_URL}"
export HTTPS_PROXY="${HTTPS_PROXY:-$PROXY_URL}"
export ALL_PROXY="${ALL_PROXY:-$PROXY_URL}"
export no_proxy="${no_proxy:-localhost,127.0.0.1,::1}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"

export PYTHONUNBUFFERED=1
export DAB_CONCISE_TERMINAL="${DAB_CONCISE_TERMINAL:-1}"
export DATA_AGENT_TIMEOUT_SEC="${DATA_AGENT_TIMEOUT_SEC:-900}"
export DATA_AGENT_MAX_TOKENS="${DATA_AGENT_MAX_TOKENS:-8192}"
export META_AGENT_TIMEOUT_SEC="${META_AGENT_TIMEOUT_SEC:-180}"
export META_AGENT_MAX_TOKENS="${META_AGENT_MAX_TOKENS:-4096}"

PATCH_LINT_ARGS=()
if [[ "$PATCH_LINT" == "0" || "$PATCH_LINT" == "false" || "$PATCH_LINT" == "False" ]]; then
  PATCH_LINT_ARGS+=(--no-patch-lint)
fi

INTERPRETER_ARGS=(--no-interpreter-llm)
if [[ "$INTERPRETER_LLM" == "1" || "$INTERPRETER_LLM" == "true" || "$INTERPRETER_LLM" == "True" ]]; then
  INTERPRETER_ARGS=()
fi

echo "== DAB full-loop demo =="
echo "case_dir      : $CASE_DIR"
echo "prompt        : $PROMPT_PATH"
echo "output_dir    : $OUTPUT_DIR"
echo "iterations    : $ITERATIONS"
echo "patch_lint    : $PATCH_LINT"
echo "interpreter   : $([[ ${#INTERPRETER_ARGS[@]} -eq 0 ]] && echo llm || echo deterministic)"
echo "terminal      : concise"
echo "proxy         : $PROXY_URL"
echo

.venv/bin/python experiments/run_autonomous_meta_agent_loop.py \
  --case-dir "$CASE_DIR" \
  --prompt "$PROMPT_PATH" \
  --version-prefix "${MODEL_TAG}_${RUN_ID}" \
  --loop-prefix "${MODEL_TAG}_${RUN_ID}" \
  --candidate-prefix "${MODEL_TAG}_${RUN_ID}" \
  --dab-root "$DAB_ROOT" \
  --timeout-sec "$TIMEOUT_SEC" \
  --iterations "$ITERATIONS" \
  --stop-condition "$STOP_CONDITION" \
  "${INTERPRETER_ARGS[@]}" \
  --qwen-proxy \
  --output-dir "$OUTPUT_DIR" \
  "${PATCH_LINT_ARGS[@]}" \
  --notes "Professor demo full loop. Run parent data-agent from case_dir, let meta-agent propose project-level evolution, then apply/lint and run child data-agent when the patch passes. Do not hard-code validator answers."

echo
echo "== Demo outputs =="
echo "summary        : $OUTPUT_DIR/auto_loop_state.json"
echo "history        : $OUTPUT_DIR/iteration_history.json"
echo "script report  : $OUTPUT_DIR/script_run_report.run_autonomous_meta_agent_loop.json"
echo
echo "Quick inspect:"
echo "  sed -n '1,220p' $OUTPUT_DIR/auto_loop_state.json"
echo "  sed -n '1,260p' $OUTPUT_DIR/iteration_history.json"
