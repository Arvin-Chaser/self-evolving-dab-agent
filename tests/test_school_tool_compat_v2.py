"""Offline strict tagged-protocol regression, including live-observed shapes."""
import copy
import unittest

from adapters.school_tool_compat_v1 import CompatibilityError, normalize_response as v1, strict_loads
from adapters.school_tool_compat_v2 import normalize_response as v2
from test_school_tool_compat_v1 import request, response


def token_request(kind="string"):
    req = request()
    req["tools"][0]["function"] = {"name": "get_test_token", "parameters": {
        "type": "object", "properties": {"label": {"type": kind}}, "required": ["label"], "additionalProperties": False}}
    return req


XML = '<tool_call>\n<function=get_test_token>\n<parameter=label>\nsynthetic_auto\n</parameter>\n</function>\n</tool_call>'


class TaggedTests(unittest.TestCase):
    def test_live_observed_auto_shape(self):
        raw = response("Need call get_test_token.\n</think>\n\n" + XML)
        original = copy.deepcopy(raw)
        out = v2(token_request(), raw)
        msg = out["choices"][0]["message"]
        self.assertEqual(out["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(msg["reasoning_content"], "Need call get_test_token.\n")
        self.assertEqual(strict_loads(msg["tool_calls"][0]["function"]["arguments"]), {"label": "synthetic_auto"})
        self.assertEqual(raw, original)
        self.assertEqual(out["school_tool_compat"]["original_message"], raw["choices"][0]["message"])

    def test_live_observed_final_shape(self):
        raw = response("The user wants just the token.\n</think>\n\ntest_synthetic")
        out = v2(token_request(), raw)
        self.assertEqual(out["choices"][0]["message"]["content"], "test_synthetic")
        self.assertEqual(out["school_tool_compat"]["original_message"], raw["choices"][0]["message"])
        self.assertEqual(out["usage"], raw["usage"])

    def test_open_and_close_think(self):
        out = v2(token_request(), response("<think>reason</think>\nfinal"))
        self.assertEqual(out["choices"][0]["message"]["reasoning_content"], "reason")
        self.assertEqual(out["choices"][0]["message"]["content"], "final")

    def test_plain_text_and_json_still_preserved(self):
        for text in ("Ordinary answer 007", '{"answer":7}'):
            raw = response(text)
            self.assertEqual(v2(token_request(), raw)["choices"], raw["choices"])
        self.assertEqual(v2(request(), response())["choices"], v1(request(), response())["choices"])

    def test_v1_does_not_silently_finish_on_tagged_calls(self):
        for text in (XML, "reason</think>answer"):
            with self.assertRaises(CompatibilityError):
                v1(token_request(), response(text))

    def test_ambiguous_or_incomplete_reasoning_rejected(self):
        for text in ("<think>unfinished", "a</think>b</think>c", "prefix<think>a</think>b", "<think><think>a</think>b", "<tool_call>x</think>final"):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                v2(token_request(), response(text))
        raw = response("reason</think>answer")
        raw["choices"][0]["message"]["reasoning_content"] = "another"
        with self.assertRaises(CompatibilityError):
            v2(token_request(), raw)

    def test_incomplete_xml_rejected(self):
        for text in (XML[:-12], XML.replace("</parameter>", ""), "I call " + XML, XML + "suffix", "```\n" + XML + "\n```", XML.replace("</function>", "</bad>")):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                v2(token_request(), response(text))

    def test_duplicate_unknown_parameters_and_tools_rejected(self):
        for text in (XML.replace("</function>", "<parameter=label>x</parameter></function>"),
                     XML.replace("parameter=label", "parameter=unknown"), XML.replace("get_test_token", "execute_shell"),
                     XML.replace("synthetic_auto", "<function=embedded>")):
            with self.subTest(text=text), self.assertRaises(CompatibilityError):
                v2(token_request(), response(text))

    def test_typed_json_arguments_no_guessing(self):
        for kind, value, expected in (("integer", "3", 3), ("boolean", "true", True), ("object", '{"a":3}', {"a": 3}), ("array", "[3]", [3])):
            with self.subTest(kind=kind):
                msg = v2(token_request(kind), response(XML.replace("synthetic_auto", value)))["choices"][0]["message"]
                self.assertEqual(strict_loads(msg["tool_calls"][0]["function"]["arguments"])["label"], expected)
        for kind, value in (("integer", "true"), ("integer", "three"), ("object", "{'a':3}"), ("number", "NaN")):
            with self.subTest(kind=kind, value=value), self.assertRaises(CompatibilityError):
                v2(token_request(kind), response(XML.replace("synthetic_auto", value)))

    def test_strings_keep_whitespace_and_leading_zero(self):
        for value in ("007", "  padded  ", "line1\n  line2"):
            msg = v2(token_request(), response(XML.replace("synthetic_auto", value)))["choices"][0]["message"]
            self.assertEqual(strict_loads(msg["tool_calls"][0]["function"]["arguments"])["label"], value)

    def test_truncated_reply_never_parsed(self):
        with self.assertRaises(CompatibilityError):
            v2(token_request(), response("reason</think>" + XML, "length"))

    def test_tool_choice_and_parallel_guard_preserved(self):
        req = token_request()
        req["tool_choice"] = "none"
        with self.assertRaises(CompatibilityError):
            v2(req, response(XML))
        req = token_request()
        req["parallel_tool_calls"] = False
        with self.assertRaises(CompatibilityError):
            v2(req, response(XML + "\n" + XML))
        req.pop("parallel_tool_calls")
        calls = v2(req, response(XML + "\n" + XML))["choices"][0]["message"]["tool_calls"]
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["id"], calls[1]["id"])


if __name__ == "__main__":
    unittest.main()
