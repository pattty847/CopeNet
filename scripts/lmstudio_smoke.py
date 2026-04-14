from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib import request

from copenet.providers.local_http import LmStudioProvider


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _detect_models(base_url: str) -> list[str]:
    req = request.Request(f"{base_url.rstrip('/')}/api/v1/models", headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    models = []
    for row in data.get("models", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "llm":
            continue
        key = str(row.get("key") or "").strip()
        if key:
            models.append(key)
    return models


async def _run(base_url: str, primary_model: str | None, secondary_model: str | None, prompt: str, skip_switch: bool) -> int:
    provider = LmStudioProvider(base_url=base_url)
    models = await provider.list_models()
    chat_models = [model.id for model in models if model.kind == "chat"]
    if not chat_models:
        print("No LM Studio chat models found.", file=sys.stderr)
        return 2

    first = primary_model or chat_models[0]
    second = None if skip_switch else (secondary_model or next((model for model in chat_models if model != first), None))

    print(f"LM Studio base URL: {base_url}")
    print(f"Chat models: {', '.join(chat_models)}")
    print(f"Primary model: {first}")
    if second:
        print(f"Secondary model: {second}")

    first_instance = await provider.ensure_model_loaded(first)
    reused_instance = await provider.ensure_model_loaded(first)
    assert first_instance == reused_instance, "expected repeated ensure_model_loaded() to reuse the same instance"

    chunks = []
    async for event in provider.run(
        prompt=prompt,
        provider_session_id="smoke-run",
        abort_event=asyncio.Event(),
        model=first,
        system_prompt="Reply briefly.",
    ):
        if event.text:
            chunks.append(event.text)

    response_text = "".join(chunks).strip()
    if not response_text:
        raise AssertionError("LM Studio returned an empty response")

    second_instance = None
    if second:
        second_instance = await provider.ensure_model_loaded(second)
        assert second_instance != first_instance, "expected switching models to produce a different loaded instance"

    unloaded = await provider.unload_model(first_instance)
    assert str(unloaded.get("instance_id") or "").strip() == first_instance
    if second_instance:
        unloaded_second = await provider.unload_model(second_instance)
        assert str(unloaded_second.get("instance_id") or "").strip() == second_instance

    print(f"Reused instance: {reused_instance}")
    if second_instance:
        print(f"Switched instance: {second_instance}")
    print(f"Response preview: {response_text[:200]}")
    print("LM Studio smoke passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live LM Studio smoke test for CopeNet provider lifecycle support")
    parser.add_argument("--base-url", default=os.environ.get("COPNET_LM_STUDIO_BASE_URL", "http://127.0.0.1:1234"))
    parser.add_argument("--model", default=os.environ.get("COPNET_LM_STUDIO_SMOKE_MODEL"))
    parser.add_argument("--secondary-model", default=os.environ.get("COPNET_LM_STUDIO_SMOKE_SECONDARY_MODEL"))
    parser.add_argument("--prompt", default=os.environ.get("COPNET_LM_STUDIO_SMOKE_PROMPT", "Say hello in one sentence."))
    parser.add_argument("--skip-switch", action="store_true", help="Skip the second-model switch step")
    args = parser.parse_args()

    if not _env_flag("COPNET_RUN_LM_STUDIO_SMOKE"):
        print("Skipping LM Studio smoke. Set COPNET_RUN_LM_STUDIO_SMOKE=1 to enable.")
        return 0

    try:
        detected = _detect_models(args.base_url)
        if not detected:
            print("Skipping LM Studio smoke. No chat models detected.")
            return 0
    except Exception as exc:
        print(f"Skipping LM Studio smoke. LM Studio is unavailable at {args.base_url}: {exc}")
        return 0

    return asyncio.run(_run(args.base_url, args.model, args.secondary_model, args.prompt, args.skip_switch))


if __name__ == "__main__":
    raise SystemExit(main())
