#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/m0st1ma/research/text2sql
ORIGINAL="$ROOT/experiments/run_codex_qwen_patents_iter003_minimal_feedback_fix_v4.sh"
TMP="$(mktemp /tmp/iter003_v4_fixed_launcher.XXXXXX.sh)"
sed 's#HELPER="$ROOT/experiments/structured_patch_spec_v4.py"#HELPER="$ROOT/experiments/structured_patch_spec_v4_fixed.py"#' "$ORIGINAL" >"$TMP"
bash "$TMP"

