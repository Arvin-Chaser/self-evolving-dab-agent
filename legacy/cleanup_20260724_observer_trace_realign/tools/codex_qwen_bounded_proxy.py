"""Bounded entry point for the Codex-Qwen compatibility proxy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from llm_client import (
    META_AGENT_API_KEY,
    META_AGENT_BASE_URL,
    META_AGENT_MODEL,
    META_AGENT_TIMEOUT_SEC,
)
from tools.codex_qwen_proxy import (
    ConversationState,
    ConversationStore,
    ProxyApplication,
    ProxyServer,
    QwenChatClient,
)


class BudgetedQwenChatClient(QwenChatClient):
    def __init__(self, *args, max_upstream_rounds: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.max_upstream_rounds = max_upstream_rounds
        self.upstream_rounds = 0

    def complete(
        self,
        model: str,
        state: ConversationState,
        chat_tools: list[dict],
    ) -> dict:
        self.upstream_rounds += 1
        effective_tools = chat_tools
        if self.upstream_rounds >= self.max_upstream_rounds:
            state.messages.append(
                {
                    "role": "system",
                    "content": (
                        "The hard tool budget is exhausted. Do not request another tool. "
                        "Finish now with the best evidence-grounded report and only claim edits "
                        "that were already completed."
                    ),
                }
            )
            effective_tools = []
        return super().complete(model, state, effective_tools)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--model", default=META_AGENT_MODEL)
    parser.add_argument("--upstream-base-url", default=META_AGENT_BASE_URL)
    parser.add_argument("--timeout-sec", type=float, default=META_AGENT_TIMEOUT_SEC)
    parser.add_argument("--local-token")
    parser.add_argument("--max-upstream-rounds", type=int, default=12)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The compatibility proxy must bind to a loopback address.")
    if args.max_upstream_rounds < 2:
        raise SystemExit("max-upstream-rounds must be at least 2.")
    if not META_AGENT_API_KEY:
        raise SystemExit("Meta-agent API key is not configured.")

    local_token = args.local_token or os.getenv("CODEX_QWEN_PROXY_TOKEN", "local-qwen-proxy")
    qwen = BudgetedQwenChatClient(
        args.upstream_base_url,
        META_AGENT_API_KEY,
        args.timeout_sec,
        max_upstream_rounds=args.max_upstream_rounds,
    )
    app = ProxyApplication(
        qwen=qwen,
        store=ConversationStore(),
        default_model=args.model,
        local_token=local_token,
    )
    server = ProxyServer((args.host, args.port), app)
    print(
        json.dumps(
            {
                "status": "listening",
                "address": f"http://{args.host}:{args.port}/v1",
                "model": args.model,
                "max_upstream_rounds": args.max_upstream_rounds,
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
        qwen.close()


if __name__ == "__main__":
    main()
