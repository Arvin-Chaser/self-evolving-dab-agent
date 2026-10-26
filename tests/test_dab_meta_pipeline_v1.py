"""Complete workflow fault simulations: no paid model, SSH, Graph or campaign effects."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from experiments import dab_meta_pipeline_v1 as flow

class Fixtures:
    def __init__(self,failures=0,kind='candidate_validation',crash=None):
        self.calls=[];self.failures=failures;self.kind=kind;self.crash=crash
    def _call(self,name,value=None):
        self.calls.append(name)
        if name==self.crash:raise RuntimeError('simulated process/network/security failure')
        return value or {'name':name},[]
    def health(self):return self._call('health')
    def review_context(self):return self._call('review_context')
    def review(self,ctx):return self._call('review')
    def graph(self,review):return self._call('graph')
    def candidate_authority(self):return self._call('candidate_authority')
    def selector_context(self):return self._call('selector_context')
    def selector(self,ctx):return self._call('selector')
    def seal(self,response,ctx):return self._call('seal',{'sealed':'immutable'})
    def prepare_candidate(self,intent,index,seed,diagnostic):
        if index:
            assert seed['attempt']==index-1 and diagnostic and intent=={'sealed':'immutable'}
        return self._call('prepare'+str(index),{'attempt':index})
    def code(self,candidate):return self._call('code'+str(candidate['attempt']))
    def audit(self,candidate):return self._call('audit'+str(candidate['attempt']),{'passed':candidate['attempt']>=self.failures,'failure_kind':self.kind})
    def diagnostic(self,candidate,audit):return self._call('diagnostic'+str(candidate['attempt']))
    def admit(self,candidate,audit):return self._call('admit')
    def handoff(self,admitted):return self._call('handoff',{'status':'meta_complete_candidate_admitted','data_evaluation_started':False})

class Pipeline(unittest.TestCase):
    def setUp(self):
        (flow.ROOT/'tmp').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='mt_',dir=flow.ROOT/'tmp');self.root=Path(self.tmp.name)
        self.store=flow.StageStore(self.root/'steps')
    def tearDown(self):self.tmp.cleanup()
    def test_full_review_graph_selector_coding_admission(self):
        f=Fixtures();result=flow.drive(self.store,f,'review_then_candidate')
        self.assertEqual(f.calls,['health','review_context','review','graph','candidate_authority','selector_context','selector','seal','prepare0','code0','audit0','admit','handoff'])
        self.assertFalse(result['data_evaluation_started'])
    def test_review_only_never_selector(self):
        f=Fixtures();r=flow.drive(self.store,f,'review');self.assertFalse(r['candidate_started']);self.assertNotIn('selector',f.calls)
    def test_candidate_only_never_review(self):
        f=Fixtures();flow.drive(self.store,f,'candidate');self.assertNotIn('review',f.calls)
    def test_failed_gate_returns_diagnostic_to_independent_Meta(self):
        f=Fixtures(failures=1);flow.drive(self.store,f,'candidate')
        self.assertIn('diagnostic0',f.calls);self.assertIn('code1',f.calls);self.assertEqual(f.calls.count('selector'),1)
    def test_two_bounded_repairs(self):
        f=Fixtures(failures=2);flow.drive(self.store,f,'candidate');self.assertIn('code2',f.calls);self.assertNotIn('code3',f.calls)
    def test_exhausted_repairs_no_admission(self):
        f=Fixtures(failures=3)
        with self.assertRaisesRegex(RuntimeError,'exhausted'):flow.drive(self.store,f,'candidate')
        self.assertNotIn('admit',f.calls);self.assertEqual(sum(c.startswith('code') for c in f.calls),3)
    def test_infrastructure_gate_never_auto_Meta_repair(self):
        f=Fixtures(failures=1,kind='infrastructure')
        with self.assertRaisesRegex(RuntimeError,'Infrastructure'):flow.drive(self.store,f,'candidate')
        self.assertNotIn('code1',f.calls)
    def test_security_denial_never_retried(self):
        f=Fixtures(crash='code0')
        with self.assertRaises(RuntimeError):flow.drive(self.store,f,'candidate')
        again=Fixtures()
        with self.assertRaisesRegex(RuntimeError,'never replay'):flow.drive(self.store,again,'candidate')
        self.assertEqual(again.calls,[])
    def test_completed_cycle_no_paid_replay(self):
        f=Fixtures();flow.drive(self.store,f,'review_then_candidate');again=Fixtures()
        flow.drive(self.store,again,'review_then_candidate');self.assertEqual(again.calls,[])
    def test_completed_stage_source_drift_rejected(self):
        evidence=self.root/'evidence.json';evidence.write_text('{}',encoding='utf-8')
        self.store.step('fixture',lambda:({'ok':True},[evidence]));evidence.write_text('{"changed":true}',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'changed'):self.store.step('fixture',lambda:self.fail('replayed'))
    def test_missing_receipt_blocks_ambiguous_commit(self):
        flow.new(self.store.root/'fixture.intent.json',{'executed':'UNKNOWN'})
        with self.assertRaisesRegex(RuntimeError,'reconcile'):self.store.step('fixture',lambda:self.fail('replayed'))
    def test_malformed_receipt_rejected(self):
        flow.new(self.store.root/'fixture.receipt.json',{'stage':'fixture','status':'running'})
        with self.assertRaisesRegex(RuntimeError,'Incomplete'):self.store.step('fixture',lambda:self.fail('replayed'))
    def test_invalid_repair_cap_rejected(self):
        for v in (3,-1,True):
            with self.assertRaises(ValueError):flow.drive(self.store,Fixtures(),'candidate',v)
    def test_candidate_authority_denial_stops_before_selector(self):
        f=Fixtures(crash='candidate_authority')
        with self.assertRaises(RuntimeError):flow.drive(self.store,f,'review_then_candidate')
        self.assertNotIn('selector',f.calls)
    def test_trust_only_config_growth_narrowly_allowed(self):
        base={'model':'fixture','projects':{'old':{'trust_level':'trusted'}}};home=self.root/'home';home.mkdir()
        profile=home/(flow.PROFILE+'.config.toml');profile.write_text('model="fixture"',encoding='utf-8')
        repo=self.root/'candidate';repo.mkdir()
        config=home/'config.toml';config.write_text('model="fixture"\n[projects.old]\ntrust_level="trusted"\n[projects.'+json.dumps(str(repo).casefold())+']\ntrust_level="trusted"\n',encoding='utf-8')
        plan={'base_config':base,'profile_sha256':flow.sha(profile)}
        with patch.object(flow.health,'HOME',home),patch.object(flow.health,'validate_config'):
            flow.stable_config(plan,[repo])
            with self.assertRaisesRegex(RuntimeError,'Unexpected'):flow.stable_config(plan,[])
    def test_model_config_change_rejected(self):
        home=self.root/'home';home.mkdir();(home/'config.toml').write_text('model="wrong"',encoding='utf-8')
        with patch.object(flow.health,'HOME',home):
            with self.assertRaisesRegex(RuntimeError,'config changed'):flow.stable_config({'base_config':{'model':'expected'}})
    def test_plan_prepare_refuses_active_gen9(self):
        with patch.object(flow.protocol,'load_campaign',return_value=({'max_generations':9},{'stage':'candidate_admitted','next_generation':9})):
            with self.assertRaisesRegex(RuntimeError,'unavailable'):flow.prepare(self.root,self.root/'meta_workflows'/'fresh','candidate','fixture',candidate_generation=9)
            with self.assertRaisesRegex(RuntimeError,'unauthorized'):flow.prepare(self.root,self.root/'meta_workflows'/'fresh','candidate','fixture',candidate_generation=10)
    def test_health_environment_drops_credentials_no_global_mutation(self):
        from experiments.dab_meta_sandbox_health_v1 import environment
        with patch.dict(flow.os.environ,{'CRS_API_KEY':'synthetic','CODEX_MCP_NODE_PATH':'synthetic'}),patch('experiments.dab_meta_sandbox_health_v1.bind_environment',side_effect=lambda env,tools:dict(env)):
            result=environment(self.root,{})
            self.assertNotIn('CRS_API_KEY',result);self.assertNotIn('CODEX_MCP_NODE_PATH',result);self.assertEqual(flow.os.environ['CRS_API_KEY'],'synthetic')
    def test_actual_native_command_prefers_mxc_and_has_no_weak_fallback(self):
        cmd=flow.health.mxc_command('fixture.exe','exec','--sandbox','read-only')
        self.assertIn('windows.sandbox="mxc"',cmd);self.assertIn('features.prefer_mxc=true',cmd)
        self.assertNotIn('unelevated',str(cmd));self.assertNotIn('danger-full-access',str(cmd))
    def test_standalone_health_pass_does_not_release_native_model(self):
        p=self.root/'report.json';flow.new(p,{'passed':True,'read_write_verified':True,'model_calls':0})
        with self.assertRaisesRegex(RuntimeError,'integration failed'):flow.require_native_integration(p)
    def test_native_failed_probe_blocks_before_model_or_auth(self):
        p=self.root/'report.json';flow.new(p,{'passed':False,'failure_type':'RuntimeError'})
        with patch.object(flow,'meta_environment') as auth:
            with self.assertRaisesRegex(RuntimeError,'zero Meta dispatch'):flow.require_native_integration(p)
            auth.assert_not_called()
if __name__=='__main__':unittest.main()
