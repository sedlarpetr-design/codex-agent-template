import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.envelopes import TaskEnvelope
from specialists.accounting import AccountingSpecialist
from specialists.files import FilesSpecialist
from specialists.web_test import WebTestSpecialist


class SpecialistTests(TestCase):
    def test_files_specialist_validates_csv_and_emits_evidence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("id,datum,castka\n1,2026-10-01,10\n", encoding="utf-8")
            task = TaskEnvelope("t", "s", "files", "inspect", {
                "paths": [str(path)],
                "rules": {"csv": {"required_columns": ["id", "datum", "castka"]}},
            })
            result = FilesSpecialist().work(task)
            self.assertTrue(result.result["files"][0]["parsed_ok"])
            self.assertEqual(result.result["files"][0]["extracted"]["rows"], 1)
            self.assertEqual(result.evidence[0].ref, "s#0")
            self.assertEqual(result.evidence[0].attempt, 1)

    def test_accounting_uses_decimal_and_rounds_each_vat_amount(self):
        task = TaskEnvelope("t", "s", "accounting", "calculate", {
            "rows": [{"desc": "a", "net": "0.05", "vat_rate": "0.21"},
                     {"desc": "b", "net": "0.05", "vat_rate": "0.21"}],
            "currency": "CZK", "rules": {"rounding": "2dp"},
        })
        result = AccountingSpecialist().work(task)
        self.assertEqual(result.result["total_net"], "0.10")
        self.assertEqual(result.result["total_vat"], "0.02")
        self.assertEqual(result.result["total"], "0.12")

    def test_web_adapter_supports_both_engines_and_recycles_contexts(self):
        class FakeLocator:
            async def click(self):
                return None

        class FakePage:
            async def goto(self, _url):
                return None

            def locator(self, _selector):
                return FakeLocator()

            def get_by_text(self, _text, exact=False):
                class Text:
                    async def count(self):
                        return 1
                return Text()

            async def screenshot(self, **_kwargs):
                return None

        class FakeContext:
            async def new_page(self):
                return FakePage()

            async def close(self):
                return None

        class FakeBrowser:
            def __init__(self):
                self.contexts = 0

            async def new_context(self):
                self.contexts += 1
                return FakeContext()

            async def close(self):
                return None

        class FakeBrowserType:
            def __init__(self):
                self.launches = 0

            async def launch(self, **_kwargs):
                self.launches += 1
                return FakeBrowser()

        class FakePlaywright:
            def __init__(self):
                self.chromium = FakeBrowserType()
                self.firefox = FakeBrowserType()

        class FakeManager:
            def __init__(self):
                self.instance = FakePlaywright()

            async def __aenter__(self):
                return self.instance

            async def __aexit__(self, *_args):
                return False

        with TemporaryDirectory() as directory:
            manager = FakeManager()
            task = TaskEnvelope("t", "s", "web_test", "check", {
                "urls": [f"https://example.test/{index}" for index in range(21)],
                "scenario": [{"step_id": "open", "action": "goto", "target": ""}],
            })
            result = asyncio.run(WebTestSpecialist(
                browser="chromium", artifact_dir=directory, recycle_every=20,
                playwright_factory=lambda: manager,
            ).work(task))
            self.assertEqual(result.result["summary"]["passed"], 21)
            self.assertEqual(manager.instance.chromium.launches, 2)
            self.assertEqual(len(result.evidence), 21)
            self.assertEqual(WebTestSpecialist(
                browser="firefox", artifact_dir=directory, playwright_factory=lambda: manager
            ).browser_name, "firefox")
