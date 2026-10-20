import copy
import unittest
from adapters.crs_responses_client_v1 import NativeResponse, input_items, request_options, NATIVE_FIELD

TOOLS = [{'type': 'function', 'name': 'fixture', 'parameters': {'type': 'object'}, 'strict': False}]


class ResponsesContractTests(unittest.TestCase):
    def response(self):
        return {'model': 'gpt-5.5', 'status': 'completed', 'error': None, 'incomplete_details': None,
                'output': [{'type': 'reasoning', 'id': 'rs', 'encrypted_content': 'opaque', 'summary': []},
                           {'type': 'function_call', 'call_id': 'call_native', 'id': 'fc_item',
                            'name': 'fixture', 'arguments': '{"x":1}'}]}

    def test_native_call_id_not_output_item_id(self):
        msg = NativeResponse(self.response(), TOOLS).choices[0].message
        self.assertEqual(msg.tool_calls[0].id, 'call_native')
        self.assertEqual(msg.model_dump()[NATIVE_FIELD], self.response()['output'])

    def test_opaque_reasoning_and_outputs_preserved_exactly(self):
        native = self.response()
        msg = NativeResponse(native, TOOLS).choices[0].message.model_dump()
        history = input_items([{'role': 'user', 'content': 'synthetic'}, msg,
                              {'role': 'tool', 'tool_call_id': 'call_native', 'content': 'OK'}])
        self.assertEqual(history[1:3], native['output'])
        self.assertEqual(history[-1]['call_id'], 'call_native')

    def test_mutated_tool_arguments_rejected(self):
        msg = NativeResponse(self.response(), TOOLS).choices[0].message.model_dump()
        msg['tool_calls'][0]['function']['arguments'] = '{}'
        with self.assertRaises(RuntimeError):
            input_items([msg])

    def test_unbound_tool_output_rejected(self):
        with self.assertRaises(RuntimeError):
            input_items([{'role': 'tool', 'tool_call_id': 'unknown', 'content': 'OK'}])

    def test_missing_output_rejected(self):
        msg = NativeResponse(self.response(), TOOLS).choices[0].message.model_dump()
        with self.assertRaises(RuntimeError):
            input_items([msg])

    def test_legacy_tool_history_without_native_items_rejected(self):
        msg = NativeResponse(self.response(), TOOLS).choices[0].message.model_dump()
        msg.pop(NATIVE_FIELD)
        with self.assertRaises(RuntimeError):
            input_items([msg])

    def test_wrong_model_and_terminal_failure_rejected(self):
        for key, value in [('model', 'other'), ('status', 'failed'), ('incomplete_details', {'reason': 'max_output_tokens'})]:
            with self.subTest(key=key):
                raw = self.response()
                raw[key] = value
                with self.assertRaises(RuntimeError):
                    NativeResponse(raw, TOOLS)

    def test_duplicate_call_identity_rejected(self):
        raw = self.response()
        raw['output'].append(copy.deepcopy(raw['output'][-1]))
        with self.assertRaises(RuntimeError):
            NativeResponse(raw, TOOLS)

    def test_unknown_tool_rejected(self):
        raw = self.response()
        raw['output'][-1]['name'] = 'unregistered'
        with self.assertRaises(RuntimeError):
            NativeResponse(raw, TOOLS)

    def test_text_never_inferred_as_tool_call(self):
        raw = self.response()
        raw['output'] = [{'type': 'message', 'role': 'assistant', 'content': [
            {'type': 'output_text', 'text': '<tool_call>fixture</tool_call>'}]}]
        self.assertIsNone(NativeResponse(raw, TOOLS).choices[0].message.tool_calls)

    def test_original_optional_schema_not_normalized(self):
        request = {'model': 'gpt-5.5', 'messages': [{'role': 'user', 'content': 'synthetic'}],
                   'tools': [{'type': 'function', 'function': {'name': 'fixture',
                              'parameters': {'type': 'object', 'properties': {'optional': {'type': 'string'}}}}}]}
        before = copy.deepcopy(request)
        result = request_options(request)
        self.assertEqual(request, before)
        self.assertFalse(result['tools'][0]['strict'])
        self.assertEqual(result['tools'][0]['parameters'], request['tools'][0]['function']['parameters'])
        self.assertEqual(result['reasoning'], {'effort': 'medium'})
        self.assertEqual(result['include'], ['reasoning.encrypted_content'])

    def test_unreviewed_options_and_streaming_rejected(self):
        for option in ({'stream': True}, {'temperature': 1}):
            with self.assertRaises(RuntimeError):
                request_options({'model': 'gpt-5.5', 'messages': [], **option})
