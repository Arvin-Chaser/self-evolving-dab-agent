"""Opt-in parser for *observed* school tagged reasoning/XML tool protocol.

Grammar matches Qwen's published chat template, not assumed model weights.
Unlike permissive inference-server parsers, incomplete tags fail closed.
"""
import copy
import hashlib
import re

from adapters.school_tool_compat_v1 import (
    CompatibilityError, MAX_BYTES, MAX_CALLS, canonical, normalize_response as v1,
    strict_loads, validate_request,
)

POLICY = "school_native_json_xml_reasoning_v2"
NAME = r"[A-Za-z_][A-Za-z0-9_.-]{0,127}"
CALL = re.compile(r"<tool_call>\s*<function=(" + NAME + r")>(.*?)</function>\s*</tool_call>", re.DOTALL)
PARAM = re.compile(r"<parameter=(" + NAME + r")>(.*?)</parameter>", re.DOTALL)
TAGS = ("<tool_call", "</tool_call", "<function=", "</function", "<parameter=", "</parameter", "<think", "</think")


def _reasoning(message):
    text = message.get("content")
    if not isinstance(text, str):
        return False
    if "</think>" not in text:
        if "<think>" in text:
            raise CompatibilityError("Unclosed reasoning section")
        return False
    if text.count("</think>") != 1 or text.count("<think>") > 1:
        raise CompatibilityError("Ambiguous reasoning boundaries")
    prefix, answer = text.split("</think>")
    if "<think>" in prefix:
        if not prefix.startswith("<think>"):
            raise CompatibilityError("Reasoning start must be at message start")
        prefix = prefix[len("<think>"):]
    if any(tag in prefix or tag in answer for tag in ("<think>", "</think>")):
        raise CompatibilityError("Nested reasoning boundaries")
    if any(tag in prefix for tag in TAGS if "think" not in tag):
        raise CompatibilityError("Tool markup inside reasoning is ambiguous")
    if message.get("reasoning_content") not in (None, ""):
        raise CompatibilityError("Both dedicated and embedded reasoning present")
    # The published generation prompt may already contain <think>, so the raw
    # continuation can contain only the closing tag. This mode is explicit.
    message["reasoning_content"] = prefix
    message["content"] = answer.lstrip("\n")
    return True


def _unwrap_newlines(value):
    # Only the one leading/trailing newline emitted by the template; preserve
    # interior newlines, indentation, spaces and string values such as "007".
    if value.startswith("\n"):
        value = value[1:]
    if value.endswith("\n"):
        value = value[:-1]
    return value


def _xml(text, request):
    tool_specs = {t["function"]["name"]: t["function"]["parameters"] for t in request.get("tools", [])}
    calls, pos = [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        match = CALL.match(text, pos)
        if not match:
            raise CompatibilityError("Incomplete/mixed XML tool envelope")
        name, body = match.groups()
        if name not in tool_specs:
            raise CompatibilityError("Unknown XML tool name")
        schema = tool_specs[name]
        props = schema.get("properties", {})
        arguments, cursor = {}, 0
        while cursor < len(body):
            while cursor < len(body) and body[cursor].isspace():
                cursor += 1
            if cursor == len(body):
                break
            param = PARAM.match(body, cursor)
            if not param:
                raise CompatibilityError("Incomplete/mixed XML parameter envelope")
            key, raw = param.groups()
            if key in arguments or key not in props:
                raise CompatibilityError("Duplicate/undeclared XML parameter")
            if any(tag in raw for tag in TAGS):
                raise CompatibilityError("Reserved markup inside parameter value")
            raw = _unwrap_newlines(raw)
            kind = props[key].get("type")
            if kind == "string":
                value = raw
            elif kind in ("integer", "number", "boolean", "object", "array", "null"):
                value = strict_loads(raw)
            else:
                raise CompatibilityError("XML argument type must be explicit and unambiguous")
            arguments[key] = value
            cursor = param.end()
        calls.append({"name": name, "parameters": arguments})
        if len(calls) > MAX_CALLS:
            raise CompatibilityError("XML tool count limit exceeded")
        pos = match.end()
    if not calls:
        raise CompatibilityError("Empty XML tool completion")
    return canonical(calls)


def normalize_response(request, response):
    validate_request(request)
    if len(canonical(response).encode()) > MAX_BYTES:
        raise CompatibilityError("Response size limit exceeded")
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or choices[0].get("finish_reason") not in ("stop", "tool_calls"):
        raise CompatibilityError("Incomplete/blocked response; no parsing or dispatch")
    projected = copy.deepcopy(response)
    message = projected["choices"][0].get("message")
    if not isinstance(message, dict):
        raise CompatibilityError("Missing assistant message")
    split = _reasoning(message)
    content = message.get("content")
    xml = isinstance(content, str) and any(tag in content for tag in TAGS)
    if xml:
        if message.get("tool_calls"):
            raise CompatibilityError("Mixed XML and standard calls")
        message["content"] = _xml(content, request)
    result = v1(request, projected)
    meta = result["school_tool_compat"]
    meta.update({"policy": POLICY, "converted": meta["converted"] or split or xml,
        "reasoning_separated": split, "xml_tool_projected": xml,
        "original_message": copy.deepcopy(response["choices"][0]["message"]),
        "original_finish_reason": response["choices"][0]["finish_reason"],
        "original_response_sha256": hashlib.sha256(canonical(response).encode()).hexdigest(),
        "raw_model_architecture_verified": False})
    return result
