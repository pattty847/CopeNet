"""HTTP-backed local model providers for LM Studio and Ollama."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from urllib import error, request

from copenet.providers.base import ProviderEvent, ProviderModel


def _trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def _http_json(url: str, timeout_sec: float = 5.0) -> Any:
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


class _StreamingHttpProvider:
    """Common helpers for HTTP providers that stream text back."""

    name = ""
    display_name = ""

    def __init__(self, base_url: str, timeout_sec: float = 30.0) -> None:
        self._base_url = _trim_trailing_slash(base_url)
        self._timeout_sec = timeout_sec

    async def describe(self) -> dict[str, object]:
        """Return runtime availability and model summary."""
        try:
            models = await self.list_models()
            default_model = next((model.id for model in models if model.kind == "chat"), models[0].id if models else None)
            return {
                "id": self.name,
                "displayName": self.display_name,
                "available": True,
                "supportsModelSelection": True,
                "modelCount": len(models),
                "defaultModel": default_model,
                "capabilities": {
                    "chat": True,
                    "embeddings": any(model.kind == "embedding" for model in models),
                    "toolCalls": False,
                    "promptedToolUse": True,
                    "streaming": True,
                    "resume": False,
                },
            }
        except Exception as exc:
            return {
                "id": self.name,
                "displayName": self.display_name,
                "available": False,
                "supportsModelSelection": True,
                "modelCount": 0,
                "capabilities": {
                    "chat": True,
                    "embeddings": False,
                    "toolCalls": False,
                    "promptedToolUse": True,
                    "streaming": True,
                    "resume": False,
                },
                "error": str(exc),
            }

    async def _resolve_model(self, explicit_model: str | None) -> str:
        if explicit_model and explicit_model.strip():
            return explicit_model.strip()
        models = await self.list_models()
        if not models:
            raise RuntimeError(f"{self.display_name} has no available models.")
        return models[0].id


class LmStudioProvider(_StreamingHttpProvider):
    """LM Studio OpenAI-compatible local runtime provider."""

    name = "lm-studio"
    display_name = "LM Studio"

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        super().__init__(base_url=base_url, timeout_sec=60.0)

    async def list_models(self) -> list[ProviderModel]:
        data = await asyncio.to_thread(_http_json, f"{self._base_url}/v1/models")
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []

        models: list[ProviderModel] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("id") or "").strip()
            if not model_id:
                continue
            lowered = model_id.lower()
            kind = "embedding" if "embed" in lowered or "embedding" in lowered else "chat"
            models.append(
                ProviderModel(
                    id=model_id,
                    display_name=model_id,
                    provider=self.name,
                    kind=kind,
                    capabilities={
                        "chat": kind == "chat",
                        "embeddings": kind == "embedding",
                        "toolCalls": False,
                        "promptedToolUse": kind == "chat",
                        "streaming": kind == "chat",
                        "resume": False,
                    },
                    recommended_for=["chat"] if kind == "chat" else ["embeddings"],
                    metadata={"ownedBy": row.get("owned_by")},
                )
            )
        return models

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ProviderEvent | Exception | object] = asyncio.Queue()
        done_marker = object()
        model_name = await self._resolve_model(model)
        messages: list[dict[str, str]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
        }

        def worker() -> None:
            req = request.Request(
                f"{self._base_url}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=self._timeout_sec) as response:
                    for raw in response:
                        if abort_event.is_set():
                            break
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        payload_obj = json.loads(chunk)
                        choices = payload_obj.get("choices") if isinstance(payload_obj, dict) else None
                        if not isinstance(choices, list):
                            continue
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            delta = choice.get("delta")
                            if not isinstance(delta, dict):
                                continue
                            text = delta.get("content")
                            if isinstance(text, str) and text:
                                loop.call_soon_threadsafe(queue.put_nowait, ProviderEvent(kind="delta", text=text))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done_marker)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                item = await queue.get()
                if item is done_marker:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        except error.URLError as exc:
            raise RuntimeError(f"LM Studio request failed: {exc.reason}") from exc
        finally:
            await task

        yield ProviderEvent(kind="final", provider_session_id=provider_session_id)


class OllamaProvider(_StreamingHttpProvider):
    """Ollama local runtime provider."""

    name = "ollama"
    display_name = "Ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        super().__init__(base_url=base_url, timeout_sec=120.0)

    async def list_models(self) -> list[ProviderModel]:
        data = await asyncio.to_thread(_http_json, f"{self._base_url}/api/tags")
        rows = data.get("models") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []

        models: list[ProviderModel] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("name") or row.get("model") or "").strip()
            if not model_id:
                continue
            details = row.get("details") if isinstance(row.get("details"), dict) else {}
            lowered = model_id.lower()
            kind = "embedding" if "embed" in lowered or "embedding" in lowered else "chat"
            description_parts = [
                str(details.get("family") or "").strip(),
                str(details.get("parameter_size") or "").strip(),
                str(details.get("quantization_level") or "").strip(),
            ]
            description = " ".join(part for part in description_parts if part) or None
            models.append(
                ProviderModel(
                    id=model_id,
                    display_name=model_id,
                    provider=self.name,
                    description=description,
                    kind=kind,
                    capabilities={
                        "chat": kind == "chat",
                        "embeddings": kind == "embedding",
                        "toolCalls": False,
                        "promptedToolUse": kind == "chat",
                        "streaming": kind == "chat",
                        "resume": False,
                    },
                    recommended_for=["chat"] if kind == "chat" else ["embeddings"],
                    metadata={"size": row.get("size"), "modifiedAt": row.get("modified_at")},
                )
            )
        return models

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ProviderEvent | Exception | object] = asyncio.Queue()
        done_marker = object()
        model_name = await self._resolve_model(model)
        messages: list[dict[str, str]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
        }

        def worker() -> None:
            req = request.Request(
                f"{self._base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=self._timeout_sec) as response:
                    for raw in response:
                        if abort_event.is_set():
                            break
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        payload_obj = json.loads(line)
                        if not isinstance(payload_obj, dict):
                            continue
                        message = payload_obj.get("message")
                        if isinstance(message, dict):
                            text = message.get("content")
                            if isinstance(text, str) and text:
                                loop.call_soon_threadsafe(queue.put_nowait, ProviderEvent(kind="delta", text=text))
                        if payload_obj.get("done") is True:
                            break
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done_marker)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                item = await queue.get()
                if item is done_marker:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        except error.URLError as exc:
            raise RuntimeError(f"Ollama request failed: {exc.reason}") from exc
        finally:
            await task

        yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
