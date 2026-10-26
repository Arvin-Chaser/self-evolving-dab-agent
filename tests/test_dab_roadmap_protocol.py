"""Synthetic lifecycle checks for the append-only DAB roadmap protocol."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as candidate_workspace
from experiments import run_multi_query_baseline as batch_runner


class DabRoadmapProtocolTests(unittest.TestCase):
    def test_candidate_revision_preserves_original_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("print('root')\n", encoding="utf-8")
            batch = root / "batch.json"
            protocol.write_json(batch, {"query_ids": ["alpha/query1"]})
            campaign = root / "campaign"
            protocol.init_campaign(argparse.Namespace(
                campaign_root=campaign, campaign_id="revision_test", evolution_batch=batch,
                source_root=source, parent_result=None, max_generations=1,
                max_agent_iterations=0, codex="codex", meta_profile="test",
                meta_model="test",
            ))
            original_workspace = root / "original"
            original_repo = original_workspace / "repo"
            original_runner = original_repo / "experiments" / "run_dab_tool_agent.py"
            original_runner.parent.mkdir(parents=True)
            original_runner.write_text("print('original')\n", encoding="utf-8")
            original_patch = original_workspace / "candidate.patch"
            original_patch.write_text("original patch\n", encoding="utf-8")
            old_ref = campaign / "generations" / "gen_001" / "candidate_ref.json"
            protocol.write_json(old_ref, {
                "repo": str(original_repo), "candidate_patch": str(original_patch),
                "patch_sha256": protocol.sha256_file(original_patch),
                "source_tree_sha256": candidate_workspace.source_tree_hash(original_repo),
            })
            intent = {"canonical_json_sha256": "intent-hash", "code_parent_hash": "parent-hash"}
            intent_path = campaign / "generations" / "gen_001" / "sealed_intent.json"
            protocol.write_json(intent_path, intent)
            state_path = campaign / "campaign_state.json"
            state = protocol.read_json(state_path)
            state.update({"stage": "candidate_admitted", "active_intent": str(intent_path),
                          "active_candidate_ref": str(old_ref)})
            protocol.write_json(state_path, state)

            revision = root / "revision"
            revised_runner = revision / "repo" / "experiments" / "run_dab_tool_agent.py"
            revised_runner.parent.mkdir(parents=True)
            revised_runner.write_text("print('revised')\n", encoding="utf-8")
            revised_patch = revision / "candidate.patch"
            revised_patch.write_text("revised patch\n", encoding="utf-8")
            protocol.write_json(revision / "workspace_manifest.json", {
                "intent_canonical_sha256": "intent-hash", "parent_source_sha256": "parent-hash",
            })
            protocol.write_json(revision / "candidate_admission.json", {
                "status": "source_preflight_passed", "patch_sha256": protocol.sha256_file(revised_patch),
                "changed_files": ["experiments/run_dab_tool_agent.py"],
                "implementation_files": ["experiments/run_dab_tool_agent.py"],
                "claim_to_source_valid": True,
            })
            original_bytes = old_ref.read_bytes()
            protocol.record_candidate_revision(argparse.Namespace(
                campaign_root=campaign, workspace=revision, reason="unsafe SQL replay classification",
            ))
            current = protocol.read_json(state_path)
            new_ref = Path(current["active_candidate_ref"])
            self.assertEqual(old_ref.read_bytes(), original_bytes)
            self.assertEqual(new_ref.name, "candidate_ref_revision_001.json")
            self.assertEqual(protocol.read_json(new_ref)["revises_candidate_ref_sha256"],
                             protocol.sha256_file(old_ref))

    def test_compact_result_excludes_unreliable_f1_and_keeps_process_exits(self) -> None:
        result = protocol.compact_result({
            "average_f1": 0.5,
            "per_query_feedback": [
                {"strict_match_passed": True, "answer_f1": 0.5, "run_exit_code": 0},
                {"strict_match_passed": False, "answer_f1": None, "run_exit_code": 0},
                {"strict_match_passed": None, "answer_f1": None, "run_exit_code": -15},
            ],
        })
        self.assertEqual(result["strict_pass_count"], 1)
        self.assertEqual(result["strict_evaluated_count"], 2)
        self.assertNotIn("average_f1", result)
        self.assertNotIn("answer_f1_scored_count", result)
        self.assertEqual(result["nonzero_exit_count"], 1)
        self.assertNotIn("per_query_feedback", result)

    def test_meta_views_do_not_expose_archived_f1(self) -> None:
        archived = {"query_count": 56, "strict_pass_count": 33,
                    "average_f1": 0.085371, "answer_f1_scored_count": 7}
        self.assertEqual(protocol.compact_metrics(archived),
                         {"query_count": 56, "strict_pass_count": 33})
        self.assertNotIn("f1", json.dumps(protocol.visible_result({
            "generation": 1, "summary": archived,
            "intent_binding": {"mechanism_key": "gate", "expected_behavioral_change": "Raise F1"},
            "evaluation_binding": {"f1_denominator": 7},
        })).lower())

    def test_formal_result_keeps_runner_wall_timeout_as_failed_query(self) -> None:
        self.assertTrue(protocol.expected_query_timeout({
            "run_exit_code": 124,
            "run_error": "query_wall_timeout_1200s",
            "terminate_reason": "query_wall_timeout_1200s",
        }))
        self.assertFalse(protocol.expected_query_timeout({
            "run_exit_code": 124,
            "run_error": "provider_timeout",
            "terminate_reason": "provider_timeout",
        }))

    def test_parent_timeout_is_not_labeled_infrastructure_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent_path = Path(temporary) / "parent.json"
            result = {
                "generation": 2,
                "summary": {"query_count": 1, "strict_pass_count": 0},
                "parent_summary": {"run_error_count": 1, "provider_error_count": 0},
                "parent_summary_path": str(parent_path),
                "strict_pass_delta": 0,
            }
            protocol.write_json(parent_path, {"per_query_feedback": [{
                "run_exit_code": 124, "run_error": "query_wall_timeout_1200s",
                "terminate_reason": "query_wall_timeout_1200s",
            }]})
            self.assertNotIn("parent_comparison_status", protocol.visible_result(result))
            protocol.write_json(parent_path, {"per_query_feedback": [{
                "run_exit_code": 1, "run_error": "worker_crashed",
            }]})
            self.assertEqual(protocol.visible_result(result)["parent_comparison_status"],
                             "infrastructure_invalid_parent_reference_not_performance_baseline")

    def test_initial_snapshot_exposes_compact_parent_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("print('ok')\n", encoding="utf-8")
            batch_path = root / "batch.json"
            protocol.write_json(batch_path, {"query_ids": ["alpha/query1"]})
            parent_result = root / "parent.json"
            protocol.write_json(parent_result, {
                "batch": {"query_ids": ["alpha/query1"]},
                "average_f1": 0.0,
                "per_query_feedback": [{
                    "query_id": "alpha/query1",
                    "terminate_reason": "max_iterations",
                    "llm_call_count": 20,
                    "tool_call_count": 25,
                    "final_answer_nonempty": False,
                    "strict_match_passed": False,
                    "selected_stage": "workflow_control",
                    "selected_signal": "budget_exhausted",
                    "selected_problem_type": "budget_exhausted",
                }],
            })
            campaign_root = root / "campaign"
            protocol.init_campaign(argparse.Namespace(
                campaign_root=campaign_root,
                campaign_id="initial_evidence",
                evolution_batch=batch_path,
                source_root=source,
                parent_result=parent_result,
                max_generations=2,
                max_agent_iterations=0,
                codex="codex",
                meta_profile="test-profile",
                meta_model="test-model",
            ))
            snapshot = protocol.build_snapshot(campaign_root)
            evidence = snapshot["root_node"]["result"]
            self.assertEqual(evidence["query_count"], 1)
            self.assertEqual(evidence["strict_pass_count"], 0)
            self.assertEqual(snapshot["selectable_parents"][0]["node_id"], protocol.ROOT_NODE_ID)

    def test_python_executable_path_preserves_virtualenv_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_python = root / "runtime" / "python3"
            real_python.parent.mkdir()
            real_python.write_text("", encoding="utf-8")
            venv_python = root / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            try:
                os.symlink(real_python, venv_python)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            selected = batch_runner.absolute_python_executable(venv_python)
            self.assertEqual(selected, venv_python.absolute())
            self.assertNotEqual(selected, real_python.absolute())

    def test_intent_schema_requires_change_decision(self) -> None:
        schema = protocol.intent_output_schema()
        self.assertEqual(schema["properties"]["decision"]["enum"], ["change"])

    def test_tree_bound_candidate_result_review_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("import argparse\nargparse.ArgumentParser().parse_args()\n", encoding="utf-8")
            (source / "AGENTS.md").write_text("# synthetic\n", encoding="utf-8")
            batch_path = root / "batch.json"
            protocol.write_json(batch_path, {"batch_id": "synthetic", "query_ids": ["alpha/query1", "beta/query2"]})
            campaign_root = root / "campaign"
            protocol.init_campaign(argparse.Namespace(
                campaign_root=campaign_root,
                campaign_id="synthetic_campaign",
                evolution_batch=batch_path,
                source_root=source,
                parent_result=None,
                max_generations=3,
                max_agent_iterations=20,
                codex="codex",
                meta_profile="test-profile",
                meta_model="test-model",
            ))

            intent = {
                "decision": "change",
                "primary_dimension": "verification",
                "target_component": "answer_verifier",
                "mechanism_key": "evidence_consistency_gate",
                "observed_prior_limitation": "Answers can be returned without checking evidence consistency.",
                "proposed_mechanism": "Add a bounded consistency gate before return_answer.",
                "planned_tool_control_flow_changes": "Check evidence references before final dispatch.",
                "expected_behavioral_change": "Unsupported answers trigger one bounded repair turn.",
                "validation_expectations": ["A trace marker records gate activation."],
                "fallback_or_bounding_rule": "Allow at most one repair turn.",
                "potential_regressions": ["One additional model turn."],
                "novelty_claim": "No prior roadmap node implements this gate.",
                "parent_selection": {
                    "materialization_base_node_id": protocol.ROOT_NODE_ID,
                    "parents": [{
                        "node_id": protocol.ROOT_NODE_ID,
                        "role": "code_base",
                        "use": "Use the frozen baseline as the concrete implementation base.",
                    }],
                    "synthesis_strategy": "Add the new gate to the root execution path.",
                    "selection_rationale": "No prior generation exists in this synthetic campaign.",
                },
            }
            sealed = protocol.seal_intent(campaign_root, intent)
            self.assertEqual(sealed["code_parent_hash"], candidate_workspace.source_tree_hash(source))

            workspace = root / "candidate"
            candidate_workspace.prepare(argparse.Namespace(
                source_root=source,
                output=workspace,
                intent=campaign_root / "generations/gen_001/sealed_intent.json",
                parent_source=None,
                parent_context=None,
                mechanism_contract=None,
            ))
            implementation = workspace / "repo/experiments/evidence_gate.py"
            implementation.write_text("def gate(value):\n    return bool(value)\n", encoding="utf-8")
            candidate_workspace.write_json(
                workspace / "repo/candidate_workspace_report.json",
                {"claim_to_source": [{
                    "claim": "A bounded evidence gate exists.",
                    "path": "experiments/evidence_gate.py",
                    "symbol": "gate",
                    "evidence": "The gate returns an explicit boolean decision.",
                }]},
            )
            self.assertEqual(candidate_workspace.audit(argparse.Namespace(workspace=workspace, python=None)), 0)
            protocol.record_candidate(argparse.Namespace(campaign_root=campaign_root, workspace=workspace))

            summary_path = root / "summary.json"
            protocol.write_json(summary_path, {
                "batch": {"query_ids": ["alpha/query1", "beta/query2"]},
                "average_f1": 0.75,
                "per_query_feedback": [
                    {"query_id": "alpha/query1", "strict_match_passed": True, "final_answer_nonempty": True, "run_error": None},
                    {"query_id": "beta/query2", "strict_match_passed": False, "final_answer_nonempty": True, "run_error": None},
                ],
            })
            protocol.record_result(argparse.Namespace(
                campaign_root=campaign_root,
                batch_summary=summary_path,
                parent_summary=None,
            ))
            recorded = protocol.read_json(campaign_root / "generations/gen_001/result.json")
            self.assertNotIn("per_query_feedback", recorded)
            self.assertEqual(recorded["summary"]["query_count"], 2)
            self.assertEqual(recorded["context_policy"], "compact_result_graph_v1")
            self.assertTrue(summary_path.is_file())
            review = {
                "outcome_label": "effective",
                "source_reuse_recommendation": "eligible_as_base",
                "intent_realization": "The gate was implemented and integrated.",
                "activation_evidence": ["alpha/query1 trace marker"],
                "behavioral_effect": "The finalization path performed a check.",
                "task_effect": "One of two tasks passed.",
                "short_review": "The bounded evidence gate was active and is safe to promote.",
                "failure_mechanism_key": None,
                "evidence_refs": [str(summary_path)],
                "relations_to_prior": [],
                "causal_diagnosis": {
                    "links": {
                        "opportunity": {"status": "positive", "evidence": ["two rows"],
                                        "interpretation": "The gate had an opportunity on both rows."},
                        "integration": {"status": "positive", "evidence": ["trace marker"],
                                        "interpretation": "The execution path included the gate."},
                        "activation": {"status": "positive", "evidence": ["alpha marker"],
                                       "interpretation": "The gate activated on one row."},
                        "delivery": {"status": "unknown", "evidence": [],
                                     "interpretation": "Delivery was not separately measured."},
                        "model_uptake": {"status": "unknown", "evidence": [],
                                         "interpretation": "Uptake was not measured."},
                        "downstream_behavior": {"status": "positive", "evidence": ["repair turn"],
                                                "interpretation": "One repair turn occurred."},
                        "task_effect": {"status": "confounded", "evidence": ["one pass"],
                                        "interpretation": "No matched control isolates task effect."},
                    },
                    "failure_boundary": "model_uptake",
                    "falsified_claims": [],
                    "unsupported_claims": ["The gate caused the pass."],
                    "excluded_equivalence_classes": [],
                    "open_discriminators": ["Whether the repair changed the model's answer."],
                },
                "detailed_analysis": "Synthetic evidence confirms the complete protocol path.",
            }
            record = protocol.append_review(campaign_root, review)
            verification = protocol.verify_roadmap(campaign_root)
            self.assertTrue(verification["ok"])
            self.assertEqual(verification["record_count"], 1)
            self.assertEqual(record["review"]["outcome_label"], "effective")
            self.assertTrue(Path(record["detail_links"]["detailed_review"]).is_file())
            snapshot = protocol.build_snapshot(campaign_root)
            self.assertEqual(snapshot["mechanism_index"]["evidence_consistency_gate"]["attempt_count"], 1)
            state = protocol.read_json(campaign_root / "campaign_state.json")
            self.assertEqual(state["stage"], "ready_for_intent")
            self.assertEqual(state["next_generation"], 2)
            self.assertNotIn("current_parent_node_id", state)
            self.assertEqual(record["parent_edges"][0]["node_id"], protocol.ROOT_NODE_ID)
            # Detailed review and patch artifacts stay archived but never get
            # automatically expanded into the coding meta-agent's parent pack.
            candidate_patch = workspace / "candidate.patch"
            candidate_patch.write_text("RAW_PATCH_SENTINEL", encoding="utf-8")
            evidence = protocol.build_selected_parent_evidence(campaign_root, {
                "generation": 2,
                "parent_selection": {
                    "materialization_base_node_id": protocol.ROOT_NODE_ID,
                    "synthesis_strategy": "Use selected compact cards.",
                    "parents": [{"node_id": record["node_id"], "role": "failure_evidence", "use": "Learn the failure."}],
                },
            })
            rendered = json.dumps(evidence)
            self.assertNotIn("RAW_PATCH_SENTINEL", rendered)
            self.assertNotIn("candidate_patch_excerpt", rendered)
            self.assertNotIn("Synthetic evidence confirms", rendered)
            self.assertNotIn("per_query_feedback", rendered)

    def test_legacy_result_is_filtered_before_review_and_small_under_large_rows(self) -> None:
        intent = {"mechanism_key": "synthetic", "proposed_mechanism": "A short mechanism",
                  "expected_behavioral_change": "A short change", "canonical_json_sha256": "intent-hash"}
        candidate = {"patch_sha256": "patch-hash", "source_tree_sha256": "source-hash",
                     "claim_to_source_valid": True, "repo": "PRIVATE_SOURCE_PATH"}
        result = {
            "generation": 3, "summary": {"query_count": 17, "strict_pass_count": 3, "average_f1": 0.2},
            "per_query_feedback": [{"query_id": "PRIVATE_QUERY_ID", "top_observations": ["RAW_ROW_SENTINEL" * 10000],
                                    "llm_call_count": 50, "tool_call_count": 100}],
        }
        prompt = protocol.build_review_prompt(intent, candidate, result, {"nodes": []})
        self.assertNotIn("PRIVATE_QUERY_ID", prompt)
        self.assertNotIn("PRIVATE_SOURCE_PATH", prompt)
        self.assertNotIn("RAW_ROW_SENTINEL", prompt)
        self.assertLess(len(prompt), 6000)
        payload = json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(set(payload), {"result", "graph"})
        self.assertEqual(payload["result"]["diagnostics"]["tool_call_count"]["total"], 100)
        self.assertEqual(payload["result"]["activation_evidence_status"], "not_supplied_in_compact_result")

    def test_compact_node_preserves_ancestry_without_long_history(self) -> None:
        record = {
            "node_id": "gen_001_test", "generation": 1,
            "parent_edges": [{"node_id": "root_baseline", "role": "code_base", "use": "x" * 10000}],
            "intent": {"mechanism_key": "test", "proposed_mechanism": "m" * 10000},
            "result": {"strict_pass_count": 1, "per_query_feedback": ["RAW_ROW_SENTINEL"]},
            "review": {"short_review": "r" * 10000, "detailed_analysis": "RAW_REVIEW_SENTINEL"},
            "detail_links": {"detailed_review": "archive/review.json", "batch_summary": "archive/raw.json"},
        }
        card = protocol.compact_graph_node(record)
        self.assertLess(len(json.dumps(card)), 1600)
        self.assertEqual(card["parent_edges"], [{"node_id": "root_baseline", "role": "code_base"}])
        self.assertNotIn("RAW_ROW_SENTINEL", json.dumps(card))
        self.assertNotIn("RAW_REVIEW_SENTINEL", json.dumps(card))

    def test_deployed_query_directory_falls_back_to_dab_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dab_root = root / "official"
            expected = dab_root / "query_alpha" / "query2"
            expected.mkdir(parents=True)
            resolved = batch_runner.resolve_query_dir(
                root=root / "candidate_source",
                dab_root=dab_root,
                case={"query_dir": "external/DataAgentBench_sparse/query_alpha/query2"},
                query_id="alpha/query2",
            )
            self.assertEqual(resolved, expected.resolve())


if __name__ == "__main__":
    unittest.main()
