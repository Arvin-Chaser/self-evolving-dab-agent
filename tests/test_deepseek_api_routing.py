"""Synthetic-only routing, credential boundary and native history tests."""
import copy
import os
import unittest
from types import SimpleNamespace
from unittest import mock
from experiments import dab_api_routing as route
from adapters import deepseek_client_v1 as adapter

class RoutingTests(unittest.TestCase):
    def test_meta_overlay_preserves_original(self):
        original={'model':'old-model','profile':'old-profile','codex':'existing'}
        with mock.patch.object(route,'active_route',return_value={'model':'deepseek-flash','meta_profile':'deepseek-dab'}):
            new=route.meta_route(original)
        self.assertEqual(original['model'],'old-model')
        self.assertEqual(new['model'],'deepseek-flash')
        self.assertEqual(new['codex'],'existing')
        self.assertIsNone(new['wall_clock_timeout_seconds'])
    def test_inactive_route_preserves_history(self):
        with mock.patch.object(route,'active_route',return_value=None):
            self.assertEqual(route.meta_route({'model':'old'}),{'model':'old'})
    def test_key_only_enters_child_environment(self):
        r={'meta_profile':'deepseek-dab','meta_codex_home':'configs/deepseek_meta_runtime_v1','api_key_env':'DEEPSEEK_API_KEY','meta_bridge_config':'configs/codex_deepseek_meta_bridge.json'}
        with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(route,'active_route',return_value=r),mock.patch.object(route,'read_explicit_key',return_value='synthetic-token'):
            env=route.routed_meta_environment('deepseek-dab')
            self.assertEqual(env['DEEPSEEK_API_KEY'],'synthetic-token')
            self.assertNotIn('DEEPSEEK_API_KEY',os.environ)
    def test_unrelated_profile_does_not_load_key(self):
        with mock.patch.object(route,'active_route',return_value={'meta_profile':'deepseek-dab'}),mock.patch.object(route,'read_explicit_key') as key:
            self.assertIsNone(route.routed_meta_environment('unrelated'))
            key.assert_not_called()
    def test_request_options_preserves_tools_and_inputs(self):
        r={'model':'deepseek-flash','messages':[{'role':'user','content':'synthetic'}],'tools':[{'type':'function'}]}
        before=copy.deepcopy(r);new=adapter.request_options(r)
        self.assertEqual(r,before)
        self.assertEqual(new['tools'],r['tools'])
        self.assertEqual(new['extra_body'],{'thinking':{'type':'enabled'}})
    def test_other_model_and_conflicting_mode_refused(self):
        with self.assertRaises(RuntimeError):adapter.request_options({'model':'old'})
        with self.assertRaises(RuntimeError):adapter.request_options({'model':'deepseek-flash','extra_body':{'thinking':{'type':'disabled'}}})
    def test_exact_native_reasoning_roundtrip(self):
        calls=[{'id':'synthetic-id','type':'function','function':{'name':'probe','arguments':'{}'}}]
        native={'role':'assistant','content':None,'reasoning_content':'synthetic reasoning','tool_calls':calls}
        message=SimpleNamespace(model_dump=lambda:copy.deepcopy(native))
        response=SimpleNamespace(choices=[SimpleNamespace(message=message)])
        original=mock.Mock(return_value=response)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=original)))
        adapter.install_client(client)
        client.chat.completions.create(model='deepseek-flash',messages=[])
        history=[{'role':'assistant','tool_calls':copy.deepcopy(calls)}]
        client.chat.completions.create(model='deepseek-flash',messages=history)
        self.assertEqual(original.call_args.kwargs['messages'][0]['reasoning_content'],'synthetic reasoning')
        self.assertNotIn('reasoning_content',history[0])
    def test_unbound_history_refused(self):
        original=mock.Mock();client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=original)))
        adapter.install_client(client)
        with self.assertRaises(RuntimeError):client.chat.completions.create(model='deepseek-flash',messages=[{'role':'assistant','tool_calls':[{'id':'unknown'}]}])
        original.assert_not_called()

if __name__=='__main__':unittest.main()
