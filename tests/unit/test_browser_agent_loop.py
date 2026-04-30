from pathlib import Path

import pytest

from copenet.browser_agent.decision import DecisionError, ScriptedDecisionProvider
from copenet.browser_agent.loop import BrowserAgentConfig, BrowserAgentLoop
from copenet.browser_agent.models import BrowserAction, PageElement, PageState
from copenet.browser_agent.trace import BrowserTraceRecorder
from copenet.browser_agent.validator import ActionValidator


class FakeSession:
    def __init__(self, fail_signatures: set[str] | None = None) -> None:
        self.url = "about:blank"
        self.executed: list[BrowserAction] = []
        self.fail_signatures = fail_signatures or set()

    async def execute(self, action: BrowserAction):
        self.executed.append(action)
        if action.url:
            self.url = action.url
        failed = action.signature() in self.fail_signatures
        return type(
            "Result",
            (),
            {
                "ok": not failed,
                "summary": action.summary or action.question or action.reason,
                "url_after": self.url,
                "screenshot_path": None,
                "error": "forced failure" if failed else None,
            },
        )()


class FakeObserver:
    def __init__(self, states: list[PageState]) -> None:
        self._states = states
        self._index = 0

    async def capture(self, session):
        del session
        state = self._states[min(self._index, len(self._states) - 1)]
        self._index += 1
        return state


class RepairProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, decision_input):
        del decision_input
        self.calls += 1
        if self.calls == 1:
            raise DecisionError("invalid JSON action: boom")
        return type(
            "Decision",
            (),
            {
                "action": BrowserAction(
                    action="finish",
                    summary="Found CopeNet in visible results",
                    reason="Visible evidence present",
                    confidence=0.9,
                    risk=0,
                ),
                "raw_text": '{}',
                "repaired": True,
            },
        )()


def _state(url: str = "https://example.com", title: str = "Example", summary: str = "Example page", text: str = "Continue") -> PageState:
    return PageState(
        url=url,
        title=title,
        page_summary=summary,
        elements=[PageElement(id="e1", role="button", text=text)],
    )


@pytest.mark.asyncio
async def test_loop_stops_after_max_steps(tmp_path: Path) -> None:
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([_state(), _state(), _state(), _state()]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(action="wait", reason="wait", confidence=1.0, risk=0, wait_ms=1),
                BrowserAction(action="wait", reason="wait", confidence=1.0, risk=0, wait_ms=1),
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(max_steps=2, stuck_threshold=5),
    )
    outcome = await loop.run(task="Wait twice", start_url="https://example.com")
    assert outcome.stop.reason == "max_steps"


@pytest.mark.asyncio
async def test_loop_stops_on_ask_user(tmp_path: Path) -> None:
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([_state(), _state()]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(
                    action="ask_user",
                    question="Need login help",
                    reason="Blocked by auth",
                    confidence=0.9,
                    risk=7,
                )
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
    )
    outcome = await loop.run(task="Need auth", start_url="https://example.com")
    assert outcome.stop.reason == "ask_user"


@pytest.mark.asyncio
async def test_loop_stops_on_repeated_stuck_state(tmp_path: Path) -> None:
    state = _state()
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([state, state, state, state, state]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(action="wait", reason="wait", confidence=1.0, risk=0, wait_ms=1),
                BrowserAction(action="wait", reason="wait", confidence=1.0, risk=0, wait_ms=1),
                BrowserAction(action="wait", reason="wait", confidence=1.0, risk=0, wait_ms=1),
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(max_steps=5, stuck_threshold=3),
    )
    outcome = await loop.run(task="Get unstuck", start_url="https://example.com")
    assert outcome.stop.reason == "stuck"


@pytest.mark.asyncio
async def test_loop_blocks_high_risk_direct_action(tmp_path: Path) -> None:
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([_state(), _state(), _state()]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(
                    action="click",
                    element_id="e1",
                    reason="Pretend this is a payment button",
                    confidence=0.9,
                    risk=9,
                ),
                BrowserAction(
                    action="click",
                    element_id="e1",
                    reason="Pretend this is a payment button",
                    confidence=0.9,
                    risk=9,
                ),
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(validation_failure_threshold=2),
    )
    outcome = await loop.run(task="Danger", start_url="https://example.com")
    assert outcome.stop.reason == "validation_failed"


@pytest.mark.asyncio
async def test_finish_rejected_without_visible_evidence(tmp_path: Path) -> None:
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([_state(summary="Nothing relevant here"), _state(summary="Still nothing")]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(
                    action="finish",
                    summary="Done, found CopeNet",
                    reason="Claiming success",
                    confidence=0.9,
                    risk=0,
                ),
                BrowserAction(
                    action="finish",
                    summary="Done, found CopeNet",
                    reason="Claiming success",
                    confidence=0.9,
                    risk=0,
                ),
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(required_terms=("copenet",), validation_failure_threshold=2),
    )
    outcome = await loop.run(task="Search for CopeNet", start_url="https://example.com")
    assert outcome.stop.reason == "validation_failed"


@pytest.mark.asyncio
async def test_page_change_detection_works(tmp_path: Path) -> None:
    loop = BrowserAgentLoop(
        session=FakeSession(),
        observer=FakeObserver([
            _state(url="https://a.com", title="A", summary="before"),
            _state(url="https://b.com", title="B", summary="after CopeNet"),
            _state(url="https://b.com", title="B", summary="after CopeNet"),
        ]),
        decision_provider=ScriptedDecisionProvider(
            actions=[
                BrowserAction(
                    action="wait",
                    reason="Advance one loop to the changed page",
                    confidence=1.0,
                    risk=0,
                    wait_ms=1,
                ),
                BrowserAction(
                    action="finish",
                    summary="CopeNet visible on page",
                    reason="Evidence present",
                    confidence=1.0,
                    risk=0,
                ),
            ]
        ),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(required_terms=("copenet",)),
    )
    outcome = await loop.run(task="Find CopeNet", start_url="https://a.com")
    assert outcome.stop.reason == "finish"


@pytest.mark.asyncio
async def test_repeated_failed_action_triggers_ask_user(tmp_path: Path) -> None:
    failed_action = BrowserAction(action="click", element_id="e1", reason="Click", confidence=1.0, risk=1)
    loop = BrowserAgentLoop(
        session=FakeSession(fail_signatures={failed_action.signature()}),
        observer=FakeObserver([_state(), _state(), _state()]),
        decision_provider=ScriptedDecisionProvider(actions=[failed_action, failed_action]),
        validator=ActionValidator(),
        trace_recorder=BrowserTraceRecorder(tmp_path),
        config=BrowserAgentConfig(repeated_failed_action_threshold=2),
    )
    outcome = await loop.run(task="Click twice", start_url="https://example.com")
    assert outcome.stop.reason == "ask_user"
