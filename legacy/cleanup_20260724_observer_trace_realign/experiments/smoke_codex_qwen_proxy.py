"""Run a real two-turn tool continuation through the local Qwen proxy."""

from __future__ import annotations

import argparse
import json
import sys
import threading
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
from tools.codex_qwen_proxy import (  # noqa: E402
    ConversationStore,
    ProxyApplication,
    ProxyServer,
    QwenChatClient,
)


TOOL = {
    "type": "function",
    "name": "get_probe_value",
    "description": "Return a deterministic diagnostic value.",
    "parameters": {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
        "additionalProperties": False,
    },
}


def function_call(response: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in response.get("output") or [] if item.get("type") == "function_call")


def output_text(response: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in response.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                texts.append(content.get("text") or "")
    return "".join(texts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=META_AGENT_MODEL)
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "logs" / "meta_agent" / "codex_qwen_proxy_smoke.json"),
    )
    args = parser.parse_args()

    if not META_AGENT_API_KEY:
        raise SystemExit("Meta-agent API key is not configured.")

    token = "proxy-smoke-token"
    app = ProxyApplication(
        qwen=QwenChatClient(META_AGENT_BASE_URL, META_AGENT_API_KEY, META_AGENT_TIMEOUT_SEC),
        store=ConversationStore(),
        default_model=args.model,
        local_token=token,
    )
    server = ProxyServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{server.server_port}/v1/responses"
    headers = {"Authorization": f"Bearer {token}"}
    report: dict[str, Any] = {"model": args.model, "url": url}
    try:
        with httpx.Client(headers=headers, timeout=120, trust_env=False) as client:
            first_response = client.post(
                url,
                json={
                    "model": args.model,
                    "input": (
                        "Call get_probe_value exactly once with key='probe'. "
                        "After receiving the output, return exactly CONTINUATION_OK."
                    ),
                    "tools": [TOOL],
                    "stream": False,
                },
            )
            first_response.raise_for_status()
            first = first_response.json()
            call = function_call(first)

            second_response = client.post(
                url,
                json={
                    "model": args.model,
                    "previous_response_id": first["id"],
                    "input": [
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": "TOOL_RESULT_OK",
                        }
                    ],
                    "tools": [TOOL],
                    "stream": False,
                },
            )
            second_response.raise_for_status()
            second = second_response.json()
            text = output_text(second)
            report.update(
                {
                    "first_response_id": first["id"],
                    "call_name": call["name"],
                    "second_response_id": second["id"],
                    "output_text": text,
                    "passed": "CONTINUATION_OK" in text,
                }
            )
    except Exception as exc:
        report.update({"passed": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        server.shutdown()
        server.server_close()
        app.qwen.close()
        thread.join(timeout=5)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "passed": report["passed"]}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
