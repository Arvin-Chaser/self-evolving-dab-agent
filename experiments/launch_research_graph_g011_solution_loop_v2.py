#!/usr/bin/env python3
"""G11 launcher v2: use the provider-supported automatic tool-call shape."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
V1 = HERE / "launch_research_graph_g011_solution_loop_v1.py"
V1_SHA256 = "227017ed908c0440e812ab6c046a10567d6c545f8f4ff15b9f46e4218ff7ad8a"


def load_v1():
    if not V1.is_file() or hashlib.sha256(V1.read_bytes()).hexdigest() != V1_SHA256:
        raise RuntimeError("G11 launcher v1 binding differs")
    spec = importlib.util.spec_from_file_location("g011_solution_loop_launcher_v1", V1)
    if spec is None or spec.loader is None:
        raise RuntimeError("G11 launcher v1 cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def provider_supported_preflight(v1, key: str) -> dict:
    basic = v1._provider_request(
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
    tool_message = v1._provider_request(
        key,
        {
            "model": "deepseek-flash",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "No task data is present. You must call record_self_observation exactly once. "
                        "Set its freeform argument to the exact string shown in the freeform schema "
                        "description. Do not answer in prose."
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
                                "freeform": {
                                    "type": "string",
                                    "description": "Use exactly: " + carrier_text,
                                }
                            },
                            "required": ["freeform"],
                        },
                    },
                }
            ],
            "max_tokens": 256,
            "stream": False,
            "temperature": 0,
        },
    )
    calls = tool_message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise RuntimeError("G11 provider did not return the requested no-task carrier tool call")
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
        "tool_response_protocol_ok": True,
        "declared_freeform_carrier_accepted": True,
        "tool_choice_mode": "provider_auto_with_explicit_no_task_instruction",
        "task_content_sent": False,
        "raw_response_persisted": False,
    }


def main() -> None:
    v1 = load_v1()
    v1.model_and_carrier_preflight = lambda key: provider_supported_preflight(v1, key)
    v1.main()


if __name__ == "__main__":
    main()
