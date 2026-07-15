#!/usr/bin/env python3
"""Run the upstream DAB multi-turn tool-using DataAgent from this project.

This is the first bridge from the current generated_solve.py-based prototype
to a DAB-style workflow agent.  It intentionally keeps the upstream scaffold
outside this repository and writes a lightweight normalized run summary that
our later analyzers/archive code can consume.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_DAB_DATA_ROOT = Path("/home/m0st1ma/research/DataAgentBench")
DEFAULT_DAB_UPSTREAM_ROOT = Path("/home/m0st1ma/research/DataAgentBench_upstream")
DEFAULT_OUTPUT_ROOT = ROOT / "logs" / "dab_tool_agent"
DEFAULT_TOOL_AGENT_POLICY = ROOT / "prompts" / "dab" / "dab_tool_agent_policy_zero_start.txt"
DEFAULT_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL_MARKERS = ("qwen", "qwq", "qvq")


SAFE_SQL_METADATA_MARKERS = (
    "information_schema",
    "sqlite_master",
    "pg_catalog",
    "show tables",
    "show columns",
    "describe ",
    "pragma ",
)

SAFE_SQL_AGGREGATE_MARKERS = (
    "group by",
    "count(",
    "count (",
    "sum(",
    "sum (",
    "avg(",
    "avg (",
    "min(",
    "min (",
    "max(",
    "max (",
    "array_agg(",
    "array_agg (",
    "string_agg(",
    "string_agg (",
)


def normalize_sql_for_capacity_guard(query: str) -> str:
    """Return a compact lowercase SQL string for cheap safety checks."""
    without_line_comments = re.sub(r"--[^\n\r]*", " ", query)
    without_block_comments = re.sub(r"/\*.*?\*/", " ", without_line_comments, flags=re.DOTALL)
    return re.sub(r"\s+", " ", without_block_comments).strip().lower()


def should_block_unbounded_select(query: str) -> tuple[bool, str]:
    """Detect result-materialization hazards before QueryDBTool executes SQL.

    Upstream DAB loads SQL query results into a pandas DataFrame and then into a
    JSON-serializable Python object before DataAgent can decide whether to write
    the result to file_storage. A full-table SELECT can therefore kill the
    process before the normal preview/storage mechanism runs. This guard is
    intentionally generic: it asks the agent to use bounded, aggregate, or
    metadata queries instead of materializing raw full-table rows.
    """
    sql = normalize_sql_for_capacity_guard(query)
    if not sql:
        return False, "empty"
    if not sql.startswith("select "):
        return False, "not_select"
    if any(marker in sql for marker in SAFE_SQL_METADATA_MARKERS):
        return False, "metadata_query"
    if re.search(r"\blimit\s+\d+\b", sql):
        return False, "bounded_limit"
    if any(marker in sql for marker in SAFE_SQL_AGGREGATE_MARKERS):
        return False, "aggregate_or_grouped"
    return True, "unbounded_select_without_limit_or_aggregation"

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
    args.tool_agent_policy = Path(args.tool_agent_policy).resolve() if args.tool_agent_policy else None
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


def load_evolved_helper_specs() -> list[dict[str, str]]:
    """Load meta-agent-created DAB tool-agent helper registry entries.

    An empty registry is the zero-start baseline. Non-empty entries are exposed
    as choices under the generic run_evolved_helper tool.
    """
    registry_path = ROOT / "adapters" / "dab_tool_agent_helpers" / "registry.py"
    if not registry_path.exists():
        return []
    module_name = "adapters.dab_tool_agent_helpers.registry"
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to import evolved helper registry {module_name}: {type(exc).__name__}: {exc}") from exc
    helpers = getattr(module, "HELPERS", [])
    if not isinstance(helpers, list):
        raise RuntimeError("adapters.dab_tool_agent_helpers.registry.HELPERS must be a list")
    normalized: list[dict[str, str]] = []
    for idx, item in enumerate(helpers):
        if not isinstance(item, dict):
            raise RuntimeError(f"HELPERS[{idx}] must be a dict")
        name = str(item.get("name") or "").strip()
        function = str(item.get("function") or "").strip()
        description = str(item.get("description") or "").strip()
        input_contract = str(item.get("input_contract") or "").strip()
        if not name or not function or ":" not in function:
            raise RuntimeError(f"HELPERS[{idx}] must define non-empty name and module:function")
        normalized.append({
            "name": name,
            "function": function,
            "description": description or name,
            "input_contract": input_contract or "payload dict plus selected prior tool outputs",
        })
    return normalized


def install_evolved_helper_tool(data_agent_module: Any, args: argparse.Namespace) -> list[dict[str, str]]:
    """Patch upstream DataAgent to expose registered local helpers as a real tool."""
    if getattr(args, "disable_evolved_helper_tools", False):
        return []
    helper_specs = load_evolved_helper_specs()
    if not helper_specs:
        return []

    BaseTool = data_agent_module.BaseTool
    original_data_agent = data_agent_module.DataAgent
    tool_name = getattr(args, "evolved_helper_tool_name", "run_evolved_helper")

    class EvolvedHelperTool(BaseTool):
        def __init__(self, log_path, name: str, helpers: list[dict[str, str]]):
            super().__init__(log_path, name)
            self.helpers = {item["name"]: item for item in helpers}
            self.result_storage_ref: dict[str, Any] = {}

        def to_dict(self):
            return {
                "name": self.name,
                "log_path": str(self.log_path),
                "helpers": list(self.helpers.values()),
            }

        def get_spec(self):
            helper_descriptions = "\n".join(
                f"- {name}: {item.get('description')} Input: {item.get('input_contract')}"
                for name, item in sorted(self.helpers.items())
            )
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": (
                        "Run a registered local helper created by the meta-agent. "
                        "Use this when repeated SQL/schema/date/CPC/data-processing failures require reusable local logic. "
                        "Available helpers:\n" + helper_descriptions
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "helper_name": {
                                "type": "string",
                                "description": "Name of the registered helper to run."
                            },
                            "payload_json": {
                                "type": "string",
                                "description": "JSON object string with helper-specific options or small inline inputs."
                            },
                            "input_keys": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional result-storage keys from prior tool calls, e.g. var_call_..., to pass into the helper."
                            },
                        },
                        "required": ["helper_name", "payload_json"],
                    },
                },
            }

        def _check_args(self, args: dict):
            args = super()._check_args(args)
            helper_name = args.get("helper_name")
            if not isinstance(helper_name, str) or helper_name not in self.helpers:
                raise ValueError(f"Unknown helper_name: {helper_name!r}. Available: {sorted(self.helpers)}")
            payload_json = args.get("payload_json", "{}")
            if not isinstance(payload_json, str):
                raise ValueError("payload_json must be a JSON object string")
            try:
                payload = json.loads(payload_json or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError(f"payload_json is not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError("payload_json must decode to a JSON object")
            input_keys = args.get("input_keys", [])
            if input_keys is None:
                input_keys = []
            if not isinstance(input_keys, list) or not all(isinstance(item, str) for item in input_keys):
                raise ValueError("input_keys must be a list of strings")
            return {"helper_name": helper_name, "payload": payload, "input_keys": input_keys}

        def _exec(self, args: dict):
            super()._exec(args)
            spec = self.helpers[args["helper_name"]]
            module_name, function_name = spec["function"].split(":", 1)
            module = importlib.import_module(module_name)
            func = getattr(module, function_name)
            inputs = {key: self.result_storage_ref.get(key) for key in args["input_keys"]}
            missing = [key for key, value in inputs.items() if value is None]
            if missing:
                raise ValueError(f"input_keys not found in result storage: {missing}")
            result = func(payload=args["payload"], inputs=inputs)
            json.dumps(result, ensure_ascii=False)
            return result

        def clean_up(self):
            return None

    class DataAgentWithEvolvedHelpers(original_data_agent):
        def __init__(self, *da_args: Any, **da_kwargs: Any):
            super().__init__(*da_args, **da_kwargs)
            helper_tool = EvolvedHelperTool(self.tool_log_path, tool_name, helper_specs)
            helper_tool.result_storage_ref = self.result_storage
            self.tools[tool_name] = helper_tool

    data_agent_module.DataAgent = DataAgentWithEvolvedHelpers
    return helper_specs


def install_self_observation_tool(data_agent_module: Any, args: argparse.Namespace) -> None:
    """Patch upstream DataAgent to expose an open-ended self-observation tool.

    This is deliberately not a fixed failure taxonomy. The DataAgent can record
    its own local reasoning state, uncertainty, evidence references, and intended
    next step in free text. Downstream analyzers only compact these observations
    for the meta-agent; they should not turn them into hard-coded repair labels.
    """
    if getattr(args, "disable_self_observation_tool", False):
        return

    BaseTool = data_agent_module.BaseTool
    original_data_agent = data_agent_module.DataAgent
    tool_name = getattr(args, "self_observation_tool_name", "record_self_observation")

    def normalize_self_observation_payload(payload: Any) -> dict[str, Any] | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            payload = {"freeform": payload}
        if not isinstance(payload, dict):
            payload = {"freeform": str(payload)}
        freeform = payload.get("freeform") or payload.get("note") or payload.get("why_this_action") or ""
        if not isinstance(freeform, str) or not freeform.strip():
            return None
        normalized: dict[str, Any] = {"freeform": freeform.strip()}
        for key in ("current_goal", "intended_next_step", "why_next_action", "why_this_action", "failure_if_stopped_now"):
            value = payload.get(key)
            if value is not None:
                normalized[key] = str(value).strip()
        for key in ("what_i_know", "uncertainties", "evidence_refs", "claims"):
            value = payload.get(key, [])
            if value is None:
                value = []
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                normalized[key] = [str(item).strip() for item in value if str(item).strip()]
        return normalized

    def write_self_observation(log_path: Path, payload: Any, *, source: str, tool_name_for_action: str | None = None, tool_call_id: str | None = None) -> bool:
        normalized = normalize_self_observation_payload(payload)
        if normalized is None:
            return False
        observation_log_path = Path(log_path).parent / "agent_self_observations.jsonl"
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "tool_name": tool_name,
            "tool_name_for_action": tool_name_for_action,
            "tool_call_id": tool_call_id,
            "payload": normalized,
        }
        observation_log_path.parent.mkdir(parents=True, exist_ok=True)
        with observation_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True

    def read_latest_tool_log_entry(log_path: Path) -> dict[str, Any] | None:
        path = Path(log_path)
        if not path.exists():
            return None
        try:
            lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        except OSError:
            return None
        if not lines:
            return None
        try:
            value = json.loads(lines[-1])
        except json.JSONDecodeError:
            return {"_parse_error": True, "raw": lines[-1][:1000]}
        return value if isinstance(value, dict) else {"value": value}

    def compact_for_observation(value: Any, max_chars: int = 800) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    def write_automatic_tool_observation(
        log_path: Path,
        *,
        tool_name_for_action: str | None,
        tool_call_id: str | None,
        raw_args: dict[str, Any] | None,
        latest_tool_log: dict[str, Any] | None,
        final_result: Any,
    ) -> bool:
        if not tool_name_for_action or tool_name_for_action == tool_name:
            return False
        latest_tool_log = latest_tool_log or {}
        result = latest_tool_log.get("result") if isinstance(latest_tool_log.get("result"), dict) else {}
        success = result.get("success")
        result_preview = result.get("preview") if isinstance(result, dict) else None
        payload = {
            "freeform": (
                f"Automatic workflow observation: tool `{tool_name_for_action}` completed "
                f"with success={success}. Result preview: {compact_for_observation(result_preview, 600)}"
            ),
            "current_goal": "track DataAgent tool-action evidence for future meta-agent repair",
            "what_i_know": [
                f"tool={tool_name_for_action}",
                f"success={success}",
                f"args={compact_for_observation(raw_args or {}, 400)}",
                f"result_preview={compact_for_observation(result_preview, 600)}",
            ],
            "uncertainties": [
                "This is runner-observed behavior, not a model-authored causal explanation.",
            ],
            "intended_next_step": (
                "use this tool result to decide the next action or final answer"
                if final_result is None else "workflow has produced a final result"
            ),
            "failure_if_stopped_now": (
                "No final answer has been submitted yet."
                if final_result is None else "Final answer has been submitted; validate answer quality next."
            ),
            "evidence_refs": [
                f"tool_call_id:{tool_call_id}",
                f"tool_log:{Path(log_path)}",
            ],
            "claims": [
                f"{tool_name_for_action} success={success}",
            ],
        }
        return write_self_observation(
            log_path,
            payload,
            source="tool_action_auto_observer",
            tool_name_for_action=tool_name_for_action,
            tool_call_id=tool_call_id,
        )

    def add_sidecar_to_tool_spec(spec: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(spec, dict):
            return spec
        function = spec.get("function")
        if not isinstance(function, dict):
            return spec
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            return spec
        properties = parameters.setdefault("properties", {})
        if not isinstance(properties, dict):
            return spec
        properties.setdefault("self_observation", {
            "type": "object",
            "description": (
                "Optional open-ended sidecar observation attached to this same tool action. "
                "Use it to explain why this action is being taken, what is known, uncertainty, "
                "and what would fail if stopping now. This does not consume a separate tool turn."
            ),
            "properties": {
                "freeform": {"type": "string"},
                "current_goal": {"type": "string"},
                "what_i_know": {"type": "array", "items": {"type": "string"}},
                "uncertainties": {"type": "array", "items": {"type": "string"}},
                "why_this_action": {"type": "string"},
                "intended_next_step": {"type": "string"},
                "failure_if_stopped_now": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "claims": {"type": "array", "items": {"type": "string"}},
            },
        })
        description = str(function.get("description") or "")
        sidecar_note = " You may include optional `self_observation` to log open reasoning/evidence for future meta-agent evolution without spending another tool call."
        if "self_observation" not in description:
            function["description"] = description.rstrip() + sidecar_note
        return spec

    def wrap_tool_get_spec_for_sidecar(tool: Any) -> None:
        if getattr(tool, "_self_observation_sidecar_wrapped", False):
            return
        original_get_spec = tool.get_spec

        def get_spec_with_sidecar():
            return add_sidecar_to_tool_spec(original_get_spec())

        tool.get_spec = get_spec_with_sidecar
        tool._self_observation_sidecar_wrapped = True

    class SelfObservationTool(BaseTool):
        def __init__(self, log_path, name: str):
            super().__init__(log_path, name)
            self.observation_log_path = Path(log_path).parent / "agent_self_observations.jsonl"

        def to_dict(self):
            base = super().to_dict()
            base.update({
                "observation_log_path": str(self.observation_log_path),
                "purpose": "open_freeform_agent_self_observation",
            })
            return base

        def get_spec(self):
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": (
                        "Record an open-ended self-observation for future meta-agent evolution. "
                        "Use this opportunistically when it helps explain your current goal, what you know, "
                        "uncertainties, why you chose a next action, or what would fail if you stopped now. "
                        "This is not a fixed stage/error label tool; write natural, task-specific observations. "
                        "Do not spend the final answer turn solely on this tool."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "freeform": {"type": "string", "description": "Natural-language observation in your own words."},
                            "current_goal": {"type": "string", "description": "Optional current local goal or subgoal."},
                            "what_i_know": {"type": "array", "items": {"type": "string"}, "description": "Optional facts/evidence currently known."},
                            "uncertainties": {"type": "array", "items": {"type": "string"}, "description": "Optional uncertainties or unresolved hypotheses."},
                            "intended_next_step": {"type": "string", "description": "Optional intended next tool/action."},
                            "why_next_action": {"type": "string", "description": "Optional rationale for the intended next action."},
                            "failure_if_stopped_now": {"type": "string", "description": "Optional description of what would be wrong/incomplete if stopping now."},
                            "evidence_refs": {"type": "array", "items": {"type": "string"}, "description": "Optional references to prior tool calls, storage keys, files, tables, or query fragments."},
                            "claims": {"type": "array", "items": {"type": "string"}, "description": "Optional concise claims that future analysis should verify."},
                        },
                        "required": ["freeform"],
                    },
                },
            }

        def _check_args(self, args: dict):
            args = super()._check_args(args)
            normalized = normalize_self_observation_payload(args)
            if normalized is None:
                raise ValueError("freeform must be a non-empty string")
            return normalized

        def _exec(self, args: dict):
            super()._exec(args)
            write_self_observation(self.log_path, args, source="data_agent_tool_call", tool_name_for_action=self.name)
            return {
                "recorded": True,
                "observation_log_path": str(self.observation_log_path),
                "note": "Open self-observation recorded for future meta-agent interpretation.",
            }

        def clean_up(self):
            return None

    class DataAgentWithSelfObservation(original_data_agent):
        def __init__(self, *da_args: Any, **da_kwargs: Any):
            super().__init__(*da_args, **da_kwargs)
            self.tools[tool_name] = SelfObservationTool(self.tool_log_path, tool_name)
            for action_tool_name, action_tool in self.tools.items():
                if action_tool_name != tool_name:
                    wrap_tool_get_spec_for_sidecar(action_tool)

        def _handle_tool_call(self, tool_call):
            tool_name_for_action = getattr(getattr(tool_call, "function", None), "name", None)
            tool_call_id = getattr(tool_call, "id", None)
            raw_arguments = getattr(getattr(tool_call, "function", None), "arguments", None)
            parsed_tool_args: dict[str, Any] | None = None
            try:
                tool_args = json.loads(raw_arguments) if isinstance(raw_arguments, str) else {}
            except json.JSONDecodeError:
                before_entry = read_latest_tool_log_entry(self.tool_log_path)
                result = super()._handle_tool_call(tool_call)
                after_entry = read_latest_tool_log_entry(self.tool_log_path)
                if after_entry != before_entry:
                    write_automatic_tool_observation(
                        self.tool_log_path,
                        tool_name_for_action=tool_name_for_action,
                        tool_call_id=tool_call_id,
                        raw_args=None,
                        latest_tool_log=after_entry,
                        final_result=self.final_result,
                    )
                return result
            if isinstance(tool_args, dict):
                parsed_tool_args = dict(tool_args)
            if isinstance(tool_args, dict) and "self_observation" in tool_args:
                sidecar = tool_args.pop("self_observation")
                write_self_observation(
                    self.tool_log_path,
                    sidecar,
                    source="tool_action_sidecar",
                    tool_name_for_action=tool_name_for_action,
                    tool_call_id=tool_call_id,
                )

                class _FunctionProxy:
                    def __init__(self, name: str | None, arguments: str):
                        self.name = name
                        self.arguments = arguments

                class _ToolCallProxy:
                    def __init__(self, original: Any, arguments: str):
                        self.id = getattr(original, "id", None)
                        self.function = _FunctionProxy(getattr(getattr(original, "function", None), "name", None), arguments)

                    def model_dump(self):
                        if hasattr(tool_call, "model_dump"):
                            dumped = tool_call.model_dump()
                            if isinstance(dumped, dict):
                                dumped = dict(dumped)
                                function = dict(dumped.get("function") or {})
                                function["arguments"] = self.function.arguments
                                dumped["function"] = function
                                return dumped
                        return {
                            "id": self.id,
                            "type": "function",
                            "function": {"name": self.function.name, "arguments": self.function.arguments},
                        }

                tool_call = _ToolCallProxy(tool_call, json.dumps(tool_args, ensure_ascii=False))
            before_entry = read_latest_tool_log_entry(self.tool_log_path)
            result = super()._handle_tool_call(tool_call)
            after_entry = read_latest_tool_log_entry(self.tool_log_path)
            if after_entry != before_entry:
                write_automatic_tool_observation(
                    self.tool_log_path,
                    tool_name_for_action=tool_name_for_action,
                    tool_call_id=tool_call_id,
                    raw_args=tool_args if isinstance(tool_args, dict) else parsed_tool_args,
                    latest_tool_log=after_entry,
                    final_result=self.final_result,
                )
            return result

    data_agent_module.DataAgent = DataAgentWithSelfObservation


def install_query_capacity_guard(data_agent_module: Any, args: argparse.Namespace) -> None:
    """Patch QueryDBTool to reject hazardous raw full-table SELECT results early."""
    if getattr(args, "disable_query_capacity_guard", False):
        return

    original_query_db_tool = data_agent_module.QueryDBTool

    class CapacityGuardedQueryDBTool(original_query_db_tool):
        def get_spec(self):
            spec = super().get_spec()
            function = spec.get("function", {}) if isinstance(spec, dict) else {}
            description = str(function.get("description", ""))
            function["description"] = (
                description.rstrip()
                + " Local capacity guard: raw unbounded SELECT queries without LIMIT, GROUP BY, "
                + "or aggregate functions are rejected before execution because they may materialize "
                + "too many rows. Prefer schema queries, COUNT/GROUP BY aggregates, LIMIT previews, "
                + "or local helper tools for streaming post-processing."
            )
            return spec

        def _check_args(self, tool_args: dict):
            query = tool_args.get("query") if isinstance(tool_args, dict) else None
            if isinstance(query, str):
                block, reason = should_block_unbounded_select(query)
                if block:
                    raise ValueError(
                        "Local query capacity guard blocked this query before DB execution "
                        f"({reason}). Rewrite it as a bounded or aggregate query: add LIMIT for "
                        "small previews; use COUNT/GROUP BY/MIN/MAX/SUM/AVG for evidence collection; "
                        "or call a registered local helper that can stream/process rows without "
                        "returning a full raw table to the LLM."
                    )
            return super()._check_args(tool_args)

    data_agent_module.QueryDBTool = CapacityGuardedQueryDBTool


def install_configurable_llm_retry(data_agent_module: Any, args: argparse.Namespace) -> None:
    """Patch upstream DataAgent.call_llm with local timeout/retry controls.

    The upstream scaffold has a hard-coded 3-attempt loop with sleep(80) and
    timeout=600.  That is painful for our evolution loop: transient DashScope
    failures either waste minutes or terminate without enough structured
    diagnostics.  Keep the same semantics, but make retry/timeout/sleep local
    runner knobs so Codex-native child eval can be stable and inspectable.
    """

    retry_count = max(1, int(getattr(args, "llm_retries", 4)))
    retry_sleep = max(0.0, float(getattr(args, "llm_retry_sleep", 20.0)))
    request_timeout = max(1.0, float(getattr(args, "llm_timeout", 600.0)))
    prompt_builder = data_agent_module.prompt_builder

    def configurable_call_llm(self):
        start = time.time()
        response = None
        last_error = None
        for attempt in range(1, retry_count + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=self.messages,
                    tools=[tool.get_spec() for tool in self.tools.values()],
                    timeout=request_timeout,
                )
                break
            except Exception as exc:  # upstream catches all here too
                response = None
                last_error = exc
                self.terminate_reason = (
                    f"llm_response_failed attempt {attempt}/{retry_count} "
                    f"({type(exc).__name__}): {str(exc)}"
                )
                self.logger.warning(
                    "LLM call failed on attempt %s/%s: %s: %s",
                    attempt,
                    retry_count,
                    type(exc).__name__,
                    exc,
                )
                if attempt < retry_count and retry_sleep > 0:
                    time.sleep(retry_sleep)
        end = time.time()

        if response is None:
            self.final_result = ""
            if self.terminate_reason is None:
                self.terminate_reason = "llm_response_failed"
            self.logger.info("Terminating (%s)...", self.terminate_reason)
            assert self.final_result is not None

        self.llm_call_count += 1
        log_entry = {
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": start,
            "end_time": end,
            "duration": end - start,
            "model": self.deployment_name,
            "response": response.to_dict() if response is not None else None,
            "messages": self.messages,
            "local_retry_config": {
                "retry_count": retry_count,
                "retry_sleep_sec": retry_sleep,
                "request_timeout_sec": request_timeout,
            },
            "last_error": f"{type(last_error).__name__}: {last_error}" if last_error is not None else None,
        }
        with open(self.llm_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        response_msg = response.choices[0].message if response is not None else None
        if response_msg is not None:
            self.logger.debug("LLM response message: %s", response_msg.to_dict())
        return response_msg

    data_agent_module.DataAgent.call_llm = configurable_call_llm


def import_upstream_data_agent(upstream_root: Path, args: argparse.Namespace | None = None):
    sys.path.insert(0, str(upstream_root))
    import importlib

    data_agent_module = importlib.import_module("common_scaffold.DataAgent")

    if args is not None and getattr(args, "disable_exec_python_tool", False):
        BaseTool = data_agent_module.BaseTool

        class DisabledExecTool(BaseTool):
            def __init__(self, log_path, name, work_dir: Path, timeout=600):
                super().__init__(log_path, name)
                self.work_dir = work_dir
                self.timeout = timeout

            def to_dict(self):
                base = super().to_dict()
                base.update({
                    "disabled": True,
                    "work_dir": str(self.work_dir),
                    "timeout": self.timeout,
                    "reason": "Disabled by run_dab_tool_agent.py --disable-exec-python-tool smoke mode.",
                })
                return base

            def get_spec(self):
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": "Smoke-mode placeholder. Python execution is disabled in this run because Docker SDK is unavailable.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "description": "Python code that would be executed in a full run."}
                            },
                            "required": ["code"],
                        },
                    },
                }

            def _check_args(self, args: dict):
                return args

            def _exec(self, args: dict):
                raise RuntimeError("execute_python is disabled in smoke mode; fix WSL Docker integration for full workflow runs.")

            def clean_up(self):
                return None

        data_agent_module.ExecTool = DisabledExecTool

    if args is not None and is_qwen_like_model(args.deployment_name):
        config = qwen_bailian_config(args)
        if not config["api_key_present"]:
            raise RuntimeError(
                "Qwen/DashScope API key is not visible. Set DASHSCOPE_API_KEY in the shell "
                "that launches this script, or pass --bailian-api-key-env with an existing env var."
            )

        original_openai = data_agent_module.OpenAI

        policy_overlay = ""
        if getattr(args, "tool_agent_policy", None) and Path(args.tool_agent_policy).exists():
            policy_overlay = Path(args.tool_agent_policy).read_text(encoding="utf-8", errors="replace").strip()

        def bailian_openai_factory(*factory_args: Any, **factory_kwargs: Any):
            if factory_kwargs.get("base_url") == "https://api.together.xyz/v1":
                factory_kwargs["api_key"] = config["api_key"]
                factory_kwargs["base_url"] = config["base_url"]
                factory_kwargs.setdefault("timeout", float(getattr(args, "llm_timeout", 600.0)))
                factory_kwargs.setdefault("max_retries", int(getattr(args, "client_max_retries", 2)))
            return original_openai(*factory_args, **factory_kwargs)

        data_agent_module.OpenAI = bailian_openai_factory

        prompt_builder = data_agent_module.prompt_builder
        original_init_messages = prompt_builder.init_messages

        def qwen_init_messages(user_query: str, db_description: str, deployment_name: str, system_prompt=prompt_builder.SYSTEM_PROMPT):
            open_self_observation_overlay = (
                "The runner automatically records a compact observation after every tool action for future meta-agent repair. "
                "Every task tool may also accept an optional `self_observation` object when you have a useful causal explanation. "
                "Attach it to the same list_db/query_db/execute_python/run_evolved_helper/return_answer action instead of spending a separate turn. "
                "Use it to record open-ended process observations: current goal, what is known, uncertainties, why this action matters, intended next step, "
                "and what would fail if stopping now. This is not a fixed stage/error taxonomy."
            )
            system_prompt = system_prompt.rstrip() + "\n\n# OPEN SELF-OBSERVATION TRACE\n" + open_self_observation_overlay + "\n"
            if policy_overlay:
                system_prompt = system_prompt.rstrip() + "\n\n# LOCAL ZERO-START POLICY OVERLAY\n" + policy_overlay + "\n"
            if is_qwen_like_model(deployment_name):
                return original_init_messages(user_query, db_description, "gpt-qwen-compatible", system_prompt)
            return original_init_messages(user_query, db_description, deployment_name, system_prompt)

        prompt_builder.init_messages = qwen_init_messages

    if args is not None:
        install_query_capacity_guard(data_agent_module, args)
        install_configurable_llm_retry(data_agent_module, args)
        install_self_observation_tool(data_agent_module, args)
        args.evolved_helper_specs = install_evolved_helper_tool(data_agent_module, args)

    return data_agent_module.DataAgent


def command_succeeds(command: list[str], timeout: int = 10) -> bool:
    try:
        proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def command_result(command: list[str], timeout: int = 10) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return {"command": command, "ok": False, "error": f"FileNotFoundError: {exc}"}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
            "error": f"TimeoutExpired after {timeout}s",
        }
    except subprocess.SubprocessError as exc:
        return {"command": command, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "command": command,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def docker_environment_diagnostics() -> dict[str, Any]:
    candidates = [
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        ["docker.exe", "info", "--format", "{{.ServerVersion}}"],
    ]
    diagnostics: dict[str, Any] = {
        "docker_cli": command_result(["which", "docker"], timeout=5),
        "docker_exe_cli": command_result(["which", "docker.exe"], timeout=5),
        "docker_context": command_result(["docker", "context", "ls"], timeout=10),
        "docker_info_candidates": [command_result(command, timeout=15) for command in candidates],
    }
    socket_paths = [
        "/var/run/docker.sock",
        "/mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock",
        "/mnt/wsl/docker-desktop/shared-sockets/guest-services/docker.proxy.sock",
    ]
    socket_info: dict[str, Any] = {}
    for socket_path in socket_paths:
        path = Path(socket_path)
        try:
            stat_result = path.stat()
            socket_info[socket_path] = {
                "exists": True,
                "mode": oct(stat_result.st_mode),
                "uid": stat_result.st_uid,
                "gid": stat_result.st_gid,
            }
        except FileNotFoundError:
            socket_info[socket_path] = {"exists": False}
        except OSError as exc:
            socket_info[socket_path] = {"exists": path.exists(), "error": f"{type(exc).__name__}: {exc}"}
    diagnostics["socket_paths"] = socket_info
    return diagnostics


def docker_failure_message() -> str:
    return (
        "Docker is not available from WSL. Start Docker Desktop and enable WSL integration for Ubuntu, "
        "then rerun this command. The DAB execute_python tool requires Docker. If Windows docker.exe works "
        "but WSL docker does not, enable Docker Desktop -> Settings -> Resources -> WSL Integration -> Ubuntu."
    )


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

    raise RuntimeError(docker_failure_message())


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


def docker_cli_for_postgres() -> list[str]:
    if command_succeeds(["docker", "info"], timeout=10):
        return ["docker"]
    if command_succeeds(["docker.exe", "info"], timeout=10):
        return ["docker.exe"]
    return ["docker"]


def docker_container_running_with(cli: list[str], name: str) -> bool:
    try:
        proc = subprocess.run(
            cli + ["inspect", "-f", "{{.State.Running}}", name],
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
    docker_cli = docker_cli_for_postgres()
    if docker_container_running_with(docker_cli, container):
        status = "already_running"
    else:
        exists = subprocess.run(
            docker_cli + ["inspect", container],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode == 0
        if exists:
            subprocess.run(docker_cli + ["start", container], check=True, stdout=subprocess.DEVNULL, timeout=30)
            status = "started_existing"
        else:
            subprocess.run(
                docker_cli + [
                    "run", "-d",
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
        if command_succeeds(docker_cli + ["exec", container, "pg_isready", "-U", "postgres"], timeout=10):
            return f"{status}_via_{docker_cli[0]}"
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
        "self_observations": copy_if_exists(
            upstream_run_dir / "agent_self_observations.jsonl",
            normalized_dir / "agent_self_observations.jsonl",
        ),
    }

    qwen_config = qwen_bailian_config(args) if is_qwen_like_model(args.deployment_name) else None
    if qwen_config is not None:
        qwen_config = {key: value for key, value in qwen_config.items() if key != "api_key"}
    llm_retry_config = {
        "request_timeout_sec": args.llm_timeout,
        "retry_count": args.llm_retries,
        "retry_sleep_sec": args.llm_retry_sleep,
        "client_max_retries": args.client_max_retries,
    }

    summary = {
        "schema_version": "dab_tool_agent_run_v001",
        "status": "failed" if run_error else "completed",
        "run_id": args.run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deployment_name": args.deployment_name,
        "qwen_client_config": qwen_config,
        "llm_retry_config": llm_retry_config,
        "docker_status": getattr(args, "docker_status", None),
        "postgres_status": getattr(args, "postgres_status", None),
        "pg_client": os.getenv("PG_CLIENT"),
        "query_dir": str(args.query_dir),
        "db_description": str(args.db_description),
        "db_config": str(args.db_config),
        "tool_agent_policy": str(args.tool_agent_policy) if args.tool_agent_policy else None,
        "evolved_helper_tool_enabled": bool(getattr(args, "evolved_helper_specs", [])),
        "evolved_helper_specs": getattr(args, "evolved_helper_specs", []),
        "query_capacity_guard_enabled": not getattr(args, "disable_query_capacity_guard", False),
        "self_observation_tool_enabled": not getattr(args, "disable_self_observation_tool", False),
        "self_observation_tool_name": getattr(args, "self_observation_tool_name", "record_self_observation"),
        "self_observation_count": len(read_jsonl(normalized_dir / "agent_self_observations.jsonl")),
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


def write_startup_failure_artifact(
    *,
    args: argparse.Namespace,
    upstream_logs_dir: Path,
    normalized_dir: Path,
    exc: Exception,
) -> Path:
    run_error = f"{type(exc).__name__}: {exc}"
    normalized = normalize_run_artifacts(
        args=args,
        upstream_run_dir=upstream_logs_dir if upstream_logs_dir.exists() else normalized_dir,
        final_result="",
        run_error=run_error,
    )
    summary_path = normalized / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["startup_failure"] = True
    if "Docker is not available" in run_error or "docker" in run_error.lower():
        summary["docker_diagnostics"] = docker_environment_diagnostics()
    write_json(summary_path, summary)
    return normalized


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

    try:
        args.docker_status = ensure_docker_ready(args)
        args.postgres_status = ensure_postgres_ready(args)
        DataAgent = import_upstream_data_agent(args.dab_upstream_root, args)
    except Exception as exc:
        normalized = write_startup_failure_artifact(
            args=args,
            upstream_logs_dir=upstream_logs_dir,
            normalized_dir=normalized_dir,
            exc=exc,
        )
        summary = json.loads((normalized / "summary.json").read_text(encoding="utf-8"))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 1

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
    parser.add_argument("--llm-timeout", type=float, default=float(os.environ.get("DAB_TOOL_AGENT_LLM_TIMEOUT", "600")), help="Per LLM request timeout passed to the upstream DataAgent chat completion call.")
    parser.add_argument("--llm-retries", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_LLM_RETRIES", "4")), help="Number of DataAgent LLM retry attempts per turn.")
    parser.add_argument("--llm-retry-sleep", type=float, default=float(os.environ.get("DAB_TOOL_AGENT_LLM_RETRY_SLEEP", "20")), help="Seconds to sleep between DataAgent LLM retry attempts.")
    parser.add_argument("--client-max-retries", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_CLIENT_MAX_RETRIES", "2")), help="OpenAI SDK internal retry count for the patched Qwen/DashScope client.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--tool-agent-policy", default=os.environ.get("DAB_TOOL_AGENT_POLICY", str(DEFAULT_TOOL_AGENT_POLICY)), help="Local prompt-policy overlay appended to the upstream DAB DataAgent system prompt.")
    parser.add_argument("--disable-evolved-helper-tools", action="store_true", help="Do not expose registered adapters/dab_tool_agent_helpers as DataAgent tools.")
    parser.add_argument("--disable-query-capacity-guard", action="store_true", help="Allow raw unbounded SELECT query_db calls. Default blocks likely full-table materialization hazards before DB execution.")
    parser.add_argument("--disable-self-observation-tool", action="store_true", help="Do not expose the open-ended record_self_observation tool to the DataAgent.")
    parser.add_argument("--self-observation-tool-name", default=os.environ.get("DAB_SELF_OBSERVATION_TOOL_NAME", "record_self_observation"), help="Tool name used for open-ended DataAgent self-observation logging.")
    parser.add_argument("--evolved-helper-tool-name", default=os.environ.get("DAB_EVOLVED_HELPER_TOOL_NAME", "run_evolved_helper"), help="Tool name used to expose registered meta-agent-created helpers.")
    parser.add_argument("--run-id")
    parser.add_argument("--prepare-only", action="store_true", help="Resolve paths and write summary without calling the LLM/tools.")
    parser.add_argument("--check-dependencies", action="store_true", help="Try importing the upstream DataAgent and report missing Python dependencies.")
    parser.add_argument("--skip-docker-check", action="store_true", help="Do not check or start Docker Desktop before a real agent run.")
    parser.add_argument("--docker-start-timeout", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_DOCKER_START_TIMEOUT", "120")))
    parser.add_argument("--skip-postgres-check", action="store_true", help="Do not auto-start the DAB PostgreSQL container for postgres-backed queries.")
    parser.add_argument("--disable-exec-python-tool", action="store_true", help="Smoke-test only: replace execute_python with a disabled placeholder so Qwen/list_db logging can be tested without WSL Docker SDK.")
    parser.add_argument("--postgres-container", default=os.environ.get("DAB_POSTGRES_CONTAINER", "dab-postgres"))
    parser.add_argument("--postgres-start-timeout", type=int, default=int(os.environ.get("DAB_TOOL_AGENT_POSTGRES_START_TIMEOUT", "120")))
    parser.add_argument("--log-level", default=os.environ.get("DAB_TOOL_AGENT_LOG_LEVEL", "INFO"))
    return parser


def main() -> int:
    return run_agent(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
