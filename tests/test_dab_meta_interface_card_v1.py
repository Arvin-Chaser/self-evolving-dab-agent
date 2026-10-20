from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from experiments import dab_meta_interface_card_v1 as card
from experiments import dab_roadmap_protocol as protocol


CAMPAIGN = (Path(__file__).resolve().parents[1] / "experiments" / "dab_evolution_campaigns"
            / "domain17_glm53_unbounded_v1_20260930")


class InterfaceCardTest(unittest.TestCase):
    def test_ast_facts_do_not_confuse_message_append_with_return(self):
        tree = ast.parse('''
def _handle_tool_call(self, tool_call):
    self.messages.append({"role": "tool", "content": "failure"})
    return
''')
        fact = card.handler_cards(tree, {"_handle_tool_call"})["_handle_tool_call"][0]
        self.assertEqual(fact["role_tool_message_append_lines"], [3])
        self.assertEqual(fact["return_statements"], [{"line": 4, "has_value": False}])

    def test_nested_proxy_return_does_not_become_handler_return(self):
        tree = ast.parse('''
def _handle_tool_call(self, tool_call):
    class Proxy:
        def model_dump(self):
            return {"id": "synthetic"}
    return
''')
        fact = card.handler_cards(tree, {"_handle_tool_call"})["_handle_tool_call"][0]
        self.assertEqual(fact["return_statements"], [{"line": 6, "has_value": False}])

    def test_real_selected_base_exposes_suppression_and_message_transport(self):
        result = card.build(CAMPAIGN, "gen_009_observable_tool_progress_contract")
        self.assertEqual(result["base_source_tree_sha256"],
                         "4c20f4678f83cb3a7ee5ffcc065732619812417a143ed77c0757da085d053012")
        self.assertTrue(result["derived_contract"]["selected_base_has_suppressed_tool_message_path"])
        self.assertTrue(result["current_overlay_journal"]["tool_handler_call_lines"])
        self.assertTrue(result["current_overlay_journal"]["cursor_advance_lines"])
        self.assertIn("second role=tool message", result["derived_contract"]
                      ["separate_advisory_tool_message_risk"])
        self.assertTrue(result["upstream"]["handlers"]["_handle_tool_call"][0]
                        ["role_tool_message_append_lines"])
        self.assertNotIn(1251, [item["line"] for item in result["runner"]["handlers"]
                          ["_handle_tool_call_with_recovery"][0]["return_statements"]])
        self.assertEqual(result["stock_tool_specs"]["QueryDBTool"]["argument_schema"]
                         ["properties"], {"db_name": "string", "query": "string"})
        self.assertEqual(result["canonical_json_sha256"],
                         protocol.canonical_hash({k: v for k, v in result.items()
                                                  if k != "canonical_json_sha256"}))
        serialized = json.dumps(result)
        self.assertNotIn("query_ids", serialized)
        self.assertNotIn("raw_trace", serialized)
        self.assertNotIn("candidate.patch", serialized)


if __name__ == "__main__":
    unittest.main()
