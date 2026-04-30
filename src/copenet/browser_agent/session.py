"""Playwright-backed browser session for the deterministic browser-agent prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright

from .models import ActionResult, BrowserAction


class BrowserSession:
    def __init__(self, headless: bool = True, artifact_dir: Path | None = None) -> None:
        self._headless = headless
        self._artifact_dir = artifact_dir
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._locators: dict[str, Locator] = {}

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session not started")
        return self._page

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._locators.clear()

    def bind_locator(self, element_id: str, locator: Locator) -> None:
        self._locators[element_id] = locator

    def require_locator(self, element_id: str) -> Locator:
        locator = self._locators.get(element_id)
        if locator is None:
            raise KeyError(f"Unknown element_id: {element_id}")
        return locator

    async def execute(self, action: BrowserAction) -> ActionResult:
        if action.action == "navigate":
            assert action.url is not None
            await self.page.goto(action.url, wait_until="domcontentloaded")
            return ActionResult(ok=True, summary=f"Navigated to {action.url}", url_after=self.page.url)

        if action.action == "click":
            locator = self.require_locator(_required(action.element_id, "element_id"))
            try:
                await locator.click(timeout=5_000)
            except Exception as exc:
                return ActionResult(ok=False, summary=f"Click failed for {action.element_id}", url_after=self.page.url, error=str(exc))
            return ActionResult(ok=True, summary=f"Clicked {action.element_id}", url_after=self.page.url)

        if action.action == "type_text":
            locator = self.require_locator(_required(action.element_id, "element_id"))
            try:
                await locator.fill(action.text or "", timeout=5_000)
            except Exception as exc:
                return ActionResult(ok=False, summary=f"Type failed for {action.element_id}", url_after=self.page.url, error=str(exc))
            return ActionResult(ok=True, summary=f"Typed into {action.element_id}", url_after=self.page.url)

        if action.action == "press_key":
            await self.page.keyboard.press(_required(action.key, "key"))
            return ActionResult(ok=True, summary=f"Pressed key {action.key}", url_after=self.page.url)

        if action.action == "scroll":
            amount = action.scroll if isinstance(action.scroll, int) else 700
            if action.scroll == "up":
                amount = -700
            elif action.scroll == "down":
                amount = 700
            await self.page.mouse.wheel(0, int(amount))
            return ActionResult(ok=True, summary=f"Scrolled {action.scroll}", url_after=self.page.url)

        if action.action == "wait":
            await self.page.wait_for_timeout(action.wait_ms or 1000)
            return ActionResult(ok=True, summary=f"Waited {action.wait_ms or 1000}ms", url_after=self.page.url)

        if action.action == "screenshot":
            screenshot_path = await self.screenshot()
            return ActionResult(
                ok=True,
                summary="Captured screenshot",
                url_after=self.page.url,
                screenshot_path=str(screenshot_path),
            )

        if action.action == "finish":
            return ActionResult(ok=True, summary=action.summary or "Finished task", url_after=self.page.url)

        if action.action == "ask_user":
            return ActionResult(ok=True, summary=action.question or "Need user input", url_after=self.page.url)

        return ActionResult(ok=False, summary=f"Unsupported action: {action.action}", error="unsupported action")

    async def screenshot(self, name: str | None = None) -> Path:
        artifact_dir = self._artifact_dir or Path.cwd() / "tmp" / "browser-agent"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / (name or "screenshot.png")
        await self.page.screenshot(path=str(path), full_page=True)
        return path


def _required(value: Any, label: str) -> Any:
    if value is None:
        raise ValueError(f"Missing required field: {label}")
    return value
