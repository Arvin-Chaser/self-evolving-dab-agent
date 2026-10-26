#!/usr/bin/env python3
"""Verify, preregister, prepare, and uniquely launch the frozen G3 run."""

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
G3 = BASE / "g003_revision001"
SOURCE = G3 / "source"
BINDINGS = G3 / "bindings"
GRAPH = BASE / "graph"
PYTHON = Path("/srv/text2sql/.venv/bin/python")
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
RUNNER = SOURCE / "experiments/run_multi_query_baseline.py"
AGENT = SOURCE / "experiments/run_dab_tool_agent.py"
STAGE = SOURCE / "experiments/g002_lifecycle_stage.py"
DIAGNOSTIC = SOURCE / "experiments/g003_proposed_call_diagnostic.py"
POLICY = SOURCE / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
PREPARE_ID = "baseline_g003_proposed_calls_prepare"
RUN_ID = "baseline_g003_proposed_calls_nohint_56_v1"
HASHES = {
    GRAPH / "g002_graph.json": "38852be6a2cef504cbc936a7b919db7f879c709f9e5a6a594ce432f716cb5b54",
    BINDINGS / "admission.json": "10a4c6c2175af63b4bdbfea54ad4d2aea1242a8906dc00232cd7e5864d749e61",
    BINDINGS / "research_result.json": "9e2297d1f6281092c7200409f5c0038de2533b40e92e75e4032956cc1cec54fb",
    BINDINGS / "research_binding.json": "c46994f838be577497ee6ba60124ba7f6d36b213d8ee62800461ac2c5fa41f84",
    RUNNER: "7e8cd381690bee6551f6ee2047a1abdf1b1993433fa03edfdd36ce3804573549",
    AGENT: "11319e6b2eaaaa8142ec7c2a73d3c1c823566dd6346fe1bd2930dee2d5428519",
    STAGE: "ce017cf6820b6dc9b329d30824ecee4305dbf3e695dbb298676c5264d70f8b00",
    DIAGNOSTIC: "a9759a49742df416a0b485df8a132095a64513ab7e9b9ebd59ea3b3577674c23",
    POLICY: "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797",
    BATCH: "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7",
    REGISTRY: "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff",
}
SOURCE_TREE_SHA = "3a09fd575f32fbd736344bdeb7ec786e987a02102bfe2d96202ae13d8b3b6d99"
PARENT_TREE_SHA = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"
MIN_FREE_BYTES = 5 * 1024**3


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
    for path, wanted in HASHES.items():
        if not path.is_file() or digest(path) != wanted:
            raise RuntimeError(f"Frozen G3 input missing or changed: {path}")
    if not PYTHON.is_file() or not UPSTREAM.is_dir():
        raise RuntimeError("Frozen upstream runtime is unavailable")
    spec = importlib.util.spec_from_file_location(
        "g3_manifest", SOURCE / "experiments/intent_candidate_workspace.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("G3 source manifest module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(rows) != SOURCE_TREE_SHA or len(rows) != 83:
        raise RuntimeError("G3 candidate source tree differs from admission")
    admission = json.loads((BINDINGS / "admission.json").read_text(encoding="utf-8"))
    if (admission.get("parent_tree_sha256") != PARENT_TREE_SHA or
            admission.get("candidate_tree_sha256") != SOURCE_TREE_SHA or
            admission.get("g2_graph_sha256") != HASHES[GRAPH / "g002_graph.json"] or
            admission.get("research_result_sha256") != HASHES[BINDINGS / "research_result.json"]):
        raise RuntimeError("G3 admission binding differs")
    decision = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    if (decision.get("research_ready") is not True or
            decision.get("experiment_spec_ready") is not True or
            decision["experiment"]["code_parent"] != "g002_lifecycle_stage" or
            decision["experiment"]["intervention_class"] != "diagnostic_instrumentation"):
        raise RuntimeError("G3 research decision is not the admitted diagnostic")
    research_binding = json.loads((BINDINGS / "research_binding.json").read_text(encoding="utf-8"))
    if research_binding.get("result_sha256") != HASHES[BINDINGS / "research_result.json"]:
        raise RuntimeError("G3 research binding differs")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("G3 batch is not exactly 56 registered tasks")
    return {
        "g2_graph_sha256": HASHES[GRAPH / "g002_graph.json"],
        "parent_tree_sha256": PARENT_TREE_SHA,
        "candidate_tree_sha256": SOURCE_TREE_SHA,
        "admission_sha256": HASHES[BINDINGS / "admission.json"],
        "research_result_sha256": HASHES[BINDINGS / "research_result.json"],
        "agent_sha256": HASHES[AGENT], "runner_sha256": HASHES[RUNNER],
        "stage_sha256": HASHES[STAGE], "diagnostic_sha256": HASHES[DIAGNOSTIC],
        "policy_sha256": HASHES[POLICY],
        "batch_sha256": HASHES[BATCH], "registry_sha256": HASHES[REGISTRY],
        "query_count": 56, "description_mode": "full_db_description_no_hints",
        "query_timeout_sec": 1200,
        "timeout_scoring": "timeout_failure_in_fixed_56_denominator",
    }


def command(output_root: Path, run_id: str, *, prepare_only: bool) -> list[str]:
    args = [
        str(PYTHON), str(RUNNER), "--batch", str(BATCH), "--registry", str(REGISTRY),
        "--dab-root", str(UPSTREAM), "--source-root", str(SOURCE),
        "--dab-upstream-root", str(UPSTREAM), "--output-root", str(output_root),
        "--run-id", run_id, "--python", str(PYTHON),
        "--deployment-name", "deepseek-flash",
        "--openai-compatible-base-url", "https://api.deepseek.com/v1",
        "--openai-compatible-api-key-env", "DEEPSEEK_API_KEY",
        "--max-iterations", "0", "--llm-timeout", "600", "--llm-retries", "2",
        "--llm-retry-sleep", "20", "--client-max-retries", "0",
        "--query-timeout-sec", "1200", "--postgres-statement-timeout-ms", "1080000",
        "--workers", "4", "--skip-observer",
    ]
    if prepare_only:
        args.append("--prepare-only")
    return args


def preregister(binding: dict) -> None:
    path = GRAPH / "g003_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8"))["binding"] != binding:
            raise RuntimeError("G3 pre-execution binding changed")
        return
    decision = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    write_new(path, {
        "schema_version": "dab_research_graph_g003_pre_execution_v1",
        "generation": 3, "created_at_utc": now(),
        "status": "pre_registered_before_evaluation", "binding": binding,
        "nodes": [{**decision["problem"], "id": "problem:g003", "kind": "problem"},
                  {**decision["hypothesis"], "id": "hypothesis:g003", "kind": "hypothesis"}, {
            **decision["experiment"], "id": "experiment:g003", "kind": "experiment",
            "candidate_source_tree_sha256": SOURCE_TREE_SHA,
            "evaluation_run_id": RUN_ID,
        }],
        "edges": [
            {"source": "problem:g003", "target": "evidence:g002", "relation": "motivated_by"},
            {"source": "hypothesis:g003", "target": "problem:g003", "relation": "explains"},
            {"source": "experiment:g003", "target": "hypothesis:g003", "relation": "tests"},
        ], "evidence_node": "pending_after_execution",
    })


def verify_preparation() -> None:
    path = G3 / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G3 prepare-only summary missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (summary.get("query_count") != 56 or len(rows) != 56 or
            any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows) or
            context.get("db_description_mode") != "base" or
            context.get("query_timeout_sec") != 1200):
        raise RuntimeError("G3 prepare-only failed exact 56/base/no-hint/1200s contract")


def prepare(binding: dict) -> None:
    preregister(binding)
    output_root = G3 / "preflight"
    if (output_root / PREPARE_ID).exists():
        raise RuntimeError("G3 preparation already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (output_root / "prepare.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(command(output_root, PREPARE_ID, prepare_only=True),
                                cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"G3 prepare-only failed: exit {result.returncode}")
    verify_preparation()
    print(json.dumps({"status": "prepared", "query_count": 56}, sort_keys=True))


def launch(binding: dict) -> None:
    verify_preparation()
    preregister(binding)
    free = shutil.disk_usage(G3).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G3 launch space below 5 GiB: {free} bytes")
    output_root = G3 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g003_launch_claim.json"
    if output.exists() or claim.exists():
        raise RuntimeError("G3 already has formal output or exclusive launch claim")
    key = sys.stdin.readline().strip()
    if not key or any(char.isspace() for char in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    output_root.mkdir(parents=True, exist_ok=True)
    args = command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g003_launch_claim_v1",
        "claimed_at_utc": now(), "binding": binding,
        "pre_execution_sha256": digest(GRAPH / "g003_pre_execution.json"),
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
    write_new(GRAPH / "g003_launch_manifest.json", {
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
