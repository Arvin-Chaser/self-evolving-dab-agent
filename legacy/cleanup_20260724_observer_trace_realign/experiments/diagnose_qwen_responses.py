"""Diagnose two-turn Responses API tool continuation against DashScope/Qwen."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from llm_client import (  # noqa: E402
    META_AGENT_API_KEY,
    META_AGENT_BASE_URL,
    META_AGENT_MODEL,
    META_AGENT_TIMEOUT_SEC,
)


PROBE_PROMPT = (
    "Call get_probe_value exactly once with key='probe'. "
    "After receiving the tool output, return exactly CONTINUATION_OK."
)
PROBE_TOOL = {
    "type": "function",
    "name": "get_probe_value",
    "description": "Return a deterministic diagnostic value for a key.",
    "parameters": {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
        "additionalProperties": False,
    },
}
PROBE_OUTPUT = "TOOL_RESULT_OK"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def response_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/responses"


def find_function_calls(value: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") == "function_call":
            calls.append(
                {
                    "call_id": value.get("call_id"),
                    "name": value.get("name"),
                    "arguments": value.get("arguments"),
                }
            )
        for nested in value.values():
            calls.extend(find_function_calls(nested))
    elif isinstance(value, list):
        for nested in value:
            calls.extend(find_function_calls(nested))
    return calls


def find_output_text(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        if value.get("type") == "output_text" and isinstance(value.get("text"), str):
            texts.append(value["text"])
        for nested in value.values():
            texts.extend(find_output_text(nested))
    elif isinstance(value, list):
        for nested in value:
            texts.extend(find_output_text(nested))
    return texts


def deduplicate_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for call in calls:
        key = (call.get("call_id"), call.get("name"), call.get("arguments"))
        if key not in seen:
            seen.add(key)
            unique.append(call)
    return unique


def response_id_from(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("id"), str) and value.get("object") == "response":
        return value["id"]
    response = value.get("response")
    if isinstance(response, dict) and isinstance(response.get("id"), str):
        return response["id"]
    return None


def summarize_json_response(response: httpx.Response, elapsed_sec: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "http_status": response.status_code,
        "elapsed_sec": round(elapsed_sec, 3),
        "content_type": response.headers.get("content-type"),
    }
    try:
        payload = response.json()
    except ValueError:
        result["parse_error"] = "Response body was not valid JSON."
        result["body_preview"] = response.text[:500]
        return result

    result.update(
        {
            "response_id": response_id_from(payload),
            "status": payload.get("status") if isinstance(payload, dict) else None,
            "function_calls": deduplicate_calls(find_function_calls(payload)),
            "output_text": "".join(find_output_text(payload)),
        }
    )
    if response.status_code >= 400 and isinstance(payload, dict):
        result["error"] = payload.get("error")
    return result


def post_json(client: httpx.Client, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    try:
        response = client.post(url, json=payload)
        return summarize_json_response(response, time.time() - started)
    except Exception as exc:  # Diagnostic code must preserve transport failures.
        return {
            "transport_error": f"{type(exc).__name__}: {exc}",
            "elapsed_sec": round(time.time() - started, 3),
        }


def post_stream(client: httpx.Client, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    event_types: list[str] = []
    calls: list[dict[str, Any]] = []
    texts: list[str] = []
    response_id: str | None = None
    terminal_event_seen = False
    done_marker_seen = False
    result: dict[str, Any] = {}
    pending_event_name: str | None = None

    try:
        with client.stream("POST", url, json=payload) as response:
            result.update(
                {
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                }
            )
            for line in response.iter_lines():
                if not line:
                    pending_event_name = None
                    continue
                if line.startswith("event:"):
                    pending_event_name = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line.split(":", 1)[1].strip()
                if data == "[DONE]":
                    done_marker_seen = True
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    result.setdefault("invalid_data_previews", []).append(data[:300])
                    continue

                event_type = event.get("type") or pending_event_name or "unknown"
                event_types.append(event_type)
                if event_type in {"response.completed", "response.failed", "response.incomplete"}:
                    terminal_event_seen = True
                response_id = response_id or response_id_from(event)
                calls.extend(find_function_calls(event))
                texts.extend(find_output_text(event))
    except Exception as exc:  # Diagnostic code must preserve transport failures.
        result["transport_error"] = f"{type(exc).__name__}: {exc}"

    result.update(
        {
            "elapsed_sec": round(time.time() - started, 3),
            "response_id": response_id,
            "event_types": event_types,
            "terminal_event_seen": terminal_event_seen,
            "done_marker_seen": done_marker_seen,
            "function_calls": deduplicate_calls(calls),
            "output_text": "".join(texts),
        }
    )
    return result


def initial_payload(model: str, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "input": PROBE_PROMPT,
        "tools": [PROBE_TOOL],
        "stream": stream,
    }


def stateful_continuation_payload(
    model: str,
    response_id: str,
    call_id: str,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": model,
        "previous_response_id": response_id,
        "input": [
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": PROBE_OUTPUT,
            }
        ],
        "tools": [PROBE_TOOL],
        "stream": stream,
    }


def full_history_continuation_payload(
    model: str,
    call: dict[str, Any],
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {"role": "user", "content": PROBE_PROMPT},
            {
                "type": "function_call",
                "call_id": call["call_id"],
                "name": call["name"],
                "arguments": call.get("arguments") or "{}",
            },
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": PROBE_OUTPUT,
            },
        ],
        "tools": [PROBE_TOOL],
        "stream": stream,
    }


def first_call(result: dict[str, Any]) -> dict[str, Any] | None:
    calls = result.get("function_calls") or []
    for call in calls:
        if call.get("call_id") and call.get("name"):
            return call
    return None


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    url = response_url(args.base_url)
    headers = {
        "Authorization": f"Bearer {META_AGENT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    timeout = httpx.Timeout(args.timeout_sec)
    report: dict[str, Any] = {
        "model": args.model,
        "base_url": args.base_url,
        "response_url": url,
        "proxy_environment_used": True,
        "tests": {},
    }

    with httpx.Client(headers=headers, timeout=timeout, trust_env=True) as client:
        nonstream_first = post_json(client, url, initial_payload(args.model, stream=False))
        report["tests"]["nonstream_initial"] = nonstream_first
        call = first_call(nonstream_first)
        response_id = nonstream_first.get("response_id")

        if call and response_id:
            report["tests"]["nonstream_stateful_continuation"] = post_json(
                client,
                url,
                stateful_continuation_payload(
                    args.model,
                    response_id=response_id,
                    call_id=call["call_id"],
                    stream=False,
                ),
            )
            report["tests"]["nonstream_full_history_continuation"] = post_json(
                client,
                url,
                full_history_continuation_payload(args.model, call, stream=False),
            )
        else:
            report["tests"]["nonstream_continuations_skipped"] = {
                "reason": "Initial response did not expose both response_id and function call."
            }

        stream_first = post_stream(client, url, initial_payload(args.model, stream=True))
        report["tests"]["stream_initial"] = stream_first
        stream_call = first_call(stream_first)
        stream_response_id = stream_first.get("response_id")
        if stream_call and stream_response_id:
            report["tests"]["stream_stateful_continuation"] = post_stream(
                client,
                url,
                stateful_continuation_payload(
                    args.model,
                    response_id=stream_response_id,
                    call_id=stream_call["call_id"],
                    stream=True,
                ),
            )
        else:
            report["tests"]["stream_continuation_skipped"] = {
                "reason": "Initial stream did not expose both response_id and function call."
            }

    report["continuation_ok"] = any(
        "CONTINUATION_OK" in str(test.get("output_text") or "")
        for test in report["tests"].values()
        if isinstance(test, dict)
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=META_AGENT_MODEL)
    parser.add_argument("--base-url", default=META_AGENT_BASE_URL)
    parser.add_argument("--timeout-sec", type=float, default=META_AGENT_TIMEOUT_SEC)
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "logs" / "meta_agent" / "qwen_responses_diagnostic.json"),
    )
    args = parser.parse_args()

    if not META_AGENT_API_KEY:
        raise SystemExit("Meta-agent API key is not configured.")

    report = run_diagnostic(args)
    output_path = Path(args.output).resolve()
    write_json(output_path, report)
    print(json.dumps({"output": str(output_path), "continuation_ok": report["continuation_ok"]}))


if __name__ == "__main__":
    main()
