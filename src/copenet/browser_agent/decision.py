"""Decision-provider abstraction and strict JSON action parsing for the browser-agent loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from copenet.core.model_request import ProviderTextRequest, collect_provider_text
from copenet.prompts import PromptPurpose
from copenet.providers import LmStudioProvider, OllamaProvider, OpenAICodexProvider, Provider

from .models import ActionDecision, BROWSER_ACTION_JSON_SCHEMA, BrowserAction, PageState


class DecisionError(ValueError):
    pass


@dataclass(frozen=True)
class DecisionInput:
    task: str
    page_state: PageState
    last_action_result: dict | None = None
    step_index: int = 0


class DecisionProvider(Protocol):
    async def decide(self, decision_input: DecisionInput) -> ActionDecision:
        """Return exactly one structured browser action decision."""


@dataclass
class ScriptedDecisionProvider:
    actions: list[BrowserAction]
    _index: int = field(default=0, init=False)

    async def decide(self, decision_input: DecisionInput) -> ActionDecision:
        del decision_input
        if self._index >= len(self.actions):
            raise DecisionError("scripted decision sequence exhausted")
        action = self.actions[self._index]
        self._index += 1
        return ActionDecision(action=action, raw_text=json.dumps(action.to_dict()))


class CopeNetProviderDecisionAdapter:
    def __init__(self, provider: Provider, model: str, system_prompt: str | None = None) -> None:
        self._provider = provider
        self._model = model
        self._system_prompt = system_prompt or _default_system_prompt()

    async def decide(self, decision_input: DecisionInput) -> ActionDecision:
        prompt = build_decision_prompt(decision_input)
        raw_text = await _run_provider_text(
            provider=self._provider,
            prompt=prompt,
            model=self._model,
            system_prompt=self._system_prompt,
        )
        try:
            action = parse_action_json(raw_text)
            return ActionDecision(action=action, raw_text=raw_text, repaired=False)
        except DecisionError as first_error:
            repair_prompt = build_repair_prompt(raw_text=raw_text, error=str(first_error), decision_input=decision_input)
            repaired_text = await _run_provider_text(
                provider=self._provider,
                prompt=repair_prompt,
                model=self._model,
                system_prompt=self._system_prompt,
            )
            action = parse_action_json(repaired_text)
            return ActionDecision(action=action, raw_text=repaired_text, repaired=True)


def build_decision_prompt(decision_input: DecisionInput) -> str:
    parts = [
        f"Task: {decision_input.task}",
        f"Step: {decision_input.step_index}",
        "Current page state:",
        json.dumps(decision_input.page_state.to_model_dict(), ensure_ascii=False, indent=2),
    ]
    if decision_input.last_action_result is not None:
        parts.extend(
            [
                "Last action result:",
                json.dumps(decision_input.last_action_result, ensure_ascii=False, indent=2),
            ]
        )
    parts.append(
        "Return exactly one JSON object matching the action schema. No markdown, no prose, no code fences."
    )
    return "\n\n".join(parts)


def build_repair_prompt(*, raw_text: str, error: str, decision_input: DecisionInput) -> str:
    return "\n\n".join(
        [
            "Your previous response was invalid.",
            f"Validation error: {error}",
            "Bad response:",
            raw_text,
            "Try again. Return JSON only.",
            build_decision_prompt(decision_input),
        ]
    )


def parse_action_json(raw_text: str) -> BrowserAction:
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        raise DecisionError("model output must be raw JSON only")
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DecisionError(f"invalid JSON action: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionError("action payload must be a JSON object")
    _validate_action_shape(payload)
    return BrowserAction(
        action=str(payload["action"]),
        reason=str(payload["reason"]),
        confidence=float(payload["confidence"]),
        risk=int(payload["risk"]),
        element_id=_optional_text(payload.get("element_id")),
        text=_optional_text(payload.get("text")),
        url=_optional_text(payload.get("url")),
        key=_optional_text(payload.get("key")),
        scroll=payload.get("scroll"),
        wait_ms=_optional_int(payload.get("wait_ms")),
        summary=_optional_text(payload.get("summary")),
        question=_optional_text(payload.get("question")),
    )


def _validate_action_shape(payload: dict) -> None:
    allowed = set(BROWSER_ACTION_JSON_SCHEMA["properties"].keys())
    unknown = sorted(set(payload.keys()) - allowed)
    if unknown:
        raise DecisionError(f"unknown action fields: {', '.join(unknown)}")
    required = list(BROWSER_ACTION_JSON_SCHEMA["required"])
    for key in required:
        if key not in payload:
            raise DecisionError(f"missing required field: {key}")
    valid_actions = set(BROWSER_ACTION_JSON_SCHEMA["properties"]["action"]["enum"])
    action = payload.get("action")
    if action not in valid_actions:
        raise DecisionError(f"unknown action type: {action}")


def provider_from_name(name: str) -> Provider:
    normalized = name.strip().lower()
    if normalized == "copenet":
        return LmStudioProvider()
    if normalized in {"codex", "openai-codex"}:
        return OpenAICodexProvider()
    if normalized in {"lmstudio", "lm-studio"}:
        return LmStudioProvider()
    if normalized == "ollama":
        return OllamaProvider()
    raise ValueError(f"unknown browser-agent provider: {name}")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


async def _run_provider_text(*, provider: Provider, prompt: str, model: str, system_prompt: str) -> str:
    return await collect_provider_text(
        provider=provider,
        request=ProviderTextRequest(
            purpose=PromptPurpose.SPECIALIZED,
            phase="browser_decision",
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
        ),
    )


def _default_system_prompt() -> str:
    return (
        "You are a deterministic browser decision engine. "
        "Return exactly one JSON action object and nothing else. "
        "Use only observed element IDs. "
        "Do not invent selectors. "
        "Choose one small safe next action. "
        "Do not finish unless visible page evidence supports the task outcome. "
        "If risk is high or the task touches login, payment, private data, sending, deleting, or irreversible actions, "
        "return ask_user instead of taking the action."
    )
