"""Claude CLI provider adapter."""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import AsyncIterator

from copenet.providers.base import ProviderEvent, ProviderModel
from copenet.runner.cli_runner import CliRunner, RunnerEvent, RunnerResult

SUPPORTED_CLAUDE_CLI_MODELS = (
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
)
DEFAULT_CLAUDE_CLI_MODEL = SUPPORTED_CLAUDE_CLI_MODELS[0]


class ClaudeCliProvider:
    """Provider adapter that talks to Claude Code via the local Claude CLI."""

    name = "claude-cli"
    display_name = "Claude CLI"

    def __init__(self, runner: CliRunner | None = None) -> None:
        self._runner = runner or CliRunner()
        self._cli = shutil.which("claude")
        if not self._cli:
            raise FileNotFoundError("Claude CLI not found on PATH (expected `claude`).")

    def _resolve_model(self, model: str | None) -> str:
        normalized = str(model or "").strip()
        if not normalized:
            return DEFAULT_CLAUDE_CLI_MODEL
        if normalized not in SUPPORTED_CLAUDE_CLI_MODELS:
            supported = ", ".join(SUPPORTED_CLAUDE_CLI_MODELS)
            raise ValueError(f"unsupported claude cli model: {normalized}. Supported models: {supported}")
        return normalized

    def _build_args(
        self,
        prompt: str,
        provider_session_id: str | None,
        model: str | None,
        system_prompt: str | None = None,
    ) -> list[str]:
        args = [
            self._cli,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--tools",
            "",
            # Match Agent SDK isolation: do not let user/project/local Claude
            # settings or CLAUDE.md silently become CopeNet model context.
            "--setting-sources=",
            "--model",
            self._resolve_model(model),
        ]
        if system_prompt:
            args.extend(["--system-prompt", system_prompt])
        if provider_session_id:
            args.extend(["--resume", provider_session_id])
        return args

    @staticmethod
    def _parse_json_line(line: str) -> tuple[str | None, str | None]:
        """Parse one Claude stream-json line into (delta_text, session_id)."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return (None, None)
        if not isinstance(payload, dict):
            return (None, None)

        session_id = payload.get("session_id")
        normalized_session = str(session_id).strip() if isinstance(session_id, str) and session_id else None

        result = payload.get("result")
        if payload.get("type") == "result" and isinstance(result, str) and result.strip():
            return (result, normalized_session)

        message = payload.get("message")
        if isinstance(message, dict):
            text = _extract_message_text(message.get("content"))
            if text:
                return (text, normalized_session)

        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return (text, normalized_session)

        return (None, normalized_session)

    async def describe(self) -> dict[str, object]:
        """Report provider status for UI catalog rendering."""
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "supportsModelSelection": True,
            "modelCount": len(SUPPORTED_CLAUDE_CLI_MODELS),
            "requiresAuth": True,
            "authType": "native-cli",
            "authInstructions": "Run `claude auth login` in a terminal, then restart CopeNet if needed.",
            "capabilities": {
                "chat": True,
                "embeddings": False,
                "toolCalls": False,
                "promptedToolUse": True,
                "streaming": True,
                "resume": True,
            },
        }

    async def list_models(self) -> list[ProviderModel]:
        """Return the supported Claude CLI chat models."""
        rows: list[ProviderModel] = []
        for model_id in SUPPORTED_CLAUDE_CLI_MODELS:
            rows.append(
                ProviderModel(
                    id=model_id,
                    display_name=_display_name(model_id),
                    kind="chat",
                    provider=self.name,
                    capabilities={
                        "chat": True,
                        "streaming": True,
                        "toolCalls": False,
                        "promptedToolUse": True,
                        "resume": True,
                    },
                    recommended_for=["chat"],
                    metadata={"ownedBy": "Anthropic", "authSource": "Claude CLI native auth"},
                )
            )
        return rows

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Run a single Claude CLI turn and stream provider events."""
        args = self._build_args(
            prompt=prompt,
            provider_session_id=provider_session_id,
            model=model,
            system_prompt=system_prompt,
        )
        discovered_session_id: str | None = provider_session_id
        emitted_text = False

        async for event in self._runner.run(args, timeout_sec=120, abort_event=abort_event):
            if isinstance(event, RunnerEvent):
                if event.stream != "stdout":
                    continue

                text, session_id = self._parse_json_line(event.line)
                if session_id and session_id != discovered_session_id:
                    discovered_session_id = session_id
                    yield ProviderEvent(kind="meta", provider_session_id=discovered_session_id)

                is_result = _json_line_type(event.line) == "result"
                if text and (not is_result or not emitted_text):
                    emitted_text = True
                    yield ProviderEvent(kind="delta", text=text)
                continue

            if isinstance(event, RunnerResult):
                if event.returncode != 0:
                    detail = event.stderr_tail.strip() or event.stdout_tail.strip() or "unknown claude cli error"
                    raise RuntimeError(f"Claude CLI failed (exit={event.returncode}): {detail}")
                yield ProviderEvent(kind="final", provider_session_id=discovered_session_id)


def _extract_message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if item.get("type") == "text" and isinstance(text, str) and text:
            parts.append(text)
    joined = "".join(parts).strip()
    return joined or None


def _json_line_type(line: str) -> str | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    line_type = payload.get("type")
    return str(line_type) if isinstance(line_type, str) else None


def _display_name(model_id: str) -> str:
    words = model_id.replace("-", " ").split()
    return "Claude " + " ".join(word.capitalize() if not word.isdigit() else word for word in words[1:])
