from __future__ import annotations

import http.client
import json
import threading
import time
import unittest



class SlowQwenClient:
    def close(self) -> None:
        pass

    def complete(self, model, state, chat_tools):
        time.sleep(1.0)
        return {
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

from tools.codex_qwen_proxy import (
    ConversationState,
    ConversationStore,
    append_responses_input,
    assistant_message_and_outputs,
    responses_tools_to_chat,
    ProxyApplication,
    ProxyServer,
    sse_events,
)


class ProxyProtocolTests(unittest.TestCase):
    def test_function_output_becomes_chat_tool_message(self) -> None:
        state = ConversationState(messages=[], response_tools=[], tool_kinds={})
        state.calls["call_1"] = {
            "call_id": "call_1",
            "name": "shell",
            "arguments": '{"command":"pwd"}',
        }
        append_responses_input(
            state,
            [{"type": "function_call_output", "call_id": "call_1", "output": "/tmp"}],
        )
        self.assertEqual(state.messages[-1]["role"], "tool")
        self.assertEqual(state.messages[-1]["tool_call_id"], "call_1")

    def test_custom_tool_is_represented_as_qwen_function(self) -> None:
        tools, kinds = responses_tools_to_chat(
            [{"type": "custom", "name": "shell", "description": "Run a shell command."}]
        )
        self.assertEqual(tools[0]["function"]["name"], "shell")
        self.assertEqual(kinds["shell"], "custom")

    def test_qwen_function_call_becomes_responses_function_call(self) -> None:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "probe", "arguments": '{"key":"x"}'},
                }
            ],
        }
        _, outputs, calls = assistant_message_and_outputs(message, {"probe": "function"})
        self.assertEqual(outputs[0]["type"], "function_call")
        self.assertEqual(calls["call_1"]["name"], "probe")


    def test_streaming_sends_initial_event_before_slow_upstream_finishes(self) -> None:
        app = ProxyApplication(
            qwen=SlowQwenClient(),
            store=ConversationStore(),
            default_model="qwen-plus",
            local_token="test-token",
        )
        server = ProxyServer(("127.0.0.1", 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            body = json.dumps({"model": "qwen-plus", "input": "hello", "stream": True})
            start = time.monotonic()
            conn.request(
                "POST",
                "/v1/responses",
                body=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer test-token"},
            )
            response = conn.getresponse()
            first_line = response.fp.readline().decode("utf-8", errors="replace")
            elapsed = time.monotonic() - start
            self.assertEqual(response.status, 200)
            self.assertLess(elapsed, 0.8)
            self.assertEqual(first_line.strip(), "event: response.created")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_sse_always_ends_with_response_completed(self) -> None:
        response = {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "instructions": None,
            "model": "qwen-plus",
            "output": [
                {
                    "id": "msg_1",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "OK", "annotations": []}],
                }
            ],
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "tools": [],
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 2,
            },
            "metadata": {},
        }
        events = sse_events(response)
        self.assertEqual(events[-1]["type"], "response.completed")
        json.dumps(events)


if __name__ == "__main__":
    unittest.main()
