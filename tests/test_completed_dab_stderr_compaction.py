import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.compact_completed_dab_stderr import compact


class CompactionTests(unittest.TestCase):
    def test_lossless_recovery_and_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "case.run.stderr"
            data = b"repeatable diagnostic log\n" * 10000
            original.write_bytes(data)
            journal = root / "journal.jsonl"
            result = compact(original, journal)
            self.assertFalse(original.exists())
            self.assertEqual(gzip.decompress(Path(result["archive"]).read_bytes()), data)
            records = [json.loads(line) for line in journal.read_text().splitlines()]
            self.assertEqual([record["state"] for record in records], ["verified_before_unlink", "uncompressed_copy_removed"])
            self.assertEqual(records[0]["original_sha256"], records[1]["original_sha256"])

    def test_failed_verification_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "case.run.stderr"
            original.write_bytes(b"original evidence")
            with patch("experiments.compact_completed_dab_stderr.stream_hash", side_effect=["before", "wrong"]):
                with self.assertRaisesRegex(AssertionError, "Lossless"):
                    compact(original, root / "journal.jsonl")
            self.assertEqual(original.read_bytes(), b"original evidence")

    def test_existing_archive_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "case.run.stderr"
            original.write_bytes(b"evidence")
            archive = root / "case.run.stderr.gz"
            archive.write_bytes(b"existing")
            with self.assertRaises(AssertionError):
                compact(original, root / "journal.jsonl")
            self.assertTrue(original.exists())
            self.assertEqual(archive.read_bytes(), b"existing")
