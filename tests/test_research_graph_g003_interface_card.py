import unittest

from experiments.build_research_graph_g003_interface_card import (
    build_card, trace_event_fields,
)


class G003InterfaceCardTests(unittest.TestCase):
    def test_card_binds_reviewed_parent_schema(self):
        card = build_card()
        self.assertEqual(card["existing_task_obligation_binding_fields"], [])
        self.assertIn("validated_args", card["tool_event_fields"]["tool_call_start"])
        self.assertIn("result", card["tool_event_fields"]["tool_call_end"])

    def test_schema_drift_is_rejected(self):
        with self.assertRaises(RuntimeError):
            trace_event_fields("def build_full_execution_trace():\n    return []\n")


if __name__ == "__main__":
    unittest.main()
