from unittest import TestCase

from core.synthesizer import synthesize_or_fallback, verify_synthesis


class SynthesizerTests(TestCase):
    def setUp(self):
        self.approved = [{
            "step_id": "s1", "verdict": "SPLNĚNO",
            "evidence": [{"ref": "s1#0"}],
        }]

    def test_unknown_reference_and_missing_gaps_fall_back_after_repair_budget(self):
        generated = []

        def generate(approved, gaps, feedback):
            generated.append(feedback)
            return {
                "schema_version": "1.0", "status": "ok",
                "deliverable": {"format": "report", "content": "Claim"},
                "claims": [{"text": "Claim", "evidence_refs": ["other#0"]}],
                "conflicts": [], "gaps": [],
            }

        outcome = synthesize_or_fallback(
            generate,
            lambda output: verify_synthesis(output, self.approved, ["step s2 unresolved"]),
            self.approved,
            ["step s2 unresolved"],
            max_repairs=1,
        )
        self.assertEqual(outcome["verdict"], "NEOVĚŘENO")
        self.assertEqual(outcome["mode"], "structured_fallback")
        self.assertEqual(len(generated), 2)
        self.assertTrue(generated[1])

    def test_repaired_synthesis_can_pass(self):
        calls = []

        def generate(approved, gaps, feedback):
            calls.append(feedback)
            return {
                "schema_version": "1.0", "status": "ok",
                "deliverable": {"format": "report", "content": "Supported"},
                "claims": [{"text": "Supported", "evidence_refs": ["s1#0"]}],
                "conflicts": [], "gaps": ["s2 not verified"],
            }

        result = synthesize_or_fallback(
            generate,
            lambda output: verify_synthesis(output, self.approved, ["s2 not verified"]),
            self.approved,
            ["s2 not verified"],
            max_repairs=1,
        )
        self.assertEqual(result["verdict"], "SPLNĚNO")
        self.assertEqual(len(calls), 1)

    def test_nonapproved_sources_and_excess_repairs_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_synthesis({}, [{"verdict": "NEOVĚŘENO", "evidence": []}], [])
        with self.assertRaises(ValueError):
            synthesize_or_fallback(lambda *args: {}, lambda _: {}, self.approved, [], 3)
