#!/usr/bin/env python3
"""Freeze, preflight, and uniquely launch the G11 structural-ledger run."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
G11 = BASE / "g011_solution_loop_revision001"
SOURCE = G11 / "source"
BINDINGS = G11 / "bindings"
GRAPH = BASE / "graph"
PYTHON = Path("/srv/text2sql/.venv/bin/python")
UPSTREAM = Path("/srv/text2sql/external/DataAgentBench_official")
RUNNER = SOURCE / "experiments/run_multi_query_baseline.py"
BATCH = SOURCE / "dab_corpus/batches/dataset17_half56_baseline_v1_20261010.json"
REGISTRY = SOURCE / "dab_corpus/registry.json"
POLICY = SOURCE / "prompts/dab/dab_tool_agent_policy_zero_start.txt"
AUTHORING_POLICY = SOURCE / "prompts/dab/g011_plan_evidence_authoring_policy.txt"

PREPARE_ID = "g011_structural_plan_evidence_ledger_prepare"
RUN_ID = "g011_structural_plan_evidence_ledger_nohint_56_v1"
SOURCE_TREE_SHA256 = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
PARENT_TREE_SHA256 = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
G10_GRAPH_SHA256 = "2426502a697c988c77edc134bba0a4dd9612543733d19ce9d7bb3107083f3b3a"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
IMPLEMENTATION_SHA256 = "44a7a9508f8f1c68ab0ab70dfb3c820ca8f61eeefe880d1bc37453f614c75675"
ADMISSION_SHA256 = "9121bfb8a6797d55086c18f433b067addd3df8f2ed0a950530442c21423ad068"
ASSEMBLY_SHA256 = "e251b93d3e1d98b2acbb095a8ea133f3e1a9da16f64ebdd3d471dc1837ad48d7"
MEMORY_SHA256 = "0c83c560e7c94522ca2b618f7cec6b8b7a81c833c6e054ff0f18dfa7d1d481bf"
BATCH_SHA256 = "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7"
REGISTRY_SHA256 = "7aba9897753c6a3394f1a6d0b27df35a39ac05ca099b815a1e2b9c6d931218ff"
POLICY_SHA256 = "d6e022a462960e961087e618087dcd1d884bab49389acae64c463583d8643797"
AUTHORING_POLICY_SHA256 = "111eb0726c7a9c795ace1ef96267d085294b6d2e8257d984117763427e50b277"
UPSTREAM_DATA_AGENT_SHA256 = "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a"
MIN_FREE_BYTES = 5 * 1024**3


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def source_tree_hash() -> tuple[str, int]:
    module_path = SOURCE / "experiments/intent_candidate_workspace.py"
    spec = importlib.util.spec_from_file_location("g011_solution_loop_manifest", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G11 source manifest unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = sorted(module.source_tree_manifest(SOURCE), key=lambda row: row["path"].lower())
    return module.source_manifest_hash(rows), len(rows)


def verify_inputs() -> dict:
    expected = {
        BINDINGS / "admission.json": ADMISSION_SHA256,
        BINDINGS / "assembly.json": ASSEMBLY_SHA256,
        BINDINGS / "research_result.json": RESEARCH_SHA256,
        BINDINGS / "implementation_manifest.json": IMPLEMENTATION_SHA256,
        BINDINGS / "research_memory_v5.json": MEMORY_SHA256,
        GRAPH / "g010_graph.json": G10_GRAPH_SHA256,
        BATCH: BATCH_SHA256,
        REGISTRY: REGISTRY_SHA256,
        POLICY: POLICY_SHA256,
        AUTHORING_POLICY: AUTHORING_POLICY_SHA256,
        UPSTREAM / "common_scaffold/DataAgent.py": UPSTREAM_DATA_AGENT_SHA256,
    }
    if any(not path.is_file() or digest(path) != wanted for path, wanted in expected.items()):
        raise RuntimeError("G11 input, parent Graph, policy, or upstream source hash differs")
    tree, count = source_tree_hash()
    if tree != SOURCE_TREE_SHA256 or count != 114 or not PYTHON.is_file() or not UPSTREAM.is_dir():
        raise RuntimeError("G11 staged source, Python, or DAB runtime differs")

    admission = json.loads((BINDINGS / "admission.json").read_text(encoding="utf-8"))
    research = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    spec = research["formal_spec"]
    protocol = spec["fixed_protocol"]
    if (
        admission.get("candidate_tree_sha256") != SOURCE_TREE_SHA256
        or admission.get("parent_tree_sha256") != PARENT_TREE_SHA256
        or admission.get("parent_graph_sha256") != G10_GRAPH_SHA256
        or admission.get("formal_activation", {}).get("formal_launcher_must_pass_flag") is not True
        or spec.get("code_parent", {}).get("candidate_tree_sha256") != PARENT_TREE_SHA256
        or protocol.get("frozen_task_count") != 56
        or protocol.get("hints") is not False
        or protocol.get("description_mode") != "full_db_description_no_hints"
        or protocol.get("per_task_wall_timeout_seconds") != 1200
        or protocol.get("formal_runs") != 1
        or protocol.get("second_arm") is not False
        or protocol.get("probe_run") is not False
        or protocol.get("sham_run") is not False
    ):
        raise RuntimeError("G11 admission, activation, or fixed protocol differs")
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = batch.get("query_ids")
    known = {row["query_id"] for row in registry.get("queries", [])}
    if not isinstance(ids, list) or len(ids) != 56 or len(set(ids)) != 56 or not set(ids) <= known:
        raise RuntimeError("G11 task selection is not exact 56")
    return {
        "generation": 11,
        "mechanism_id": "mech_g011_structural_plan_evidence_ledger",
        "code_parent_generation": 7,
        "parent_tree_sha256": PARENT_TREE_SHA256,
        "candidate_tree_sha256": SOURCE_TREE_SHA256,
        "parent_graph_generation": 10,
        "parent_graph_sha256": G10_GRAPH_SHA256,
        "admission_sha256": ADMISSION_SHA256,
        "assembly_sha256": ASSEMBLY_SHA256,
        "research_result_sha256": RESEARCH_SHA256,
        "implementation_manifest_sha256": IMPLEMENTATION_SHA256,
        "research_memory_v5_sha256": MEMORY_SHA256,
        "batch_sha256": BATCH_SHA256,
        "registry_sha256": REGISTRY_SHA256,
        "policy_sha256": POLICY_SHA256,
        "authoring_policy_sha256": AUTHORING_POLICY_SHA256,
        "upstream_data_agent_sha256": UPSTREAM_DATA_AGENT_SHA256,
        "query_count": 56,
        "description_mode": "full_db_description_no_hints",
        "query_timeout_sec": 1200,
        "timeout_scoring": "failure_in_fixed_56_denominator",
        "formal_activation_flag": "--enable-g011-plan-evidence-ledger",
    }


def command(output_root: Path, run_id: str, *, prepare_only: bool) -> list[str]:
    args = [
        str(PYTHON),
        str(RUNNER),
        "--batch",
        str(BATCH),
        "--registry",
        str(REGISTRY),
        "--dab-root",
        str(UPSTREAM),
        "--source-root",
        str(SOURCE),
        "--dab-upstream-root",
        str(UPSTREAM),
        "--output-root",
        str(output_root),
        "--run-id",
        run_id,
        "--python",
        str(PYTHON),
        "--deployment-name",
        "deepseek-flash",
        "--openai-compatible-base-url",
        "https://api.deepseek.com/v1",
        "--openai-compatible-api-key-env",
        "DEEPSEEK_API_KEY",
        "--max-iterations",
        "0",
        "--llm-timeout",
        "600",
        "--llm-retries",
        "2",
        "--llm-retry-sleep",
        "20",
        "--client-max-retries",
        "0",
        "--query-timeout-sec",
        "1200",
        "--postgres-statement-timeout-ms",
        "1080000",
        "--workers",
        "4",
        "--skip-observer",
        "--enable-g011-plan-evidence-ledger",
    ]
    if prepare_only:
        args.append("--prepare-only")
    return args


def freeze(binding: dict) -> None:
    path = GRAPH / "g011_solution_loop_pre_execution.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")).get("binding") != binding:
            raise RuntimeError("G11 solution-loop pre-execution binding changed")
        return
    research = json.loads((BINDINGS / "research_result.json").read_text(encoding="utf-8"))
    target = research["research_target"]
    spec = research["formal_spec"]
    nodes = [
        {
            "id": "problem:g011",
            "kind": "problem",
            "mechanism_id": target["mechanism_id"],
            "statement": target["problem"],
            "scope": "structural plan/evidence state and guidance; semantic validity remains unknown",
        },
        {
            "id": "hypothesis:g011",
            "kind": "hypothesis",
            "mechanism_id": target["mechanism_id"],
            "statement": target["hypothesis"],
            "prediction_policy": spec["behavioral_effect"]["prediction_policy"],
        },
        {
            "id": "experiment:g011",
            "kind": "experiment",
            "mechanism_id": target["mechanism_id"],
            "statement": spec["measurement_plan"]["design"],
            "formal_spec": spec,
            "candidate_source_tree_sha256": SOURCE_TREE_SHA256,
            "evaluation_run_id": RUN_ID,
            "activation_flag": "--enable-g011-plan-evidence-ledger",
        },
    ]
    write_new(
        path,
        {
            "schema_version": "dab_research_graph_g011_solution_loop_pre_execution_v1",
            "generation": 11,
            "created_at_utc": now(),
            "status": "pre_registered_before_evaluation",
            "binding": binding,
            "nodes": nodes,
            "edges": [
                {"source": "problem:g011", "target": "evidence:g007", "relation": "motivated_by"},
                {"source": "problem:g011", "target": "evidence:g008", "relation": "motivated_by"},
                {"source": "problem:g011", "target": "evidence:g009", "relation": "motivated_by"},
                {"source": "problem:g011", "target": "evidence:g010", "relation": "motivated_by"},
                {"source": "hypothesis:g011", "target": "problem:g011", "relation": "explains"},
                {"source": "experiment:g011", "target": "hypothesis:g011", "relation": "tests"},
                {"source": "experiment:g011", "target": "experiment:g007", "relation": "derives_code_from"},
            ],
            "evidence_node": "pending_after_execution",
        },
    )


def verify_preparation() -> dict:
    path = G11 / "preflight" / PREPARE_ID / "multi_query_summary.json"
    if not path.is_file():
        raise RuntimeError("G11 prepare-only summary missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("per_query_feedback", [])
    context = summary.get("execution_context", {})
    if (
        summary.get("query_count") != 56
        or len(rows) != 56
        or any(row.get("status") != "prepared" or row.get("run_exit_code") != 0 for row in rows)
        or context.get("db_description_mode") != "base"
        or context.get("query_timeout_sec") != 1200
    ):
        raise RuntimeError("G11 prepare-only failed exact56/base/no-hint/1200s")
    return {"summary_sha256": digest(path), "query_count": 56}


def prepare(binding: dict) -> None:
    freeze(binding)
    output_root = G11 / "preflight"
    if (output_root / PREPARE_ID).exists():
        raise RuntimeError("G11 preparation already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with (output_root / "prepare.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(
            command(output_root, PREPARE_ID, prepare_only=True),
            cwd=SOURCE,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"G11 prepare-only failed: exit {result.returncode}")
    verified = verify_preparation()
    print(json.dumps({"status": "prepared", **verified}, sort_keys=True))


def assert_server_idle() -> dict:
    result = subprocess.run(
        ["pgrep", "-af", "run_multi_query_baseline.py|run_dab_tool_agent.py"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    own_pid = os.getpid()
    other = [line for line in rows if not line.startswith(f"{own_pid} ")]
    if other:
        raise RuntimeError("Another DAB formal runner is active; refusing G11 launch")
    return {"other_dab_formal_process_count": 0}


def infrastructure_preflight() -> dict:
    checks = [
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        ["docker", "exec", "dab-postgres", "pg_isready"],
        ["docker", "inspect", "-f", "{{.State.Running}}", "dab-mongo"],
    ]
    results = [subprocess.run(item, capture_output=True, text=True, timeout=15) for item in checks]
    if any(result.returncode != 0 for result in results) or results[-1].stdout.strip() != "true":
        raise RuntimeError("G11 Docker or database preflight failed")
    import openai  # noqa: F401
    import psycopg2  # noqa: F401
    return {"docker": True, "postgres": True, "mongo": True, "python_dab_imports": True}


def _provider_request(key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise RuntimeError(f"G11 model preflight HTTP status {response.status}")
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"G11 model preflight HTTP failure: {exc.code}") from None
    except Exception as exc:
        raise RuntimeError(f"G11 model preflight transport failure: {type(exc).__name__}") from None
    choices = body.get("choices") if isinstance(body, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    if not isinstance(message, dict):
        raise RuntimeError("G11 model preflight response protocol invalid")
    return message


def model_and_carrier_preflight(key: str) -> dict:
    basic = _provider_request(
        key,
        {
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 8,
            "stream": False,
            "temperature": 0,
        },
    )
    if not isinstance(basic.get("content"), str):
        raise RuntimeError("G11 basic model response content missing")

    carrier_text = (
        'G011_PLAN_RECORD_V1 {"schema":"g011_plan_record_v1","plan_id":"p1",'
        '"revision":1,"supersedes":null,"steps":[]}'
    )
    tool_name = "record_self_observation"
    tool_message = _provider_request(
        key,
        {
            "model": "deepseek-flash",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "No task data is present. Call the required tool once with the exact supplied "
                        "synthetic freeform string."
                    ),
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": "Record a synthetic no-task structural carrier fixture.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "freeform": {"type": "string", "description": carrier_text},
                            },
                            "required": ["freeform"],
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
            "max_tokens": 160,
            "stream": False,
            "temperature": 0,
        },
    )
    calls = tool_message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise RuntimeError("G11 provider did not return the forced no-task carrier tool call")
    function = calls[0].get("function") if isinstance(calls[0], dict) else None
    if not isinstance(function, dict) or function.get("name") != tool_name:
        raise RuntimeError("G11 provider carrier tool name differs")
    try:
        arguments = json.loads(function.get("arguments", ""))
    except (TypeError, ValueError):
        raise RuntimeError("G11 provider carrier arguments are not JSON") from None
    freeform = arguments.get("freeform") if isinstance(arguments, dict) else None
    if not isinstance(freeform, str) or not freeform.startswith("G011_PLAN_RECORD_V1"):
        raise RuntimeError("G11 provider rejected or changed the declared freeform carrier")
    try:
        record = json.loads(freeform[len("G011_PLAN_RECORD_V1") :].strip())
    except (TypeError, ValueError):
        raise RuntimeError("G11 provider carrier record is not JSON") from None
    if set(record) != {"schema", "plan_id", "revision", "supersedes", "steps"}:
        raise RuntimeError("G11 provider carrier record fields differ")
    return {
        "http_status": 200,
        "model_requested": "deepseek-flash",
        "basic_response_protocol_ok": True,
        "forced_tool_response_protocol_ok": True,
        "declared_freeform_carrier_accepted": True,
        "task_content_sent": False,
        "raw_response_persisted": False,
    }


def real_upstream_probe() -> dict:
    sys.path.insert(0, str(SOURCE))
    sys.path.insert(0, str(UPSTREAM))
    from common_scaffold import DataAgent as upstream
    from experiments.g011_plan_evidence_record import ACTION_PROCEED
    from experiments.g011_runtime_plan_evidence import install_plan_evidence_ledger

    class Tool:
        def __init__(self) -> None:
            self.arguments: list[dict] = []

        def exec(self, arguments: dict) -> dict:
            self.arguments.append(dict(arguments))
            return {"success": True, "result": {"synthetic": True}}

    class Call:
        def __init__(self, identifier: str, name: str, arguments: dict) -> None:
            self.id = identifier
            self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))

        def model_dump(self) -> dict:
            return {
                "id": self.id,
                "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments},
            }

    class Response:
        def __init__(self, calls: list[Call]) -> None:
            self.tool_calls = calls
            self.content = None

    with tempfile.TemporaryDirectory(prefix="g011_no_task_upstream_") as location:
        root = Path(location)
        args = SimpleNamespace(
            enable_g011_plan_evidence_ledger=True,
            disable_self_observation_tool=False,
            self_observation_tool_name="record_self_observation",
            g011_sidecar_path=root / "g011_plan_evidence.jsonl",
        )
        state = install_plan_evidence_ledger(upstream, args)
        if state.get("installed") is not True or state.get("authoring_policy_installed") is not True:
            raise RuntimeError("G11 did not install on the real upstream DataAgent class")
        agent = upstream.DataAgent.__new__(upstream.DataAgent)
        tool = Tool()
        agent.logger = logging.getLogger("g011_no_task_upstream")
        agent.tools = {"query_db": tool}
        agent.messages = []
        agent.result_storage = {}
        agent.file_storage_dir = root
        agent.tool_log_path = root / "tool_calls.jsonl"
        agent.final_result = None
        agent.terminate_reason = None
        agent.llm_call_count = 1
        agent.max_iterations = 10
        agent.handle_reponse(Response([Call("call-q1", "query_db", {"query": "synthetic"})]))
        record = {
            "schema": "g011_plan_record_v1",
            "plan_id": "p1",
            "revision": 1,
            "supersedes": None,
            "steps": [{"step_id": "s1", "refs": ["call-q1"]}],
        }
        carrier = "G011_PLAN_RECORD_V1 " + json.dumps(record, sort_keys=True)
        agent.handle_reponse(
            Response(
                [
                    Call(
                        "call-q2",
                        "query_db",
                        {"query": "synthetic", "self_observation": {"freeform": carrier}},
                    )
                ]
            )
        )
        adapter = getattr(agent, "_g011_plan_evidence_adapter", None)
        ledger = getattr(adapter, "ledger", None)
        assessment = ledger.active_assessment() if ledger is not None else None
        if assessment is None or assessment.directive.code != ACTION_PROCEED:
            raise RuntimeError("G11 real-upstream structural response-boundary fixture failed")
        if len(tool.arguments) != 2 or any("self_observation" in row for row in tool.arguments):
            raise RuntimeError("G11 real-upstream carrier was not redacted before dispatch")
        per_agent_state = getattr(agent, "_g011_plan_evidence_state", {})
        if per_agent_state.get("redacted_plan_record_observation_count") != 1:
            raise RuntimeError("G11 real-upstream redaction count differs")
    return {
        "real_upstream_source_hash_bound": True,
        "installed_on_real_data_agent": True,
        "response_boundary_fixture_passed": True,
        "prior_dispatch_reference_resolved_structurally": True,
        "carrier_redacted_before_dispatch": True,
        "semantic_support_claimed": False,
        "task_content_used": False,
    }


def launch(binding: dict) -> None:
    preparation = verify_preparation()
    freeze(binding)
    idle = assert_server_idle()
    free = shutil.disk_usage(G11).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"G11 launch space below 5 GiB: {free} bytes")
    output_root = G11 / "evaluation"
    output = output_root / RUN_ID
    claim = GRAPH / "g011_solution_loop_launch_claim.json"
    manifest = GRAPH / "g011_solution_loop_launch_manifest.json"
    preflight = GRAPH / "g011_solution_loop_preflight.json"
    if output.exists() or claim.exists() or manifest.exists() or preflight.exists():
        raise RuntimeError("G11 formal output, claim, manifest, or preflight already exists")
    key = sys.stdin.readline().strip()
    if not key or any(character.isspace() for character in key):
        raise RuntimeError("Missing or malformed DeepSeek credential")
    infrastructure = infrastructure_preflight()
    upstream_probe = real_upstream_probe()
    provider_probe = model_and_carrier_preflight(key)
    write_new(
        preflight,
        {
            "schema_version": "dab_research_graph_g011_solution_loop_preflight_v1",
            "created_at_utc": now(),
            "status": "passed",
            "binding": binding,
            "free_bytes": free,
            "server_idle": idle,
            "infrastructure": infrastructure,
            "real_upstream_probe": upstream_probe,
            "provider_probe": provider_probe,
            "prepare_summary_sha256": preparation["summary_sha256"],
        },
    )
    args = command(output_root, RUN_ID, prepare_only=False)
    payload = {
        "schema_version": "dab_research_graph_g011_solution_loop_launch_claim_v1",
        "claimed_at_utc": now(),
        "binding": binding,
        "pre_execution_sha256": digest(GRAPH / "g011_solution_loop_pre_execution.json"),
        "preflight_sha256": digest(preflight),
        "command": args,
        "status": "claimed_exclusive",
    }
    write_new(claim, payload)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DEEPSEEK_API_KEY"] = key
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = output_root / "launcher.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(
            args,
            cwd=SOURCE,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    write_new(
        manifest,
        {
            **payload,
            "launched_at_utc": now(),
            "pid": process.pid,
            "output": str(output),
            "log_path": str(log_path),
            "credential_env_name": "DEEPSEEK_API_KEY",
            "launch_free_bytes": free,
        },
    )
    print(
        json.dumps(
            {
                "status": "launched",
                "pid": process.pid,
                "run_id": RUN_ID,
                "output": str(output),
                "free_bytes_at_launch": free,
            },
            sort_keys=True,
        )
    )


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
