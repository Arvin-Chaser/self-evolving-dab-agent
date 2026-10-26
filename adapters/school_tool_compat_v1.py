"""Opt-in projection of school native tool JSON to Chat Completions calls.

This module never executes tools or rewrites prompts/results. Malformed or
ambiguous calls fail closed. Requires jsonschema >=4.23,<5.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from jsonschema import validators

POLICY = "school_native_tool_json_v1"
MODEL = "qwen3.8-27b"
MAX_BYTES = 2 * 1024 * 1024
MAX_CALLS = 16


class CompatibilityError(ValueError):
    """A protocol boundary is unsafe or unsupported (never a model answer fix)."""


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > 64:
        raise CompatibilityError("JSON nesting limit exceeded")
    if isinstance(value, float) and not math.isfinite(value):
        raise CompatibilityError("Nonfinite JSON number")
    if isinstance(value, dict):
        for child in value.values():
            _bounded(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _bounded(child, depth + 1)


def strict_loads(data: str | bytes) -> Any:
    if len(data.encode("utf-8") if isinstance(data, str) else data) > MAX_BYTES:
        raise CompatibilityError("JSON size limit exceeded")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CompatibilityError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise CompatibilityError("Nonfinite JSON constant")

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        _bounded(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, CompatibilityError):
            raise
        raise CompatibilityError("Invalid strict JSON") from None


def canonical(value: Any) -> str:
    _bounded(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _reject_external_refs(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("$ref", "$dynamicRef", "$recursiveRef") and (
                not isinstance(child, str) or not child.startswith("#")
            ):
                raise CompatibilityError("Only document-local schema references are permitted")
            if key == "$id":
                raise CompatibilityError("Schema resource identifiers are not supported")
            _reject_external_refs(child)
    elif isinstance(value, list):
        for child in value:
            _reject_external_refs(child)


def _tools(request: dict) -> dict:
    result = {}
    specs = request.get("tools") or []
    if not isinstance(specs, list) or len(specs) > 128:
        raise CompatibilityError("Invalid tools list")
    for tool in specs:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise CompatibilityError("Only function tools are supported")
        fn = tool.get("function")
        if not isinstance(fn, dict):
            raise CompatibilityError("Missing function specification")
        name, schema = fn.get("name"), fn.get("parameters")
        if not isinstance(name, str) or not name or name in result or not isinstance(schema, dict):
            raise CompatibilityError("Invalid/duplicate tool name or missing object schema")
        _bounded(schema)
        _reject_external_refs(schema)
        try:
            cls = validators.validator_for(schema)
            cls.check_schema(schema)
            result[name] = cls(schema)
        except Exception:
            raise CompatibilityError("Invalid advertised tool schema") from None
    return result


def _arguments(name: Any, arguments: Any, tools: dict) -> None:
    if not isinstance(name, str) or name not in tools:
        raise CompatibilityError("Unknown tool name")
    if not isinstance(arguments, dict):
        raise CompatibilityError("Tool arguments must be a JSON object")
    _bounded(arguments)
    try:
        if not tools[name].is_valid(arguments):
            raise CompatibilityError("Arguments do not match advertised schema")
    except CompatibilityError:
        raise
    except Exception:
        raise CompatibilityError("Unable to validate advertised schema") from None


def _choice(request: dict, tools: dict) -> str:
    choice = request.get("tool_choice", "auto")
    if isinstance(choice, str) and choice in ("auto", "none", "required"):
        if choice == "required" and not tools:
            raise CompatibilityError("Required tool choice without tools")
        return choice
    if isinstance(choice, dict) and set(choice) == {"type", "function"} and choice["type"] == "function":
        fn = choice["function"]
        if isinstance(fn, dict) and set(fn) == {"name"} and isinstance(fn["name"], str) and fn["name"] in tools:
            return fn["name"]
    raise CompatibilityError("Unsupported tool choice")


def validate_request(request: dict) -> dict:
    """Validate the request and completed tool-result history; return unchanged."""
    if not isinstance(request, dict) or request.get("model") != MODEL:
        raise CompatibilityError("Adapter is restricted to the verified school model ID")
    if request.get("stream", False) is not False or type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise CompatibilityError("Only one non-streaming choice is supported")
    if request.get("functions") is not None or request.get("function_call") is not None:
        raise CompatibilityError("Legacy function protocol is not supported")
    if "parallel_tool_calls" in request and type(request["parallel_tool_calls"]) is not bool:
        raise CompatibilityError("parallel_tool_calls must be boolean")
    if request.get("response_format", {"type": "text"}) != {"type": "text"}:
        raise CompatibilityError("Structured answer mode is ambiguous with native tool JSON")
    if not isinstance(request.get("messages"), list) or not request["messages"]:
        raise CompatibilityError("Missing messages")
    if len(canonical(request).encode("utf-8")) > MAX_BYTES:
        raise CompatibilityError("Request size limit exceeded")
    tools = _tools(request)
    _choice(request, tools)
    seen, pending = set(), set()
    for message in request["messages"]:
        if not isinstance(message, dict):
            raise CompatibilityError("Invalid history message")
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or call_id not in pending or not isinstance(message.get("content"), str):
                raise CompatibilityError("Unpaired/duplicate tool result")
            pending.remove(call_id)
            continue
        if pending:
            raise CompatibilityError("New turn before all tool results returned")
        if role not in ("system", "developer", "user", "assistant"):
            raise CompatibilityError("Unsupported history role")
        if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
            raise CompatibilityError("History tool_calls must be a list or null")
        if message.get("tool_calls"):
            if role != "assistant":
                raise CompatibilityError("Tool calls require assistant role")
            calls = message["tool_calls"]
            if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_CALLS:
                raise CompatibilityError("Invalid history tool calls")
            for call in calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise CompatibilityError("Invalid history tool call")
                cid, fn = call.get("id"), call.get("function")
                if not isinstance(cid, str) or not cid or cid in seen or not isinstance(fn, dict):
                    raise CompatibilityError("Invalid/duplicate history call ID")
                if not isinstance(fn.get("arguments"), str):
                    raise CompatibilityError("History arguments must be serialized JSON")
                _arguments(fn.get("name"), strict_loads(fn["arguments"]), tools)
                seen.add(cid)
                pending.add(cid)
    if pending:
        raise CompatibilityError("Missing tool results at request boundary")
    return request


def _native_intent(content: Any) -> list | None:
    if content is None or content == "":
        return None
    if not isinstance(content, str):
        raise CompatibilityError("Unsupported assistant content type")
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise CompatibilityError("Content size limit exceeded")
    if any(tag in content for tag in ("<think>", "</think>", "<tool_call>", "</tool_call>", "<function=", "<parameter=")):
        raise CompatibilityError("Tagged native protocol requires explicit v2 parser")
    # Do not extract JSON from prose/code fences, infer arguments, or repair JSON.
    looks_like_intent = ('"name"' in content and ('"parameters"' in content or '"arguments"' in content))
    try:
        obj = strict_loads(content)
    except CompatibilityError:
        if looks_like_intent:
            raise CompatibilityError("Malformed/embedded native tool intent") from None
        return None
    if isinstance(obj, list) and obj and any(isinstance(item, dict) and "name" in item for item in obj):
        if not 1 <= len(obj) <= MAX_CALLS:
            raise CompatibilityError("Native tool call count limit exceeded")
        for item in obj:
            if not isinstance(item, dict) or set(item) != {"name", "parameters"}:
                raise CompatibilityError("Ambiguous native tool envelope")
        return obj
    if looks_like_intent:
        raise CompatibilityError("Unrecognized native tool envelope")
    return None


def normalize_response(request: dict, response: dict) -> dict:
    """Return a new response; preserve original message/finish in metadata."""
    validate_request(request)
    tools = _tools(request)
    wanted = _choice(request, tools)
    if not isinstance(response, dict) or response.get("model") != MODEL:
        raise CompatibilityError("Unexpected response model")
    if len(canonical(response).encode("utf-8")) > MAX_BYTES:
        raise CompatibilityError("Response size limit exceeded")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise CompatibilityError("Expected one response choice")
    original = choices[0]
    if not isinstance(original, dict) or original.get("finish_reason") not in ("stop", "tool_calls"):
        raise CompatibilityError("Incomplete/blocked response; no tool dispatch")
    message = original.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("function_call"):
        raise CompatibilityError("Invalid assistant message")
    native = _native_intent(message.get("content"))
    standard = message.get("tool_calls")
    if standard is not None and not isinstance(standard, list):
        raise CompatibilityError("Standard tool_calls must be a list or null")
    if native is not None and standard:
        raise CompatibilityError("Mixed native and standard tool intents")
    calls = []
    if standard:
        if original["finish_reason"] != "tool_calls" or not isinstance(standard, list) or not 1 <= len(standard) <= MAX_CALLS:
            raise CompatibilityError("Invalid standard tool completion")
        ids = set()
        for call in standard:
            if not isinstance(call, dict) or set(call) != {"id", "type", "function"} or call.get("type") != "function":
                raise CompatibilityError("Invalid standard tool envelope")
            cid, fn = call["id"], call["function"]
            if not isinstance(cid, str) or not cid or cid in ids or not isinstance(fn, dict) or set(fn) != {"name", "arguments"}:
                raise CompatibilityError("Invalid standard tool function/ID")
            if not isinstance(fn["arguments"], str):
                raise CompatibilityError("Standard arguments must be JSON string")
            _arguments(fn["name"], strict_loads(fn["arguments"]), tools)
            ids.add(cid)
            calls.append(copy.deepcopy(call))
    elif native is not None:
        if original["finish_reason"] != "stop":
            raise CompatibilityError("Unexpected native finish reason")
        binding = canonical({"request": request, "raw_message": message})
        for index, item in enumerate(native):
            _arguments(item["name"], item["parameters"], tools)
            cid = "call_school_" + hashlib.sha256((binding + ":" + str(index)).encode()).hexdigest()[:32]
            calls.append({"id": cid, "type": "function", "function": {"name": item["name"], "arguments": canonical(item["parameters"])}})
    if calls:
        if wanted == "none" or (wanted not in ("auto", "required") and any(c["function"]["name"] != wanted for c in calls)):
            raise CompatibilityError("Response violates requested tool choice")
        if request.get("parallel_tool_calls") is False and len(calls) > 1:
            raise CompatibilityError("Parallel calls were disabled")
        historical_ids = {call["id"] for msg in request["messages"] for call in (msg.get("tool_calls") or [])}
        if any(call["id"] in historical_ids for call in calls):
            raise CompatibilityError("Response reused an executed history call ID")
    elif wanted not in ("auto", "none") or original["finish_reason"] != "stop" or not isinstance(message.get("content"), str) or not message["content"].strip():
        raise CompatibilityError("Missing required call or empty final answer")
    result = copy.deepcopy(response)
    if native is not None:
        result["choices"][0]["message"]["content"] = None
        result["choices"][0]["message"]["tool_calls"] = calls
        result["choices"][0]["finish_reason"] = "tool_calls"
    result["school_tool_compat"] = {
        "policy": POLICY, "converted": native is not None,
        "original_finish_reason": original["finish_reason"],
        "original_message": copy.deepcopy(message),
        "request_sha256": hashlib.sha256(canonical(request).encode()).hexdigest(),
        "original_response_sha256": hashlib.sha256(canonical(response).encode()).hexdigest(),
        "tool_execution_performed": False,
    }
    return result
