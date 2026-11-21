"""Offline example of evaluating one project criterion from a local artifact."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


def check_item_count(evidence):
    expected = 3
    report = {
        "scenario_id": "EXAMPLE-COUNT-01",
        "criterion": "Výstup obsahuje právě tři položky.",
        "expected": expected,
        "actual": None,
        "evidence": None,
        "verdict": "NEOVĚŘENO",
        "reason": "Soubor s důkazem chybí.",
    }
    try:
        source = evidence.read_text(encoding="utf-8")
    except FileNotFoundError:
        return report
    except (OSError, UnicodeError):
        report.update(evidence=evidence.name, reason="Soubor s důkazem nelze přečíst.")
        return report

    report["evidence"] = evidence.name
    try:
        data = json.loads(source)
    except ValueError:
        report["reason"] = "Důkaz není platný JSON."
        return report
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        report["reason"] = "Důkaz neobsahuje čitelný seznam položek."
        return report

    actual = len(data["items"])
    report.update(
        actual=actual,
        verdict="SPLNĚNO" if actual == expected else "NESPLNĚNO",
        reason=f"Důkaz obsahuje {actual} položek, očekávaný počet je {expected}.",
    )
    return report


class ProjectVerificationExampleTests(TestCase):
    def check_fixture(self, content):
        with TemporaryDirectory() as work:
            evidence = Path(work) / "output.json"
            if content is not None:
                evidence.write_text(content, encoding="utf-8")
            report = check_item_count(evidence)
        self.assertEqual(set(report), {
            "scenario_id", "criterion", "expected", "actual", "evidence", "verdict", "reason",
        })
        self.assertEqual(report["expected"], 3)
        self.assertTrue(report["reason"])
        return report

    def test_documented_success(self):
        report = self.check_fixture('{"items": ["a", "b", "c"]}')
        self.assertEqual((report["verdict"], report["actual"], report["evidence"]),
                         ("SPLNĚNO", 3, "output.json"))

    def test_documented_violation(self):
        report = self.check_fixture('{"items": ["a", "b"]}')
        self.assertEqual((report["verdict"], report["actual"], report["evidence"]),
                         ("NESPLNĚNO", 2, "output.json"))

    def test_missing_or_insufficient_evidence(self):
        for content, link in ((None, None), ('{}', "output.json"), ('{', "output.json")):
            with self.subTest(content=content):
                report = self.check_fixture(content)
                self.assertEqual((report["verdict"], report["actual"], report["evidence"]),
                                 ("NEOVĚŘENO", None, link))
