"""Synthetic context-only checks: no models, database, SSH, or real campaign writes."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import dab_meta_detail_context_v1 as detail
from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as workspace


class SafeMetaDetailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "campaign"
        self.root.mkdir()
        self.campaign = {"campaign_id": "synthetic", "meta_agent": {}, "query_ids": ["alpha/query1"]}
        protocol.write_json(self.root / "campaign.json", self.campaign)
        protocol.write_json(self.root / "campaign_state.json", {"stage": "ready_for_intent", "next_generation": 2})
        source = self.root / "root/repo"
        source.mkdir(parents=True)
        protocol.write_json(self.root / "root_node.json", {"source_root": str(source), "source_tree_sha256": "x"})
        self.intent_path = self.root / "generations/gen_001/sealed_intent.json"
        self.review_path = self.root / "details/review_gen_001.json"
        self.intent = {"generation": 1, "campaign_id": "synthetic", "mechanism_key": "bounded_recovery",
                       "proposed_mechanism": "Persist successful progress. Bound restore attempts.",
                       "expected_behavioral_change": "Reuse validated artifacts.",
                       "validation_expectations": ["Restore no more than twice."],
                       "potential_regressions": ["Avoid suppressing a valid new request."]}
        self.intent["canonical_json_sha256"] = protocol.canonical_hash(self.intent)
        self.review = {"generation": 1, "campaign_id": "synthetic", "intent_sha256": self.intent["canonical_json_sha256"],
                       "candidate_patch_sha256": "patch", "outcome_label": "inconclusive",
                       "short_review": "Missing activation is unknown.",
                       "detailed_analysis": "Source compatibility is plausible. alpha/query1 returned 42. Activation remains unknown.",
                       "activation_evidence": ["No mechanism-specific measurements.", "alpha had a failure."],
                       "evidence_refs": ["RAW_EVIDENCE_REF"], "per_query_feedback": ["RAW_ROWS"],
                       "final_answer": "RAW_ANSWER", "raw_trace": "RAW_TRACE", "candidate_patch": "RAW_PATCH"}
        protocol.write_json(self.intent_path, self.intent)
        protocol.write_json(self.review_path, self.review)
        self.record = {"generation": 1, "node_id": "gen_001_bounded_recovery", "intent": {"mechanism_key": "bounded_recovery"},
                       "candidate": {"patch_sha256": "patch"}, "result": {"query_count": 1, "strict_pass_count": 0},
                       "review": {"outcome_label": "inconclusive", "short_review": self.review["short_review"]},
                       "parent_edges": [{"node_id": "root_baseline", "role": "code_base"}],
                       "previous_record_sha256": None,
                       "detail_links": {"sealed_intent": str(self.intent_path), "detailed_review": str(self.review_path)}}
        self.record["record_sha256"] = protocol.record_hash(self.record)
        (self.root / "roadmap.jsonl").write_text(protocol.canonical_json(self.record) + "\n", encoding="utf-8")

    def enable(self):
        protocol.write_json(self.root / detail.POLICY_FILE,
                            {"enabled": True, "context_policy": detail.POLICY, "human_authority": "synthetic approval"})

    def view(self):
        return detail.build_detail(self.root, self.campaign, self.record, protocol.compact_metrics(self.record["result"]), {})

    def test_default_campaign_keeps_original_policy(self):
        snapshot = protocol.build_snapshot(self.root)
        self.assertEqual(snapshot["context_policy"], "compact_result_graph_v1")
        self.assertNotIn("safe_detail_access", snapshot)
        self.assertNotIn("# Optional historical", protocol.build_intent_prompt(snapshot))

    def test_opt_in_index_is_bounded_not_eager_prose(self):
        self.enable()
        snapshot = protocol.build_snapshot(self.root)
        self.assertEqual(snapshot["context_policy"], detail.POLICY)
        self.assertEqual(snapshot["safe_detail_access"]["nodes"][0]["status"], "available")
        self.assertNotIn("Source compatibility is plausible", json.dumps(snapshot))
        self.assertFalse((self.root / "meta_detail_summaries_v1").exists())

    def test_filter_keeps_mechanism_reasoning_but_not_task_examples(self):
        value = self.view()
        rendered = json.dumps(value)
        self.assertIn("Source compatibility is plausible", rendered)
        self.assertIn("Activation remains unknown", rendered)
        for forbidden in ("alpha", "query1", "returned 42", "RAW_EVIDENCE_REF", "RAW_ROWS", "RAW_ANSWER", "RAW_TRACE", "RAW_PATCH"):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(value["projection_notes"]["omitted_or_bounded_sentences"])
        self.assertFalse(value["projection_notes"]["new_activation_measurements_supplied"])

    def test_sql_trace_credentials_and_answer_fragments_are_omitted(self):
        text, count = detail.safe_text("Safe mechanism. SELECT secret FROM rows. Bearer abc. final_answer=42. Traceback error. Still unknown.", [])
        self.assertEqual(text, "Safe mechanism. Still unknown.")
        self.assertEqual(count, 4)

    def test_dict_in_prose_never_serializes_nested_rows(self):
        self.assertEqual(detail.safe_text({"query_id": "alpha/query1", "answer": 42}, []), ("", 0))

    def test_intent_tamper_rejected(self):
        changed = {**self.intent, "proposed_mechanism": "tampered"}
        protocol.write_json(self.intent_path, changed)
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            self.view()

    def test_review_patch_mismatch_rejected(self):
        protocol.write_json(self.review_path, {**self.review, "candidate_patch_sha256": "other"})
        with self.assertRaisesRegex(ValueError, "patch binding"):
            self.view()

    def test_review_outcome_conflict_rejected(self):
        protocol.write_json(self.review_path, {**self.review, "outcome_label": "effective"})
        with self.assertRaisesRegex(ValueError, "immutable graph"):
            self.view()

    def test_wrong_generation_rejected(self):
        protocol.write_json(self.review_path, {**self.review, "generation": 9})
        with self.assertRaisesRegex(ValueError, "generation mismatch"):
            self.view()

    def test_arbitrary_original_path_rejected(self):
        self.record["detail_links"]["detailed_review"] = str(self.root / "other.json")
        with self.assertRaisesRegex(ValueError, "expected archive"):
            self.view()

    def test_source_escape_and_oversize_rejected(self):
        outside = self.root.parent / "outside.json"
        outside.write_text("{}")
        with self.assertRaisesRegex(ValueError, "outside"):
            detail.read_confined(self.root, outside)
        self.review_path.write_bytes(b" " * (detail.MAX_ARCHIVE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "size bound"):
            self.view()

    def test_symlink_source_rejected(self):
        target = self.root / "original.json"
        target.write_bytes(self.review_path.read_bytes())
        self.review_path.unlink()
        try:
            self.review_path.symlink_to(target)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            self.view()

    def test_symlink_guard_without_os_creation_privilege(self):
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path == self.review_path or original(path)):
            with self.assertRaisesRegex(ValueError, "Symlinked"):
                self.view()

    def test_missing_detail_is_unknown_not_raw_fallback(self):
        self.enable()
        self.review_path.unlink()
        snapshot = protocol.build_snapshot(self.root)
        self.assertEqual(snapshot["safe_detail_access"]["nodes"][0]["status"], "unavailable_or_invalid")

    def test_materialization_preserves_originals_and_rejects_modified_view(self):
        self.enable()
        paths = [self.intent_path, self.review_path, self.root / "roadmap.jsonl", self.root / "campaign_state.json"]
        before = {path: path.read_bytes() for path in paths}
        snapshot = protocol.build_snapshot(self.root)
        protocol.materialize_safe_details(self.root, snapshot)
        entry = snapshot["safe_detail_access"]["nodes"][0]
        path = Path(entry["safe_mechanism_detail"])
        self.assertEqual(detail.digest(path.read_bytes()), entry["sha256"])
        protocol.materialize_safe_details(self.root, snapshot)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        path.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "modified"):
            protocol.materialize_safe_details(self.root, snapshot)

    def test_archive_change_after_snapshot_fails_before_write(self):
        self.enable()
        snapshot = protocol.build_snapshot(self.root)
        protocol.write_json(self.review_path, {**self.review, "detailed_analysis": "Different reasoning."})
        with self.assertRaisesRegex(ValueError, "after the snapshot"):
            protocol.materialize_safe_details(self.root, snapshot)
        self.assertFalse((self.root / "meta_detail_summaries_v1").exists())

    def test_intent_review_and_coding_prompts_only_authorize_safe_views(self):
        self.enable()
        snapshot = protocol.build_snapshot(self.root)
        for prompt in (protocol.build_intent_prompt(snapshot), protocol.build_review_prompt({}, {}, {}, snapshot)):
            self.assertIn("safe_mechanism_detail", prompt)
            self.assertIn("provenance ONLY", prompt)
            self.assertIn("not execution/deployment powers", prompt)
        task = workspace.implementation_task(self.intent, intent_hash="i", parent_hash="p", contract=None,
                                            upstream_available=False, parent_context_available=True, safe_detail_available=True)
        self.assertIn("safe_mechanism_detail", task)
        self.assertIn("Do not open original", task)
        legacy = workspace.implementation_task(self.intent, intent_hash="i", parent_hash="p", contract=None,
                                              upstream_available=False, parent_context_available=True)
        self.assertNotIn("safe_mechanism_detail", legacy)

    def test_selected_parent_pack_limits_detail_index_to_selected_nodes(self):
        self.enable()
        intent = {"generation": 2, "parent_selection": {"parents": [{"node_id": self.record["node_id"], "role": "code_base"}],
                  "materialization_base_node_id": self.record["node_id"], "synthesis_strategy": "Refine"}}
        evidence = protocol.build_selected_parent_evidence(self.root, intent)
        self.assertEqual([item["node_id"] for item in evidence["safe_detail_access"]["nodes"]], [self.record["node_id"]])

    def test_no_new_measurements_or_label_reclassification(self):
        value = self.view()
        self.assertEqual(value["review"]["outcome_label"], "inconclusive")
        self.assertNotIn("checkpoint_restore_count", json.dumps(value))
        self.assertLess(len(detail.encoded(value)), detail.MAX_DETAIL_BYTES)

    def test_causal_diagnosis_is_safely_projected_without_becoming_a_recommendation(self):
        links = {name: {
            "status": "unknown",
            "evidence": ["Aggregate counter unavailable.", "alpha/query1 exposed a target."],
            "interpretation": "This link remains unmeasured.",
        } for name in protocol.CAUSAL_LINKS}
        diagnosis = {
            "links": links,
            "failure_boundary": "undetermined",
            "falsified_claims": [],
            "unsupported_claims": ["Task gain was caused by the mechanism."],
            "excluded_equivalence_classes": ["More of the same unmeasured intervention."],
            "open_discriminators": ["Whether model uptake occurs after delivery."],
        }
        protocol.write_json(self.review_path, {**self.review, "causal_diagnosis": diagnosis})
        value = self.view()
        projected = value["review"]["causal_diagnosis"]
        self.assertEqual(projected["failure_boundary"], "undetermined")
        self.assertEqual(projected["links"]["activation"]["status"], "unknown")
        self.assertNotIn("alpha", json.dumps(projected))
        self.assertNotIn("next_recommendation", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
