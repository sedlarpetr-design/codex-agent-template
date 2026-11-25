"""Triplet regressions for every required verifier criterion."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.verifier import R, build_verdict, verify


CRITERIA = {
    "envelope_ok": "accounting",
    "status_ok": "accounting",
    "evidence_present": "accounting",
    "quotes_in_source": "accounting",
    "steps_passed": "web_test",
    "scenario_covered": "web_test",
    "files_readable": "files",
    "all_inputs_covered": "files",
    "totals_match": "accounting",
    "rows_match_input": "accounting",
    "refs_exist": "synthesis",
    "deliverable_ok": "synthesis",
    "gaps_reported": "synthesis",
}


def fixture(kind: str, criterion: str, scratch: Path | None, mode: str):
    evidence = [{
        "ref": "s#0", "type": "quote", "id": "q1", "uri": None,
        "excerpt": "valid quote", "attempt": 1,
    }]
    out = {
        "schema_version": "1.0", "task_id": "t", "step_id": "s",
        "attempt": 1, "kind": kind, "status": "ok", "notes": "",
        "result": {}, "evidence": evidence,
    }
    ctx = {
        "available_refs": {"s#0"}, "source_text": "valid quote",
        "task_input": {},
    }
    if kind == "web_test":
        step = {"step_id": "w1", "name": "open", "status": "passed",
                "target_observed": True, "evidence_ref": "s#0"}
        out["result"] = {"steps": [step], "summary": {"failed": 0}}
        ctx["task_input"] = {"scenario": [{"step_id": "w1"}]}
        if mode == "violate" and criterion == "steps_passed":
            step.update(status="failed", actual="target absent")
        if mode != "pass" and criterion == "scenario_covered":
            out["result"]["steps"] = []
    elif kind == "files":
        path = scratch / "sample.txt"
        path.write_text("data", encoding="utf-8")
        out["result"] = {"files": [{"path": str(path), "parsed_ok": True, "errors": []}]}
        ctx["task_input"] = {"paths": [str(path)]}
        if mode == "violate" and criterion == "files_readable":
            out["result"]["files"][0]["parsed_ok"] = False
            out["result"]["files"][0]["errors"] = ["parse failure"]
        if mode != "pass" and criterion == "all_inputs_covered":
            out["result"]["files"] = []
    elif kind == "accounting":
        out["result"] = {
            "items": [{"net": "100.00", "vat": "21.00", "amount": "121.00"}],
            "total_net": "100.00", "total_vat": "21.00", "total": "121.00",
        }
        ctx["task_input"] = {"rows": [{"net": "100.00"}]}
        if mode == "violate" and criterion == "totals_match":
            out["result"]["total"] = "120.00"
        if mode == "violate" and criterion == "rows_match_input":
            ctx["task_input"]["rows"].append({"net": "1"})
    elif kind == "synthesis":
        out = {
            "schema_version": "1.0", "status": "ok",
            "deliverable": {"format": "report", "content": "Claim"},
            "claims": [{"text": "Claim", "evidence_refs": ["s#0"]}],
            "conflicts": [], "gaps": [],
        }
        ctx = {"known_refs": {"s#0"}, "unverified_count": 0}
        if mode == "violate" and criterion == "refs_exist":
            out["claims"][0]["evidence_refs"] = ["unknown#9"]
        if mode == "violate" and criterion == "deliverable_ok":
            out.pop("schema_version")
        if mode == "violate" and criterion == "gaps_reported":
            ctx["unverified_count"] = 1
    if mode == "violate":
        if criterion == "envelope_ok":
            out.pop("schema_version")
        elif criterion == "status_ok":
            out["status"] = "failed"
        elif criterion == "evidence_present":
            ctx["available_refs"] = set()
        elif criterion == "quotes_in_source":
            out["evidence"][0]["excerpt"] = "not in source"
    if mode == "missing" and criterion == "quotes_in_source":
        out["evidence"] = [dict(evidence[0], type="file")]
    if mode == "missing" and criterion == "evidence_present":
        out["evidence"] = []
    return out, ctx


def make_test(criterion: str, mode: str):
    kind = CRITERIA[criterion]

    def test(self):
        with TemporaryDirectory() as work:
            out, ctx = fixture(kind, criterion, Path(work), mode)
            if mode == "missing":
                verdict = build_verdict(
                    kind, out, [R(criterion, "met", [])], common=kind != "synthesis"
                )
                self.assertEqual(verdict.verdict, "NEOVĚŘENO")
                return
            verdict = verify(kind, out, ctx, common=kind != "synthesis")
            result = next(item for item in verdict.criteria if item.criterion == criterion)
            if mode == "pass":
                self.assertEqual(result.status, "met")
            else:
                self.assertIn(result.status, {"violated", "unverified"})
                if criterion in {
                    "envelope_ok", "quotes_in_source", "steps_passed", "files_readable",
                    "totals_match", "rows_match_input", "refs_exist", "gaps_reported",
                    "deliverable_ok",
                }:
                    self.assertEqual(result.status, "violated")
                else:
                    self.assertEqual(result.status, "unverified")
    return test


class VerifierCriterionTriplets(TestCase):
    pass


for criterion in CRITERIA:
    for mode in ("pass", "violate", "missing"):
        setattr(
            VerifierCriterionTriplets,
            f"test_{criterion}_{mode}",
            make_test(criterion, mode),
        )
