import json
import unittest
from adapters.crs_responses_client_v2 import parse_completed_wire

class NativeSSETests(unittest.TestCase):
    def wire(self, kind='response.completed'):
        return ('event: '+kind+'\ndata: '+json.dumps({'type':kind,'response':{'status':'completed','output':[{'type':'reasoning','encrypted_content':'opaque'}]}})+'\n\n').encode()

    def test_exact_completed_items_preserved(self):
        self.assertEqual(parse_completed_wire(self.wire())['output'], [{'type':'reasoning','encrypted_content':'opaque'}])

    def test_delta_is_not_inferred_as_completion(self):
        with self.assertRaises(RuntimeError):parse_completed_wire(self.wire('response.output_text.delta'))

    def test_duplicate_final_rejected(self):
        with self.assertRaises(RuntimeError):parse_completed_wire(self.wire()+self.wire())

    def test_terminal_failure_rejected(self):
        for kind in ('error','response.failed','response.incomplete'):
            with self.subTest(kind=kind),self.assertRaises(RuntimeError):parse_completed_wire(self.wire(kind))

    def test_bad_wire_rejected(self):
        for wire in (b'{}',b'data: {bad}\n\n',b'\xff'):
            with self.subTest(wire=wire),self.assertRaises((ValueError,RuntimeError)):parse_completed_wire(wire)

    def test_crlf_done_supported(self):
        self.assertEqual(parse_completed_wire(self.wire().replace(b'\n',b'\r\n')+b'data: [DONE]\r\n\r\n')['status'],'completed')
