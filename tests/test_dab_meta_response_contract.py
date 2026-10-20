import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from experiments import dab_roadmap_protocol as protocol


class MetaResponseContractTests(unittest.TestCase):
    @staticmethod
    def _intent(mechanism_key):
        return {
            "decision": "change",
            "primary_dimension": "open research dimension",
            "target_component": "runtime",
            "mechanism_key": mechanism_key,
            "observed_prior_limitation": "The causal boundary remains unresolved.",
            "proposed_mechanism": f"Test {mechanism_key} on the active path.",
            "planned_tool_control_flow_changes": "Make one bounded observable control-flow change.",
            "expected_behavioral_change": "The trace exposes a discriminating behavior.",
            "validation_expectations": ["A deterministic activation marker is present."],
            "fallback_or_bounding_rule": "Fail open after one bounded intervention.",
            "potential_regressions": ["One additional bounded operation."],
            "novelty_claim": "This differs causally from the other proposals.",
            "parent_selection": {
                "materialization_base_node_id": protocol.ROOT_NODE_ID,
                "parents": [{
                    "node_id": protocol.ROOT_NODE_ID,
                    "role": "code_base",
                    "use": "Use the frozen root implementation.",
                }],
                "synthesis_strategy": "Apply only this hypothesis to the root.",
                "selection_rationale": "The root supplies a clean materialization base.",
            },
        }

    def test_complete_schema_is_visible_without_prescribing_a_judgment(self):
        schema = protocol.review_output_schema()
        prompt = protocol.explicit_response_contract("COMPACT_CONTEXT", schema)
        self.assertIn("COMPACT_CONTEXT", prompt)
        rendered_schema = json.loads(prompt.split("```json\n")[-1].split("\n```")[0])
        self.assertEqual(rendered_schema, schema)
        self.assertIn("Independently choose", prompt)
        self.assertIn("Do not invent measurements", prompt)

    def test_attempt_allocation_preserves_prior_response_and_reuses_only_uninvoked_session(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            first = protocol.next_meta_session(campaign, 4, "review")
            first.mkdir(parents=True)
            self.assertEqual(protocol.next_meta_session(campaign, 4, "review"), first)
            old_response = b'{"short_review":"prior failed attempt"}'
            (first / "review_response.json").write_bytes(old_response)
            second = protocol.next_meta_session(campaign, 4, "review")
            self.assertEqual(second.name, "review_attempt_002")
            second.mkdir()
            (second / "invocation.json").write_text('{"status":"failed"}')
            self.assertEqual(protocol.next_meta_session(campaign, 4, "review").name, "review_attempt_003")
            self.assertEqual((first / "review_response.json").read_bytes(), old_response)

    def test_incomplete_successful_cli_response_fails_closed_without_synthesized_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            schema_path = session / "output_schema.json"
            protocol.write_json(schema_path, protocol.review_output_schema())
            response = {"short_review": "Unknown activation", "detailed_analysis": "No measurements",
                        "source_reuse_recommendation": "evidence_only"}

            def fake_run(*args, **kwargs):
                self.assertIn('"outcome_label"', kwargs["prompt"])
                protocol.write_json(session / "review_response.json", response)
                return SimpleNamespace(returncode=0)

            with patch.object(protocol, "resolve_codex", return_value="codex"), \
                    patch.object(protocol, "meta_environment", return_value={}), \
                    patch.object(protocol, "run_logged_command", side_effect=fake_run):
                with self.assertRaisesRegex(SystemExit, "omitted required fields"):
                    protocol.invoke_codex_json(campaign={"meta_agent": {}}, session=session,
                                               prompt="COMPACT_CONTEXT", schema_path=schema_path,
                                               output_name="review_response.json")
            self.assertEqual(protocol.read_json(session / "review_response.json"), response)
            self.assertTrue(protocol.validate_review(response, set()))
            self.assertTrue((session / "request_prompt.md").exists())

    def test_diagnosis_schema_has_complete_chain_and_no_patch_recommendation(self):
        schema = protocol.review_output_schema()
        self.assertIn("causal_diagnosis", schema["required"])
        self.assertNotIn("next_recommendation", schema["properties"])
        links = schema["properties"]["causal_diagnosis"]["properties"]["links"]
        self.assertEqual(set(links["required"]), set(protocol.CAUSAL_LINKS))
        prompt = protocol.build_review_prompt({}, {}, {}, {})
        self.assertIn("fact-and-constraint diagnosis only", prompt)
        self.assertIn("Do not propose a next", prompt)

    def test_competing_intents_are_validated_then_selected_without_rewriting(self):
        pool = {"hypotheses": [{
            "hypothesis_id": f"h{index}",
            "causal_hypothesis": f"Causal explanation {index}",
            "discriminating_prediction": f"Prediction {index}",
            "intent": self._intent(f"mechanism_{index}"),
        } for index in range(1, 4)]}
        snapshot = {
            "selectable_parents": [{"node_id": protocol.ROOT_NODE_ID}],
            "selection_policy": {},
        }
        self.assertEqual(protocol.validate_hypothesis_pool(pool, snapshot), [])
        selection = {
            "selected_hypothesis_id": "h2",
            "comparative_assessment": [{
                "hypothesis_id": f"h{index}",
                "decision": "selected" if index == 2 else "rejected",
                "evidence_fit": "Grounded in the compact evidence.",
                "discriminating_value": "Produces an observable distinction.",
                "implementation_risk": "Bounded but nonzero.",
                "reason": "Best tradeoff." if index == 2 else "Weaker discriminator.",
            } for index in range(1, 4)],
            "selection_rationale": "h2 has the strongest discriminator without inventing a new intent.",
        }
        self.assertEqual(protocol.validate_intent_selection(selection, pool), [])
        selection["selected_hypothesis_id"] = "h4"
        self.assertTrue(protocol.validate_intent_selection(selection, pool))

    def test_invoke_intent_archives_pool_and_independent_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            runner = source / "experiments" / "run_dab_tool_agent.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("print('ok')\n", encoding="utf-8")
            batch = root / "batch.json"
            protocol.write_json(batch, {"query_ids": ["alpha/query1"]})
            campaign_root = root / "campaign"
            protocol.init_campaign(SimpleNamespace(
                campaign_root=campaign_root,
                campaign_id="competition_test",
                evolution_batch=batch,
                source_root=source,
                parent_result=None,
                max_generations=3,
                max_agent_iterations=0,
                codex="codex",
                meta_profile="test",
                meta_model="test",
            ))
            pool = {"hypotheses": [{
                "hypothesis_id": f"h{index}",
                "causal_hypothesis": f"Causal explanation {index}",
                "discriminating_prediction": f"Prediction {index}",
                "intent": self._intent(f"mechanism_{index}"),
            } for index in range(1, 4)]}
            selection = {
                "selected_hypothesis_id": "h3",
                "comparative_assessment": [{
                    "hypothesis_id": f"h{index}",
                    "decision": "selected" if index == 3 else "rejected",
                    "evidence_fit": "Fits compact evidence.",
                    "discriminating_value": "Has an observable prediction.",
                    "implementation_risk": "Bounded risk.",
                    "reason": "Selected." if index == 3 else f"Rejected h{index} for weaker reach.",
                } for index in range(1, 4)],
                "selection_rationale": "h3 best separates the open explanations.",
            }

            def fake_invoke(*, session, output_name, **kwargs):
                value = pool if output_name == "hypothesis_pool.json" else selection
                protocol.write_json(session / output_name, value)
                return value

            with patch.object(protocol, "invoke_codex_json", side_effect=fake_invoke):
                self.assertEqual(protocol.invoke_intent(SimpleNamespace(
                    campaign_root=campaign_root, prepare_only=False,
                )), 0)

            state = protocol.read_json(campaign_root / "campaign_state.json")
            sealed = protocol.read_json(Path(state["active_intent"]))
            binding = sealed["competition_binding"]
            self.assertEqual(sealed["mechanism_key"], "mechanism_3")
            self.assertEqual(binding["selected_hypothesis_id"], "h3")
            self.assertEqual(len(binding["alternatives"]), 3)
            self.assertEqual(
                [item["decision"] for item in binding["alternatives"]],
                ["rejected", "rejected", "selected"],
            )
            self.assertTrue(Path(binding["hypothesis_pool_path"]).is_file())
            self.assertTrue(Path(binding["selection_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
