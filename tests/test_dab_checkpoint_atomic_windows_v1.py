import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from experiments import dab_checkpoint_atomic_windows_v1 as a
class WindowsAtomicTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name);self.src=self.root/'cp.json.new';self.dst=self.root/'cp.json';self.src.write_bytes(b'new');self.dst.write_bytes(b'old')
    def error(self,code=5):
        e=PermissionError('synthetic contention');e.winerror=code;return e
    def test_success_once(self):
        with patch.object(a.os,'replace',wraps=a.os.replace) as replace:a.replace_checkpoint(self.src,self.dst,platform_name='nt');self.assertEqual(replace.call_count,1)
        self.assertEqual(self.dst.read_bytes(),b'new')
    def test_transient_failure_waits_then_replaces(self):
        original=a.os.replace
        with patch.object(a.os,'replace',side_effect=[self.error(),None]) as replace,patch.object(a.time,'sleep') as sleep:
            a.replace_checkpoint(self.src,self.dst,platform_name='nt');self.assertEqual(replace.call_count,2);sleep.assert_called_once()
        self.assertEqual(self.dst.read_bytes(),b'old');original(self.src,self.dst);self.assertEqual(self.dst.read_bytes(),b'new')
    def test_persistent_error_bounded_old_checkpoint_unchanged(self):
        with patch.object(a.os,'replace',side_effect=self.error()) as replace,patch.object(a.time,'sleep'):
            with self.assertRaises(PermissionError):a.replace_checkpoint(self.src,self.dst,platform_name='nt')
            self.assertEqual(replace.call_count,6)
        self.assertEqual(self.dst.read_bytes(),b'old');self.assertEqual(self.src.read_bytes(),b'new')
    def test_non_windows_no_retry(self):
        with patch.object(a.os,'replace',side_effect=self.error()) as replace:
            with self.assertRaises(PermissionError):a.replace_checkpoint(self.src,self.dst,platform_name='posix')
            self.assertEqual(replace.call_count,1)
    def test_other_error_no_retry(self):
        with patch.object(a.os,'replace',side_effect=self.error(13)) as replace:
            with self.assertRaises(PermissionError):a.replace_checkpoint(self.src,self.dst,platform_name='nt')
            self.assertEqual(replace.call_count,1)
    def test_source_change_rejects(self):
        def fail(*_):self.src.write_bytes(b'tamper');raise self.error()
        with patch.object(a.os,'replace',side_effect=fail) as replace:
            with self.assertRaisesRegex(RuntimeError,'changed'):a.replace_checkpoint(self.src,self.dst,platform_name='nt')
            self.assertEqual(replace.call_count,1)
    def test_destination_change_rejects(self):
        def fail(*_):self.dst.write_bytes(b'tamper');raise self.error()
        with patch.object(a.os,'replace',side_effect=fail) as replace:
            with self.assertRaisesRegex(RuntimeError,'changed'):a.replace_checkpoint(self.src,self.dst,platform_name='nt')
            self.assertEqual(replace.call_count,1)
    def test_non_same_directory_rejects(self):
        with self.assertRaises(RuntimeError):a.replace_checkpoint(self.src,self.root/'other/cp.json',platform_name='nt')
if __name__=='__main__':unittest.main()
