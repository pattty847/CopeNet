"""Structured models for the deterministic browser-agent prototype."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


BrowserActionName = Literal[
    "navigate",
    "click",
    "type_text",
    "press_key",
    "scroll",
    "wait",
    "screenshot",
    "finish",
    "ask_user",
]
ElementRole = Literal[
    "button",
    "link",
    "input",
    "textarea",
    "checkbox",
    "select",
    "radio",
    "tab",
    "menuitem",
    "textbox",
    "other",
]


@dataclass(frozen=True)
class ElementBox:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PageElement:
    id: str
    role: ElementRole
    text: str = ""
    aria_label: str = ""
    placeholder: str = ""
    enabled: bool = True
    visible: bool = True
    box: ElementBox | None = None
    rank: float = 0.0

    def summary_label(self) -> str:
        for value in (self.text, self.aria_label, self.placeholder):
            if value.strip():
                return value.strip()
        return self.role

    def to_model_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "role": self.role,
            "text": self.text,
            "enabled": self.enabled,
            "rank": round(self.rank, 2),
        }
        if self.aria_label:
            payload["ariaLabel"] = self.aria_label
        if self.placeholder:
            payload["placeholder"] = self.placeholder
        if self.box is not None:
            payload["box"] = asdict(self.box)
        return payload


@dataclass(frozen=True)
class PageState:
    url: str
    title: str
    page_summary: str
    elements: list[PageElement] = field(default_factory=list)

    def signature(self) -> str:
        element_bits = "|".join(f"{element.id}:{element.role}:{element.summary_label()}" for element in self.elements[:12])
        return f"{self.url}::{self.title}::{element_bits}::{self.page_summary[:300]}"

    def visible_text_blob(self) -> str:
        labels = " ".join(element.summary_label() for element in self.elements[:30])
        return f"{self.title} {self.page_summary} {labels}".strip()

    def contains_terms(self, terms: list[str]) -> bool:
        haystack = self.visible_text_blob().lower()
        return all(term.lower() in haystack for term in terms if term.strip())

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "page_summary": self.page_summary,
            "elements": [element.to_model_dict() for element in self.elements],
        }


@dataclass(frozen=True)
class BrowserAction:
    action: BrowserActionName
    reason: str
    confidence: float
    risk: int
    element_id: str | None = None
    text: str | None = None
    url: str | None = None
    key: str | None = None
    scroll: str | int | None = None
    wait_ms: int | None = None
    summary: str | None = None
    question: str | None = None

    def signature(self) -> str:
        return "|".join(
            [
                self.action,
                self.element_id or "",
                self.text or "",
                self.url or "",
                self.key or "",
                str(self.scroll) if self.scroll is not None else "",
                str(self.wait_ms) if self.wait_ms is not None else "",
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ActionDecision:
    action: BrowserAction
    raw_text: str | None = None
    repaired: bool = False


@dataclass(frozen=True)
class PageChange:
    url_changed: bool
    title_changed: bool
    summary_changed: bool
    relevant_terms_present: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    summary: str
    url_after: str | None = None
    screenshot_path: str | None = None
    error: str | None = None
    page_changed: bool | None = None
    page_change: PageChange | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class LoopStop:
    reason: str
    summary: str
    steps: int


BROWSER_ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "navigate",
                "click",
                "type_text",
                "press_key",
                "scroll",
                "wait",
                "screenshot",
                "finish",
                "ask_user",
            ],
        },
        "element_id": {"type": "string"},
        "text": {"type": "string"},
        "url": {"type": "string"},
        "key": {"type": "string"},
        "scroll": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        "wait_ms": {"type": "integer", "minimum": 0},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "risk": {"type": "integer", "minimum": 0, "maximum": 10},
        "summary": {"type": "string"},
        "question": {"type": "string"},
    },
    "required": ["action", "reason", "confidence", "risk"],
}
