#!/usr/bin/env python3
"""Preflight and uniquely launch G3 attempt 2 after attempt 1 infrastructure failure."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G3 = BASE / "g003_revision001"
BINDINGS = G3 / "bindings"
GRAPH = BASE / "graph"
ORIGINAL_LAUNCHER = BINDINGS / "launch_research_graph_g003.py"
ORIGINAL_LAUNCHER_SHA256 = "98abce2d519a40317f82f77689b6ffc28cfac5646cd2a80d769fb3ae5d1c8118"
ATTEMPT1_RUN_ID = "baseline_g003_proposed_calls_nohint_56_v1"
RUN_ID = "baseline_g003_proposed_calls_nohint_56_v2"
ATTEMPT1_PID = 436296
MIN_FREE_BYTES = 5 * 1024**3
MODEL = "deepseek-flash"
ENDPOINT = "https://api.deepseek.com/v1/chat/completions"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")


def load_original_launcher():
    if not ORIGINAL_LAUNCHER.is_file() or digest(ORIGINAL_LAUNCHER) != ORIGINAL_LAUNCHER_SHA256:
        raise RuntimeError("Frozen G3 launcher is missing or changed")
    spec = importlib.util.spec_from_file_location("g003_original_launcher", ORIGINAL_LAUNCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen G3 launcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_attempt1() -> dict:
    if Path(f"/proc/{ATTEMPT1_PID}/cmdline").is_file():
        raise RuntimeError("G3 attempt 1 runner is still present")
    run = G3 / "evaluation" / ATTEMPT1_RUN_ID
    summary_path = run / "multi_query_summary.json"
    progress_path = run / "multi_query_progress.json"
    if not summary_path.is_file() or not progress_path.is_file():
        raise RuntimeError("G3 attempt 1 terminal artifacts are missing")
    summary = read(summary_path)
    rows = read(progress_path).get("queries", [])
    if (summary.get("query_count") != 56 or len(rows) != 56 or
            any(row.get("status") != "completed" or row.get("run_exit_code") != 0 or
                row.get("llm_call_count") != 1 or row.get("tool_call_count") != 0 or
                row.get("final_answer_nonempty") is not False or
                "(APIConnectionError):" not in (row.get("terminate_reason") or "")
                for row in rows)):
        raise RuntimeError("G3 attempt 1 is not the admitted uniform connection incident")
    return {
        "run_id": ATTEMPT1_RUN_ID,
        "summary_sha256": digest(summary_path),
        "progress_sha256": digest(progress_path),
        "classification": "invalid_infrastructure_hypothesis_not_tested",
    }


def model_preflight(key: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 8,
        "stream": False,
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"G3 model preflight HTTP failure: {exc.code}") from None
    except Exception as exc:
        raise RuntimeError(f"G3 model preflight transport failure: {type(exc).__name__}") from None
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if status != 200 or not isinstance(choices, list) or not choices:
        raise RuntimeError("G3 model preflight returned an invalid response contract")
    return {"http_status": status, "model_requested": MODEL,
            "choices_nonempty": True, "task_content_sent": False}


def main() -> None:
    original = load_original_launcher()
    binding = original.verify_inputs()
    original.verify_preparation()
    attempt1 = verify_attempt1()
    free = shutil.disk_usage(G3).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G3 attempt 2 space below 5 GiB: {free} bytes")
    output_root = G3 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g003_launch_claim_attempt002.json"
    manifest = GRAPH / "g003_launch_manifest_attempt002.json"
    preflight_path = GRAPH / "g003_preflight_attempt002.json"
    if output.exists() or claim.exists() or manifest.exists() or preflight_path.exists():
        raise RuntimeError("G3 attempt 2 already has output, preflight, claim, or manifest")
    key = sys.stdin.readline().strip()
    if not key or any(character.isspace() for character in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    probe = model_preflight(key)
    preflight = {
        "schema_version": "dab_research_graph_g003_preflight_attempt_v1",
        "generation": 3, "attempt": 2, "created_at_utc": now(),
        "binding": binding, "prior_attempt": attempt1,
        "model_probe": probe, "free_bytes": free,
        "status": "passed",
    }
    write_new(preflight_path, preflight)
    args = original.command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g003_launch_claim_attempt_v1",
        "generation": 3, "attempt": 2, "claimed_at_utc": now(),
        "binding": binding, "prior_attempt": attempt1,
        "pre_execution_sha256": digest(GRAPH / "g003_pre_execution.json"),
        "preflight_sha256": digest(preflight_path),
        "command": args, "status": "claimed_exclusive",
    }
    write_new(claim, payload)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = output_root / "launcher_attempt002.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(
            args, cwd=original.SOURCE, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    write_new(manifest, {
        **payload, "launched_at_utc": now(), "pid": process.pid,
        "output": str(output), "log_path": str(log_path),
        "credential_env_name": "DEEPSEEK_API_KEY",
        "launch_free_bytes": free,
    })
    print(json.dumps({"status": "launched", "attempt": 2, "pid": process.pid,
                      "run_id": RUN_ID, "output": str(output),
                      "free_bytes_at_launch": free}, sort_keys=True))


if __name__ == "__main__":
    main()
