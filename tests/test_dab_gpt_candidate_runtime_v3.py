import copy,math,unittest,tempfile,struct
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from experiments import dab_gpt_candidate_runtime_v3 as r
class StateTests(unittest.TestCase):
    def tearDown(self):r.CONTRACT=[]
    def test_explicit_stateless(self):self.assertEqual(r.validate_contract({'persistent_fields':[],'stateless':True}),[])
    def test_missing(self):
        with self.assertRaises(r.base.UnsafeResume):r.validate_contract({})
    def test_ambiguous(self):
        with self.assertRaises(r.base.UnsafeResume):r.validate_contract({'persistent_fields':[],'stateless':False})
    def test_reserved(self):
        with self.assertRaises(r.base.UnsafeResume):r.validate_contract({'persistent_fields':[{'name':'client','type':'json'}],'stateless':False})
    def test_field_missing(self):
        r.CONTRACT=[{'name':'ledger','type':'json'}]
        with self.assertRaises(r.base.UnsafeResume):r.pack(SimpleNamespace())
    def test_set_roundtrip(self):
        r.CONTRACT=[{'name':'signatures','type':'string_set'}];a=SimpleNamespace(signatures={'z','a'});wire=r.pack(a);self.assertEqual(wire,{'signatures':['a','z']});b=SimpleNamespace();r.restore_fields(b,wire);self.assertEqual(a.signatures,b.signatures)
    def test_noncanonical_set_rejected(self):
        r.CONTRACT=[{'name':'signatures','type':'string_set'}]
        with self.assertRaises(r.base.UnsafeResume):r.restore_fields(SimpleNamespace(),{'signatures':['z','a']})
    def test_nonfinite_not_null(self):
        r.CONTRACT=[{'name':'ledger','type':'json'}];a=SimpleNamespace(ledger={'n':float('nan'),'i':float('inf'),'collision':{'__type__':'not_a_wire_tag'}});wire=r.pack(a);b=SimpleNamespace();r.restore_fields(b,wire);self.assertTrue(math.isnan(b.ledger['n']));self.assertTrue(math.isinf(b.ledger['i']));self.assertEqual(a.ledger['collision'],b.ledger['collision'])
    def test_unknown_state_key_rejected(self):
        r.CONTRACT=[]
        with self.assertRaises(r.base.UnsafeResume):r.restore_fields(SimpleNamespace(),{'surprise':1})
    def test_no_silent_tuple_conversion(self):
        r.CONTRACT=[{'name':'ledger','type':'json'}]
        with self.assertRaises(r.base.UnsafeResume):r.pack(SimpleNamespace(ledger=(1,2)))
    def test_no_silent_dict_key_conversion(self):
        r.CONTRACT=[{'name':'ledger','type':'json'}]
        with self.assertRaises(r.base.UnsafeResume):r.pack(SimpleNamespace(ledger={1:'x'}))
    def test_lossless_durable_journal_roundtrip(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        r.CONTRACT=[{'name':'memo','type':'json'},{'name':'signatures','type':'string_set'}]
        with tempfile.TemporaryDirectory() as folder:
            a=FakeAgent(Path(folder));a.memo={'nan':float('nan'),'inf':float('inf'),'collision':{'__dab_checkpoint_codec_v1__':'ordinary_user_dict'}};a.signatures={'b','a'}
            with patch.object(r.base,'STATE_FIELDS',(*r.base.STATE_FIELDS,'_gen8_checkpoint_state','_gen9_candidate_state')):
                j=r.CandidateJournal(a,{'fixture':'new_candidate'});j.save();payload=j.read(j.path,j.binding,a.exec_tool_work_dir)
                b=FakeAgent(Path(folder));b.memo={};b.signatures=set();r.CandidateJournal(b,j.binding).restore(payload)
                self.assertEqual(struct.pack('!d',a.memo['nan']),struct.pack('!d',b.memo['nan']));self.assertEqual(a.memo['inf'],b.memo['inf']);self.assertEqual(a.memo['collision'],b.memo['collision']);self.assertEqual(a.signatures,b.signatures)
    def test_missing_candidate_durable_state_rejected(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(r.base.UnsafeResume):r.CandidateJournal(FakeAgent(Path(folder)),{}).restore({'state':{}})
    def test_committed_native_tool_is_not_replayed(self):
        from tests.test_dab_runtime_repair_v1 import FakeAgent
        from adapters.crs_responses_client_v1 import NativeResponse
        r.CONTRACT=[{'name':'memo','type':'json'}]
        raw={'model':'gpt-5.5','status':'completed','output':[{'type':'reasoning','id':'rs','summary':[],'encrypted_content':'opaque'},{'type':'function_call','call_id':'first','name':'fixture','arguments':'{}'},{'type':'function_call','call_id':'second','name':'fixture','arguments':'{}'}]}
        with tempfile.TemporaryDirectory() as folder:
            a=FakeAgent(Path(folder));a.memo={'persistent':'fixture'}
            with patch.object(r.base,'STATE_FIELDS',(*r.base.STATE_FIELDS,'_gen8_checkpoint_state','_gen9_candidate_state')):
                j=r.CandidateJournal(a,{'fixture':'native'});j.accept(NativeResponse(raw,[{'name':'fixture'}]).choices[0].message);a._handle_tool_call(SimpleNamespace(id='first'));j.cursor=1;j.save();payload=j.read(j.path,j.binding,a.exec_tool_work_dir)
                b=FakeAgent(Path(folder));b.memo={};resumed=r.CandidateJournal(b,j.binding);resumed.restore(payload);resumed.dispatch()
                self.assertEqual(b.executions,['second']);self.assertEqual(b.memo,a.memo);self.assertIsNone(resumed.pending);self.assertEqual(resumed.cursor,0)
if __name__=='__main__':unittest.main()
