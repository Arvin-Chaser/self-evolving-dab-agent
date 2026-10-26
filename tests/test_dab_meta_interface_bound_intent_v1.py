from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from experiments import dab_meta_interface_bound_intent_v1 as flow
from experiments import dab_meta_interface_card_v1 as cards


CAMPAIGN = (Path(__file__).resolve().parents[1] / "experiments" / "dab_evolution_campaigns"
            / "domain17_glm53_unbounded_v1_20260930")
GEN = CAMPAIGN / "generations" / "gen_012"


class InterfaceBoundIntentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = cards.build(CAMPAIGN, "gen_009_observable_tool_progress_contract")
        cls.response = json.loads((GEN / "meta_agent" / "intent_attempt_003" / "intent_response.json")
                                  .read_text(encoding="utf-8"))

    def binding(self):
        card = self.card
        return {
            "card_canonical_sha256": card["canonical_json_sha256"],
            "base_node_id": card["base_node_id"],
            "base_source_tree_sha256": card["base_source_tree_sha256"],
            "runner_source_sha256": card["runner"]["source_sha256"],
            "upstream_source_sha256": card["upstream"]["source_sha256"],
            "overlay_journal_source_sha256": card["current_overlay_journal"]["source_sha256"],
            "inherited_suppression_present": True,
            "tool_result_transport": card["derived_contract"]["upstream_tool_result_transport"],
            "inherited_suppression_treatment": "remove_or_disable_with_tests",
            "inherited_suppression_plan": "Explicitly remove both inherited suppression branches.",
            "tool_message_shape": "modify_existing_tool_message",
            "tool_message_attachment_plan": "Add a delimited advisory to the existing bound message.",
            "tool_message_cardinality_plan": "Keep exactly one role=tool response per call ID.",
        }

    def test_extended_schema_requires_card_facts(self):
        schema = flow.bound_schema(self.card)
        self.assertIn("interface_binding", schema["required"])
        properties = schema["properties"]["interface_binding"]["properties"]
        self.assertEqual(properties["runner_source_sha256"]["const"], self.card["runner"]["source_sha256"])
        self.assertIs(properties["inherited_suppression_present"]["const"], True)

    def test_base_or_interface_mismatch_is_rejected(self):
        response = copy.deepcopy(self.response)
        response["interface_binding"] = self.binding()
        self.assertEqual(flow.validate_bound_response(response, self.card), [])
        response["interface_binding"]["inherited_suppression_present"] = False
        self.assertTrue(any("inherited_suppression_present" in error
                            for error in flow.validate_bound_response(response, self.card)))
        response["interface_binding"] = self.binding()
        response["interface_binding"]["tool_message_shape"] = "add_second_tool_message"
        self.assertTrue(any("Unverified extra tool-message shape" in error
                            for error in flow.validate_bound_response(response, self.card)))
        response["interface_binding"] = self.binding()
        response["parent_selection"]["materialization_base_node_id"] = "gen_011_delivered_repeat_failure_steering"
        self.assertTrue(any("changed the selected code base" in error
                            for error in flow.validate_bound_response(response, self.card)))


if __name__ == "__main__":
    unittest.main()
