"""Playwright-backed web-test adapter with isolated recycled contexts."""

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from core.envelopes import Evidence, ResultEnvelope, TaskEnvelope


class WebTestSpecialist:
    def __init__(
        self,
        browser: str = "chromium",
        artifact_dir: str | Path | None = None,
        recycle_every: int = 25,
        playwright_factory: Any = None,
    ) -> None:
        if browser not in {"chromium", "firefox"}:
            raise ValueError("browser must be chromium or firefox")
        if type(recycle_every) is not int or not 20 <= recycle_every <= 25:
            raise ValueError("recycle_every must be from 20 to 25")
        if artifact_dir is None:
            raise ValueError("artifact_dir is required for persistent evidence")
        self.browser_name = browser
        self.artifact_dir = Path(artifact_dir)
        self.recycle_every = recycle_every
        self.playwright_factory = playwright_factory

    async def work(self, task: TaskEnvelope) -> ResultEnvelope:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            if self.playwright_factory is None:
                raise RuntimeError("Playwright is required for web_test specialist") from exc
            async_playwright = None
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        urls = task.input.get("urls") or [task.input.get("base_url", "")]
        scenario = task.input.get("scenario", [])
        if not urls or any(not isinstance(url, str) or not url for url in urls):
            return ResultEnvelope(
                task.task_id, task.attempt, task.step_id, task.kind, "needs_input",
                {}, [], notes="input.urls nebo input.base_url je povinné",
            )
        if not scenario:
            scenario = [{"step_id": "open_url", "step": "Otevřít URL",
                         "action": "goto", "target": "", "expect": ""}]
        steps = []
        evidence = []
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        manager = self.playwright_factory() if self.playwright_factory else async_playwright()
        async with manager as playwright:
            browser_type = getattr(playwright, self.browser_name)
            browser = await browser_type.launch(headless=True)
            try:
                for url_index, url in enumerate(urls):
                    if url_index and url_index % self.recycle_every == 0:
                        await browser.close()
                        browser = await browser_type.launch(headless=True)
                    context = await browser.new_context()
                    try:
                        page = await context.new_page()
                        for step_index, definition in enumerate(scenario):
                            step_id = str(definition.get("step_id", step_index))
                            ref_index = len(evidence)
                            ref = f"{task.step_id}#{ref_index}"
                            record = await self._execute(page, url, definition)
                            record.update({
                                "step_id": step_id,
                                "name": definition.get("step", step_id),
                                "expected": definition.get("expect", ""),
                                "url": url,
                                "evidence_ref": ref,
                            })
                            log_path = self.artifact_dir / f"{task.step_id}-{url_index}-{step_index}.json"
                            log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
                            evidence.append(Evidence(
                                ref=ref, type="log", id=f"log-{url_index}-{step_index}",
                                uri=str(log_path), excerpt=json.dumps(record, ensure_ascii=False)[:500],
                                attempt=task.attempt,
                            ))
                            if record["status"] in {"failed", "error"}:
                                screenshot = self.artifact_dir / (
                                    f"{task.step_id}-{url_index}-{step_index}.png"
                                )
                                await page.screenshot(path=str(screenshot), full_page=True)
                                evidence.append(Evidence(
                                    ref=f"{task.step_id}#{len(evidence)}", type="screenshot",
                                    id=f"screenshot-{url_index}-{step_index}", uri=str(screenshot),
                                    excerpt=f"Screenshot after failed step {step_id}",
                                    attempt=task.attempt,
                                ))
                                record["screenshot_ref"] = evidence[-1].ref
                            steps.append(record)
                            counts["passed" if record["status"] == "passed" else
                                   "failed" if record["status"] == "failed" else "skipped"] += 1
                    finally:
                        await context.close()
            finally:
                await browser.close()
        return ResultEnvelope(
            task_id=task.task_id, attempt=task.attempt, step_id=task.step_id, kind=task.kind,
            status="ok", result={"steps": steps, "summary": counts}, evidence=evidence,
        )

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def _execute(self, page: Any, base_url: str, definition: dict[str, Any]) -> dict[str, Any]:
        action = definition.get("action")
        target = definition.get("target", "")
        observed = False
        try:
            if action == "goto":
                await self._maybe_await(page.goto(urljoin(base_url, target)))
            elif action == "click":
                await self._maybe_await(page.locator(target).click())
            elif action == "fill":
                await self._maybe_await(page.locator(target).fill(str(definition.get("value", ""))))
            elif action == "fill_submit":
                for selector, value in definition.get("values", {}).items():
                    await self._maybe_await(page.locator(selector).fill(str(value)))
                form = page.locator(target)
                await self._maybe_await(form.locator('button[type="submit"]').click())
            elif action not in {None, "assert_text"}:
                raise ValueError(f"unsupported browser action: {action}")
            expected = definition.get("expect")
            if expected:
                count = await self._maybe_await(page.get_by_text(str(expected), exact=False).count())
                observed = True
                if not count:
                    return {"status": "failed", "actual": "expected text not found",
                            "target_observed": True, "duration_ms": 0}
            return {"status": "passed", "actual": "expectation observed" if expected else "action completed",
                    "target_observed": observed, "duration_ms": 0}
        except Exception as exc:
            return {"status": "error", "actual": f"{exc.__class__.__name__}: {exc}",
                    "target_observed": False, "duration_ms": 0}
