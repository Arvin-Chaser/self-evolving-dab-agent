"""Immutable diagnosis recovery and revision metadata regression checks."""

import tempfile
import unittest
from pathlib import Path

from experiments import dab_roadmap_protocol as protocol


class ReviewRecoveryTests(unittest.TestCase):
    def test_revision_uses_bound_patch_not_original_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.json"
            protocol.write_json(original, {"changed_files": ["obsolete.py"]})
            patch = root / "candidate.patch"
            patch.write_text(
                "diff --git a/new.py b/new.py\nnew file mode 100644\n"
                "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+pass\n",
                encoding="utf-8",
            )
            candidate = {
                "schema_version": "dab_versioned_engineering_candidate_ref_v1",
                "repo": str(root), "candidate_patch": str(patch),
                "patch_sha256": protocol.sha256_file(patch),
                "original_ref": str(original),
                "original_ref_sha256": protocol.sha256_file(original),
            }
            self.assertEqual(protocol.review_candidate_changed_files(candidate), ["new.py"])
            patch.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "patch hash"):
                protocol.review_candidate_changed_files(candidate)

    def test_identical_review_recovery_preserves_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            review = {"diagnosis": "measured zero", "result_sha256": "bound", "reviewed_at": "original"}
            protocol.preserve_review_artifact(path, review)
            saved = path.read_bytes()
            protocol.preserve_review_artifact(path, {**review, "reviewed_at": "retry"})
            self.assertEqual(path.read_bytes(), saved)
            for field, value in (("diagnosis", "different"), ("result_sha256", "changed")):
                with self.assertRaisesRegex(SystemExit, "differs"):
                    protocol.preserve_review_artifact(path, {**review, field: value})
                self.assertEqual(path.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
