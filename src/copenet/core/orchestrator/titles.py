"""Background title generation helpers for the orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from copenet.core.model_request import ProviderTextRequest, collect_provider_text
from copenet.prompts import PromptPurpose

if TYPE_CHECKING:
    from . import Orchestrator


def schedule_title_generation(
    orchestrator: "Orchestrator",
    session_key: str,
    provider_name: str,
    model: str | None,
    first_user_message: str,
    first_assistant_message: str,
) -> None:
    async def run() -> None:
        try:
            title = await generate_title(
                orchestrator=orchestrator,
                provider_name=provider_name,
                model=model,
                first_user_message=first_user_message,
                first_assistant_message=first_assistant_message,
            )
            if not title:
                return
            current = orchestrator._session_store.get(session_key)
            if current is None or (current.title or "").strip():
                return
            orchestrator._session_store.rename_session(session_key=session_key, title=title)
        except Exception:
            return

    task = asyncio.create_task(run())
    orchestrator._background_tasks.add(task)
    task.add_done_callback(orchestrator._background_tasks.discard)


async def generate_title(
    orchestrator: "Orchestrator",
    provider_name: str,
    model: str | None,
    first_user_message: str,
    first_assistant_message: str,
) -> str | None:
    provider = orchestrator._providers.get(provider_name)
    if provider is None:
        return None

    title_prompt = (
        "Generate a concise chat session title from the conversation.\n"
        "Return only the title as plain text.\n"
        "Rules: 2 to 5 words, no quotes, no markdown, no list markers, avoid trailing punctuation.\n\n"
        f"User message:\n{first_user_message}\n\n"
        f"Assistant response:\n{first_assistant_message}\n"
    )
    title = await collect_provider_text(
        provider=provider,
        request=ProviderTextRequest(
            purpose=PromptPurpose.UTILITY,
            phase="session_title",
            prompt=title_prompt,
            model=model,
            system_prompt="You generate short session titles. Return only the title text.",
        ),
    )
    if not title:
        return None
    title = title.replace("\n", " ").strip().strip("\"'` ")
    title = " ".join(title.split())
    if not title:
        return None
    return title[:64].rstrip(" .,:;!-")
