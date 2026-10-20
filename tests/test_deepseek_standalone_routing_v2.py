"""Offline dedicated runtime routing: no model, credentials or network."""
import copy,json,os,unittest
from unittest.mock import patch
from experiments import dab_api_routing as routing
from experiments import dab_meta_standalone_runtime_v1 as runtime
from experiments import dab_meta_pipeline_v2 as flow

class Routing(unittest.TestCase):
    def setUp(self):self.route=json.loads(runtime.ROUTE.read_bytes())
    def test_default_shared_route_and_native_release(self):
        self.assertEqual(routing.active_route(),self.route)
        self.assertTrue(flow.require_native_integration()['passed'])
    def test_exact_executable_no_desktop_fallback(self):
        original={'model':'historical','codex':'desktop'}
        value=routing.meta_route(original)
        self.assertEqual(value['codex'],str(runtime.CODEX));self.assertEqual(value['model'],runtime.MODEL)
        self.assertEqual(original['codex'],'desktop')
    def test_wrong_runtime_key_home_profile_rejected_before_key(self):
        for field in ('meta_runtime_binding','meta_profile','meta_codex_home','meta_bridge_config','api_key_file'):
            r=copy.deepcopy(self.route);r[field]='wrong'
            with patch.object(routing,'read_explicit_key') as key:
                with self.assertRaises(RuntimeError):routing.validate_standalone_route(r)
                key.assert_not_called()
    def test_private_environment_isolated_no_global_changes(self):
        with patch.dict(os.environ,{'CODEX_HOME':'desktop','CODEX_THREAD_ID':'old','CRS_API_KEY':'synthetic','CODEX_MANAGED_REQUIREMENTS':'preserved'}):
            child=runtime.isolate_environment(os.environ)
            self.assertEqual(child['CODEX_HOME'],str(runtime.HOME));self.assertNotIn('CRS_API_KEY',child)
            self.assertNotIn('CODEX_THREAD_ID',child)
            self.assertEqual(child['CODEX_MANAGED_REQUIREMENTS'],'preserved')
            self.assertEqual(os.environ['CODEX_HOME'],'desktop')
    def test_changed_executable_binding_fails_closed(self):
        with patch.object(runtime,'sha',return_value='tampered'):
            with self.assertRaisesRegex(RuntimeError,'executable changed'):runtime.validate()
    def test_missing_schema_proof_blocks_paid_release(self):
        with self.assertRaisesRegex(RuntimeError,'structured'):
            flow.require_native_integration(schema_report=runtime.ROOT/'tmp/not-created-schema-report.json')
    def test_data_entry_overrides_old_environment_without_key_read(self):
        from experiments.run_dab_deepseek_data_v2 import parser
        with patch.dict(os.environ,{'DAB_TOOL_AGENT_MODEL':'gpt-5.5','DAB_TOOL_AGENT_OPENAI_BASE_URL':'https://crs.uuid.im/openai','DAB_TOOL_AGENT_CLIENT_MAX_RETRIES':'2'}),patch.object(routing,'read_explicit_key') as key:
            a=parser().parse_args([])
            self.assertEqual(a.deployment_name,runtime.MODEL);self.assertEqual(a.openai_compatible_base_url,self.route['base_url'])
            self.assertEqual(a.client_max_retries,0);self.assertEqual(a.max_iterations,0);key.assert_not_called()
if __name__=='__main__':unittest.main()
