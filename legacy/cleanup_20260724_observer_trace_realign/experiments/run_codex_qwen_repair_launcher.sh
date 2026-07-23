#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/m0st1ma/research/text2sql}"
cd "$ROOT"

exec "$ROOT/.venv/bin/python" "$ROOT/experiments/run_codex_qwen_repair_launcher.py" "$@"
