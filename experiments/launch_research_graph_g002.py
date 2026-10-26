#!/usr/bin/env python3
"""Verify, preregister, prepare, and uniquely launch the frozen G2 run."""

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
G2 = BASE / "g002_revision001"
SOURCE = G2 / "source"
BINDINGS = G2 / "bindings"
GRAPH = BASE / "graph"
PYTHON = Path("/srv/text2sql/.venv/bin/python")
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
RUNNER = SOURCE / "experiments/run_multi_query_baseline.py"
AGENT = SOURCE / "experiments/run_dab_tool_agent.py"
STAGE = SOURCE / "experiments/g002_lifecycle_stage.py"
POLICY = SOURCE / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
PREPARE_ID = "baseline_g002_lifecycle_prepare"
RUN_ID = "baseline_g002_lifecycle_nohint_56_v1"
HASHES = {
    GRAPH / "g001_graph.json": "c8d35afeb677d018c76711737df8c30b468e1574c18d7450702188a857196b9b",
    BINDINGS / "admission.json": "c3205fb07022a778cff9a76c0f2e8f1b3c21c6fa0378c444a029993b8b7233bb",
    BINDINGS / "research_result.json": "56d5a3b376a335cca3f4289ee955addaa5ae017a6d7c3b14915bfe9b2b5411e3",
    BINDINGS / "research_canonical_binding.json": "b72dbd78f0dc112ccb08467ad8024a66bba2b86366b7612b49f6a611272091d5",
    RUNNER: "7e8cd381690bee6551f6ee2047a1abdf1b1993433fa03edfdd36ce3804573549",
    AGENT: "31d1b3fdbb21f6313b5e8f0a1ca2eacd6096ac2922cfe5abacec5218cdd1a66a",
    STAGE: "ce017cf6820b6dc9b329d30824ecee4305dbf3e695dbb298676c5264d70f8b00",
    POLICY: "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797",
    BATCH: "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7",
    REGISTRY: "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff",
}
SOURCE_TREE_SHA = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"
PARENT_TREE_SHA = "8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d"
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
            raise RuntimeError(f"Frozen G2 input missing or changed: {path}")
    if not PYTHON.is_file() or not UPSTREAM.is_dir():
        raise RuntimeError("Frozen upstream runtime is unavailable")
    spec = importlib.util.spec_from_file_location(
        "g2_manifest", SOURCE / "experiments/intent_candidate_workspace.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("G2 source manifest module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    if module.source_manifest_hash(rows) != SOURCE_TREE_SHA or len(rows) != 81:
        raise RuntimeError("G2 candidate source tree differs from admission")
    admission = json.loads((BINDINGS / "admission.json").read_text(encoding="utf-8"))
    if (admission.get("parent_tree_sha256") != PARENT_TREE_SHA or
            admission.get("candidate_tree_sha256") != SOURCE_TREE_SHA or
            admission.get("g1_graph_sha256") != HASHES[GRAPH / "g001_graph.json"] or
            admission.get("research_result_sha256") != HASHES[BINDINGS / "research_result.json"]):
        raise RuntimeError("G2 admission binding differs")
    decision = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    if (decision.get("research_ready") is not True or
            decision.get("implementation_ready") is not True or
            decision["experiment"]["code_parent"] != "g001_deadline_reserve"):
        raise RuntimeError("G2 research decision is not implementation-ready")
    canonical = json.loads((BINDINGS / "research_canonical_binding.json").read_text(encoding="utf-8"))
    if canonical.get("canonical_result_sha256") != HASHES[BINDINGS / "research_result.json"]:
        raise RuntimeError("G2 research canonicalization binding differs")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("G2 batch is not exactly 56 registered tasks")
    return {
        "g1_graph_sha256": HASHES[GRAPH / "g001_graph.json"],
        "parent_tree_sha256": PARENT_TREE_SHA,
        "candidate_tree_sha256": SOURCE_TREE_SHA,
        "admission_sha256": HASHES[BINDINGS / "admission.json"],
        "research_result_sha256": HASHES[BINDINGS / "research_result.json"],
        "agent_sha256": HASHES[AGENT], "runner_sha256": HASHES[RUNNER],
        "stage_sha256": HASHES[STAGE], "policy_sha256": HASHES[POLICY],
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
    path = GRAPH / "g002_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8"))["binding"] != binding:
            raise RuntimeError("G2 pre-execution binding changed")
        return
    decision = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    write_new(path, {
        "schema_version": "dab_research_graph_g002_pre_execution_v1",
        "generation": 2, "created_at_utc": now(),
        "status": "pre_registered_before_evaluation", "binding": binding,
        "nodes": [decision["problem"], decision["hypothesis"], {
            **decision["experiment"], "candidate_source_tree_sha256": SOURCE_TREE_SHA,
            "evaluation_run_id": RUN_ID,
        }],
        "edges": [
            {"source": "problem:g002", "target": "evidence:g001", "relation": "motivated_by"},
            {"source": "hypothesis:g002", "target": "problem:g002", "relation": "explains"},
            {"source": "experiment:g002", "target": "hypothesis:g002", "relation": "tests"},
        ], "evidence_node": "pending_after_execution",
    })


def verify_preparation() -> None:
    path = G2 / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G2 prepare-only summary missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (summary.get("query_count") != 56 or len(rows) != 56 or
            any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows) or
            context.get("db_description_mode") != "base" or
            context.get("query_timeout_sec") != 1200):
        raise RuntimeError("G2 prepare-only failed exact 56/base/no-hint/1200s contract")


def prepare(binding: dict) -> None:
    preregister(binding)
    output_root = G2 / "preflight"
    if (output_root / PREPARE_ID).exists():
        raise RuntimeError("G2 preparation already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (output_root / "prepare.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(command(output_root, PREPARE_ID, prepare_only=True),
                                cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"G2 prepare-only failed: exit {result.returncode}")
    verify_preparation()
    print(json.dumps({"status": "prepared", "query_count": 56}, sort_keys=True))


def launch(binding: dict) -> None:
    verify_preparation()
    preregister(binding)
    free = shutil.disk_usage(G2).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G2 launch space below 5 GiB: {free} bytes")
    output_root = G2 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g002_launch_claim.json"
    if output.exists() or claim.exists():
        raise RuntimeError("G2 already has formal output or exclusive launch claim")
    key = sys.stdin.readline().strip()
    if not key or any(char.isspace() for char in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    output_root.mkdir(parents=True, exist_ok=True)
    args = command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g002_launch_claim_v1",
        "claimed_at_utc": now(), "binding": binding,
        "pre_execution_sha256": digest(GRAPH / "g002_pre_execution.json"),
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
    write_new(GRAPH / "g002_launch_manifest.json", {
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
