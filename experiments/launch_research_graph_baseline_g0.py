#!/usr/bin/env python3
"""Prepare and uniquely launch the fresh Research Graph G0 baseline on ct104."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
SOURCE = BASE / "source"
RUNNER = Path("/srv/text2sql/evolution_runtime/half56_v1/run_multi_query_baseline.py")
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
PYTHON = Path("/srv/text2sql/.venv/bin/python")
PREPARE_ID = "baseline_g000_prepare"
RUN_ID = "baseline_g000_nohint_56_v1"
SOURCE_TREE_SHA256 = "93e4d9ebf9d8e8b0f4d6b8b356926b7ab7a66a125dc9652d30aac86e930d4eb9"
AGENT_SHA256 = "023e27d18df276f4cb25588884c0aff3798f91957e31f6c5ab1ab316745c7fba"
RUNNER_SHA256 = "6bff187bc483d92aa47ebf6471c79383d6e31f701aff2d52b3c5086974cf9baf"
BATCH_SHA256 = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA256 = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
MIN_LAUNCH_FREE_BYTES = 22 * 1024**3


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_inputs() -> dict:
    expected = {
        SOURCE / "experiments/run_dab_tool_agent.py": AGENT_SHA256,
        RUNNER: RUNNER_SHA256,
        BATCH: BATCH_SHA256,
    }
    for path, wanted in expected.items():
        if not path.is_file() or digest(path) != wanted:
            raise RuntimeError(f"Frozen input missing or changed: {path}")
    if not REGISTRY.is_file() or digest(REGISTRY) != REGISTRY_SHA256:
        raise RuntimeError("Frozen task registry is missing or changed")
    if not UPSTREAM.is_dir() or not PYTHON.is_file():
        raise RuntimeError("Registry, upstream scaffold, or Python runtime is missing")
    spec = importlib.util.spec_from_file_location(
        "baseline_source_manifest", SOURCE / "experiments/intent_candidate_workspace.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Baseline source manifest module is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The frozen manifest was generated on Windows, where Path sorting is case-insensitive.
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    tree = module.source_manifest_hash(rows)
    if tree != SOURCE_TREE_SHA256:
        raise RuntimeError("Baseline source tree differs from frozen root baseline")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("Frozen batch is not exactly 56 unique registered tasks")
    return {
        "source_tree_sha256": tree,
        "agent_sha256": AGENT_SHA256,
        "runner_sha256": RUNNER_SHA256,
        "batch_sha256": BATCH_SHA256,
        "registry_sha256": digest(REGISTRY),
        "query_count": len(ids),
        "description_mode": "full_db_description_no_hints",
    }


def command(output_root: Path, run_id: str, *, prepare_only: bool) -> list[str]:
    args = [
        str(PYTHON), str(RUNNER),
        "--batch", str(BATCH),
        "--registry", str(REGISTRY),
        "--dab-root", str(UPSTREAM),
        "--source-root", str(SOURCE),
        "--dab-upstream-root", str(UPSTREAM),
        "--output-root", str(output_root),
        "--run-id", run_id,
        "--python", str(PYTHON),
        "--deployment-name", "deepseek-flash",
        "--openai-compatible-base-url", "https://api.deepseek.com/v1",
        "--openai-compatible-api-key-env", "DEEPSEEK_API_KEY",
        "--max-iterations", "0",
        "--llm-timeout", "600",
        "--llm-retries", "2",
        "--llm-retry-sleep", "20",
        "--client-max-retries", "0",
        "--query-timeout-sec", "1200",
        "--postgres-statement-timeout-ms", "1080000",
        "--workers", "4",
        "--skip-observer",
    ]
    if prepare_only:
        args.append("--prepare-only")
    return args


def preregister(binding: dict) -> None:
    path = BASE / "graph/g000_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8"))["binding"] != binding:
            raise RuntimeError("G0 pre-execution binding changed")
        return
    write_new(path, {
        "schema_version": "dab_research_graph_g000_pre_execution_v1",
        "generation": 0,
        "created_at_utc": now(),
        "status": "pre_registered_before_evaluation",
        "binding": binding,
        "nodes": [
            {"id": "problem:g000", "kind": "problem", "statement":
             "Establish the unmodified zero-start agent's no-hint behavior and failure distribution on the frozen 56 tasks."},
            {"id": "hypothesis:g000", "kind": "hypothesis", "statement":
             "The unmodified zero-start agent will produce a nonempty final answer for at least one frozen task without hints.",
             "prediction": "At least one completed task has a nonempty final answer.",
             "falsification_condition": "No completed task has a nonempty final answer."},
            {"id": "experiment:g000", "kind": "experiment", "statement":
             "Run the frozen root baseline without any candidate intervention or per-query observer.",
             "code_parent": "root_baseline", "source_tree_sha256": binding["source_tree_sha256"],
             "evaluation_run_id": RUN_ID, "query_count": 56, "no_hints": True},
        ],
        "edges": [
            {"source": "hypothesis:g000", "target": "problem:g000", "relation": "explains"},
            {"source": "experiment:g000", "target": "hypothesis:g000", "relation": "tests"},
        ],
        "evidence_node": "pending_after_execution",
    })


def prepare(binding: dict) -> None:
    preregister(binding)
    output_root = BASE / "preflight"
    output = output_root / PREPARE_ID
    if output.exists():
        raise RuntimeError("G0 preparation already exists; refusing a second prepare")
    output_root.mkdir(parents=True, exist_ok=True)
    args = command(output_root, PREPARE_ID, prepare_only=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    log_path = BASE / "preflight/prepare.log"
    with log_path.open("x", encoding="utf-8") as log:
        result = subprocess.run(args, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"G0 preparation failed with exit code {result.returncode}")
    verify_preparation()
    print(json.dumps({"status": "prepared", "query_count": 56, "output": str(output)}))


def verify_preparation() -> None:
    path = BASE / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G0 preparation summary is missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    if (summary.get("query_count") != 56 or len(rows) != 56 or
            any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows)):
        raise RuntimeError("G0 preparation did not pass for exactly 56 tasks")


def launch(binding: dict) -> None:
    verify_preparation()
    preregister(binding)
    free = shutil.disk_usage(BASE).free
    if free < MIN_LAUNCH_FREE_BYTES:
        raise RuntimeError(f"Insufficient launch headroom: {free} bytes available")
    key = sys.stdin.readline().strip()
    if not key or any(char.isspace() for char in key):
        raise RuntimeError("Missing or malformed one-line DeepSeek credential")
    output_root = BASE / "evaluation"
    output = output_root / RUN_ID
    claim = BASE / "graph/g000_launch_claim.json"
    if output.exists() or claim.exists():
        raise RuntimeError("G0 already has an output or launch claim")
    output_root.mkdir(parents=True, exist_ok=True)
    args = command(output_root, RUN_ID, prepare_only=False)
    claim_payload = {"schema_version": "dab_research_graph_g000_launch_claim_v1",
                     "claimed_at_utc": now(), "binding": binding,
                     "pre_execution_sha256": digest(BASE / "graph/g000_pre_execution.json"),
                     "command": args, "status": "claimed_exclusive"}
    write_new(claim, claim_payload)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    log_path = BASE / "evaluation/launcher.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(
            args, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    write_new(BASE / "graph/g000_launch_manifest.json", {
        **claim_payload, "launched_at_utc": now(), "pid": process.pid,
        "output": str(output), "log_path": str(log_path),
        "credential_env_name": "DEEPSEEK_API_KEY",
        "launch_free_bytes": free,
    })
    print(json.dumps({"status": "launched", "pid": process.pid,
                      "output": str(output), "free_bytes_at_launch": free}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch"))
    args = parser.parse_args()
    binding = verify_inputs()
    if args.action == "prepare":
        prepare(binding)
    else:
        launch(binding)


if __name__ == "__main__":
    main()
