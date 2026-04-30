"""Deterministic one-action-per-turn browser-agent loop controller."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path

from .decision import DecisionInput, DecisionProvider, DecisionError
from .models import ActionResult, BrowserAction, LoopStop, PageChange, PageState
from .observer import PageObserver
from .session import BrowserSession
from .trace import BrowserTraceRecorder
from .validator import ActionValidationError, ActionValidator


@dataclass(frozen=True)
class BrowserAgentConfig:
    max_steps: int = 12
    stuck_threshold: int = 3
    validation_failure_threshold: int = 2
    repeated_failed_action_threshold: int = 2
    required_terms: tuple[str, ...] = ()


@dataclass
class BrowserAgentOutcome:
    stop: LoopStop
    last_state: PageState
    trace_path: Path


class BrowserAgentLoop:
    def __init__(
        self,
        *,
        session: BrowserSession,
        observer: PageObserver,
        decision_provider: DecisionProvider,
        validator: ActionValidator,
        trace_recorder: BrowserTraceRecorder,
        config: BrowserAgentConfig | None = None,
    ) -> None:
        self._session = session
        self._observer = observer
        self._decision_provider = decision_provider
        self._validator = validator
        self._trace_recorder = trace_recorder
        self._config = config or BrowserAgentConfig()

    async def run(self, *, task: str, start_url: str) -> BrowserAgentOutcome:
        trace_ctx = self._trace_recorder.create_context()
        repeated_signatures: deque[str] = deque(maxlen=self._config.stuck_threshold)
        validation_failures = 0
        last_result: ActionResult | None = None
        failed_action_counts: Counter[str] = Counter()
        trace_path = self._trace_recorder.trace_path(trace_ctx)

        navigate = BrowserAction(
            action="navigate",
            url=start_url,
            reason="Initial navigation to the requested start URL",
            confidence=1.0,
            risk=1,
        )
        await self._session.execute(navigate)
        current_state = await self._observer.capture(self._session)

        for step_index in range(1, self._config.max_steps + 1):
            decision_input = DecisionInput(
                task=task,
                page_state=current_state,
                last_action_result=last_result.to_dict() if last_result is not None else None,
                step_index=step_index,
            )
            try:
                decision = await self._decision_provider.decide(decision_input)
            except DecisionError as exc:
                return BrowserAgentOutcome(
                    stop=LoopStop(reason="decision_error", summary=str(exc), steps=step_index - 1),
                    last_state=current_state,
                    trace_path=trace_path,
                )

            validation_error = self._preflight_validate(action=decision.action, state=current_state)
            if validation_error is not None:
                validation_failures += 1
                synthetic_result = ActionResult(ok=False, summary="Validation failed", error=validation_error)
                self._trace_recorder.record(
                    trace_ctx,
                    step_index=step_index,
                    task=task,
                    state_before=current_state,
                    action=decision.action,
                    validation_result=f"invalid: {validation_error}",
                    result=synthetic_result,
                    state_after=current_state,
                    stop_reason="validation_failed" if validation_failures >= self._config.validation_failure_threshold else None,
                )
                if validation_failures >= self._config.validation_failure_threshold:
                    return BrowserAgentOutcome(
                        stop=LoopStop(reason="validation_failed", summary=validation_error, steps=step_index),
                        last_state=current_state,
                        trace_path=trace_path,
                    )
                last_result = synthetic_result
                continue

            validation_failures = 0
            raw_result = await self._session.execute(decision.action)
            next_state = await self._observer.capture(self._session)
            page_change = self._detect_page_change(current_state, next_state)
            result = ActionResult(
                ok=raw_result.ok,
                summary=raw_result.summary,
                url_after=raw_result.url_after,
                screenshot_path=raw_result.screenshot_path,
                error=raw_result.error,
                page_changed=(page_change.url_changed or page_change.title_changed or page_change.summary_changed),
                page_change=page_change,
            )

            if not result.ok:
                failed_action_counts[decision.action.signature()] += 1
                if failed_action_counts[decision.action.signature()] >= self._config.repeated_failed_action_threshold:
                    ask_user = BrowserAction(
                        action="ask_user",
                        question=f"Blocked after repeated failure: {result.error or result.summary}",
                        reason="Repeated failed action threshold hit",
                        confidence=0.95,
                        risk=7,
                    )
                    self._trace_recorder.record(
                        trace_ctx,
                        step_index=step_index,
                        task=task,
                        state_before=current_state,
                        action=ask_user,
                        validation_result="valid",
                        result=ActionResult(ok=True, summary=ask_user.question or "Need user input", page_change=page_change),
                        state_after=next_state,
                        stop_reason="ask_user",
                    )
                    return BrowserAgentOutcome(
                        stop=LoopStop(reason="ask_user", summary=ask_user.question or "Blocked", steps=step_index),
                        last_state=next_state,
                        trace_path=trace_path,
                    )
            else:
                failed_action_counts[decision.action.signature()] = 0

            stop_reason = None
            if decision.action.action in {"finish", "ask_user"}:
                stop_reason = decision.action.action

            self._trace_recorder.record(
                trace_ctx,
                step_index=step_index,
                task=task,
                state_before=current_state,
                action=decision.action,
                validation_result="valid",
                result=result,
                state_after=next_state,
                stop_reason=stop_reason,
            )

            signature = f"{decision.action.signature()}::{next_state.signature()}"
            repeated_signatures.append(signature)
            if len(repeated_signatures) == self._config.stuck_threshold and len(set(repeated_signatures)) == 1:
                return BrowserAgentOutcome(
                    stop=LoopStop(reason="stuck", summary="Repeated the same action/page signature too many times", steps=step_index),
                    last_state=next_state,
                    trace_path=trace_path,
                )

            if decision.action.action == "finish":
                return BrowserAgentOutcome(
                    stop=LoopStop(reason="finish", summary=decision.action.summary or result.summary, steps=step_index),
                    last_state=next_state,
                    trace_path=trace_path,
                )
            if decision.action.action == "ask_user":
                return BrowserAgentOutcome(
                    stop=LoopStop(reason="ask_user", summary=decision.action.question or result.summary, steps=step_index),
                    last_state=next_state,
                    trace_path=trace_path,
                )

            last_result = result
            current_state = next_state

        return BrowserAgentOutcome(
            stop=LoopStop(reason="max_steps", summary="Reached max browser-agent steps", steps=self._config.max_steps),
            last_state=current_state,
            trace_path=trace_path,
        )

    def _preflight_validate(self, *, action: BrowserAction, state: PageState) -> str | None:
        if action.risk >= 7 and action.action != "ask_user":
            return "high-risk actions must use ask_user instead of direct execution"
        try:
            self._validator.validate(action, state)
        except ActionValidationError as exc:
            return str(exc)
        if action.action == "finish":
            terms = list(self._config.required_terms)
            if terms and not state.contains_terms(terms):
                return "finish rejected: visible page evidence does not confirm required task terms"
            summary = (action.summary or "").lower()
            if terms and not any(term.lower() in summary for term in terms):
                return "finish rejected: summary does not reference required visible evidence"
        return None

    def _detect_page_change(self, before: PageState, after: PageState) -> PageChange:
        return PageChange(
            url_changed=before.url != after.url,
            title_changed=before.title != after.title,
            summary_changed=before.page_summary != after.page_summary,
            relevant_terms_present=after.contains_terms(list(self._config.required_terms)),
        )
