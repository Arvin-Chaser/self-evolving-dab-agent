import unittest
from experiments import intent_candidate_workspace as workspace


class CandidateClaimBindingTests(unittest.TestCase):
    def setUp(self):
        self.implementation = "experiments/run_dab_tool_agent.py"
        self.test = "tests/test_dab_turn_checkpoints.py"
        self.changed = [self.implementation, self.test]

    def claim(self, path):
        return {"claim": "A source-backed claim", "path": path,
                "symbol": "real_symbol", "evidence": "Bound to this changed source"}

    def valid(self, claims):
        return workspace.valid_claim_source_bindings(claims, self.changed, [self.implementation])

    def test_implementation_plus_changed_test_claim_is_accepted(self):
        self.assertTrue(self.valid([self.claim(self.implementation), self.claim(self.test)]))

    def test_test_only_claim_does_not_prove_implementation(self):
        self.assertFalse(self.valid([self.claim(self.test)]))

    def test_unchanged_or_forbidden_file_claim_is_rejected(self):
        for path in ("tests/not_changed.py", "logs/formal_trace.json"):
            self.assertFalse(self.valid([self.claim(self.implementation), self.claim(path)]))

    def test_empty_or_missing_field_claim_is_rejected(self):
        self.assertFalse(self.valid([]))
        claim = self.claim(self.implementation)
        del claim["evidence"]
        self.assertFalse(self.valid([claim]))


if __name__ == "__main__":
    unittest.main()
