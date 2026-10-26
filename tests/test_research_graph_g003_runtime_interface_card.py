import unittest

from experiments.build_research_graph_g003_runtime_interface_card import (
    SOURCE, UPSTREAM, build_card, verify_lifecycle,
)


class G003RuntimeInterfaceCardTests(unittest.TestCase):
    def test_card_separates_trace_from_live_dispatch(self):
        card = build_card()
        self.assertFalse(card["trace_event_lifecycle"]["trace_events_are_live_hooks"])
        self.assertIn("validated_args", card["tool_event_fields"]["tool_call_start"])
        self.assertFalse(card["live_tool_dispatch"]["before_exec_validated_args_available"])
        self.assertNotIn("validated_args", card["live_tool_dispatch"]["before_exec_fields"])
        self.assertEqual(card["live_tool_dispatch"]["hook"],
                         "DataAgentWithSelfObservation._handle_tool_call")
        self.assertFalse(card["live_tool_dispatch"]["parsed_tool_args_match_executed_args_verified"])
        self.assertFalse(card["live_tool_dispatch"]["blocking_response_contract_verified"])

    def test_lifecycle_drift_is_rejected(self):
        agent = SOURCE.read_text(encoding="utf-8")
        upstream = UPSTREAM.read_text(encoding="utf-8")
        verify_lifecycle(agent, upstream)
        with self.assertRaises(RuntimeError):
            verify_lifecycle(agent.replace("row.get(\"val_args\")", "row.get(\"args\")"), upstream)
        with self.assertRaises(RuntimeError):
            verify_lifecycle(agent, upstream.replace("self.tools[tool_name].exec(tool_args)",
                                                       "self.tools[tool_name].exec({})"))


if __name__ == "__main__":
    unittest.main()
