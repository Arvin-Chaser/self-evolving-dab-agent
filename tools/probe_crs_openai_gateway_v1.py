"""Explicit local CRS connectivity probe. No credential output or redirects/retries."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://crs.uuid.im/openai"
KEY_PATH = Path("C:/Users/34934/.config/dab/crs_api_key.txt")
MODEL = "gpt-5.5"


def decode_wire(raw):
    """Accept native JSON or native Responses SSE, never text-derived tool calls."""
    try:
        value = json.loads(raw)
        return value, "json"
    except (ValueError, UnicodeError):
        pass
    terminal = []
    for block in raw.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        if event.get("type") in ("response.completed", "response.failed", "response.incomplete"):
            terminal.append(event["response"])
    if len(terminal) != 1:
        raise ValueError("Missing or duplicate terminal Responses event")
    return terminal[0], "responses_sse"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Credential forwarding via redirect is prohibited")


def request(path, key, payload=None):
    started = time.monotonic()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=90) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise RuntimeError("Oversized provider response")
            result, wire_format = decode_wire(raw)
            return result, {"http_status": response.status, "elapsed_seconds": round(time.monotonic() - started, 3),
                            "wire_format": wire_format, "wire_sha256": hashlib.sha256(raw).hexdigest()}
    except urllib.error.HTTPError as exc:
        # Do not print body/header/URL exceptions that could echo a credential.
        return None, {"http_status": exc.code, "elapsed_seconds": round(time.monotonic() - started, 3),
                      "failure_class": "HTTPError", "automatic_retry": False}
    except Exception as exc:
        return None, {"http_status": None, "elapsed_seconds": round(time.monotonic() - started, 3),
                      "failure_class": type(exc).__name__, "automatic_retry": False}


def build_first_request():
    return {"model": MODEL, "store": False, "stream": True,
            "reasoning": {"effort": "low"}, "max_output_tokens": 1024,
            "include": ["reasoning.encrypted_content"],
            "input": [{"role": "user", "content": "Call add_probe with a=3 and b=4. After its result, reply exactly PROBE_OK_7."}],
            "tools": [{"type": "function", "name": "add_probe", "description": "Synthetic integer addition only.",
                       "strict": True, "parameters": {"type": "object", "properties": {
                           "a": {"type": "integer"}, "b": {"type": "integer"}},
                           "required": ["a", "b"], "additionalProperties": False}}],
            "tool_choice": {"type": "function", "name": "add_probe"}, "parallel_tool_calls": False}


def validate_response(value):
    if not isinstance(value, dict) or value.get("status") != "completed" or not isinstance(value.get("output"), list):
        raise ValueError("Invalid or incomplete native response")
    if value.get("model") not in (MODEL, "gpt-5.5-2026-04-23"):
        raise ValueError("Unbound returned model label")


def build_second_request(first, value):
    validate_response(value)
    calls = [item for item in value["output"] if item.get("type") == "function_call"]
    if len(calls) != 1 or calls[0].get("name") != "add_probe":
        raise ValueError("Unexpected tool call")
    call = calls[0]
    arguments = json.loads(call["arguments"])
    if arguments != {"a": 3, "b": 4} or any(type(x) is not int for x in arguments.values()):
        raise ValueError("Unexpected tool arguments")
    if not isinstance(call.get("call_id"), str) or not call["call_id"]:
        raise ValueError("Missing native call ID")
    # Carry ALL returned native output items, including reasoning, without modification.
    return {**first, "input": [*first["input"], *value["output"],
                              {"type": "function_call_output", "call_id": call["call_id"], "output": "7"}],
            "tool_choice": "none"}


def final_text(value):
    validate_response(value)
    if any(item.get("type") == "function_call" for item in value["output"]):
        raise ValueError("Unexpected repeated tool call")
    return "".join(part.get("text", "") for item in value["output"] if item.get("type") == "message"
                   for part in item.get("content", []) if part.get("type") == "output_text")


def usage_counts(value):
    usage = value.get("usage", {}) if isinstance(value, dict) else {}
    return {name: usage.get(name) for name in ("input_tokens", "output_tokens", "total_tokens")
            if type(usage.get(name)) is int}


def probe_tools(key, transport=request):
    report = {"probe": "native_responses_tools", "model": MODEL, "base_url": BASE_URL,
              "reasoning_effort": "low", "maximum_requests": 2, "automatic_retry": False,
              "experimental_data_sent": False, "success": False, "requests": []}
    payload = build_first_request()
    first, metadata = transport("/responses", key, payload)
    report["requests"].append({**metadata, "usage": usage_counts(first)})
    try:
        second_payload = build_second_request(payload, first)
    except (ValueError, TypeError, KeyError) as exc:
        report["failure_stage"] = "first_response_contract"
        report["failure_class"] = type(exc).__name__
        return report
    second, metadata = transport("/responses", key, second_payload)
    report["requests"].append({**metadata, "usage": usage_counts(second)})
    try:
        report["success"] = final_text(second).strip() == "PROBE_OK_7"
        if not report["success"]:
            report["failure_stage"] = "unexpected_final_text"
    except (ValueError, TypeError, KeyError) as exc:
        report["failure_stage"] = "second_response_contract"
        report["failure_class"] = type(exc).__name__
    report["native_tool_roundtrip_verified"] = report["success"]
    report["native_history_preserved"] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--models", action="store_true")
    mode.add_argument("--gpt55-tools", action="store_true")
    args = parser.parse_args()
    key = KEY_PATH.read_text(encoding="utf-8-sig").strip()
    if not key.startswith("cr_") or any(char.isspace() for char in key) or len(key) > 4096:
        raise SystemExit("Invalid single-line CRS credential; value not displayed")
    if args.gpt55_tools:
        report = probe_tools(key)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["success"] else 1
    value, metadata = request("/models", key)
    models = []
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        for item in value["data"][:300]:
            name = item.get("id") if isinstance(item, dict) else None
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._/:+-]{1,120}", name) and not name.startswith(("cr_", "sk_")):
                models.append(name)
    print(json.dumps({"probe": "models", "base_url": BASE_URL, "credential_valid_format": True,
                      **metadata, "models": sorted(set(models)), "inference_requests": 0}, ensure_ascii=False, indent=2))
    return 0 if metadata.get("http_status") == 200 and models else 1


if __name__ == "__main__":
    raise SystemExit(main())
