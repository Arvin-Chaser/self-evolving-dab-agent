from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import dab_research_route as route
from experiments import replay_dab_research_route as replay
from experiments import run_dab_research_workflow as workflow


def fixture() -> dict:
    value = {"schema": route.SCHEMA, "through_generation": 1,
        "nodes": [{"id": "h1", "kind": "hypothesis", "generation": 1, "content": {}, "state": "unassessed"},
                  {"id": "e1", "kind": "evidence", "generation": 1,
                   "content": {"observations": {"opportunity": 0}}}],
        "edges": [{"source": "e1", "target": "h1", "relation": "challenges"}],
        "code_bases": [{"node_id": "root_baseline", "source_available_now": True}],
        "compact_nodes": [{"node_id": "g1", "intent": {"mechanism_key": "old"}}], "limits": []}
    value["snapshot_sha256"] = route.digest(value)
    return value


def update(view: dict, state: str = "challenged_in_scope") -> dict:
    judgment = {"status": "unknown", "reason": "not measured", "evidence_ids": ["e1"]}
    return {"snapshot_sha256": view["snapshot_sha256"], "new_nodes": [], "new_edges": [],
        "assessments": [{"hypothesis_id": "h1", "state": state, "scope": "one measured query",
            "evidence_ids": ["e1"], "remaining_questions": ["Could another signature match?"],
            "causal_chain": {name: copy.deepcopy(judgment) for name in route.CAUSAL_CHAIN_FIELDS},
            "validity": {"confounding": copy.deepcopy(judgment)},
            "facets": []}]}


def decision(view: dict) -> dict:
    option = {"id": "a", "question": "Does the target recur?", "hypothesis": "Possibly",
              "evidence_ids": ["e1"], "context_ids": ["h1", "e1"],
              "competing_explanation": "No real opportunity",
              "opportunity_status": "unknown", "scope_and_coverage": "not measured",
              "discriminating_observation": "count target events", "falsification_condition": "zero events",
              "expected_task_value": "avoid ineffective patches"}
    return {"snapshot_sha256": view["snapshot_sha256"], "options": [option, {**option, "id": "b"}],
            "selected_option_id": "a", "decision": "probe", "selection_reason": "measure premise",
            "research_parents": [{"node_id": "e1", "role": "failure_evidence", "use": "motivation"}],
            "code_parent": None, "code_parent_reason": "no source change",
            "experiment": {key: "measure before implementing" for key in (
                "design", "observable_prediction", "negative_control", "opportunity_gate", "resource_budget")},
            "read_node_ids": ["e1", "h1"], "unresolved_questions": ["actual frequency"]}


def navigation(view: dict) -> dict:
    choice = decision(view)
    assessment = {"question_origin": "missing_opportunity", "source_node_ids": ["h1"],
                  "origin_evidence_ids": ["e1"], "impact": "high", "evidence_strength": "unknown",
                  "discrimination": "strong", "cost": "low", "novelty": "new",
                  "readiness": "probe_first", "opportunity_measurement": None,
                  "rank_reason": "Measure whether the target occurs"}
    return {"snapshot_sha256": view["snapshot_sha256"], "decision": choice,
            "priority_order": ["a", "b"],
            "option_assessments": [{**assessment, "option_id": "a"},
                                   {**assessment, "option_id": "b", "rank_reason": "Less direct"}],
            "selection_rule": route.PRIORITY_POLICY,
            "stop_condition": "Stop if both questions lack measurable targets"}


class ResearchRouteTests(unittest.TestCase):
    def test_review_requires_causal_chain_validity_and_cited_scope(self):
        view = fixture()
        bad = update(view)
        del bad["assessments"][0]["causal_chain"]["behavior"]
        with self.assertRaises(ValueError):
            route.apply_update(view, bad)
        self.assertEqual(view["nodes"][0]["state"], "unassessed")
        bad = update(view)
        del bad["assessments"][0]["validity"]["confounding"]
        with self.assertRaises(ValueError):
            route.apply_update(view, bad)

    def test_open_facets_accept_new_names_and_reject_duplicates(self):
        view = fixture()
        value = update(view)
        value["assessments"][0]["facets"] = [
            {"name": "tool_semantics", "status": "mixed", "reason": "two signatures",
             "evidence_ids": ["e1"]},
            {"name": "cross_turn_credit_assignment", "status": "unknown",
             "reason": "trace lacks binding", "evidence_ids": ["e1"]},
        ]
        reviewed = route.apply_update(view, value)
        self.assertEqual(len(reviewed["nodes"][0]["latest_assessment"]["facets"]), 2)
        value["assessments"][0]["facets"].append(
            {"name": "Tool_Semantics", "status": "supported", "reason": "duplicate",
             "evidence_ids": ["e1"]})
        with self.assertRaises(ValueError):
            route.apply_update(view, value)

    def test_agenda_uses_causal_chain_and_open_facets(self):
        view = route.apply_update(fixture(), update(fixture()))
        questions = route.research_agenda(view)
        self.assertTrue(any(item["origin"] == "missing_opportunity" for item in questions))
        self.assertTrue(any("behavior" in item["question"] for item in questions))

    def test_review_context_is_local_but_snapshot_bound(self):
        view = fixture()
        context = route.review_context(view, ["h1"])
        self.assertEqual(context["snapshot_sha256"], view["snapshot_sha256"])
        self.assertEqual(context["review_hypothesis_ids"], ["h1"])
        self.assertEqual({node["id"] for node in context["nodes"]}, {"h1", "e1"})
        with self.assertRaises(ValueError):
            route.review_context(view, ["e1"])

    def test_review_prompt_states_new_nodes_bind_current_boundary(self):
        prompt = route.review_prompt(fixture(), ["h1"])
        self.assertIn("generation must equal through_generation", prompt)
        self.assertIn("evidence --supports/challenges--> hypothesis", prompt)

    def test_model_json_parser_allows_only_a_single_json_fence(self):
        self.assertEqual(route.parse_model_json("```json\n{\"a\": 1}\n```"), {"a": 1})
        with self.assertRaises(ValueError):
            route.parse_model_json("before\n```json\n{}\n```")

    def test_new_evidence_cannot_be_invented_by_reviewer(self):
        view = fixture()
        bad = update(view)
        bad["new_nodes"] = [{"id": "fake", "kind": "evidence", "generation": 1,
                             "content": {}, "evidence_ids": ["e1"]}]
        with self.assertRaises(ValueError):
            route.apply_update(view, bad)

    def test_new_question_requires_origin_evidence_and_typed_link(self):
        view = fixture()
        base = update(view)
        node = {"id": "p2", "kind": "problem", "generation": 1,
                "content": {"statement": "Unexplained residual", "prediction": "It recurs",
                            "falsification_condition": "No recurrence", "scope": "measured rows"},
                "evidence_ids": ["e1"], "question_origin": "residual_failure",
                "origin_reason": "The prior evidence leaves a residual"}
        base["new_nodes"] = [node]
        with self.assertRaises(ValueError):
            route.apply_update(view, base)
        hypothesis = {**node, "id": "h2", "kind": "hypothesis",
                      "question_origin": "competing_explanation"}
        base["new_nodes"] = [node, hypothesis]
        base["new_edges"] = [{"source": "h2", "target": "p2", "relation": "explains",
                              "evidence_ids": ["e1"], "reason": "Candidate explanation"}]
        result = route.apply_update(view, base)
        self.assertEqual(next(item for item in result["nodes"] if item["id"] == "h2")["state"], "open")

    def test_future_or_non_evidence_citations_rejected(self):
        view = fixture()
        for ref in ("e2", "h1"):
            bad = update(view)
            bad["assessments"][0]["evidence_ids"] = [ref]
            with self.assertRaises(ValueError):
                route.apply_update(view, bad)

    def test_revised_state_keeps_original_and_event_chain(self):
        view = fixture()
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "events.jsonl"
            next_view = route.append_update(log, view, update(view))
            latest = route.append_update(log, next_view, update(next_view, "mixed"))
            self.assertEqual(view["nodes"][0]["state"], "unassessed")
            self.assertEqual(latest["nodes"][0]["state"], "mixed")
            events = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(events[1]["previous_sha256"], events[0]["event_sha256"])
            with self.assertRaises(ValueError):
                route.append_update(log, view, update(view))

    def test_snapshot_tampering_rejected(self):
        view = fixture()
        view["nodes"][0]["state"] = "supported_in_scope"
        with self.assertRaises(ValueError):
            route.retrieve(view, ["h1"])

    def test_implementation_requires_measured_opportunity_and_source(self):
        view = fixture()
        value = decision(view)
        route.validate_decision(value, view)
        value.update({"decision": "implement", "code_parent": "root_baseline"})
        with self.assertRaises(ValueError):
            route.validate_decision(value, view)
        value["options"][0]["opportunity_status"] = "measured"
        route.validate_decision(value, view)
        value["code_parent"] = "deleted_gen8"
        with self.assertRaises(ValueError):
            route.validate_decision(value, view)

    def test_duplicate_options_and_unread_citations_rejected(self):
        view = fixture()
        value = decision(view)
        value["options"][1]["id"] = "a"
        with self.assertRaises(ValueError):
            route.validate_decision(value, view)

    def test_read_set_can_cover_multiple_options(self):
        view = fixture()
        value = decision(view)
        value["read_node_ids"] = ["e1", "h1"] * 10
        route.validate_decision(value, view)
        value = decision(view)
        value["read_node_ids"] = ["e1"]
        with self.assertRaises(ValueError):
            route.validate_decision(value, view)

    def test_context_can_reference_hypothesis_but_measurements_must_be_evidence(self):
        view = fixture()
        value = decision(view)
        route.validate_decision(value, view)
        value["options"][0]["evidence_ids"] = ["h1"]
        with self.assertRaises(ValueError):
            route.validate_decision(value, view)

    def test_navigation_ranks_all_options_and_requires_exact_positive_opportunity(self):
        view = fixture()
        plan = navigation(view)
        route.validate_navigation(plan, view)
        plan["priority_order"] = ["b", "a"]
        with self.assertRaises(ValueError):
            route.validate_navigation(plan, view)
        plan["priority_order"] = ["a", "b"]
        plan["decision"].update({"decision": "implement", "code_parent": "root_baseline"})
        plan["decision"]["options"][0]["opportunity_status"] = "measured"
        plan["option_assessments"][0]["readiness"] = "implement_ready"
        with self.assertRaises(ValueError):
            route.validate_navigation(plan, view)
        plan["option_assessments"][0]["opportunity_measurement"] = {
            "evidence_id": "e1", "count_pointer": "/content/observations/opportunity",
            "count": 1, "coverage_pointer": "/content/observations/coverage", "coverage": 3}
        view["nodes"][1]["content"]["observations"]["coverage"] = 3
        view["snapshot_sha256"] = route.digest({k: v for k, v in view.items() if k != "snapshot_sha256"})
        plan["snapshot_sha256"] = plan["decision"]["snapshot_sha256"] = view["snapshot_sha256"]
        with self.assertRaises(ValueError):
            route.validate_navigation(plan, view)
        view["nodes"][1]["content"]["observations"]["opportunity"] = 1
        view["snapshot_sha256"] = route.digest({k: v for k, v in view.items() if k != "snapshot_sha256"})
        plan["snapshot_sha256"] = plan["decision"]["snapshot_sha256"] = view["snapshot_sha256"]
        route.validate_navigation(plan, view)

    def test_reviewed_hypothesis_carries_forward_without_rewriting_history(self):
        old = fixture()
        old["historical_head"] = "head1"
        old["snapshot_sha256"] = route.digest({k: v for k, v in old.items() if k != "snapshot_sha256"})
        reviewed = route.apply_update(old, update(old))
        newer = copy.deepcopy(old)
        newer["through_generation"] = 2
        newer["historical_head"] = "head2"
        newer["nodes"].append({"id": "e2", "kind": "evidence", "generation": 2,
                               "content": {"observations": {"opportunity": 2}}})
        newer["snapshot_sha256"] = route.digest({k: v for k, v in newer.items() if k != "snapshot_sha256"})
        with patch.object(route, "history", side_effect=lambda _root, through: copy.deepcopy(
                old if through == 1 else newer)):
            carried = route.advance_history(Path("campaign"), reviewed, 2)
            self.assertEqual(carried["nodes"][0]["state"], "challenged_in_scope")
            self.assertIn("latest_assessment", carried["nodes"][0])
            self.assertEqual(carried["nodes"][-1]["id"], "e2")
            tampered = copy.deepcopy(reviewed)
            tampered["nodes"][1]["content"]["observations"]["opportunity"] = 99
            tampered["snapshot_sha256"] = route.digest({k: v for k, v in tampered.items()
                                                          if k != "snapshot_sha256"})
            with self.assertRaises(ValueError):
                route.advance_history(Path("campaign"), tampered, 2)

    def test_probe_import_reads_hash_bound_scalar_measurements(self):
        view = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact = root / "probe.json"
            artifact.write_text(json.dumps({"activation": 4, "coverage": 12, "raw_answer": "secret"}))
            record = {"snapshot_sha256": view["snapshot_sha256"], "probe_id": "probe_one",
                      "generation": 1, "hypothesis_ids": ["h1"],
                      "design": {"question": "Does it fire?", "intervention": "instrument only",
                          "observable_prediction": "positive activation", "negative_control": "easy rows",
                          "falsification_condition": "zero activation", "resource_budget": "one trace pass",
                          "scope": "internal evolution split"},
                      "artifacts": [{"path": "probe.json", "sha256": route.protocol.sha256_file(artifact),
                          "measurements": [{"name": "activation", "json_pointer": "/activation"},
                                           {"name": "coverage", "json_pointer": "/coverage"}]}]}
            imported = route.import_probe(view, root, record)
            evidence = next(node for node in imported["nodes"] if node["id"] == "evidence:probe_one")
            self.assertEqual(evidence["content"]["observations"]["probe_measurements"],
                             {"activation": 4, "coverage": 12})
            self.assertNotIn("secret", json.dumps(evidence))
            record["artifacts"][0]["measurements"][0]["json_pointer"] = "/raw_answer"
            with self.assertRaises(ValueError):
                route.import_probe(view, root, record)

    def test_row_projection_blocks_heldout_and_answers(self):
        row = {"query_id": "a/query1", "strict_match_passed": True, "tool_call_count": 2,
               "final_answer": "secret", "answer_f1": 1, "answer_quality": {"ground_truth": "secret"}}
        view = route.row_view({"per_query_feedback": [row]}, {"a/query1"})
        self.assertNotIn("secret", json.dumps(view))
        self.assertNotIn("f1", json.dumps(view))
        with self.assertRaises(ValueError):
            route.row_view({"per_query_feedback": [row]}, {"a/query3"})

    def test_flat_route_node_evidence_identical(self):
        arms = workflow.contexts(fixture())
        self.assertEqual(arms["flat"]["history"], arms["route"]["history"])
        self.assertNotIn("relations", arms["flat"])
        self.assertIn("relations", arms["route"])

    def test_source_provenance_rejects_outside_campaign(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "campaign"
            root.mkdir()
            external = Path(temp) / "external.json"
            external.write_text("{}")
            with self.assertRaises(ValueError):
                route.artifact(root, external, "/", {})

    def test_outcome_reveal_blocked_before_predictions(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            route.new_json(out / "manifest.json", {"cases": [{"session": "one"}]})
            with self.assertRaises(ValueError):
                replay.reveal(out, out)

    def test_request_failure_records_no_automatic_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            session = out / "one"
            session.mkdir()
            (session / "request.txt").write_text("prompt")
            case = {"session": "one", "request_sha256": route.protocol.sha256_file(session / "request.txt")}
            with patch.object(replay, "_request", side_effect=RuntimeError("failure")) as call:
                result = replay.run_case(out, case, {"output_token_cap": 100})
                self.assertEqual(call.call_count, 1)
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["automatic_retry"])


if __name__ == "__main__":
    unittest.main()
