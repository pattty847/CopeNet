"""Strict action validation for deterministic browser-agent decisions."""

from __future__ import annotations

from .models import BrowserAction, PageState


class ActionValidationError(ValueError):
    pass


class ActionValidator:
    def validate(self, action: BrowserAction, state: PageState) -> None:
        if not 0.0 <= action.confidence <= 1.0:
            raise ActionValidationError("confidence must be between 0.0 and 1.0")
        if not 0 <= action.risk <= 10:
            raise ActionValidationError("risk must be between 0 and 10")

        known_ids = {element.id for element in state.elements}

        if action.action == "navigate":
            if not action.url:
                raise ActionValidationError("navigate requires url")
            return

        if action.action in {"click", "type_text"}:
            if not action.element_id:
                raise ActionValidationError(f"{action.action} requires element_id")
            if action.element_id not in known_ids:
                raise ActionValidationError(f"unknown element_id: {action.element_id}")
            if action.action == "type_text" and action.text is None:
                raise ActionValidationError("type_text requires text")
            return

        if action.action == "press_key":
            if not action.key:
                raise ActionValidationError("press_key requires key")
            return

        if action.action == "scroll":
            if action.scroll is None:
                raise ActionValidationError("scroll requires scroll direction or pixel amount")
            return

        if action.action == "wait":
            if action.wait_ms is not None and action.wait_ms < 0:
                raise ActionValidationError("wait_ms must be >= 0")
            return

        if action.action == "finish":
            if not (action.summary or "").strip():
                raise ActionValidationError("finish requires summary")
            return

        if action.action == "ask_user":
            if not (action.question or "").strip():
                raise ActionValidationError("ask_user requires question")
            return

        if action.action == "screenshot":
            return

        raise ActionValidationError(f"unsupported action: {action.action}")
