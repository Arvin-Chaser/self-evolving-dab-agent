"""Opt-in loopback-only Chat Completions bridge. No tool execution or retries.

Existing DAB --openai-compatible-base-url can target this endpoint without any
candidate edits. Do not mix provider outputs into an existing GLM run.
"""
from __future__ import annotations

import argparse
import hmac
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.school_tool_compat_v1 import CompatibilityError, MAX_BYTES, MODEL, POLICY, strict_loads, validate_request
from adapters.school_tool_transport_v1 import SchoolToolClient, TransportError


class SchoolBridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, key: str, port: int = 0, timeout: float = 45, complete=None, protocol="v1", relay_key=None):
        # Remote callers authenticate with an independent, revocable relay
        # credential. The school credential never leaves this computer.
        self._key = key if relay_key is None else relay_key
        if not isinstance(self._key, str) or not self._key or any(c in self._key for c in "\r\n"):
            raise CompatibilityError("Invalid single-line relay credential")
        client = SchoolToolClient(key, timeout, protocol)
        self.policy = POLICY if protocol == "v1" else "school_native_json_xml_reasoning_v2"
        self.complete = complete or client.complete
        self.capacity = threading.BoundedSemaphore(3)
        super().__init__(("127.0.0.1", port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    # No access logs, headers, credentials, request bodies, or provider error
    # bodies are printed. Provenance travels with the response, not to disk.
    def log_message(self, fmt, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def _send(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _error(self, status, code, text, evidence=None):
        body = {"error": {"type": "school_tool_compat_error", "code": code, "message": text}}
        if evidence is not None:
            body["school_tool_compat_rejected_response"] = evidence
        self._send(status, body)

    def _authorized(self):
        supplied = self.headers.get_all("Authorization") or []
        return len(supplied) == 1 and hmac.compare_digest(supplied[0].encode(), ("Bearer " + self.server._key).encode())

    def do_GET(self):
        if not self._authorized():
            return self._error(401, "unauthorized", "Valid local API authentication required")
        if self.path == "/v1/models":
            # Adapter-supported model inventory, not a live upstream discovery.
            return self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": self.server.policy}]})
        return self._error(404, "not_found", "Only /v1/models and /v1/chat/completions are supported")

    def do_POST(self):
        lengths = self.headers.get_all("Content-Length") or []
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            return self._error(400, "invalid_framing", "Exactly one Content-Length and no Transfer-Encoding required")
        try:
            length = int(lengths[0])
        except ValueError:
            return self._error(400, "invalid_length", "Invalid Content-Length")
        if not 0 < length <= MAX_BYTES:
            return self._error(413, "size_limit", "Request size limit exceeded")
        # Drain the bounded body before rejecting capacity. Closing a Windows
        # socket with unread input can reset it before the 503 reaches callers.
        body = self.rfile.read(length)
        if len(body) != length:
            return self._error(400, "incomplete_body", "Incomplete request body")
        if not self._authorized():
            return self._error(401, "unauthorized", "Valid local API authentication required")
        if self.path != "/v1/chat/completions":
            return self._error(404, "not_found", "Unsupported endpoint")
        if self.headers.get_content_type() != "application/json":
            return self._error(415, "content_type", "application/json required")
        if not self.server.capacity.acquire(blocking=False):
            return self._error(503, "capacity", "Three requests already active; no automatic retry is performed here")
        try:
            request = strict_loads(body)
            validate_request(request)
            normalized = self.server.complete(request)
            self._send(200, normalized)
        except CompatibilityError as error:
            # 422: nonretryable fail-closed protocol failure (OpenAI clients do
            # not normally retry this status). No inferred/repaired tool call.
            self._error(422, "protocol_rejected", str(error), getattr(error, "provider_evidence", None))
        except TransportError as error:
            # Do not trigger SDK retries after ambiguous provider dispatch.
            self._error(424, "upstream_request_failed", f"Upstream request failed ({error.kind}; status={error.status}); do not automatically replay")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._error(424, "local_failure", "Unexpected local bridge failure; no automatic replay")
        finally:
            self.server.capacity.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key-file", type=Path, required=True, help="Existing one-line key file; contents are never printed")
    parser.add_argument("--port", type=int, default=32789)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--protocol", choices=("v1", "v2"), default="v1", help="v2 explicitly enables observed reasoning/XML parsing")
    parser.add_argument("--relay-key-file", type=Path, help="Separate one-line local authentication key; school key stays local")
    args = parser.parse_args()
    key = args.api_key_file.read_text(encoding="utf-8-sig").strip()
    relay_key = args.relay_key_file.read_text(encoding="utf-8-sig").strip() if args.relay_key_file else None
    with SchoolBridge(key, args.port, args.timeout, protocol=args.protocol, relay_key=relay_key) as server:
        print(json.dumps({"local_base_url": f"http://127.0.0.1:{server.server_port}/v1", "policy": server.policy,
                          "model": MODEL, "streaming": False, "tool_execution": False, "upstream_retries": 0}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
