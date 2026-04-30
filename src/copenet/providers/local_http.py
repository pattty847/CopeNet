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


def _http_json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 5.0,
    accept: str = "application/json",
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": accept}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _lmstudio_tool_support(kind: str, capabilities: dict[str, Any]) -> bool:
    if kind != "chat":
        return False
    trained = capabilities.get("trained_for_tool_use")
    if trained is None:
        return True
    return bool(trained)


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
                    "toolCalls": True,
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
                    "toolCalls": True,
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
    """LM Studio local runtime provider with native lifecycle support."""

    name = "lm-studio"
    display_name = "LM Studio"

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        super().__init__(base_url=base_url, timeout_sec=120.0)

    async def describe(self) -> dict[str, object]:
        meta = await super().describe()
        caps = dict(meta.get("capabilities") or {})
        caps["nativeModelLifecycle"] = True
        meta["capabilities"] = caps
        return meta

    async def _list_native_models(self) -> list[dict[str, Any]]:
        data = await asyncio.to_thread(_http_json, f"{self._base_url}/api/v1/models")
        rows = data.get("models") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    async def list_loaded_instances(self) -> list[dict[str, Any]]:
        rows = await self._list_native_models()
        loaded: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_key = str(row.get("key") or "").strip()
            model_type = str(row.get("type") or "").strip() or None
            instances = row.get("loaded_instances")
            if not isinstance(instances, list):
                continue
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                instance_id = str(inst.get("id") or "").strip()
                if not instance_id:
                    continue
                loaded.append(
                    {
                        "instanceId": instance_id,
                        "modelKey": model_key,
                        "type": model_type,
                        "config": inst.get("config") if isinstance(inst.get("config"), dict) else {},
                    }
                )
        return loaded

    async def load_model(self, model_key: str) -> dict[str, Any]:
        normalized = model_key.strip()
        if not normalized:
            raise ValueError("model_key is required")
        data = await asyncio.to_thread(
            _http_json_request,
            f"{self._base_url}/api/v1/models/load",
            method="POST",
            payload={"model": normalized},
            timeout_sec=self._timeout_sec,
        )
        if not isinstance(data, dict):
            raise RuntimeError("LM Studio returned an invalid load response")
        return data

    async def unload_model(self, instance_id: str) -> dict[str, Any]:
        normalized = instance_id.strip()
        if not normalized:
            raise ValueError("instance_id is required")
        data = await asyncio.to_thread(
            _http_json_request,
            f"{self._base_url}/api/v1/models/unload",
            method="POST",
            payload={"instance_id": normalized},
            timeout_sec=self._timeout_sec,
        )
        if not isinstance(data, dict):
            raise RuntimeError("LM Studio returned an invalid unload response")
        return data

    async def ensure_model_loaded(self, explicit_model: str | None) -> str:
        desired = (explicit_model or "").strip()
        rows = await self._list_native_models()
        chat_model_keys: list[str] = []
        loaded_chat_instance_id: str | None = None
        matched_loaded_instance_id: str | None = None
        matched_model_key: str | None = None

        for row in rows:
            if not isinstance(row, dict):
                continue
            model_key = str(row.get("key") or "").strip()
            if not model_key:
                continue
            model_type = str(row.get("type") or "").strip().lower()
            kind = "embedding" if model_type == "embedding" or "embed" in model_key.lower() else "chat"
            if kind != "chat":
                continue
            chat_model_keys.append(model_key)
            instances = row.get("loaded_instances") if isinstance(row.get("loaded_instances"), list) else []
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                instance_id = str(inst.get("id") or "").strip()
                if not instance_id:
                    continue
                if loaded_chat_instance_id is None:
                    loaded_chat_instance_id = instance_id
                if desired and (instance_id == desired or model_key == desired):
                    matched_loaded_instance_id = instance_id
                    matched_model_key = model_key
                    break
            if desired and model_key == desired:
                matched_model_key = model_key
            if matched_loaded_instance_id is not None:
                break

        if matched_loaded_instance_id is not None:
            return matched_loaded_instance_id

        if desired:
            target_model_key = matched_model_key or desired
        else:
            if loaded_chat_instance_id is not None:
                return loaded_chat_instance_id
            if not chat_model_keys:
                raise RuntimeError("LM Studio has no available chat models.")
            target_model_key = chat_model_keys[0]

        loaded = await self.load_model(target_model_key)
        instance_id = str(loaded.get("instance_id") or "").strip()
        if not instance_id:
            raise RuntimeError(f"LM Studio loaded {target_model_key} but did not return an instance_id")
        return instance_id

    async def list_models(self) -> list[ProviderModel]:
        rows = await self._list_native_models()
        models: list[ProviderModel] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("key") or row.get("id") or "").strip()
            if not model_id:
                continue
            model_type = str(row.get("type") or "").strip().lower()
            lowered = model_id.lower()
            kind = "embedding" if model_type == "embedding" or "embed" in lowered or "embedding" in lowered else "chat"
            loaded_instances = row.get("loaded_instances") if isinstance(row.get("loaded_instances"), list) else []
            capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
            models.append(
                ProviderModel(
                    id=model_id,
                    display_name=str(row.get("display_name") or model_id),
                    provider=self.name,
                    description=str(row.get("description") or "").strip() or None,
                    kind=kind,
                    capabilities={
                        "chat": kind == "chat",
                        "embeddings": kind == "embedding",
                        "toolCalls": _lmstudio_tool_support(kind, capabilities),
                        "promptedToolUse": kind == "chat",
                        "streaming": kind == "chat",
                        "resume": False,
                    },
                    recommended_for=["chat"] if kind == "chat" else ["embeddings"],
                    metadata={
                        "publisher": row.get("publisher"),
                        "architecture": row.get("architecture"),
                        "format": row.get("format"),
                        "sizeBytes": row.get("size_bytes"),
                        "maxContextLength": row.get("max_context_length"),
                        "quantization": row.get("quantization"),
                        "variants": row.get("variants") if isinstance(row.get("variants"), list) else [],
                        "selectedVariant": row.get("selected_variant"),
                        "loadedInstanceCount": len(loaded_instances),
                        "loadedInstances": [
                            {
                                "instanceId": str(inst.get("id") or "").strip(),
                                "config": inst.get("config") if isinstance(inst.get("config"), dict) else {},
                            }
                            for inst in loaded_instances
                            if isinstance(inst, dict) and str(inst.get("id") or "").strip()
                        ],
                        "vision": capabilities.get("vision"),
                        "trainedForToolUse": capabilities.get("trained_for_tool_use"),
                        "reasoning": capabilities.get("reasoning") if isinstance(capabilities.get("reasoning"), dict) else None,
                    },
                )
            )
        return models

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        model_name = await self.ensure_model_loaded(model)
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        try:
            data = await asyncio.to_thread(
                _http_json_request,
                f"{self._base_url}/v1/chat/completions",
                method="POST",
                payload=payload,
                timeout_sec=self._timeout_sec,
                accept="application/json",
            )
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            detail = str(reason or exc).strip() or "unknown network failure"
            raise RuntimeError(f"LM Studio chat completion timed out or failed: {detail}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("LM Studio returned an invalid chat completion response")
        return data

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
        model_name = await self.ensure_model_loaded(model)
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
                if isinstance(exc, error.URLError):
                    reason = getattr(exc, "reason", None)
                    detail = str(reason or exc).strip() or "unknown network failure"
                    exc = RuntimeError(f"LM Studio streaming request timed out or failed: {detail}")
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
        except error.HTTPError as exc:
            reason = exc.read().decode("utf-8", errors="replace").strip() or exc.reason
            raise RuntimeError(f"LM Studio request failed: {reason}") from exc
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
