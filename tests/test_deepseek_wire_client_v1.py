import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from adapters.deepseek_wire_client_v1 import install_native_transport
class NativeWire(unittest.TestCase):
    def fixture(self,root):
        native={'role':'assistant','content':None,'reasoning_content':'real fixture reasoning','tool_calls':[{'id':'c1','type':'function','function':{'name':'fixture','arguments':'{}'}}]}
        wire=json.dumps({'choices':[{'message':native}]}).encode()
        parsed=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda:dict(native)))])
        raw=Mock(return_value=SimpleNamespace(content=wire,parse=lambda:parsed))
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(),with_raw_response=SimpleNamespace(create=raw))))
        install_native_transport(client,root);return client,raw,wire,native
    def test_exact_wire_checksum_and_native_thinking(self):
        with tempfile.TemporaryDirectory() as t:
            client,raw,wire,native=self.fixture(Path(t));client.chat.completions.create(model='deepseek-flash',messages=[])
            record=json.loads((Path(t)/'deepseek_native_wire.jsonl').read_text())
            self.assertEqual(base64.b64decode(record['wire_base64']),wire);self.assertEqual(record['wire_sha256'],hashlib.sha256(wire).hexdigest())
            self.assertEqual(raw.call_args.kwargs['extra_body']['thinking'],{'type':'enabled'});self.assertEqual(raw.call_args.kwargs['reasoning_effort'],'high');self.assertFalse(record['automatic_replay'])
    def test_tool_history_reasoning_not_invented(self):
        with tempfile.TemporaryDirectory() as t:
            client,raw,wire,native=self.fixture(Path(t));client.chat.completions.create(model='deepseek-flash',messages=[])
            history=[{'role':'assistant','tool_calls':native['tool_calls']}];client.chat.completions.create(model='deepseek-flash',messages=history)
            self.assertEqual(raw.call_args.kwargs['messages'][0]['reasoning_content'],native['reasoning_content']);self.assertNotIn('reasoning_content',history[0])
    def test_dispatch_failure_not_replayed(self):
        with tempfile.TemporaryDirectory() as t:
            client,raw,_,_=self.fixture(Path(t));raw.side_effect=TimeoutError('synthetic')
            with self.assertRaises(TimeoutError):client.chat.completions.create(model='deepseek-flash',messages=[])
            self.assertEqual(raw.call_count,1)
    def test_wrong_model_refused_before_network(self):
        with tempfile.TemporaryDirectory() as t:
            client,raw,_,_=self.fixture(Path(t))
            with self.assertRaises(RuntimeError):client.chat.completions.create(model='gpt-5.5',messages=[])
            raw.assert_not_called()
if __name__=='__main__':unittest.main()
