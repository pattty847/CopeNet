"""Page observation and model-facing compression for the browser-agent prototype."""

from __future__ import annotations

from textwrap import shorten

from playwright.async_api import Locator

from .models import ElementBox, PageElement, PageState
from .session import BrowserSession


INTERACTIVE_SELECTOR = "a, button, input, textarea, select, [role='button'], [role='link'], [role='tab'], [role='menuitem']"


class PageObserver:
    async def capture(self, session: BrowserSession) -> PageState:
        page = session.page
        session._locators.clear()  # type: ignore[attr-defined]

        title = await page.title()
        url = page.url
        page_text = await page.locator("body").inner_text()
        summary = shorten(" ".join(page_text.split()), width=1200, placeholder=" …")

        ranked: list[tuple[float, PageElement, Locator]] = []
        locators: Locator = page.locator(INTERACTIVE_SELECTOR)
        count = await locators.count()
        for index in range(count):
            locator = locators.nth(index)
            if not await locator.is_visible():
                continue
            element = await self._describe_locator(locator)
            if element is None:
                continue
            ranked.append((element.rank, element, locator))

        ranked.sort(key=lambda item: item[0], reverse=True)
        elements: list[PageElement] = []
        for ordinal, (_, element, locator) in enumerate(ranked, start=1):
            stable = PageElement(
                id=f"e{ordinal}",
                role=element.role,
                text=element.text,
                aria_label=element.aria_label,
                placeholder=element.placeholder,
                enabled=element.enabled,
                visible=element.visible,
                box=element.box,
                rank=element.rank,
            )
            session.bind_locator(stable.id, locator)
            elements.append(stable)
        return PageState(url=url, title=title, page_summary=summary, elements=elements)

    async def _describe_locator(self, locator: Locator) -> PageElement | None:
        tag_name = (await locator.evaluate("el => el.tagName.toLowerCase()")) or "other"
        role_attr = (await locator.get_attribute("role")) or ""
        role = _normalize_role(role_attr or tag_name)
        text = ((await locator.inner_text()) or "").strip()
        aria_label = ((await locator.get_attribute("aria-label")) or "").strip()
        placeholder = ((await locator.get_attribute("placeholder")) or "").strip()
        disabled_attr = await locator.get_attribute("disabled")
        enabled = disabled_attr is None
        box = await locator.bounding_box()
        element_box = None
        if box is not None:
            element_box = ElementBox(
                x=round(box.get("x", 0.0), 1),
                y=round(box.get("y", 0.0), 1),
                width=round(box.get("width", 0.0), 1),
                height=round(box.get("height", 0.0), 1),
            )
        if not any((text, aria_label, placeholder, role)):
            return None
        rank = score_element(role=role, text=text, aria_label=aria_label, placeholder=placeholder, box=element_box)
        return PageElement(
            id="",
            role=role,
            text=text,
            aria_label=aria_label,
            placeholder=placeholder,
            enabled=enabled,
            visible=True,
            box=element_box,
            rank=rank,
        )


def score_element(*, role: str, text: str, aria_label: str, placeholder: str, box: ElementBox | None) -> float:
    label = " ".join(part for part in (text, aria_label, placeholder) if part).strip().lower()
    score = 0.0

    if role in {"input", "textbox", "textarea"}:
        score += 8.0
    if "search" in label:
        score += 12.0
    if placeholder:
        score += 3.0
    if aria_label:
        score += 2.0
    if text.strip():
        score += min(len(text.strip()) / 10.0, 3.0)
    if role in {"button", "link"}:
        score += 2.0
    if box is not None:
        if box.y < 220:
            score += 4.0
        elif box.y < 900:
            score += 1.5
        if box.y > 6000:
            score -= 4.0
    junk_terms = ["skip to content", "back to top", "language", "english", "footnote", "subscribe"]
    if any(term in label for term in junk_terms):
        score -= 10.0
    if not label:
        score -= 3.0
    if role == "link" and len(label) <= 1:
        score -= 2.0
    return score


def _normalize_role(raw: str) -> str:
    value = raw.strip().lower()
    if value in {"button", "link", "input", "textarea", "checkbox", "select", "radio", "tab", "menuitem", "textbox"}:
        return value
    if value == "a":
        return "link"
    if value == "button":
        return "button"
    if value == "input":
        return "input"
    return "other"
