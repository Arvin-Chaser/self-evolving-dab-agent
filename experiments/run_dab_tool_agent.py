#!/usr/bin/env python3
"""Run the upstream DAB multi-turn tool-using DataAgent from this project.

This is the first bridge from the current generated_solve.py-based prototype
to a DAB-style workflow agent.  It intentionally keeps the upstream scaffold
outside this repository and writes a lightweight normalized run summary that
our later analyzers/archive code can consume.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAB_DATA_ROOT = Path("/home/m0st1ma/research/DataAgentBench")
DEFAULT_DAB_UPSTREAM_ROOT = Path("/home/m0st1ma/research/DataAgentBench_upstream")
DEFAULT_OUTPUT_ROOT = ROOT / "logs" / "dab_tool_agent"
DEFAULT_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL_MARKERS = ("qwen", "qwq", "qvq")


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = {"_parse_error": True, "raw": line}
        rows.append(value if isinstance(value, dict) else {"value": value})
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def resolve_defaults(args: argparse.Namespace) -> argparse.Namespace:
    data_root = Path(args.dab_data_root).resolve()
    query_dir = Path(args.query_dir).resolve() if args.query_dir else data_root / "query_PATENTS" / "query1"
    query_family_dir = query_dir.parent
    db_description = Path(args.db_description).resolve() if args.db_description else query_family_dir / "db_description_withhint.txt"
    if not db_description.exists():
        db_description = query_family_dir / "db_description.txt"
    db_config = Path(args.db_config).resolve() if args.db_config else query_family_dir / "db_config.yaml"
    args.dab_data_root = data_root
    args.query_dir = query_dir
    args.db_description = db_description
    args.db_config = db_config
    args.dab_upstream_root = Path(args.dab_upstream_root).resolve()
    args.output_root = Path(args.output_root).resolve()
    if not args.run_id:
        args.run_id = f"dab_tool_agent_{utc_slug()}"
    return args


def validate_paths(args: argparse.Namespace) -> None:
    required = {
        "dab_upstream_root": args.dab_upstream_root,
        "DataAgent.py": args.dab_upstream_root / "common_scaffold" / "DataAgent.py",
        "query_dir": args.query_dir,
        "query.json": args.query_dir / "query.json",
        "db_description": args.db_description,
        "db_config": args.db_config,
    }
    missing = [f"{name}: {path}" for name, path in required.items() if not Path(path).exists()]
    if missing:
        raise FileNotFoundError("Missing required DAB tool-agent path(s):\n" + "\n".join(missing))


def is_qwen_like_model(deployment_name: str) -> bool:
    name = deployment_name.lower()
    return any(marker in name for marker in QWEN_MODEL_MARKERS)


def first_env(names: list[str]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name)
        if value:
            return name, value
    return None, None


def normalize_openai_base_url(value: str | None) -> str:
    if not value:
        return DEFAULT_BAILIAN_BASE_URL
    base_url = value.strip()
    if not base_url:
        return DEFAULT_BAILIAN_BASE_URL
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1") or base_url.endswith("/compatible-mode/v1"):
        return base_url
    return f"{base_url}/compatible-mode/v1"


def qwen_bailian_config(args: argparse.Namespace) -> dict[str, Any]:
    key_env_candidates = [
        args.bailian_api_key_env,
        "DASHSCOPE_API_KEY",
        "dashscope_api_key",
        "BAILIAN_API_KEY",
        "DAB_TOOL_AGENT_API_KEY",
        "TOGETHER_API_KEY",
    ]
    key_env_candidates = [name for name in key_env_candidates if name]
    key_env, api_key = first_env(key_env_candidates)
    base_env, base_url_from_env = first_env(["DAB_TOOL_AGENT_BASE_URL", "DASHSCOPE_BASE_URL", "BAILIAN_BASE_URL"])
    base_url = normalize_openai_base_url(args.bailian_base_url or base_url_from_env)
    return {
        "provider": "bailian_dashscope",
        "api_key_env": key_env,
        "api_key": api_key,
        "api_key_present": bool(api_key),
        "base_url_env": base_env,
        "base_url": base_url,
    }


def import_upstream_data_agent(upstream_root: Path, args: argparse.Namespace | None = None):
    sys.path.insert(0, str(upstream_root))
    import importlib

    data_agent_module = importlib.import_module("common_scaffold.DataAgent")

    if args is not None and is_qwen_like_model(args.deployment_name):
        config = qwen_bailian_config(args)
        if not config["api_key_present"]:
            raise RuntimeError(
                "Qwen/DashScope API key is not visible. Set DASHSCOPE_API_KEY in the shell "
                "that launches this script, or pass --bailian-api-key-env with an existing env var."
            )

        original_openai = data_agent_module.OpenAI

        def bailian_openai_factory(*factory_args: Any, **factory_kwargs: Any):
            if factory_kwargs.get("base_url") == "https://api.together.xyz/v1":
                factory_kwargs["api_key"] = config["api_key"]
                factory_kwargs["base_url"] = config["base_url"]
            return original_openai(*factory_args, **factory_kwargs)

        data_agent_module.OpenAI = bailian_openai_factory

        prompt_builder = data_agent_module.prompt_builder
        original_init_messages = prompt_builder.init_messages

        def qwen_init_messages(user_query: str, db_description: str, deployment_name: str, system_prompt=prompt_builder.SYSTEM_PROMPT):
            if is_qwen_like_model(deployment_name):
                return original_init_messages(user_query, db_description, "gpt-qwen-compatible", system_prompt)
            return original_init_messages(user_query, db_description, deployment_name, system_prompt)

        prompt_builder.init_messages = qwen_init_messages

    return data_agent_module.DataAgent


def command_succeeds(command: list[str], timeout: int = 10) -> bool:
    try:
        proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def ensure_docker_ready(args: argparse.Namespace) -> str:
    if args.skip_docker_check:
        return "skipped"
    if command_succeeds(["docker", "info"], timeout=10):
        return "already_running"

    docker_desktop = Path("/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe")
    if docker_desktop.exists():
        subprocess.Popen([str(docker_desktop)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + args.docker_start_timeout
        while time.time() < deadline:
            if command_succeeds(["docker", "info"], timeout=10):
                return "started_docker_desktop"
            time.sleep(5)

    raise RuntimeError(
        "Docker is not available from WSL. Start Docker Desktop and enable WSL integration for Ubuntu, "
        "then rerun this command. The DAB execute_python tool requires Docker."
    )


def db_config_uses_postgres(db_config: Path) -> bool:
    return "db_type: postgres" in db_config.read_text(encoding="utf-8", errors="replace")


def docker_container_running(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def ensure_postgres_ready(args: argparse.Namespace) -> str:
    if args.skip_postgres_check or not db_config_uses_postgres(args.db_config):
        return "skipped"

    psql_wrapper = ROOT / "tools" / "psql_via_docker.sh"
    if psql_wrapper.exists() and not os.getenv("PG_CLIENT"):
        os.environ["PG_CLIENT"] = str(psql_wrapper)

    container = args.postgres_container
    if docker_container_running(container):
        status = "already_running"
    else:
        exists = subprocess.run(
            ["docker", "inspect", container],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode == 0
        if exists:
            subprocess.run(["docker", "start", container], check=True, stdout=subprocess.DEVNULL, timeout=30)
            status = "started_existing"
        else:
            subprocess.run(
                [
                    "docker", "run", "-d",
                    "--name", container,
                    "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                    "-p", "5432:5432",
                    "-v", f"{args.dab_data_root}:{args.dab_data_root}:ro",
                    "postgres:16",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                timeout=args.postgres_start_timeout,
            )
            status = "created"

    deadline = time.time() + args.postgres_start_timeout
    while time.time() < deadline:
        if command_succeeds(["docker", "exec", container, "pg_isready", "-U", "postgres"], timeout=10):
            return status
        time.sleep(2)
    raise RuntimeError(f"PostgreSQL container {container!r} did not become ready before timeout.")


def build_workflow_trace(upstream_run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    llm_rows = read_jsonl(upstream_run_dir / "llm_calls.jsonl")
    tool_rows = read_jsonl(upstream_run_dir / "tool_calls.jsonl")

    for idx, row in enumerate(llm_rows, start=1):
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        choices = response.get("choices") if isinstance(response.get("choices"), list) else []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        rows.append(
            {
                "event": "llm_call",
                "index": idx,
                "timestamp": row.get("timestamp"),
                "duration": row.get("duration"),
                "model": row.get("model"),
                "tool_call_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
                "has_content": bool(message.get("content")) if isinstance(message, dict) else False,
            }
        )

    for idx, row in enumerate(tool_rows, start=1):
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        rows.append(
            {
                "event": "tool_call",
                "index": idx,
                "tool_name": row.get("tool_name"),
                "success": result.get("success"),
                "args": row.get("args"),
                "validated_args": row.get("val_args"),
                "result_preview": result.get("preview"),
                "duration": row.get("time"),
                "start": row.get("start"),
                "end": row.get("end"),
            }
        )

    return rows


def copy_if_exists(src: Path, dst: Path) -> str | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)


def normalize_run_artifacts(*, args: argparse.Namespace, upstream_run_dir: Path, final_result: str | None, run_error: str | None) -> Path:
    normalized_dir = args.output_root / args.run_id
    normalized_dir.mkdir(parents=True, exist_ok=True)

    workflow_trace = build_workflow_trace(upstream_run_dir)
    append_jsonl(normalized_dir / "workflow_trace.jsonl", workflow_trace)

    final_agent = {}
    final_agent_path = upstream_run_dir / "final_agent.json"
    if final_agent_path.exists():
        try:
            final_agent = json.loads(final_agent_path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            final_agent = {"_parse_error": str(exc)}

    answer = final_result
    if answer is None:
        answer = final_agent.get("final_result") if isinstance(final_agent, dict) else None
    if answer is None:
        answer = ""
    (normalized_dir / "final_answer.txt").write_text(str(answer), encoding="utf-8")

    copied = {
        "llm_calls": copy_if_exists(upstream_run_dir / "llm_calls.jsonl", normalized_dir / "llm_calls.jsonl"),
        "tool_calls": copy_if_exists(upstream_run_dir / "tool_calls.jsonl", normalized_dir / "tool_calls.jsonl"),
        "final_agent": copy_if_exists(upstream_run_dir / "final_agent.json", normalized_dir / "final_agent.json"),
        "validation": copy_if_exists(upstream_run_dir / "validation.jsonl", normalized_dir / "validation.jsonl"),
        "execute_python_artifacts": copy_if_exists(
            upstream_run_dir / "execute_python_artifacts.jsonl",
            normalized_dir / "execute_python_artifacts.jsonl",
        ),
    }

    qwen_config = qwen_bailian_config(args) if is_qwen_like_model(args.deployment_name) else None
    if qwen_config is not None:
        qwen_config = {key: value for key, value in qwen_config.items() if key != "api_key"}

    summary = {
        "schema_version": "dab_tool_agent_run_v001",
        "status": "failed" if run_error else "completed",
        "run_id": args.run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deployment_name": args.deployment_name,
        "qwen_client_config": qwen_config,
        "docker_status": getattr(args, "docker_status", None),
        "postgres_status": getattr(args, "postgres_status", None),
        "pg_client": os.getenv("PG_CLIENT"),
        "query_dir": str(args.query_dir),
        "db_description": str(args.db_description),
        "db_config": str(args.db_config),
        "dab_upstream_root": str(args.dab_upstream_root),
        "upstream_run_dir": str(upstream_run_dir),
        "normalized_run_dir": str(normalized_dir),
        "final_answer_path": str(normalized_dir / "final_answer.txt"),
        "final_answer_nonempty": bool(str(answer).strip()),
        "final_answer_preview": str(answer)[:1000],
        "run_error": run_error,
        "llm_call_count": final_agent.get("llm_call_count") if isinstance(final_agent, dict) else None,
        "terminate_reason": final_agent.get("terminate_reason") if isinstance(final_agent, dict) else None,
        "workflow_event_count": len(workflow_trace),
        "tool_call_count": sum(1 for item in workflow_trace if item.get("event") == "tool_call"),
        "artifacts": copied,
    }
    write_json(normalized_dir / "summary.json", summary)
    return normalized_dir


def run_agent(args: argparse.Namespace) -> int:
    args = resolve_defaults(args)
    validate_paths(args)

    upstream_logs_dir = args.query_dir / "logs" / "data_agent" / args.run_id
    normalized_dir = args.output_root / args.run_id
    if upstream_logs_dir.exists() or normalized_dir.exists():
        raise FileExistsError(f"Run id already exists: {args.run_id}")

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.check_dependencies:
        summary = {
            "schema_version": "dab_tool_agent_dependency_check_v001",
            "status": "unknown",
            "run_id": args.run_id,
            "dab_upstream_root": str(args.dab_upstream_root),
            "python_executable": sys.executable,
        }
        try:
            DataAgent = import_upstream_data_agent(args.dab_upstream_root)
            if is_qwen_like_model(args.deployment_name):
                config = qwen_bailian_config(args)
                summary["qwen_client_config"] = {key: value for key, value in config.items() if key != "api_key"}
            summary.update({"status": "ok", "data_agent": f"{DataAgent.__module__}.{DataAgent.__name__}"})
            exit_code = 0
        except Exception as exc:
            summary.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            exit_code = 1
        write_json(normalized_dir / "dependency_check.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return exit_code

    if args.prepare_only:
        summary = {
            "schema_version": "dab_tool_agent_prepare_v001",
            "status": "prepared",
            "run_id": args.run_id,
            "query_dir": str(args.query_dir),
            "db_description": str(args.db_description),
            "db_config": str(args.db_config),
            "dab_upstream_root": str(args.dab_upstream_root),
            "would_write_upstream_run_dir": str(upstream_logs_dir),
            "would_write_normalized_run_dir": str(normalized_dir),
        }
        write_json(normalized_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    args.docker_status = ensure_docker_ready(args)
    args.postgres_status = ensure_postgres_ready(args)
    DataAgent = import_upstream_data_agent(args.dab_upstream_root, args)
    final_result: str | None = None
    run_error: str | None = None
    try:
        agent = DataAgent(
            query_dir=args.query_dir,
            db_description=args.db_description.read_text(encoding="utf-8", errors="replace"),
            db_config_path=str(args.db_config),
            deployment_name=args.deployment_name,
            exec_python_timeout=args.exec_python_timeout,
            max_iterations=args.max_iterations,
            root_name=args.run_id,
        )
        final_result = agent.run()
    except Exception as exc:  # Keep a normalized failure artifact for analyzers.
        run_error = f"{type(exc).__name__}: {exc}"

    run_dir = upstream_logs_dir if upstream_logs_dir.exists() else normalized_dir
    normalized = normalize_run_artifacts(
        args=args,
        upstream_run_dir=run_dir,
        final_result=final_result,
        run_error=run_error,
    )
    summary = json.loads((normalized / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if run_error else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dab-data-root", default=str(DEFAULT_DAB_DATA_ROOT))
    parser.add_argument("--dab-upstream-root", default=str(DEFAULT_DAB_UPSTREAM_ROOT))
    parser.add_argument("--query-dir")
    parser.add_argument("--db-description")
    parser.add_argument("--db-config")
    parser.add_argument("--deployment-name", default=os.environ.get("DAB_TOOL_AGENT_MODEL", "qwen-plus"))
    parser.add_argument("--bailian-api-key-env", default=os.environ.get("DAB_TOOL_AGENT_API_KEY_ENV"))
    parser.add_argument("--bailian-base-url", default=os.environ.get("DAB_TOOL_AGENT_BASE_URL"))
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_MAX_ITERATIONS", "20")))
    parser.add_argument("--exec-python-timeout", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_EXEC_TIMEOUT", "300")))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-id")
    parser.add_argument("--prepare-only", action="store_true", help="Resolve paths and write summary without calling the LLM/tools.")
    parser.add_argument("--check-dependencies", action="store_true", help="Try importing the upstream DataAgent and report missing Python dependencies.")
    parser.add_argument("--skip-docker-check", action="store_true", help="Do not check or start Docker Desktop before a real agent run.")
    parser.add_argument("--docker-start-timeout", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_DOCKER_START_TIMEOUT", "120")))
    parser.add_argument("--skip-postgres-check", action="store_true", help="Do not auto-start the DAB PostgreSQL container for postgres-backed queries.")
    parser.add_argument("--postgres-container", default=os.environ.get("DAB_POSTGRES_CONTAINER", "dab-postgres"))
    parser.add_argument("--postgres-start-timeout", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_POSTGRES_START_TIMEOUT", "120")))
    parser.add_argument("--log-level", default=os.environ.get("DAB_TOOL_AGENT_LOG_LEVEL", "INFO"))
    return parser


def main() -> int:
    return run_agent(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
