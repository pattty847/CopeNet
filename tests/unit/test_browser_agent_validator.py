from copenet.browser_agent.models import BrowserAction, PageElement, PageState
from copenet.browser_agent.validator import ActionValidationError, ActionValidator


def _state() -> PageState:
    return PageState(
        url="https://example.com",
        title="Example",
        page_summary="Example page",
        elements=[PageElement(id="e1", role="button", text="Continue")],
    )


def test_validator_accepts_known_click() -> None:
    validator = ActionValidator()
    action = BrowserAction(
        action="click",
        element_id="e1",
        reason="Click the only button",
        confidence=0.9,
        risk=2,
    )
    validator.validate(action, _state())


def test_validator_rejects_unknown_element_id() -> None:
    validator = ActionValidator()
    action = BrowserAction(
        action="click",
        element_id="e99",
        reason="Bad id",
        confidence=0.5,
        risk=1,
    )
    try:
        validator.validate(action, _state())
    except ActionValidationError as exc:
        assert "unknown element_id" in str(exc)
    else:
        raise AssertionError("Expected validation error")


def test_validator_rejects_missing_finish_summary() -> None:
    validator = ActionValidator()
    action = BrowserAction(
        action="finish",
        reason="Done",
        confidence=1.0,
        risk=0,
        summary="",
    )
    try:
        validator.validate(action, _state())
    except ActionValidationError as exc:
        assert "finish requires summary" in str(exc)
    else:
        raise AssertionError("Expected validation error")
