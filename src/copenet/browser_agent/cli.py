"""CLI demo runner for the deterministic browser-agent prototype."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from copenet._paths import default_run_logs_dir

from .decision import CopeNetProviderDecisionAdapter, ScriptedDecisionProvider, provider_from_name
from .loop import BrowserAgentConfig, BrowserAgentLoop
from .models import BrowserAction
from .observer import PageObserver
from .session import BrowserSession
from .trace import BrowserTraceRecorder
from .validator import ActionValidator


def _scripted_provider(name: str) -> ScriptedDecisionProvider:
    if name == "github-search":
        return ScriptedDecisionProvider(
            actions=[
                BrowserAction(
                    action="click",
                    element_id="e1",
                    reason="Use the highest-ranked search affordance",
                    confidence=0.8,
                    risk=2,
                ),
                BrowserAction(
                    action="type_text",
                    element_id="e1",
                    text="CopeNet",
                    reason="Type the target repository/query",
                    confidence=0.8,
                    risk=2,
                ),
                BrowserAction(
                    action="press_key",
                    key="Enter",
                    reason="Submit the search",
                    confidence=0.9,
                    risk=2,
                ),
                BrowserAction(
                    action="ask_user",
                    question="Scripted demo reached the handoff point; use provider-backed mode for full browsing.",
                    reason="Stop safely after proving the loop mechanics",
                    confidence=0.9,
                    risk=1,
                ),
            ]
        )
    return ScriptedDecisionProvider(
        actions=[
            BrowserAction(
                action="finish",
                summary="Observed the page successfully; scripted demo complete.",
                reason="Minimal safe scripted completion",
                confidence=1.0,
                risk=0,
            )
        ]
    )


async def run_demo(
    *,
    task: str,
    start_url: str,
    headless: bool = True,
    max_steps: int = 8,
    scripted_demo: str | None = None,
    provider_name: str | None = None,
    model: str | None = None,
) -> int:
    artifact_dir = Path.cwd() / "tmp" / "browser-agent"
    trace_root = default_run_logs_dir() / "browser-agent"
    session = BrowserSession(headless=headless, artifact_dir=artifact_dir)
    observer = PageObserver()
    validator = ActionValidator()
    recorder = BrowserTraceRecorder(trace_root)
    if scripted_demo:
        decision_provider = _scripted_provider(scripted_demo)
    else:
        provider = provider_from_name(provider_name or "copenet")
        resolved_model = model or (await provider.list_models())[0].id
        decision_provider = CopeNetProviderDecisionAdapter(provider=provider, model=resolved_model)
    loop = BrowserAgentLoop(
        session=session,
        observer=observer,
        decision_provider=decision_provider,
        validator=validator,
        trace_recorder=recorder,
        config=BrowserAgentConfig(max_steps=max_steps, required_terms=("copenet",)),
    )

    await session.start()
    try:
        outcome = await loop.run(task=task, start_url=start_url)
        print(json.dumps(outcome.last_state.to_model_dict(), ensure_ascii=False, indent=2))
        print(f"\nStop: {outcome.stop.reason} — {outcome.stop.summary}")
        print(f"Trace: {outcome.trace_path}")
        return 0
    finally:
        await session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CopeNet browser-agent prototype demo")
    parser.add_argument("--task", help="Task for the browser agent", required=True)
    parser.add_argument("--start-url", help="Initial URL", required=True)
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum browser-agent steps")
    parser.add_argument("--scripted-demo", help="Use a scripted decision provider demo")
    parser.add_argument("--provider", help="Decision provider name (copenet/codex-cli/lm-studio/ollama)")
    parser.add_argument("--model", help="Explicit provider model id")
    parser.add_argument("--headed", action="store_true", help="Run Chromium with a visible window")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run_demo(
                task=args.task,
                start_url=args.start_url,
                headless=not args.headed,
                max_steps=args.max_steps,
                scripted_demo=args.scripted_demo,
                provider_name=args.provider,
                model=args.model,
            )
        )
    )


if __name__ == "__main__":
    main()
