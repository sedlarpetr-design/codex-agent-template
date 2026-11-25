from unittest import TestCase

from core.envelopes import Deliverable, Evidence, ResultEnvelope, TaskEnvelope, Verdict


class EnvelopeTests(TestCase):
    def test_round_trip_preserves_schema_version_and_canonical_evidence(self):
        task = TaskEnvelope("t", "s", "files", "inspect", {"paths": []})
        restored_task = TaskEnvelope.from_dict(task.to_dict())
        self.assertEqual(restored_task.schema_version, "1.0")

        result = ResultEnvelope(
            "t", 1, "s", "files", "ok", {},
            [Evidence("s#0", "calc", "c0", None, "rows=0", 1)],
        )
        restored_result = ResultEnvelope.from_dict(result.to_dict())
        self.assertEqual(restored_result.evidence[0].ref, "s#0")
        self.assertEqual(restored_result.schema_version, "1.0")

    def test_external_envelopes_require_supported_schema_version(self):
        task = TaskEnvelope("t", "s", "files", "inspect", {}).to_dict()
        task.pop("schema_version")
        with self.assertRaises(ValueError):
            TaskEnvelope.from_dict(task)
        task["schema_version"] = "9.0"
        with self.assertRaises(ValueError):
            TaskEnvelope.from_dict(task)

    def test_verdict_and_deliverable_validate_contract_values(self):
        verdict = Verdict(
            "t", "s", 1, "NEOVĚŘENO", "needs_evidence", [],
        )
        self.assertEqual(Verdict.from_dict(verdict.to_dict()).verdict, "NEOVĚŘENO")
        deliverable = Deliverable("ok", {"format": "report", "content": "text"})
        self.assertEqual(Deliverable.from_dict(deliverable.to_dict()).status, "ok")
        with self.assertRaises(ValueError):
            Evidence("s/0", "file", "f", "data.pdf", "", 1)
