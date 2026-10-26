#!/usr/bin/env python3
"""Freeze, preflight, and uniquely launch the G5 diagnostic on ct104."""

from __future__ import annotations

import argparse
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
G5 = BASE / "g005_revision001"
SOURCE = G5 / "source"
BINDINGS = G5 / "bindings"
GRAPH = BASE / "graph"
PYTHON = Path("/srv/text2sql/.venv/bin/python")
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
RUNNER = SOURCE / "experiments/run_multi_query_baseline.py"
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
POLICY = SOURCE / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
PREPARE_ID = "baseline_g005_provenance_prepare"
RUN_ID = "baseline_g005_provenance_nohint_56_v1"
SOURCE_TREE_SHA = "b26ec227aba71e4fa90c712de31bc499fcc23d5b64ffd6eb7e16bd6cb6a0ae95"
PARENT_SHA = "e89a4f905425162682426c4dc8a058f3490e540069908c875b7d108c74ecc8a3"
G4_GRAPH_SHA = "fdb9de4a70e4b18c95845b3c6ac753f4650bdca7b6be370de92071a0ce6c2eda"
RESEARCH_SHA = "492a54d4f2b30f4b70ffc4c2c7134b5443fb4bcc86e384b04ec148966ba37426"
IMPLEMENTATION_SHA = "8d5e0bf5bd3a368f500510cbd6260d2691e27cb6c42b4062b34a3e98702e4d3d"
ADMISSION_SHA = "d599074b3aac26a2b82a63dc464224f730d14797a7834290b4747ddbdc1839be"
BATCH_SHA = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
POLICY_SHA = "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797"
MIN_FREE_BYTES = 5 * 1024**3


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_tree_hash() -> str:
    path = SOURCE / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g4_manifest", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G5 source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    if len(rows) != 92:
        raise RuntimeError("G5 source file count differs")
    return module.source_manifest_hash(rows)


def verify_inputs() -> dict:
    expected = {
        BINDINGS / "admission.json": ADMISSION_SHA,
        BINDINGS / "research_result.json": RESEARCH_SHA,
        BINDINGS / "implementation_manifest.json": IMPLEMENTATION_SHA,
        GRAPH / "g004_graph.json": G4_GRAPH_SHA,
        BATCH: BATCH_SHA,
        REGISTRY: REGISTRY_SHA,
        POLICY: POLICY_SHA,
    }
    if any(not path.is_file() or digest(path) != wanted for path, wanted in expected.items()):
        raise RuntimeError("G5 input hash or parent Graph differs")
    if source_tree_hash() != SOURCE_TREE_SHA or not PYTHON.is_file() or not UPSTREAM.is_dir():
        raise RuntimeError("G5 source or Python/DAB runtime differs")
    admission = json.loads((BINDINGS / "admission.json").read_text(encoding="utf-8"))
    research = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    if (
        admission["parent_tree_sha256"] != PARENT_SHA
        or admission["candidate_tree_sha256"] != SOURCE_TREE_SHA
        or admission["g4_graph_sha256"] != G4_GRAPH_SHA
        or research["experiment"]["code_parent_tree_sha256"] != PARENT_SHA
        or research["experiment"]["fixed_protocol"]["frozen_task_count"] != 56
        or research["experiment"]["fixed_protocol"]["hints"] is not False
        or research["experiment"]["fixed_protocol"]["per_task_wall_timeout_seconds"] != 1200
    ):
        raise RuntimeError("G5 admission or protocol differs")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("G5 task selection is not exact 56")
    return {
        "generation": 5,
        "parent_tree_sha256": PARENT_SHA,
        "candidate_tree_sha256": SOURCE_TREE_SHA,
        "g4_graph_sha256": G4_GRAPH_SHA,
        "admission_sha256": ADMISSION_SHA,
        "research_result_sha256": RESEARCH_SHA,
        "implementation_manifest_sha256": IMPLEMENTATION_SHA,
        "batch_sha256": BATCH_SHA,
        "registry_sha256": REGISTRY_SHA,
        "policy_sha256": POLICY_SHA,
        "query_count": 56,
        "description_mode": "full_db_description_no_hints",
        "query_timeout_sec": 1200,
        "timeout_scoring": "failure_in_fixed_56_denominator",
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


def freeze(binding: dict) -> None:
    path = GRAPH / "g005_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")).get("binding") != binding:
            raise RuntimeError("G5 pre-execution binding changed")
        return
    research = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    nodes = [
        {**research[key], "id": f"{key}:g005", "kind": key}
        for key in ("problem", "hypothesis", "experiment")
    ]
    nodes[-1]["candidate_source_tree_sha256"] = SOURCE_TREE_SHA
    nodes[-1]["evaluation_run_id"] = RUN_ID
    write_new(path, {
        "schema_version": "dab_research_graph_g005_pre_execution_v1",
        "generation": 5,
        "created_at_utc": now(),
        "status": "pre_registered_before_evaluation",
        "binding": binding,
        "nodes": nodes,
        "edges": research["cross_generation_relations"] + [
            {"source": "problem:g005", "target": "evidence:g004", "relation": "motivated_by"},
            {"source": "hypothesis:g005", "target": "problem:g005", "relation": "explains"},
            {"source": "experiment:g005", "target": "hypothesis:g005", "relation": "tests"},
        ],
        "evidence_node": "pending_after_execution",
    })


def verify_preparation() -> None:
    path = G5 / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G5 prepare-only summary missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (
        summary.get("query_count") != 56 or len(rows) != 56
        or any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows)
        or context.get("db_description_mode") != "base"
        or context.get("query_timeout_sec") != 1200
    ):
        raise RuntimeError("G5 prepare-only failed exact 56/base/no-hint/1200s")


def prepare(binding: dict) -> None:
    freeze(binding)
    output_root = G5 / "preflight"
    if (output_root / PREPARE_ID).exists():
        raise RuntimeError("G5 preparation already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (output_root / "prepare.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(command(output_root, PREPARE_ID, prepare_only=True),
                                cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"G5 prepare-only failed: exit {result.returncode}")
    verify_preparation()
    print(json.dumps({"status": "prepared", "query_count": 56}, sort_keys=True))


def infrastructure_preflight() -> dict:
    checks = [
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        ["docker", "exec", "dab-postgres", "pg_isready"],
        ["docker", "inspect", "-f", "{{.State.Running}}", "dab-mongo"],
    ]
    results = [subprocess.run(item, capture_output=True, text=True, timeout=15) for item in checks]
    if any(result.returncode != 0 for result in results) or results[-1].stdout.strip() != "true":
        raise RuntimeError("G5 Docker or database preflight failed")
    import openai  # noqa: F401
    import psycopg2  # noqa: F401
    return {"docker": True, "postgres": True, "mongo": True, "python_dab_imports": True}


def model_preflight(key: str) -> dict:
    body = json.dumps({
        "model": "deepseek-flash", "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 8, "stream": False,
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"G5 model preflight HTTP failure: {exc.code}") from None
    except Exception as exc:
        raise RuntimeError(f"G5 model preflight transport failure: {type(exc).__name__}") from None
    choices = payload.get("choices") if isinstance(payload, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    if status != 200 or not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("G5 model preflight response protocol invalid")
    return {"http_status": 200, "model_requested": "deepseek-flash",
            "response_protocol_ok": True, "task_content_sent": False}


def launch(binding: dict) -> None:
    verify_preparation()
    freeze(binding)
    free = shutil.disk_usage(G5).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G5 launch space below 5 GiB: {free} bytes")
    output_root = G5 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g005_launch_claim.json"
    manifest = GRAPH / "g005_launch_manifest.json"
    preflight = GRAPH / "g005_preflight.json"
    if output.exists() or claim.exists() or manifest.exists() or preflight.exists():
        raise RuntimeError("G5 formal output, claim, manifest, or preflight already exists")
    key = sys.stdin.readline().strip()
    if not key or any(character.isspace() for character in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    infra = infrastructure_preflight()
    probe = model_preflight(key)
    write_new(preflight, {
        "schema_version": "dab_research_graph_g005_preflight_v1", "created_at_utc": now(),
        "status": "passed", "binding": binding, "free_bytes": free,
        "infrastructure": infra, "model_probe": probe,
        "prepare_summary_sha256": digest(G5 / "preflight" / PREPARE_ID / "multi_query_summary.json"),
    })
    args = command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g005_launch_claim_v1", "claimed_at_utc": now(),
        "binding": binding, "pre_execution_sha256": digest(GRAPH / "g005_pre_execution.json"),
        "preflight_sha256": digest(preflight), "command": args, "status": "claimed_exclusive",
    }
    write_new(claim, payload)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = output_root / "launcher.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(args, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write_new(manifest, {
        **payload, "launched_at_utc": now(), "pid": process.pid,
        "output": str(output), "log_path": str(log_path),
        "credential_env_name": "DEEPSEEK_API_KEY", "launch_free_bytes": free,
    })
    print(json.dumps({"status": "launched", "pid": process.pid, "run_id": RUN_ID,
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
