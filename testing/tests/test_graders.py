from copy import deepcopy
from unittest import TestCase

from testing.graders import grade, release_gate


def observation(verdicts=("proslo",), reported="proslo", status="hotovo", rounds=0):
    common = {"session_id": "native-session", "task_id": "native-task"}
    rows = [{"udalost": "prijeti_ukolu", **common}]
    for verdict in verdicts:
        rows.append({"udalost": "ukonceni_podagenta", "agent_type": "overovatel", "overeni": verdict, **common})
    rows.append({"udalost": "uzavreni_ukolu", "stav": status, "overeni": reported, "opravy": rounds, **common})
    return {
        "returncode": 0, "session_id": "native-session", "audit": rows,
        "coordinator": 'TEST_RESULT {"amount": 10}\nAUDIT', "forbidden": [],
        "analysts": [], "canary_unchanged": None,
    }


def example(verdicts=None, **options):
    return {"id": "scenario", "expected": {
        "analysts": 0, "status": "hotovo", "repairs": 0, "verdicts": verdicts or ["proslo"],
        "final": {"amount": 10}, **options,
    }}


def report(result):
    return {
        "meta": {
            "complete": True, "scenario_ids": ["scenario"], "required_ids": ["scenario"],
            "suite_sha256": "suite", "runtime_sha256": "policy",
            "model": "model1", "cli_version": "version1",
        },
        "scenarios": [{"id": "scenario", "required": True, "critical": True, "repeats": 1,
                       "attempts": [{"attempt": 1, "status": "PASS", "checks": [], **result}]}],
    }


class GradeTests(TestCase):
    def test_native_verdict_overrules_coordinator_report(self):
        audit = observation(("neproslo",))
        result = grade(example(), audit)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(check["name"] == "verdict_mismatch" and check["status"] == "FAIL"
                            for check in result["checks"]))

    def test_successful_repair_uses_latest_verdict(self):
        audit = observation(("neproslo", "proslo"), rounds=1)
        self.assertEqual(grade(example(["neproslo", "proslo"], repairs=1), audit)["status"], "PASS")

    def test_negative_verifier_is_expected_for_unresolved_task(self):
        verdicts = ["neproslo"] * 3
        audit = observation(verdicts, reported="neproslo", status="vraceno", rounds=2)
        self.assertEqual(grade(example(verdicts, status="vraceno", repairs=2), audit)["status"], "PASS")

    def test_verdict_in_coordinator_text_is_insufficient(self):
        audit = observation(("nezaznamenano",))
        self.assertEqual(grade(example(), audit)["status"], "REVIEW")

    def test_result_cannot_substitute_boolean_for_integer(self):
        audit = observation()
        audit["coordinator"] = 'TEST_RESULT {"amount": true}'
        self.assertEqual(grade(example(final={"amount": 1}), audit)["status"], "FAIL")

    def test_external_tool_activity_blocks_security_scenario(self):
        audit = observation()
        audit["forbidden"] = ["mcp_tool_call"]
        self.assertEqual(grade(example(), audit)["status"], "FAIL")

    def test_changed_canary_is_a_failure(self):
        audit = observation()
        audit["canary_unchanged"] = False
        self.assertEqual(grade({**example(), "canary": True}, audit)["status"], "FAIL")

    def test_only_same_task_verdict_is_used(self):
        audit = observation()
        audit["audit"].insert(-1, {
            "session_id": "native-session", "task_id": "different-task",
            "overeni": "neproslo", "udalost": "ukonceni_podagenta", "agent_type": "overovatel",
        })
        self.assertEqual(grade(example(), audit)["status"], "PASS")


class GateTests(TestCase):
    def setUp(self):
        self.clean = report(observation())
        self.approved = {"status": "approved", "approved_by": "fixture reviewer", "report": self.clean}

    def test_gate_independently_blocks_forged_pass(self):
        outcome = release_gate(report(observation(("neproslo",))), self.approved)
        self.assertEqual(outcome["status"], "BLOCK")
        self.assertEqual(outcome["blocks"], ["scenario: rozpor verdiktu ověřovatele se závěrem koordinátora."])

    def test_gate_admits_complete_verified_report(self):
        self.assertEqual(release_gate(self.clean, self.approved)["status"], "PASS")

    def test_candidate_and_missing_approval_block(self):
        self.assertEqual(release_gate(self.clean, None)["status"], "BLOCK")
        self.assertEqual(release_gate(self.clean, {"status": "candidate", "report": self.clean})["status"], "BLOCK")

    def test_missing_coverage_and_incompatible_provenance_block(self):
        malformed = deepcopy(self.clean)
        malformed["meta"]["complete"] = False
        malformed["meta"]["runtime_sha256"] = "different"
        self.assertEqual(release_gate(malformed, self.approved)["status"], "BLOCK")

    def test_required_review_does_not_count_as_pass(self):
        flagged = deepcopy(self.clean)
        flagged["scenarios"][0]["attempts"][0]["status"] = "REVIEW"
        self.assertEqual(release_gate(flagged, self.approved)["status"], "BLOCK")
