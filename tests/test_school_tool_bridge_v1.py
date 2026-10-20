"""Local loopback/mocked upstream tests: no school/model/DB requests."""
import base64
import copy
import hashlib
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from adapters.school_tool_compat_v1 import CompatibilityError, normalize_response
from adapters.school_tool_transport_v1 import SchoolToolClient, TransportError, _NoRedirect
from experiments.serve_school_tool_compat_v1 import SchoolBridge
from test_school_tool_compat_v1 import request, response, call


class TransportTests(unittest.TestCase):
    def test_single_dispatch_preserves_exact_wire(self):
        wire = json.dumps(response()).encode()
        fake = io.BytesIO(wire)
        fake.status = 200
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = fake
            out = SchoolToolClient("synthetic-test-key").complete(request())
            self.assertEqual(factory.return_value.open.call_count, 1)
            meta = out["school_tool_compat"]
            self.assertEqual(base64.b64decode(meta["original_wire_base64"]), wire)
            self.assertEqual(meta["original_wire_sha256"], hashlib.sha256(wire).hexdigest())
            self.assertEqual(meta["attempts"], 1)
            self.assertFalse(meta["outbound_request_changed"])
            self.assertNotIn("synthetic-test-key", json.dumps(out))

    def test_timeout_never_retried(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = TimeoutError("redacted")
            with self.assertRaises(TransportError):
                SchoolToolClient("synthetic-test-key").complete(request())
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_rejected_truncation_evidence_preserved(self):
        wire = json.dumps(response(finish="length")).encode()
        fake = io.BytesIO(wire)
        fake.status = 200
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = fake
            with self.assertRaises(CompatibilityError) as caught:
                SchoolToolClient("synthetic-test-key").complete(request())
            self.assertEqual(base64.b64decode(caught.exception.provider_evidence["original_wire_base64"]), wire)
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_invalid_request_never_dispatched(self):
        with patch("urllib.request.build_opener") as factory:
            with self.assertRaises(CompatibilityError):
                SchoolToolClient("synthetic-test-key").complete(request(stream=True))
            factory.assert_not_called()

    def test_malformed_wire_evidence_preserved(self):
        wire = b'{"choices":broken}'
        fake = io.BytesIO(wire)
        fake.status = 200
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = fake
            with self.assertRaises(CompatibilityError) as caught:
                SchoolToolClient("synthetic-test-key").complete(request())
            self.assertEqual(base64.b64decode(caught.exception.provider_evidence["original_wire_base64"]), wire)

    def test_redirect_refused(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "http://other.invalid"))

    def test_upstream_http_error_body_not_exposed(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError("bound", 401, "sensitive provider message", {}, io.BytesIO(b"secret"))
            with self.assertRaises(TransportError) as caught:
                SchoolToolClient("synthetic-test-key").complete(request())
            self.assertEqual(caught.exception.status, 401)
            self.assertNotIn("secret", str(caught.exception))
            self.assertEqual(factory.return_value.open.call_count, 1)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.dispatched = []

        def complete(req):
            self.dispatched.append(copy.deepcopy(req))
            return normalize_response(req, response())

        self.server = SchoolBridge("synthetic-test-key", complete=complete)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, payload, key="synthetic-test-key", path="/v1/chat/completions"):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(req, timeout=3) as remote:
                return remote.status, json.loads(remote.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_loopback_projection(self):
        status, out = self.post(request())
        self.assertEqual(status, 200)
        self.assertEqual(out["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(self.dispatched, [request()])
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_auth_required(self):
        self.assertEqual(self.post(request(), key="wrong")[0], 401)
        self.assertEqual(self.dispatched, [])

    def test_separate_relay_credential_keeps_upstream_key_local(self):
        self.server._key = "independent-relay-key"
        self.assertEqual(self.post(request(), key="synthetic-test-key")[0], 401)
        self.assertEqual(self.dispatched, [])
        self.assertEqual(self.post(request(), key="independent-relay-key")[0], 200)
        self.assertEqual(len(self.dispatched), 1)

    def test_unsupported_endpoint_no_dispatch(self):
        self.assertEqual(self.post(request(), path="/v1/responses")[0], 404)
        self.assertEqual(self.dispatched, [])

    def test_invalid_protocol_no_dispatch(self):
        self.assertEqual(self.post(request(stream=True))[0], 422)
        self.assertEqual(self.dispatched, [])

    def test_provider_failure_is_nonretryable_status(self):
        def fail(req):
            self.dispatched.append(req)
            raise TransportError("upstream_connection_or_timeout")
        self.server.complete = fail
        self.assertEqual(self.post(request())[0], 424)
        self.assertEqual(len(self.dispatched), 1)

    def test_capacity_limit_no_dispatch(self):
        for _ in range(3):
            self.server.capacity.acquire()
        try:
            self.assertEqual(self.post(request())[0], 503)
            self.assertEqual(self.dispatched, [])
        finally:
            for _ in range(3):
                self.server.capacity.release()

    def test_two_round_tool_result_returned_unmodified(self):
        status, first = self.post(request())
        self.assertEqual(status, 200)
        assistant = first["choices"][0]["message"]
        cid = assistant["tool_calls"][0]["id"]
        req = request()
        req["messages"] += [assistant, {"role": "tool", "tool_call_id": cid, "content": "synthetic_token_only_here"}]
        def finish(payload):
            self.dispatched.append(copy.deepcopy(payload))
            self.assertEqual(payload, req)
            return normalize_response(payload, response("synthetic_token_only_here"))
        self.server.complete = finish
        status, final = self.post(req)
        self.assertEqual(status, 200)
        self.assertEqual(final["choices"][0]["message"]["content"], "synthetic_token_only_here")
        self.assertEqual(len(self.dispatched), 2)

    def test_long_history_all_calls_results_retained(self):
        req = request()
        for index in range(30):
            cid = f"history_{index}"
            req["messages"] += [{"role": "assistant", "content": None, "tool_calls": [call(cid)]},
                                {"role": "tool", "tool_call_id": cid, "content": f"result_{index}"}]
        status, _ = self.post(req)
        self.assertEqual(status, 200)
        self.assertEqual(self.dispatched, [req])
        self.assertEqual(len(self.dispatched[0]["messages"]), 61)

    def test_three_concurrent_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(3, timeout=3)
        def simultaneous(req):
            self.dispatched.append(copy.deepcopy(req))
            barrier.wait()
            return normalize_response(req, response())
        self.server.complete = simultaneous
        requests = [request(messages=[{"role": "user", "content": f"synthetic_{index}"}]) for index in range(3)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(self.post, requests))
        self.assertEqual([r[0] for r in rows], [200, 200, 200])
        self.assertEqual(len(self.dispatched), 3)
        ids = [r[1]["choices"][0]["message"]["tool_calls"][0]["id"] for r in rows]
        self.assertEqual(len(set(ids)), 3)


if __name__ == "__main__":
    unittest.main()
