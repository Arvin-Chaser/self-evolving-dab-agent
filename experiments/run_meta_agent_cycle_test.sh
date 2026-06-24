#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/m0st1ma/research/text2sql}"
ARCHIVE_ROOT="archive"
CANDIDATE_DIR=""
CANDIDATE_ID=""
LAUNCHER=""
CANDIDATE_ID_ENV="ITER003_CANDIDATE_ID"
CASE_ID="PATENTS_query1"
PARENT_AGENT_ID="codex_qwen_meta_v4_structured_patch_spec"
CANDIDATE_TYPE="feedback_analyzer_repair"
SCOPE_NOTE="Feedback/error-analysis infrastructure repair only; not a PATENTS answer solver repair."
RECOMMENDED_GOAL="Repair the data-agent side for PATENTS_query1 so CPC level-5 mapping, filing-date year extraction, EMA/best-year calculation, and final answer generation produce a non-empty validated answer."

usage() {
  cat <<'EOF'
Usage:
  experiments/run_meta_agent_cycle_test.sh --candidate-dir <dir>

  experiments/run_meta_agent_cycle_test.sh \
    --launcher <launcher.sh> \
    --candidate-id <candidate_id>

Purpose:
  Reusable wrapper for testing the meta-agent cycle plumbing.

What it does:
  1. Optionally runs a candidate launcher with CANDIDATE_ID_ENV=<candidate_id>.
  2. Runs experiments/meta_agent_cycle.py postprocess-candidate.
  3. Runs experiments/validate_archive.py.
  4. Writes <candidate_dir>/cycle_run_summary.json.

What it does NOT do:
  - It does not merge to main.
  - It does not push.
  - It does not override human review gates.

Options:
  --candidate-dir DIR       Existing candidate directory to postprocess.
  --launcher PATH           Optional launcher to run before postprocess.
  --candidate-id ID         Candidate id used with --launcher.
  --candidate-id-env NAME   Env var passed to launcher; default ITER003_CANDIDATE_ID.
  --archive-root DIR        Archive root; default archive.
  --case-id ID              Case id; default PATENTS_query1.
  --parent-agent-id ID      Parent agent/protocol id.
  --candidate-type TYPE     Candidate type.
  --scope-note TEXT         Candidate scope note.
  --recommended-goal TEXT   Next repair goal.
  -h, --help                Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate-dir)
      CANDIDATE_DIR="$2"
      shift 2
      ;;
    --launcher)
      LAUNCHER="$2"
      shift 2
      ;;
    --candidate-id)
      CANDIDATE_ID="$2"
      shift 2
      ;;
    --candidate-id-env)
      CANDIDATE_ID_ENV="$2"
      shift 2
      ;;
    --archive-root)
      ARCHIVE_ROOT="$2"
      shift 2
      ;;
    --case-id)
      CASE_ID="$2"
      shift 2
      ;;
    --parent-agent-id)
      PARENT_AGENT_ID="$2"
      shift 2
      ;;
    --candidate-type)
      CANDIDATE_TYPE="$2"
      shift 2
      ;;
    --scope-note)
      SCOPE_NOTE="$2"
      shift 2
      ;;
    --recommended-goal)
      RECOMMENDED_GOAL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"

if [[ -n "$LAUNCHER" ]]; then
  if [[ -z "$CANDIDATE_ID" ]]; then
    echo "--candidate-id is required when --launcher is provided" >&2
    exit 2
  fi
  if [[ -z "$CANDIDATE_DIR" ]]; then
    CANDIDATE_DIR="candidates/dab/$CANDIDATE_ID"
  fi
  echo "[cycle] running launcher: $LAUNCHER"
  env "$CANDIDATE_ID_ENV=$CANDIDATE_ID" /bin/bash "$LAUNCHER"
fi

if [[ -z "$CANDIDATE_DIR" ]]; then
  echo "--candidate-dir is required when --launcher is not provided" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$CANDIDATE_DIR" ]]; then
  echo "candidate directory not found: $CANDIDATE_DIR" >&2
  exit 3
fi

echo "[cycle] postprocess candidate: $CANDIDATE_DIR"
".venv/bin/python" experiments/meta_agent_cycle.py postprocess-candidate \
  --candidate-dir "$CANDIDATE_DIR" \
  --archive-root "$ARCHIVE_ROOT" \
  --parent-agent-id "$PARENT_AGENT_ID" \
  --candidate-type "$CANDIDATE_TYPE" \
  --scope-note "$SCOPE_NOTE" \
  --case-id "$CASE_ID" \
  --recommended-goal "$RECOMMENDED_GOAL"

echo "[cycle] validate archive: $ARCHIVE_ROOT"
".venv/bin/python" experiments/validate_archive.py --archive-root "$ARCHIVE_ROOT"

".venv/bin/python" - "$CANDIDATE_DIR" "$ARCHIVE_ROOT" "$LAUNCHER" "$CANDIDATE_ID" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

candidate_dir = Path(sys.argv[1])
archive_root = sys.argv[2]
launcher = sys.argv[3] or None
candidate_id = sys.argv[4] or candidate_dir.name

def git(args):
    return subprocess.run(["git", *args], text=True, capture_output=True, check=False).stdout.strip()

summary = {
    "status": "cycle_postprocess_complete",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "candidate_id": candidate_id,
    "candidate_dir": str(candidate_dir),
    "launcher": launcher,
    "archive_root": archive_root,
    "branch": git(["branch", "--show-current"]),
    "head": git(["rev-parse", "HEAD"]),
    "outputs": {
        "candidate_state": str(candidate_dir / "candidate_state.json"),
        "merge_review_package": str(candidate_dir / "merge_review_package.md"),
        "next_data_agent_repair_seed": str(candidate_dir / "next_data_agent_repair_seed.json"),
    },
}
(candidate_dir / "cycle_run_summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY

echo "[cycle] done"

