"""Offline orchestration checks; no credentials, SSH, model, DB or Meta."""
import ast,unittest
from pathlib import Path
from unittest.mock import patch
from experiments import launch_gen009_deepseek_once_v1 as local
from experiments import monitor_gen009_deepseek_data_v1 as monitor
ROOT=Path(__file__).resolve().parent
class Checks(unittest.TestCase):
    def test_local_duplicate_rejected_before_key_or_network(self):
        with patch.object(local,'verify',return_value={'run_id':'fixture'}),patch.object(local,'sha',return_value='fixture_digest'),patch.object(local,'save_new',side_effect=FileExistsError),patch.object(local.subprocess,'run') as call:
            with self.assertRaises(FileExistsError):local.run_once()
            call.assert_not_called()
    def test_offline_compile(self):
        for name in ('launch_gen009_deepseek_once_v1.py','launch_gen009_deepseek_remote_once_v1.py','monitor_gen009_deepseek_data_v1.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'))
        compile(monitor.REMOTE.replace('BINDING','{}',1).replace('RETRIEVE','False',1),'<remote>','exec')
    def test_remote_intent_precedes_key_and_dispatch(self):
        source=(ROOT/'launch_gen009_deepseek_remote_once_v1.py').read_text(encoding='utf-8')
        self.assertLess(source.index("save_new(audit_dir/'gen009_deepseek_launch_intent.json'"),source.index('fd=os.open(key_path'))
        self.assertLess(source.index('fd=os.open(key_path'),source.index('child=subprocess.Popen'))
        self.assertIn('os.O_EXCL,0o600',source)
    def test_no_key_hash_or_env_dump(self):
        source=(ROOT/'launch_gen009_deepseek_remote_once_v1.py').read_text(encoding='utf-8')
        self.assertNotIn('sha(key_path)',source);self.assertNotIn('sha256(key',source)
        self.assertNotIn('print(env',source);self.assertNotIn('print(plan',source)
    def test_monitor_generic_contract_not_gen8_gate(self):
        self.assertIn('validate_contract',monitor.REMOTE)
        self.assertNotIn('validate_gate',monitor.REMOTE)
        self.assertNotIn('recovery_checkpoint.json',monitor.REMOTE)
    def test_monitor_finished_delta_unknown(self):
        self.assertIsNone(monitor.snapshot({'finished_count':5},{'observation':{'finished_count':'UNKNOWN'}},'now')['finished_delta'])
        self.assertEqual(monitor.snapshot({'finished_count':5},{'observation':{'finished_count':2}},'now')['finished_delta'],3)
    def test_binding_and_final_order_checks(self):
        self.assertIn("gen009_deepseek_launch_binding.json",monitor.REMOTE)
        self.assertIn("assert ids==s['query_ids']",monitor.REMOTE)
        self.assertIn("summary.read_bytes()==raw",monitor.REMOTE)
    def test_monitor_not_due_never_network(self):
        import json
        from datetime import datetime,timezone
        fixture=json.dumps({'started_at':datetime.now(timezone.utc).isoformat()})
        with patch.object(Path,'read_text',return_value=fixture),patch.object(monitor.sys,'argv',['monitor']),patch.object(monitor.subprocess,'run') as call:
            self.assertEqual(monitor.main(),0);call.assert_not_called()
if __name__=='__main__':unittest.main()
