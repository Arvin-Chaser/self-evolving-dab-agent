"""Distinguish provider/transport termination from an agent's task outcome."""
import re
from typing import Any


def provider_failure(row: dict[str, Any]) -> bool:
    reason = str(row.get("terminate_reason") or "")
    if not reason.startswith("llm_response_failed"):
        return False
    codes = re.findall(r"(?:Error code:\s*|status code\s+)(\d{3})", reason, flags=re.I)
    if any(int(code) >= 500 or int(code) in {401, 403, 429} for code in codes):
        return True
    return any(name in reason for name in (
        "APIConnectionError", "APITimeoutError", "ConnectTimeout", "ReadTimeout", "TimeoutError",
    ))
