"""CopeNet host and admin CLI entry.

From root directory run:
  uv run copenet
  uv run copenet auth status --provider openai-codex
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import uvicorn

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.provider_auth import OPENAI_CODEX_PROVIDER_ID, OpenAICodexAuthService
from copenet.host.api import create_app


SUPPORTED_AUTH_PROVIDERS = {OPENAI_CODEX_PROVIDER_ID}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CopeNet host or provider auth helpers")
    subparsers = parser.add_subparsers(dest="command")

    auth = subparsers.add_parser("auth", help="Manage provider-backed auth")
    auth_subparsers = auth.add_subparsers(dest="auth_command", required=True)

    login = auth_subparsers.add_parser("login", help="Login to a provider auth flow")
    login.add_argument("--provider", default=OPENAI_CODEX_PROVIDER_ID)
    login.add_argument("--no-browser", action="store_true", help="Print the authorize URL instead of opening a browser")
    login.add_argument("--timeout-sec", type=float, default=300.0)

    status = auth_subparsers.add_parser("status", help="Show provider auth status")
    status.add_argument("--provider", default=OPENAI_CODEX_PROVIDER_ID)

    logout = auth_subparsers.add_parser("logout", help="Clear provider auth state")
    logout.add_argument("--provider", default=OPENAI_CODEX_PROVIDER_ID)

    chat = subparsers.add_parser("chat", help="Send messages through the real CopeNet orchestrator")
    chat_subparsers = chat.add_subparsers(dest="chat_command", required=True)

    send = chat_subparsers.add_parser("send", help="Create or continue a CopeNet chat session")
    send.add_argument("message", nargs="*", help="Message to send. If omitted, stdin is used.")
    send.add_argument("--session", default=os.environ.get("COPNET_CLI_SESSION", "69696469"), help="CopeNet session key to create or continue")
    send.add_argument("--provider", default=os.environ.get("COPNET_CLI_PROVIDER", OPENAI_CODEX_PROVIDER_ID))
    send.add_argument("--model", default=os.environ.get("COPNET_CLI_MODEL"))
    send.add_argument("--profile", dest="system_prompt_id", default=os.environ.get("COPNET_CLI_PROFILE"))
    send.add_argument("--task-mode", dest="task_prompt_id", default=os.environ.get("COPNET_CLI_TASK_MODE"))
    send.add_argument("--persona", dest="persona_id", default=os.environ.get("COPNET_CLI_PERSONA"))
    send.add_argument("--persona-flavor", dest="persona_flavor_id", default=os.environ.get("COPNET_CLI_PERSONA_FLAVOR"))
    send.add_argument("--persona-privacy", dest="persona_privacy_tier", default=os.environ.get("COPNET_CLI_PERSONA_PRIVACY"))
    send.add_argument("--workspace-root", default=os.environ.get("COPNET_CLI_WORKSPACE_ROOT"))
    send.add_argument("--no-tools", action="store_true", help="Disable CopeNet tool execution for this turn")
    send.add_argument("--json", action="store_true", help="Print captured events as JSON instead of a readable transcript")

    history = chat_subparsers.add_parser("history", help="Print recent messages from a CopeNet chat session")
    history.add_argument("--session", default=os.environ.get("COPNET_CLI_SESSION", "69696469"))
    history.add_argument("--limit", type=int, default=12)
    history.add_argument("--json", action="store_true")

    return parser



def _require_supported_provider(provider: str) -> str:
    normalized = provider.strip() or OPENAI_CODEX_PROVIDER_ID
    if normalized not in SUPPORTED_AUTH_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_AUTH_PROVIDERS))
        raise SystemExit(f"Unsupported auth provider: {normalized}. Supported providers: {supported}")
    return normalized



def _auth_service_for(provider: str) -> OpenAICodexAuthService:
    normalized = _require_supported_provider(provider)
    if normalized == OPENAI_CODEX_PROVIDER_ID:
        return OpenAICodexAuthService()
    raise SystemExit(f"Unsupported auth provider: {normalized}")



def _run_auth_command(args: argparse.Namespace) -> None:
    service = _auth_service_for(args.provider)
    if args.auth_command == "status":
        print(json.dumps(service.status(), indent=2, sort_keys=True))
        return
    if args.auth_command == "logout":
        print(json.dumps(service.logout(), indent=2, sort_keys=True))
        return
    if args.auth_command == "login":
        result = service.login_with_browser(timeout_sec=float(args.timeout_sec), open_browser=not bool(args.no_browser))
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    raise SystemExit(f"Unknown auth command: {args.auth_command}")


def _read_cli_message(args: argparse.Namespace) -> str:
    message = " ".join(args.message or []).strip()
    if message:
        return message
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("chat send requires a message argument or stdin input")


def _event_line(event: dict[str, Any]) -> str | None:
    state = str(event.get("state") or "")
    if state == "tool_called":
        tool_call = event.get("toolCall") if isinstance(event.get("toolCall"), dict) else {}
        tool_id = str(tool_call.get("toolId") or "tool")
        target = str(tool_call.get("target") or tool_call.get("hint") or "").strip()
        return f"[tool call] {tool_id}{f' -> {target}' if target else ''}"
    if state == "tool_result":
        tool = event.get("toolExecution") if isinstance(event.get("toolExecution"), dict) else {}
        tool_id = str(tool.get("toolId") or "tool")
        ok = "ok" if tool.get("ok") is not False else "failed"
        summary = str(tool.get("summary") or "").strip()
        lines = [f"[tool result] {tool_id} {ok}{f' - {summary}' if summary else ''}"]
        if tool.get("error"):
            lines.append(f"  error: {tool['error']}")
        preview = tool.get("preview")
        if isinstance(preview, dict):
            text = preview.get("preview") or preview.get("text")
            if isinstance(text, str) and text.strip():
                lines.append("  preview:")
                for row in text.strip().splitlines()[:20]:
                    lines.append(f"    {row}")
        return "\n".join(lines)
    if state == "delta":
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        content = str(message.get("content") or "").strip()
        return f"[assistant]\n{content}" if content else None
    if state == "reasoning_delta":
        text = str(event.get("text") or "").strip()
        return f"[thinking] {text}" if text else None
    if state == "final":
        return "[final]"
    if state == "error":
        return f"[error] {event.get('errorMessage') or event.get('error') or event.get('message') or ''}".strip()
    return None


async def _run_chat_send(args: argparse.Namespace) -> None:
    events: list[dict[str, Any]] = []
    orchestrator = Orchestrator()

    async def emit(payload: dict[str, Any]) -> None:
        events.append(dict(payload))
        if not args.json:
            line = _event_line(payload)
            if line:
                print(line)

    request = ChatSendRequest(
        session_key=str(args.session).strip(),
        message=_read_cli_message(args),
        provider=str(args.provider).strip() or OPENAI_CODEX_PROVIDER_ID,
        model=str(args.model).strip() if args.model else None,
        system_prompt_id=str(args.system_prompt_id).strip() if args.system_prompt_id else None,
        task_prompt_id=str(args.task_prompt_id).strip() if args.task_prompt_id else None,
        persona_id=str(args.persona_id).strip() if args.persona_id else None,
        persona_flavor_id=str(args.persona_flavor_id).strip() if args.persona_flavor_id else None,
        persona_privacy_tier=str(args.persona_privacy_tier).strip() if args.persona_privacy_tier else None,  # type: ignore[arg-type]
        workspace_root=str(args.workspace_root).strip() if args.workspace_root else None,
        allow_tools=not bool(args.no_tools),
    )
    if not args.json:
        model_suffix = f" / {request.model}" if request.model else ""
        print(f"[session] {request.session_key} ({request.provider}{model_suffix})")
    result = await orchestrator.send_chat(request, emit=emit)
    if args.json:
        print(json.dumps({"result": result, "events": events}, indent=2, sort_keys=True))


def _run_chat_history(args: argparse.Namespace) -> None:
    orchestrator = Orchestrator()
    messages = orchestrator.history(session_key=str(args.session).strip(), limit=int(args.limit))
    if args.json:
        print(json.dumps({"session": args.session, "messages": messages}, indent=2, sort_keys=True))
        return
    print(f"[session] {args.session}")
    if not messages:
        print("(no messages)")
        return
    for message in messages:
        role = message.get("role", "message")
        content = str(message.get("content") or "").strip()
        print(f"\n[{role}]")
        print(content)
        tool = message.get("toolExecution")
        if isinstance(tool, dict):
            print(_event_line({"state": "tool_result", "toolExecution": tool}) or "")


def _run_chat_command(args: argparse.Namespace) -> None:
    if args.chat_command == "send":
        asyncio.run(_run_chat_send(args))
        return
    if args.chat_command == "history":
        _run_chat_history(args)
        return
    raise SystemExit(f"Unknown chat command: {args.chat_command}")



def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "auth":
        _run_auth_command(args)
        return
    if args.command == "chat":
        _run_chat_command(args)
        return

    host = os.environ.get("COPNET_HOST", "127.0.0.1")
    port = int(os.environ.get("COPNET_PORT", "17123"))

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
