"""Model-free regression tests for the actual installed journal binding."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from experiments import dab_deepseek_candidate_runtime_v2 as runtime
from tests.test_dab_runtime_repair_v1 import FakeAgent

def response(ids):
    value={'role':'assistant','content':None,'reasoning_content':'native fixture reasoning',
           'tool_calls':[{'id':ident,'type':'function','function':{'name':'fixture','arguments':'{}'}} for ident in ids]}
    return SimpleNamespace(model_dump=lambda:copy.deepcopy(value))

class InstalledRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.stack=__import__('contextlib').ExitStack()
        self.stack.enter_context(patch.object(runtime,'CONTRACT',[{'name':'memo','type':'json'}]))
        self.stack.enter_context(patch.object(runtime.base,'Journal',runtime.CandidateJournal))
        self.stack.enter_context(patch.object(runtime.base,'STATE_FIELDS',(*runtime.base.STATE_FIELDS,'_gen8_checkpoint_state','_gen9_candidate_state')))
    def tearDown(self):
        self.stack.close();self.folder.cleanup()
    def journal(self):
        agent=FakeAgent(self.root);agent.memo={'persist':'unchanged'}
        return runtime.CandidateJournal(agent,{'fixture':'installed-v2'})
    def test_installed_single_tool_dispatch_once(self):
        journal=self.journal();journal.accept(response(['first']));journal.dispatch()
        self.assertEqual(journal.agent.executions,['first'])
        self.assertIsNone(journal.pending);self.assertEqual(journal.cursor,0)
    def test_installed_multiple_tools_native_history(self):
        journal=self.journal();journal.accept(response(['first','second']));journal.dispatch()
        self.assertEqual(journal.agent.executions,['first','second'])
        assistant=[m for m in journal.agent.messages if m['role']=='assistant'][0]
        self.assertEqual(assistant['reasoning_content'],'native fixture reasoning')
        self.assertEqual([m['tool_call_id'] for m in journal.agent.messages if m['role']=='tool'],['first','second'])
    def test_installed_restored_cursor_does_not_replay(self):
        journal=self.journal();journal.accept(response(['first','second']))
        journal.agent._handle_tool_call(SimpleNamespace(id='first'));journal.cursor=1;journal.save()
        payload=journal.read(journal.path,journal.binding,journal.agent.exec_tool_work_dir)
        other=self.journal();other.restore(payload);other.dispatch()
        self.assertEqual(other.agent.executions,['second'])
        self.assertEqual(other.agent.memo,{'persist':'unchanged'})
    def test_installed_inflight_rejected_before_replay(self):
        journal=self.journal();journal.accept(response(['first']))
        journal.inflight={'tool_call_id':'first','signature':'synthetic'};journal.save()
        with self.assertRaises(runtime.base.UnsafeResume):
            journal.read(journal.path,journal.binding,journal.agent.exec_tool_work_dir)
        self.assertEqual(journal.agent.executions,[])
    def test_installed_content_path_preserves_native_reasoning(self):
        journal=self.journal();journal.accept(SimpleNamespace(model_dump=lambda:{'role':'assistant','content':'fixture final','tool_calls':None,'reasoning_content':'original fixture'}));journal.dispatch()
        self.assertEqual(journal.agent.final_result,'fixture final')
        self.assertEqual(journal.agent.messages[-1]['reasoning_content'],'original fixture')
        self.assertIsNone(journal.pending)
    def test_installed_empty_tools_clear_without_execution(self):
        journal=self.journal();journal.accept(response([]));journal.dispatch()
        self.assertEqual(journal.agent.executions,[]);self.assertIsNone(journal.pending)
    def test_old_dynamic_binding_failure_is_reproduced(self):
        # Reproduce the old lookup without importing an old deployment overlay.
        class BrokenJournal:
            def dispatch(self):return runtime.base.Journal.dispatch(self)
        broken=BrokenJournal()
        with patch.object(runtime.base,'Journal',BrokenJournal):
            with self.assertRaises(RecursionError):broken.dispatch()
    def test_real_install_rebind_then_dispatch(self):
        query=self.root/'query1';query.mkdir();(query/'query.json').write_text('{}')
        cfg=self.root/'db_config.yaml';cfg.write_text('db_clients: {}')
        args=SimpleNamespace(deployment_name=runtime.MODEL,openai_compatible_base_url=runtime.ENDPOINT,
            client_max_retries=0,llm_retries=1,dab_upstream_root=self.root,query_dir=query,db_config=cfg,
            repaired_db_description='fixture',exec_python_timeout=1,llm_timeout=1,run_id='installed_fixture')
        class Parent(FakeAgent):
            def __init__(self,**kwargs):
                root=query/'logs/data_agent'/args.run_id;root.mkdir(parents=True,exist_ok=True)
                super().__init__(root);self.memo={'persist':'unchanged'};self.client=SimpleNamespace()
                self.recovery_restorations_this_turn=0
                self.recovery_budget_exhausted_count=0
                self.last_recorded_turn_key='count:0'
        module=SimpleNamespace(DataAgent=Parent)
        binding={'runtime_state_contract':{'persistent_fields':[{'name':'memo','type':'json'}],'stateless':False},
                 'admitted_source_sha256':'fixture','admitted_patch_sha256':'fixture','sealed_intent_sha256':'fixture'}
        read=Path.read_text
        def scoped_read(path,*pos,**kwargs):
            return json.dumps(binding) if path.name=='candidate_runtime_binding.json' else read(path,*pos,**kwargs)
        with __import__('contextlib').ExitStack() as stack:
            for name in ('POLICY','ADMITTED_SOURCE_SHA256','ADMITTED_PATCH_SHA256','SEALED_INTENT_SHA256','STATE_FIELDS','Journal'):
                if hasattr(runtime.base,name):stack.enter_context(patch.object(runtime.base,name,getattr(runtime.base,name)))
                else:stack.enter_context(patch.object(runtime.base,name,None,create=True))
            stack.enter_context(patch.dict(os.environ,{k:'' for k in ('DAB_REPAIR_RESUME','DAB_DEEPSEEK_SINGLE_TRIAL','DAB_SCHOOL_REMAINING8_TRIAL')}))
            stack.enter_context(patch.object(Path,'read_text',scoped_read))
            stack.enter_context(patch.object(runtime,'prepare_isolation'))
            stack.enter_context(patch.object(runtime,'install_native_transport'))
            runtime.install(module,args);agent=module.DataAgent(root_name=args.run_id)
            self.assertIs(runtime.base.Journal,runtime.CandidateJournal)
            agent.journal.accept(response(['installed']));agent.journal.dispatch()
            self.assertEqual(agent.executions,['installed'])
            if hasattr(agent,'_recovery_lease'):agent._recovery_lease.close()

if __name__=='__main__':unittest.main()
