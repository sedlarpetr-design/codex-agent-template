from unittest import TestCase

from core.envelopes import CriterionResult, Verdict
from core.verifier import readiness_after_cpu


class VerifierReadinessTests(TestCase):
    def setUp(self):
        self.passed = Verdict(
            "task", "step", 1, "SPLNĚNO", "none",
            [CriterionResult("cpu", "met", ["step#0"])],
        )

    def test_not_needed_skips_content_stage(self):
        self.assertEqual(readiness_after_cpu(
            self.passed, content_criteria=[], evidence_records=[]
        ), "not_needed")

    def test_program_failure_skips_content_stage(self):
        failed = Verdict("task", "step", 1, "NESPLNĚNO", "substantive", [])
        self.assertEqual(readiness_after_cpu(
            failed, content_criteria=["meaning"], evidence_records=[]
        ), "skipped_due_to_failure")

    def test_missing_or_mismatched_evidence_waits(self):
        self.assertEqual(readiness_after_cpu(
            self.passed, content_criteria=["meaning"],
            evidence_records=[{
                "task_id": "task", "attempt": 0, "criterion": "meaning",
                "ref": "step#1", "readable": True,
            }],
            task_id="task", attempt=1,
        ), "waiting_for_evidence")

    def test_complete_readable_evidence_is_ready(self):
        self.assertEqual(readiness_after_cpu(
            self.passed, content_criteria=["meaning"],
            evidence_records=[{
                "task_id": "task", "attempt": 1, "criterion": "meaning",
                "ref": "step#1", "readable": True,
            }],
            task_id="task", attempt=1,
            required_evidence={"meaning": ["step#1"]},
        ), "ready")
