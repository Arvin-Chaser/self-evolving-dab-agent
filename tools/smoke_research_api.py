#!/usr/bin/env python3
"""Verify the configured research API without printing credentials or content."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def request(base_url: str, api_key: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.status, json.load(response)


def main() -> int:
    api_key = os.environ.get("DAB_TOOL_AGENT_API_KEY", "")
    base_url = os.environ.get("DAB_TOOL_AGENT_OPENAI_BASE_URL", "").rstrip("/")
    model = os.environ.get("DAB_TOOL_AGENT_MODEL", "glm-5.3-flash")
    if not api_key or not base_url:
        print("configuration=missing_api_key_or_base_url")
        return 2
    try:
        models_status, catalog = request(base_url, api_key, "/models")
        model_ids = {
            row.get("id")
            for row in catalog.get("data", [])
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        print(f"models_http={models_status}")
        print(f"requested_model={model}")
        print(f"requested_model_present={str(model in model_ids).lower()}")
        if model not in model_ids:
            return 3
        completion_status, completion = request(
            base_url,
            api_key,
            "/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply exactly OK."}],
                "temperature": 0,
                "max_tokens": 8,
            },
        )
        print(f"completion_http={completion_status}")
        print(f"response_model={completion.get('model', 'missing')}")
        print(f"completion_has_choice={str(bool(completion.get('choices'))).lower()}")
        return 0 if completion_status == 200 and completion.get("choices") else 4
    except urllib.error.HTTPError as exc:
        print(f"api_http_error={exc.code}")
        return 5
    except Exception as exc:
        print(f"api_error_type={type(exc).__name__}")
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
