#!/usr/bin/env python3
"""Freeze, prepare, and uniquely launch the G1 deadline-reserve evaluation."""

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
G1 = BASE / "g001_revision001"
SOURCE = G1 / "source"
BINDINGS = G1 / "bindings"
GRAPH = BASE / "graph"
RUNNER = SOURCE / "experiments/run_multi_query_baseline.py"
AGENT = SOURCE / "experiments/run_dab_tool_agent.py"
POLICY = SOURCE / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
PYTHON = Path("/srv/text2sql/.venv/bin/python")
PREPARE_ID = "baseline_g001_deadline_reserve_prepare"
RUN_ID = "baseline_g001_deadline_reserve_nohint_56_v1"
SOURCE_TREE_SHA = "8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d"
G0_GRAPH_SHA = "256570b3813f79bced5332994c5e3506765cd88ebdbaf6371115e9e3290bc86e"
G0_SOURCE_TREE_SHA = "93e4d9ebf9d8e8b0f4d6b8b356926b7ab7a66a125dc9652d30aac86e930d4eb9"
RESEARCH_SHA = "fc8bf2c66be8c53fbe4af12fc5af15d27f460351400fed44a7f9e50805be0459"
TIMEOUT_EVIDENCE_SHA = "6d88608247da569d2987cfb954a7c0df60bb533b43df77788c60c4b8f0283196"
AGENT_SHA = "83980fd974bb7ac2728adcbceecae035eba199acad0d2147cfda4b86bc31173f"
RUNNER_SHA = "f0a48379538d5cedb8b030dd9ae9fa957230a78ca81c195b53b22a20ff4e3211"
POLICY_SHA = "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797"
BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
MIN_FREE_BYTES = 5 * 1024**3


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_inputs() -> dict:
    expected = {
        GRAPH / "g000_graph.json": G0_GRAPH_SHA,
        BINDINGS / "g001_research_meta_result.json": RESEARCH_SHA,
        BINDINGS / "g000_timeout_partial_v1.json": TIMEOUT_EVIDENCE_SHA,
        AGENT: AGENT_SHA,
        RUNNER: RUNNER_SHA,
        POLICY: POLICY_SHA,
        BATCH: BATCH_SHA,
        REGISTRY: REGISTRY_SHA,
    }
    for path, wanted in expected.items():
        if not path.is_file() or digest(path) != wanted:
            raise RuntimeError(f"Frozen G1 input missing or changed: {path}")
    if not PYTHON.is_file() or not UPSTREAM.is_dir():
        raise RuntimeError("Frozen upstream runtime is unavailable")
    spec = importlib.util.spec_from_file_location("g1_manifest", SOURCE / "experiments/intent_candidate_workspace.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("G1 source manifest module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(rows) != SOURCE_TREE_SHA:
        raise RuntimeError("G1 candidate source tree differs from admitted source")
    admission_path = BINDINGS / "g001_admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if (admission.get("parent_tree_sha256") != G0_SOURCE_TREE_SHA or
            admission.get("candidate_tree_sha256") != SOURCE_TREE_SHA or
            admission.get("research_result_sha256") != RESEARCH_SHA):
        raise RuntimeError("G1 source admission binding differs")
    decision = json.loads((BINDINGS / "g001_research_meta_result.json").read_text(encoding="utf-8"))
    if decision.get("implementation_ready") is not True or decision["experiment"]["code_parent"] != "root_baseline":
        raise RuntimeError("G1 research decision is not implementation-ready")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("Frozen G1 batch is not exactly 56 registered tasks")
    return {
        "g0_graph_sha256": G0_GRAPH_SHA,
        "parent_tree_sha256": G0_SOURCE_TREE_SHA,
        "candidate_tree_sha256": SOURCE_TREE_SHA,
        "admission_sha256": digest(admission_path),
        "research_result_sha256": RESEARCH_SHA,
        "timeout_sidecar_sha256": TIMEOUT_EVIDENCE_SHA,
        "agent_sha256": AGENT_SHA,
        "runner_sha256": RUNNER_SHA,
        "policy_sha256": POLICY_SHA,
        "batch_sha256": BATCH_SHA,
        "registry_sha256": REGISTRY_SHA,
        "query_count": 56,
        "description_mode": "full_db_description_no_hints",
        "query_timeout_sec": 1200,
        "timeout_scoring": "timeout_failure_in_fixed_56_denominator",
    }


def command(output_root: Path, run_id: str, *, prepare_only: bool) -> list[str]:
    args = [
        str(PYTHON), str(RUNNER),
        "--batch", str(BATCH), "--registry", str(REGISTRY),
        "--dab-root", str(UPSTREAM), "--source-root", str(SOURCE),
        "--dab-upstream-root", str(UPSTREAM), "--output-root", str(output_root),
        "--run-id", run_id, "--python", str(PYTHON),
        "--deployment-name", "deepseek-flash",
        "--openai-compatible-base-url", "https://api.deepseek.com/v1",
        "--openai-compatible-api-key-env", "DEEPSEEK_API_KEY",
        "--max-iterations", "0", "--llm-timeout", "600",
        "--llm-retries", "2", "--llm-retry-sleep", "20",
        "--client-max-retries", "0", "--query-timeout-sec", "1200",
        "--postgres-statement-timeout-ms", "1080000",
        "--workers", "4", "--skip-observer",
    ]
    if prepare_only:
        args.append("--prepare-only")
    return args


def preregister(binding: dict) -> None:
    path = GRAPH / "g001_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8"))["binding"] != binding:
            raise RuntimeError("G1 pre-execution node binding changed")
        return
    decision = json.loads((BINDINGS / "g001_research_meta_result.json").read_text(encoding="utf-8"))
    write_new(path, {
        "schema_version": "dab_research_graph_g001_pre_execution_v1",
        "generation": 1, "created_at_utc": now(),
        "status": "pre_registered_before_evaluation",
        "binding": binding,
        "nodes": [
            {"id": "problem:g001", "kind": "problem", **decision["problem"]},
            {"id": "hypothesis:g001", "kind": "hypothesis", **decision["hypothesis"]},
            {"id": "experiment:g001", "kind": "experiment", **decision["experiment"],
             "candidate_source_tree_sha256": SOURCE_TREE_SHA, "evaluation_run_id": RUN_ID},
        ],
        "edges": [
            {"source": "problem:g001", "target": "evidence:g000", "relation": "motivated_by"},
            {"source": "hypothesis:g001", "target": "problem:g001", "relation": "explains"},
            {"source": "experiment:g001", "target": "hypothesis:g001", "relation": "tests"},
        ],
        "evidence_node": "pending_after_execution",
    })


def verify_preparation() -> None:
    path = G1 / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G1 prepare-only summary missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (summary.get("query_count") != 56 or len(rows) != 56 or
            any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows) or
            context.get("db_description_mode") != "base" or
            context.get("query_timeout_sec") != 1200):
        raise RuntimeError("G1 prepare-only did not pass exact 56/base/no-hint/1200s contract")


def prepare(binding: dict) -> None:
    preregister(binding)
    output_root = G1 / "preflight"
    if (output_root / PREPARE_ID).exists():
        raise RuntimeError("G1 preparation already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (output_root / "prepare.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(command(output_root, PREPARE_ID, prepare_only=True),
                                cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"G1 prepare-only failed: exit {result.returncode}")
    verify_preparation()
    print(json.dumps({"status": "prepared", "query_count": 56}, sort_keys=True))


def launch(binding: dict) -> None:
    verify_preparation()
    preregister(binding)
    free = shutil.disk_usage(G1).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G1 launch space below 5 GiB: {free} bytes")
    key = sys.stdin.readline().strip()
    if not key or any(char.isspace() for char in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    output_root = G1 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g001_launch_claim.json"
    if output.exists() or claim.exists():
        raise RuntimeError("G1 already has a formal output or exclusive launch claim")
    output_root.mkdir(parents=True, exist_ok=True)
    args = command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g001_launch_claim_v1",
        "claimed_at_utc": now(), "binding": binding,
        "pre_execution_sha256": digest(GRAPH / "g001_pre_execution.json"),
        "command": args, "status": "claimed_exclusive",
    }
    write_new(claim, payload)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    log_path = output_root / "launcher.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(args, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write_new(GRAPH / "g001_launch_manifest.json", {
        **payload, "launched_at_utc": now(), "pid": process.pid,
        "output": str(output), "log_path": str(log_path),
        "credential_env_name": "DEEPSEEK_API_KEY", "launch_free_bytes": free,
    })
    print(json.dumps({"status": "launched", "pid": process.pid,
                      "output": str(output), "free_bytes_at_launch": free}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "prepare", "launch"))
    args = parser.parse_args()
    binding = verify_inputs()
    if args.action == "verify":
        print(json.dumps({"status": "verified", "binding": binding}, sort_keys=True))
    elif args.action == "prepare":
        prepare(binding)
    else:
        launch(binding)


if __name__ == "__main__":
    main()
