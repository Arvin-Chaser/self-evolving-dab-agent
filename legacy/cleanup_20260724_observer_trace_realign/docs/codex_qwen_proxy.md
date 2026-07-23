# Codex-Qwen Responses Compatibility Proxy

This local proxy lets Codex CLI use a Qwen model through DashScope while
preserving Codex's Responses API tool loop.

## Why It Exists

DashScope accepts an initial Responses function call, but its continuation
adapter currently converts `function_call_output` into `role="tool"` while its
internal Agent validator only accepts `user`, `assistant`, `system`, and
`function`. The second turn therefore fails before Qwen can observe the tool
result.

The proxy accepts Codex Responses requests, stores conversation state in
memory, translates tools and tool outputs to Qwen Chat Completions messages,
and emits a local Responses-compatible result. Upstream Qwen calls are
non-streaming; the proxy synthesizes the SSE events expected by Codex and
always terminates successful streams with `response.completed`.

## Start The Proxy

Run inside WSL after activating the repository environment and configuring the
host proxy documented in the Codex memory for this repository:

```bash
cd /home/m0st1ma/research/text2sql
source .venv/bin/activate
python tools/codex_qwen_proxy.py --port 8787
```

The server binds to `127.0.0.1` by default and refuses non-loopback bindings.
It reads the existing meta-agent Qwen configuration from `.env` through
`llm_client.py`. API keys are never included in proxy responses or logs.

## Codex Provider Configuration

Use an isolated Codex configuration while testing:

```toml
model = "qwen-plus"
model_provider = "qwen_proxy"

[model_providers.qwen_proxy]
name = "Local Qwen Responses Proxy"
base_url = "http://127.0.0.1:8787/v1"
env_key = "CODEX_QWEN_PROXY_TOKEN"
wire_api = "responses"
```

Set the local token before starting Codex:

```bash
export CODEX_QWEN_PROXY_TOKEN="local-qwen-proxy"
```

The default token is only a loopback guard. It is not the DashScope API key.

## Current Scope

Supported:

- text input and output;
- function and custom tools;
- function and custom tool outputs;
- `previous_response_id` continuation;
- non-streaming Responses JSON;
- synthesized Responses SSE.

Not yet supported:

- persisted state across proxy restarts;
- images, audio, or hosted tools;
- parallel custom tool execution;
- production authentication or remote binding.
