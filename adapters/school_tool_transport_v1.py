"""One-shot transport for the explicitly authorized school endpoint; no retries.

Credentials stay outside source/logs. Redirects are refused to avoid forwarding
Authorization to a different host. Raw response bytes are preserved as metadata.
"""
from __future__ import annotations

import base64
import hashlib
import time
import urllib.error
import urllib.request

from adapters.school_tool_compat_v1 import (
    CompatibilityError, MAX_BYTES, canonical, normalize_response, strict_loads,
    validate_request,
)

BASE_URL = "http://10.27.130.10:32788/v1"


class TransportError(RuntimeError):
    def __init__(self, kind: str, status: int | None = None):
        super().__init__(kind)
        self.kind, self.status = kind, status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SchoolToolClient:
    def __init__(self, api_key: str, timeout: float = 45, protocol: str = "v1"):
        if not isinstance(api_key, str) or not api_key or "\n" in api_key or "\r" in api_key:
            raise CompatibilityError("Invalid single-line credential")
        if not 1 <= timeout <= 300:
            raise CompatibilityError("Timeout must be between 1 and 300 seconds")
        self._key = api_key
        self.timeout = timeout
        if protocol == "v1":
            self.normalize = normalize_response
        elif protocol == "v2":
            from adapters.school_tool_compat_v2 import normalize_response as v2
            self.normalize = v2
        else:
            raise CompatibilityError("Unsupported protocol version")

    def complete(self, payload: dict) -> dict:
        validate_request(payload)
        request = urllib.request.Request(
            BASE_URL + "/chat/completions", data=canonical(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"},
            method="POST",
        )
        # Honor the user's configured network route (including a local VPN
        # proxy), as the original verified probe did. Never redirect or retry.
        opener = urllib.request.build_opener(_NoRedirect())
        started = time.perf_counter()
        try:
            with opener.open(request, timeout=self.timeout) as remote:
                if remote.status != 200:
                    raise TransportError("unexpected_http_status", remote.status)
                body = remote.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise TransportError("upstream_http_error", error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TransportError("upstream_connection_or_timeout") from None
        if len(body) > MAX_BYTES:
            raise CompatibilityError("Upstream response size limit exceeded")
        evidence = {
            "upstream_url": BASE_URL,
            "original_wire_sha256": hashlib.sha256(body).hexdigest(),
            "original_wire_base64": base64.b64encode(body).decode("ascii"),
            "http_status": 200, "attempts": 1,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "outbound_request_changed": False,
            "network_route": "system_proxy_configuration",
        }
        try:
            original = strict_loads(body)
            normalized = self.normalize(payload, original)
        except CompatibilityError as error:
            # Preserve rejected provider bytes too. Callers may explicitly
            # archive them; do not print evidence/contents from this module.
            error.provider_evidence = evidence
            raise
        normalized["school_tool_compat"].update(evidence)
        return normalized
