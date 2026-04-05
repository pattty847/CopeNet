"""Codex CLI provider adapter (Codex-first v1 path)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import AsyncIterator, Callable

from copenet.providers.base import ProviderEvent, ProviderModel
from copenet.runner.cli_runner import CliRunner, RunnerEvent, RunnerResult


def _default_config_get(key: str, default: str | None = None) -> str | None:
    """Read execution_mode from env only (no app config)."""
    if key == "execution_mode":
        raw = os.environ.get("COPNET_EXECUTION_MODE", "tools-enabled").strip().lower()
        if raw in {"safe", "tools-enabled", "unrestricted"}:
            return raw
        return "tools-enabled"
    return default


class CodexCliProvider:
    """Provider adapter that talks to Codex CLI via subprocess."""

    name = "codex-cli"
    display_name = "Codex"

    def __init__(
        self,
        runner: CliRunner | None = None,
        config_get: Callable[[str, str | None], str | None] | None = None,
    ) -> None:
        self._runner = runner or CliRunner()
        self._cli = shutil.which("codex.cmd") or shutil.which("codex")
        self._config_get = config_get or _default_config_get
        if not self._cli:
            raise FileNotFoundError("Codex CLI not found on PATH (expected `codex` or `codex.cmd`).")

    def _execution_mode(self) -> str:
        """Resolve execution mode from config getter or env."""
        raw = str(self._config_get("execution_mode", "tools-enabled") or "tools-enabled").strip().lower()
        if raw in {"safe", "tools-enabled", "unrestricted"}:
            return raw
        return "tools-enabled"

    def _mode_flags(self, resume: bool) -> list[str]:
        """Return codex flags for current execution mode."""
        mode = self._execution_mode()
        if mode == "safe":
            if resume:
                return ["--json", "--skip-git-repo-check"]
            return [
                "--json",
                "--color",
                "never",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
            ]
        if mode == "unrestricted":
            return [
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
            ]
        return [
            "--json",
            "--full-auto",
            "--skip-git-repo-check",
        ]

    def _build_args(self, prompt: str, provider_session_id: str | None) -> list[str]:
        if provider_session_id:
            return [
                self._cli,
                "exec",
                "resume",
                *self._mode_flags(resume=True),
                provider_session_id,
                prompt,
            ]
        return [
            self._cli,
            "exec",
            *self._mode_flags(resume=False),
            prompt,
        ]

    @staticmethod
    def _parse_json_line(line: str) -> tuple[str | None, str | None]:
        """Parse one JSONL line into (delta_text, thread_id)."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return (None, None)
        if not isinstance(payload, dict):
            return (None, None)

        thread_id = payload.get("thread_id")
        normalized_thread = str(thread_id).strip() if isinstance(thread_id, str) and thread_id else None

        item = payload.get("item")
        if isinstance(item, dict):
            text = item.get("text")
            item_type = str(item.get("type") or "").lower()
            if isinstance(text, str) and text.strip() and ("message" in item_type or not item_type):
                return (text, normalized_thread)

        for key in ("text", "message", "content", "output_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return (value, normalized_thread)

        return (None, normalized_thread)

    async def describe(self) -> dict[str, object]:
        """Report provider status for UI catalog rendering."""
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "supportsModelSelection": False,
            "modelCount": 0,
            "capabilities": {
                "chat": True,
                "embeddings": False,
                "toolCalls": True,
                "streaming": True,
                "resume": True,
            },
        }

    async def list_models(self) -> list[ProviderModel]:
        """Codex CLI does not expose model selection through this adapter."""
        return []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Run a single Codex turn and stream provider events."""
        args = self._build_args(prompt=prompt, provider_session_id=provider_session_id)
        discovered_session_id: str | None = provider_session_id

        async for event in self._runner.run(args, timeout_sec=120, abort_event=abort_event):
            if isinstance(event, RunnerEvent):
                if event.stream != "stdout":
                    continue

                text, thread_id = self._parse_json_line(event.line)
                if thread_id and thread_id != discovered_session_id:
                    discovered_session_id = thread_id
                    yield ProviderEvent(kind="meta", provider_session_id=discovered_session_id)

                if text:
                    yield ProviderEvent(kind="delta", text=text)
                continue

            if isinstance(event, RunnerResult):
                if event.returncode != 0:
                    detail = event.stderr_tail.strip() or event.stdout_tail.strip() or "unknown codex error"
                    raise RuntimeError(f"Codex CLI failed (exit={event.returncode}): {detail}")
                yield ProviderEvent(kind="final", provider_session_id=discovered_session_id)
