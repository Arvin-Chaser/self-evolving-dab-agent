"""Offline protocol tests. No model, network, DAB or database calls."""
import copy
import json
import unittest

from adapters.school_tool_compat_v1 import (
    CompatibilityError, MODEL, MAX_BYTES, canonical, normalize_response,
    strict_loads, validate_request,
)


TOOL = {"type": "function", "function": {
    "name": "add_numbers", "parameters": {"type": "object", "properties": {
        "a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"], "additionalProperties": False}}}


def request(**options):
    value = {"model": MODEL, "messages": [{"role": "user", "content": "Add 3 and 4."}], "tools": [copy.deepcopy(TOOL)]}
    value.update(options)
    return value


def response(content='[{"name":"add_numbers","parameters":{"a":3,"b":4}}]', finish="stop", calls=None):
    return {"id": "synthetic", "model": MODEL, "choices": [{"index": 0, "finish_reason": finish,
        "message": {"role": "assistant", "content": content, "tool_calls": calls}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 10, "total_tokens": 22}}


def call(cid="call_original"):
    return {"id": cid, "type": "function", "function": {"name": "add_numbers", "arguments": '{"a":3,"b":4}'}}


class SchoolProtocolTests(unittest.TestCase):
    def test_observed_native_projection_and_preservation(self):
        req, raw = request(), response()
        originals = copy.deepcopy((req, raw))
        out = normalize_response(req, raw)
        c = out["choices"][0]
        self.assertEqual(c["finish_reason"], "tool_calls")
        self.assertIsNone(c["message"]["content"])
        self.assertEqual(strict_loads(c["message"]["tool_calls"][0]["function"]["arguments"]), {"a": 3, "b": 4})
        self.assertEqual(out["school_tool_compat"]["original_message"], raw["choices"][0]["message"])
        self.assertEqual(out["usage"], raw["usage"])
        self.assertEqual((req, raw), originals)

    def test_deterministic_ids_and_distinct_calls(self):
        raw = response('[{"name":"add_numbers","parameters":{"a":3,"b":4}},{"name":"add_numbers","parameters":{"a":3,"b":4}}]')
        a = normalize_response(request(), raw)
        b = normalize_response(request(), raw)
        self.assertEqual(a, b)
        ids = [c["id"] for c in a["choices"][0]["message"]["tool_calls"]]
        self.assertEqual(len(set(ids)), 2)
        with self.assertRaises(CompatibilityError):
            normalize_response(request(parallel_tool_calls=False), raw)

    def test_standard_calls_preserved(self):
        raw = response(None, "tool_calls", [call()])
        out = normalize_response(request(), raw)
        self.assertEqual(out["choices"], raw["choices"])
        self.assertFalse(out["school_tool_compat"]["converted"])

    def test_plain_answers_and_json_answers_unchanged(self):
        for text in ("The result is 7.", '{"answer":7}', "[]", "An example has a name and parameters."):
            with self.subTest(text=text):
                raw = response(text)
                self.assertEqual(normalize_response(request(), raw)["choices"], raw["choices"])

    def test_no_tools_is_not_a_dispatch_authority(self):
        with self.assertRaises(CompatibilityError):
            normalize_response(request(tools=[]), response())

    def test_unknown_tool_rejected(self):
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), response('[{"name":"execute_shell","parameters":{}}]'))

    def test_invalid_arguments_rejected(self):
        for args in ({"a": True, "b": 4}, {"a": "3", "b": 4}, {"a": 3}, {"a": 3, "b": 4, "extra": 0}, [], None):
            with self.subTest(args=args), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(json.dumps([{"name": "add_numbers", "parameters": args}])))

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for text in ('[{"name":"add_numbers","parameters":{"a":3,"a":4,"b":4}}]',
                     '[{"name":"add_numbers","parameters":{"a":NaN,"b":4}}]',
                     '[{"name":"add_numbers","parameters":{"a":1e999,"b":4}}]'):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(text))

    def test_only_whole_exact_native_envelope(self):
        base = response()["choices"][0]["message"]["content"]
        for text in ("```json\n" + base + "\n```", "I will call " + base, base[:-1],
                     '{"name":"add_numbers","parameters":{"a":3,"b":4}}',
                     '[{"name":"add_numbers","arguments":{"a":3,"b":4}}]',
                     '[{"name":"add_numbers","parameters":{"a":3,"b":4},"extra":1}]',
                     '[{"name":"add_numbers"}]'):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(text))

    def test_mixed_native_and_standard_rejected(self):
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), response(calls=[call()]))

    def test_incomplete_completions_rejected(self):
        for finish in ("length", "content_filter", None, "error"):
            with self.subTest(finish=finish), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(finish=finish))

    def test_tool_choice_enforced(self):
        self.assertTrue(normalize_response(request(tool_choice="required"), response()))
        self.assertTrue(normalize_response(request(tool_choice={"type": "function", "function": {"name": "add_numbers"}}), response()))
        with self.assertRaises(CompatibilityError):
            normalize_response(request(tool_choice="none"), response())
        with self.assertRaises(CompatibilityError):
            normalize_response(request(tool_choice="required"), response("I did not call anything."))
        for choice in ("bad", {"type": "function", "function": {"name": []}}):
            with self.subTest(choice=choice), self.assertRaises(CompatibilityError):
                validate_request(request(tool_choice=choice))

    def test_named_choice_not_other_tool(self):
        other = copy.deepcopy(TOOL)
        other["function"]["name"] = "other"
        req = request(tools=[copy.deepcopy(TOOL), other], tool_choice={"type": "function", "function": {"name": "other"}})
        with self.assertRaises(CompatibilityError):
            normalize_response(req, response())

    def test_empty_final_rejected(self):
        for text in (None, "", "  "):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(text))

    def test_standard_envelope_errors(self):
        for calls in ([call(), call()], [{**call(), "type": "custom"}], [{**call(), "id": ""}],
                      [{**call(), "function": {"name": "add_numbers", "arguments": {"a": 3, "b": 4}}}]):
            with self.subTest(calls=calls), self.assertRaises(CompatibilityError):
                normalize_response(request(), response(None, "tool_calls", calls))
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), response(None, "stop", [call()]))

    def test_empty_wrong_tool_calls_type_rejected(self):
        for bad in ({}, "", False):
            with self.subTest(bad=bad), self.assertRaises(CompatibilityError):
                normalize_response(request(), response("Answer", calls=bad))
            with self.subTest(history=bad), self.assertRaises(CompatibilityError):
                validate_request(request(messages=[{"role": "assistant", "content": "Answer", "tool_calls": bad}]))

    def test_model_binding_and_choice_count(self):
        with self.assertRaises(CompatibilityError):
            validate_request(request(model="another_model"))
        raw = response()
        raw["model"] = "another_model"
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), raw)
        raw = response()
        raw["choices"] *= 2
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), raw)

    def test_unsupported_modes(self):
        for options in ({"stream": True}, {"n": 2}, {"n": True}, {"parallel_tool_calls": "false"}, {"functions": []}, {"function_call": "auto"},
                        {"response_format": {"type": "json_object"}}):
            with self.subTest(options=options), self.assertRaises(CompatibilityError):
                validate_request(request(**options))

    def test_valid_result_history_is_not_rewritten(self):
        req = request()
        req["messages"] += [{"role": "assistant", "content": None, "tool_calls": [call()]},
                            {"role": "tool", "tool_call_id": "call_original", "content": '{"sum":7}'}]
        original = copy.deepcopy(req)
        self.assertEqual(validate_request(req), original)
        self.assertEqual(normalize_response(req, response("The sum is 7."))["choices"][0]["message"]["content"], "The sum is 7.")

    def test_unpaired_duplicate_missing_results(self):
        assistant = {"role": "assistant", "content": None, "tool_calls": [call()]}
        tool = {"role": "tool", "tool_call_id": "call_original", "content": "7"}
        for suffix in ([tool], [assistant], [assistant, tool, tool],
                       [assistant, {**tool, "tool_call_id": "wrong"}],
                       [assistant, {"role": "user", "content": "Continue"}],
                       [assistant, tool, assistant, tool]):
            with self.subTest(suffix=suffix), self.assertRaises(CompatibilityError):
                validate_request(request(messages=[{"role": "user", "content": "Add"}] + suffix))

    def test_reused_executed_id_rejected(self):
        req = request(messages=[{"role": "assistant", "content": None, "tool_calls": [call()]},
                                {"role": "tool", "tool_call_id": "call_original", "content": "7"}])
        with self.assertRaises(CompatibilityError):
            normalize_response(req, response(None, "tool_calls", [call()]))

    def test_external_schema_resolution_disabled(self):
        for schema in ({"$ref": "https://example.invalid/schema"}, {"$dynamicRef": "file:///secret"}, {"$id": "http://example.invalid/root"}, {"type": "not-a-type"}):
            spec = copy.deepcopy(TOOL)
            spec["function"]["parameters"] = schema
            with self.subTest(schema=schema), self.assertRaises(CompatibilityError):
                validate_request(request(tools=[spec]))

    def test_local_ref_schema_works(self):
        spec = copy.deepcopy(TOOL)
        spec["function"]["parameters"]["$defs"] = {"integer": {"type": "integer"}}
        spec["function"]["parameters"]["properties"]["a"] = {"$ref": "#/$defs/integer"}
        self.assertTrue(normalize_response(request(tools=[spec]), response()))

    def test_duplicate_tools_rejected(self):
        with self.assertRaises(CompatibilityError):
            validate_request(request(tools=[copy.deepcopy(TOOL), copy.deepcopy(TOOL)]))

    def test_bounds(self):
        with self.assertRaises(CompatibilityError):
            strict_loads("[" * 70 + "0" + "]" * 70)
        with self.assertRaises(CompatibilityError):
            normalize_response(request(), response("x" * (MAX_BYTES + 1)))
        with self.assertRaises(CompatibilityError):
            canonical({"x": float("inf")})


if __name__ == "__main__":
    unittest.main()
