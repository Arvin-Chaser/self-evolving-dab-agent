from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from experiments import run_dab_meta_two_stage_intent_v1 as flow


class TwoStageIntentTest(TestCase):
    def test_not_ready_rejected_before_any_meta_call(self):
        with patch.object(flow.protocol, "load_campaign", return_value=({}, {
                "stage": "intent_sealed", "active_candidate_ref": None})):
            with patch.object(flow.protocol, "invoke_codex_json") as invoke:
                with self.assertRaisesRegex(RuntimeError, "ready_for_intent"):
                    flow.run_once(Path("unused"))
                invoke.assert_not_called()

    def test_generation_ceiling_rejected_before_any_meta_call(self):
        with patch.object(flow.protocol, "load_campaign", return_value=({"max_generations": 3}, {
                "stage": "ready_for_intent", "next_generation": 4,
                "active_candidate_ref": None})):
            with patch.object(flow.protocol, "invoke_codex_json") as invoke:
                with self.assertRaisesRegex(RuntimeError, "ceiling"):
                    flow.run_once(Path("unused"))
                invoke.assert_not_called()
