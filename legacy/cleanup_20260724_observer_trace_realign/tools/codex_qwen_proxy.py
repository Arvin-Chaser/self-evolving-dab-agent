"""Local Responses-to-Qwen compatibility proxy for Codex CLI.

The proxy implements the small Responses API subset needed by Codex CLI and
translates it to DashScope's OpenAI-compatible Chat Completions endpoint.
It deliberately calls Qwen non-streaming and synthesizes Responses SSE events
locally so upstream streaming differences cannot break tool continuation.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("input_text") or item.get("output_text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def normalized_role(role: str | None) -> str:
    if role in {"developer", "tool"}:
        return "system" if role == "developer" else "tool"
    if role in {"system", "assistant", "user", "function"}:
        return role
    return "user"


def responses_tools_to_chat(tools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    chat_tools: list[dict[str, Any]] = []
    tool_kinds: dict[str, str] = {}
    for tool in tools:
        tool_type = str(tool.get("type") or "function")
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            function = tool.get("function")
            if isinstance(function, dict):
                name = function.get("name")
        if not isinstance(name, str) or not name:
            continue

        tool_kinds[name] = tool_type
        if tool_type == "function":
            parameters = tool.get("parameters") or {}
            description = tool.get("description") or ""
        else:
            parameters = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Raw input for this custom tool.",
                    }
                },
                "required": ["input"],
                "additionalProperties": False,
            }
            description = tool.get("description") or f"Invoke the {name} tool."

        chat_tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return chat_tools, tool_kinds


@dataclass
class ConversationState:
    messages: list[dict[str, Any]]
    response_tools: list[dict[str, Any]]
    tool_kinds: dict[str, str]
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)


class ConversationStore:
    def __init__(self) -> None:
        self._items: dict[str, ConversationState] = {}
        self._lock = threading.Lock()

    def get(self, response_id: str) -> ConversationState | None:
        with self._lock:
            state = self._items.get(response_id)
            return copy.deepcopy(state) if state else None

    def put(self, response_id: str, state: ConversationState) -> None:
        with self._lock:
            self._items[response_id] = copy.deepcopy(state)


def append_responses_input(state: ConversationState, input_value: Any) -> None:
    if isinstance(input_value, str):
        state.messages.append({"role": "user", "content": input_value})
        return
    if not isinstance(input_value, list):
        return

    for item in input_value:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"function_call_output", "custom_tool_call_output"}:
            call_id = item.get("call_id")
            call = state.calls.get(str(call_id), {})
            state.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": call.get("name"),
                    "content": str(item.get("output") or ""),
                }
            )
            continue
        if item_type in {"function_call", "custom_tool_call"}:
            call_id = str(item.get("call_id") or new_id("call"))
            name = str(item.get("name") or "")
            arguments = item.get("arguments")
            if arguments is None:
                raw_input = item.get("input") or ""
                arguments = json.dumps({"input": raw_input})
            call = {"call_id": call_id, "name": name, "arguments": str(arguments)}
            state.calls[call_id] = call
            state.messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": str(arguments)},
                        }
                    ],
                }
            )
            continue

        role = normalized_role(item.get("role"))
        content = text_content(item.get("content"))
        if content:
            state.messages.append({"role": role, "content": content})


def legacy_payload(payload: dict[str, Any], calls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    converted_messages: list[dict[str, Any]] = []
    for message in payload["messages"]:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            tool_call = message["tool_calls"][0]
            converted_messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "function_call": tool_call["function"],
                }
            )
        elif message.get("role") == "tool":
            call = calls.get(str(message.get("tool_call_id")), {})
            converted_messages.append(
                {
                    "role": "function",
                    "name": message.get("name") or call.get("name") or "tool",
                    "content": message.get("content") or "",
                }
            )
        else:
            converted_messages.append(
                {key: value for key, value in message.items() if key in {"role", "content", "name"}}
            )

    legacy = {
        "model": payload["model"],
        "messages": converted_messages,
        "temperature": payload.get("temperature", 0),
    }
    functions = [tool["function"] for tool in payload.get("tools") or []]
    if functions:
        legacy["functions"] = functions
    return legacy


class QwenChatClient:
    def __init__(self, base_url: str, api_key: str, timeout_sec: float) -> None:
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_sec),
            trust_env=True,
        )

    def close(self) -> None:
        self.client.close()

    def complete(
        self,
        model: str,
        state: ConversationState,
        chat_tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": state.messages,
            "temperature": 0,
        }
        if chat_tools:
            payload["tools"] = chat_tools

        retries = max(1, int(os.getenv("CODEX_QWEN_UPSTREAM_RETRIES", "3")))
        last_exc: BaseException | None = None
        for attempt in range(1, retries + 1):
            try:
                response = self.client.post(self.url, json=payload)
                if response.status_code >= 400 and any(message.get("role") == "tool" for message in state.messages):
                    response = self.client.post(self.url, json=legacy_payload(payload, state.calls))
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else 0
                if status < 500:
                    raise
            if attempt < retries:
                delay = min(8.0, 0.75 * attempt)
                sys.stderr.write(
                    f"[codex-qwen-proxy] upstream retry {attempt}/{retries} after "
                    f"{type(last_exc).__name__}: {last_exc}\n"
                )
                sys.stderr.flush()
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc


def qwen_message(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("Qwen response contained no choices.")
    message = choices[0].get("message") or {}
    usage = payload.get("usage") or {}
    return message, usage


def assistant_message_and_outputs(
    message: dict[str, Any],
    tool_kinds: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    tool_calls = message.get("tool_calls") or []
    if not tool_calls and message.get("function_call"):
        tool_calls = [
            {
                "id": new_id("call"),
                "type": "function",
                "function": message["function_call"],
            }
        ]

    if tool_calls:
        normalized_calls: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        call_index: dict[str, dict[str, Any]] = {}
        for raw_call in tool_calls:
            function = raw_call.get("function") or {}
            call_id = str(raw_call.get("id") or new_id("call"))
            name = str(function.get("name") or "")
            arguments = str(function.get("arguments") or "{}")
            normalized_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
            call_index[call_id] = {"call_id": call_id, "name": name, "arguments": arguments}
            if tool_kinds.get(name) == "custom":
                try:
                    decoded = json.loads(arguments)
                    custom_input = decoded.get("input", arguments) if isinstance(decoded, dict) else arguments
                except json.JSONDecodeError:
                    custom_input = arguments
                outputs.append(
                    {
                        "id": new_id("ctc"),
                        "type": "custom_tool_call",
                        "status": "completed",
                        "call_id": call_id,
                        "name": name,
                        "input": custom_input,
                    }
                )
            else:
                outputs.append(
                    {
                        "id": new_id("fc"),
                        "type": "function_call",
                        "status": "completed",
                        "call_id": call_id,
                        "name": name,
                        "arguments": arguments,
                    }
                )

        assistant = {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": normalized_calls,
        }
        return assistant, outputs, call_index

    text = message.get("content") or ""
    assistant = {"role": "assistant", "content": text}
    outputs = [
        {
            "id": new_id("msg"),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]
    return assistant, outputs, {}


def responses_usage(usage: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens),
    }


def response_object(
    request: dict[str, Any],
    response_id: str,
    outputs: list[dict[str, Any]],
    usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": request.get("instructions"),
        "model": request.get("model") or META_AGENT_MODEL,
        "output": outputs,
        "parallel_tool_calls": True,
        "previous_response_id": request.get("previous_response_id"),
        "tools": request.get("tools") or [],
        "usage": responses_usage(usage),
        "metadata": request.get("metadata") or {},
    }


def in_progress_response(response: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(response)
    value["status"] = "in_progress"
    value["output"] = []
    value["usage"] = None
    return value


def sse_events(response: dict[str, Any], *, start_sequence: int = 0, include_initial: bool = True) -> list[dict[str, Any]]:
    sequence = start_sequence
    events: list[dict[str, Any]] = []

    def add(event_type: str, **values: Any) -> None:
        nonlocal sequence
        events.append({"type": event_type, "sequence_number": sequence, **values})
        sequence += 1

    progress = in_progress_response(response)
    if include_initial:
        add("response.created", response=progress)
        add("response.in_progress", response=progress)
    for output_index, item in enumerate(response["output"]):
        add("response.output_item.added", output_index=output_index, item=item)
        if item["type"] == "function_call":
            add(
                "response.function_call_arguments.done",
                item_id=item["id"],
                output_index=output_index,
                name=item["name"],
                arguments=item["arguments"],
            )
        elif item["type"] == "custom_tool_call":
            add(
                "response.custom_tool_call_input.done",
                item_id=item["id"],
                output_index=output_index,
                input=item["input"],
            )
        else:
            part = item["content"][0]
            add("response.content_part.added", item_id=item["id"], output_index=output_index, content_index=0, part=part)
            add("response.output_text.done", item_id=item["id"], output_index=output_index, content_index=0, text=part["text"])
            add("response.content_part.done", item_id=item["id"], output_index=output_index, content_index=0, part=part)
        add("response.output_item.done", output_index=output_index, item=item)
    add("response.completed", response=response)
    return events


@dataclass
class PreparedResponse:
    request: dict[str, Any]
    state: ConversationState
    chat_tools: list[dict[str, Any]]
    response_id: str


@dataclass
class ProxyApplication:
    qwen: QwenChatClient
    store: ConversationStore
    default_model: str
    local_token: str

    def prepare_response(self, request: dict[str, Any]) -> PreparedResponse:
        previous_response_id = request.get("previous_response_id")
        state = self.store.get(str(previous_response_id)) if previous_response_id else None
        if state is None:
            response_tools = request.get("tools") or []
            chat_tools, tool_kinds = responses_tools_to_chat(response_tools)
            state = ConversationState(messages=[], response_tools=response_tools, tool_kinds=tool_kinds)
            instructions = request.get("instructions")
            if isinstance(instructions, str) and instructions:
                state.messages.append({"role": "system", "content": instructions})
        else:
            chat_tools, _ = responses_tools_to_chat(state.response_tools)

        append_responses_input(state, request.get("input"))
        return PreparedResponse(request=request, state=state, chat_tools=chat_tools, response_id=new_id("resp"))

    def progress_response(self, prepared: PreparedResponse) -> dict[str, Any]:
        return response_object(prepared.request, prepared.response_id, [], {})

    def complete_prepared_response(self, prepared: PreparedResponse) -> dict[str, Any]:
        model = str(prepared.request.get("model") or self.default_model)
        qwen_payload = self.qwen.complete(model, prepared.state, prepared.chat_tools)
        message, usage = qwen_message(qwen_payload)
        assistant, outputs, new_calls = assistant_message_and_outputs(message, prepared.state.tool_kinds)
        prepared.state.messages.append(assistant)
        prepared.state.calls.update(new_calls)
        self.store.put(prepared.response_id, prepared.state)
        return response_object(prepared.request, prepared.response_id, outputs, usage)

    def failed_response(self, prepared: PreparedResponse, exc: BaseException) -> dict[str, Any]:
        response = response_object(prepared.request, prepared.response_id, [], {})
        response["status"] = "failed"
        response["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return response

    def create_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.complete_prepared_response(self.prepare_response(request))

    def create_chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        """Forward an OpenAI-compatible chat completion request to Qwen.

        This non-streaming endpoint is intentionally simple. It lets local
        structured patch-spec generation use llm_client/OpenAI directly against
        the local proxy, avoiding Codex CLI Responses streaming when no tool
        continuation is needed.
        """

        messages = request.get("messages") or []
        if not isinstance(messages, list):
            raise ValueError("chat/completions request.messages must be a list")
        normalized_messages: list[dict[str, Any]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = normalized_role(item.get("role"))
            content = item.get("content")
            if isinstance(content, list):
                content = text_content(content)
            elif content is None:
                content = ""
            normalized: dict[str, Any] = {"role": role, "content": str(content)}
            if item.get("name"):
                normalized["name"] = str(item.get("name"))
            if item.get("tool_calls"):
                normalized["tool_calls"] = item.get("tool_calls")
            if item.get("tool_call_id"):
                normalized["tool_call_id"] = item.get("tool_call_id")
            normalized_messages.append(normalized)

        tools = request.get("tools") or []
        if not isinstance(tools, list):
            tools = []
        state = ConversationState(messages=normalized_messages, response_tools=tools, tool_kinds={})
        model = str(request.get("model") or self.default_model)
        return self.qwen.complete(model, state, tools)


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "CodexQwenProxy/0.1"

    @property
    def app(self) -> ProxyApplication:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"[codex-qwen-proxy] {format % args}\n")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_sse_headers(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def write_sse_event(self, event: dict[str, Any]) -> None:
        event_type = event["type"]
        data = json.dumps(event, ensure_ascii=False)
        self.wfile.write(f"event: {event_type}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def write_sse_comment(self, comment: str = "keep-alive") -> None:
        self.wfile.write(f": {comment}\n\n".encode("utf-8"))
        self.wfile.flush()

    def authorized(self) -> bool:
        if not self.app.local_token:
            return True
        return self.headers.get("Authorization") == f"Bearer {self.app.local_token}"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health", "/v1/health"}:
            self.send_json(HTTPStatus.OK, {"status": "ok"})
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found."}})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path not in {"/responses", "/v1/responses", "/chat/completions", "/v1/chat/completions"}:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found."}})
            return
        if not self.authorized():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "Invalid local proxy token."}})
            return

        try:
            content_length = int(self.headers.get("Content-Length") or "0")
            request = json.loads(self.rfile.read(content_length))
            if path in {"/chat/completions", "/v1/chat/completions"}:
                if request.get("stream"):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": "chat/completions streaming is not implemented by this local proxy."}})
                    return
                response = self.app.create_chat_completion(request)
                self.send_json(HTTPStatus.OK, response)
                return
            if request.get("stream"):
                prepared = self.app.prepare_response(request)
                self.send_sse_headers()
                progress_response = self.app.progress_response(prepared)
                for event in sse_events(progress_response, include_initial=True):
                    if event["type"] in {"response.created", "response.in_progress"}:
                        self.write_sse_event(event)
                result: dict[str, Any] = {}

                def run_upstream() -> None:
                    try:
                        result["response"] = self.app.complete_prepared_response(prepared)
                    except BaseException as exc:  # noqa: BLE001 - returned as SSE failure event
                        result["error"] = exc

                worker = threading.Thread(target=run_upstream, daemon=True)
                worker.start()
                heartbeat_interval = float(os.getenv("CODEX_QWEN_PROXY_HEARTBEAT_SEC", "5"))
                while worker.is_alive():
                    worker.join(heartbeat_interval)
                    if worker.is_alive():
                        self.write_sse_comment("qwen-proxy upstream pending")
                if "error" in result:
                    failed = self.app.failed_response(prepared, result["error"])
                    self.write_sse_event({"type": "response.failed", "sequence_number": 2, "response": failed})
                else:
                    for event in sse_events(result["response"], start_sequence=2, include_initial=False):
                        self.write_sse_event(event)
                self.close_connection = True
            else:
                response = self.app.create_response(request)
                self.send_json(HTTPStatus.OK, response)
        except Exception as exc:
            self.log_message("request failed: %s: %s", type(exc).__name__, exc)
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": {"type": type(exc).__name__, "message": str(exc)}},
            )


class ProxyServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], app: ProxyApplication) -> None:
        super().__init__(address, ProxyHandler)
        self.app = app


def build_application(args: argparse.Namespace) -> ProxyApplication:
    if not META_AGENT_API_KEY:
        raise SystemExit("Meta-agent API key is not configured.")
    local_token = args.local_token or os.getenv("CODEX_QWEN_PROXY_TOKEN", "local-qwen-proxy")
    return ProxyApplication(
        qwen=QwenChatClient(args.upstream_base_url, META_AGENT_API_KEY, args.timeout_sec),
        store=ConversationStore(),
        default_model=args.model,
        local_token=local_token,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--model", default=META_AGENT_MODEL)
    parser.add_argument("--upstream-base-url", default=META_AGENT_BASE_URL)
    parser.add_argument("--timeout-sec", type=float, default=META_AGENT_TIMEOUT_SEC)
    parser.add_argument("--local-token")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The compatibility proxy must bind to a loopback address.")

    app = build_application(args)
    server = ProxyServer((args.host, args.port), app)
    print(
        json.dumps(
            {
                "status": "listening",
                "address": f"http://{args.host}:{args.port}/v1",
                "model": args.model,
                "upstream_base_url": args.upstream_base_url,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.qwen.close()


if __name__ == "__main__":
    main()
