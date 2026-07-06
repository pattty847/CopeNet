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
from pathlib import Path
import sys
from typing import Any

import uvicorn

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.nasa.wallpaper import (
    apply_apod_wallpaper,
    install_launch_agent,
    launch_agent_status,
    uninstall_launch_agent,
)
from copenet.core.provider_auth import OPENAI_CODEX_PROVIDER_ID, OpenAICodexAuthService


def _resolve_bind_host(raw: str) -> str:
    """Resolve the uvicorn bind host, with a ``tailscale`` convenience value.

    ``COPNET_HOST=tailscale`` binds to this machine's Tailscale IPv4 so the agent
    is reachable from your phone/laptop anywhere on the tailnet — and ONLY the
    tailnet (unlike ``0.0.0.0``, which also exposes it to local wifi). Any other
    value (an explicit IP, ``0.0.0.0``, the default ``127.0.0.1``) passes through.
    """
    value = (raw or "").strip()
    if value.lower() != "tailscale":
        return value or "127.0.0.1"

    import shutil
    import subprocess

    candidates = ["tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"]
    for exe in candidates:
        path = exe if exe.startswith("/") else shutil.which(exe)
        if not path:
            continue
        try:
            out = subprocess.run([path, "ip", "-4"], capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        for line in (out.stdout or "").splitlines():
            ip = line.strip()
            if ip:
                return ip
    raise SystemExit(
        "COPNET_HOST=tailscale: could not resolve a Tailscale IPv4 — is Tailscale running and logged in?"
    )
from copenet.host.api import create_app


SUPPORTED_AUTH_PROVIDERS = {OPENAI_CODEX_PROVIDER_ID}


_HOST_EPILOG = """\
running the host + UI (no subcommand):
  copenet                          serve on 127.0.0.1:17123 (open http://localhost:17123)
  COPNET_HOST=tailscale copenet    serve privately on your tailnet IP (not local wifi)
  COPNET_PORT=17124 copenet        use a custom port
  COPNET_WORKDIR=/path copenet     set the workspace root for full-access file/shell tools

environment variables:
  COPNET_HOST      bind host: 127.0.0.1 (default) | tailscale | 0.0.0.0 | explicit IP
  COPNET_PORT      bind port (default 17123)
  COPNET_WORKDIR   workspace root for tools (default: current directory)
  COPNET_TOKEN     gateway auth token (default: dev-token)
  COPNET_TRACE     set to 1 to write per-run JSONL traces to ~/.copenet/logs/runs/

tailnet HTTPS (needed for mic / getUserMedia from other devices):
  enable Serve in the Tailscale admin, then: tailscale serve --bg --https=443 17123
  (bind CopeNet to 127.0.0.1 first so only the tailnet-scoped proxy reaches it)
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the CopeNet host or provider auth helpers",
        epilog=_HOST_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help", help="Show the self-describing feature guide (run, tailnet, test prompts, auth)")

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

    nasa = subparsers.add_parser("nasa", help="NASA data helpers")
    nasa_subparsers = nasa.add_subparsers(dest="nasa_command", required=True)
    wallpaper = nasa_subparsers.add_parser("wallpaper", help="Manage NASA APOD desktop wallpaper")
    wallpaper_subparsers = wallpaper.add_subparsers(dest="wallpaper_command", required=True)

    apply_wallpaper = wallpaper_subparsers.add_parser("apply", help="Fetch APOD and apply it as the macOS wallpaper")
    apply_wallpaper.add_argument("--date", default=None, help="APOD date to fetch (YYYY-MM-DD); defaults to today")
    apply_wallpaper.add_argument("--refresh", action="store_true", help="Refresh the APOD record even if cached")
    apply_wallpaper.add_argument("--json", action="store_true", help="Print structured JSON output")

    wallpaper_subparsers.add_parser("install-agent", help="Install the morning APOD wallpaper LaunchAgent")
    wallpaper_subparsers.add_parser("uninstall-agent", help="Remove the APOD wallpaper LaunchAgent")
    wallpaper_subparsers.add_parser("status", help="Show APOD wallpaper LaunchAgent status")

    webull = subparsers.add_parser("webull", help="Read-only Webull portfolio sync (no trading)")
    webull_subparsers = webull.add_subparsers(dest="webull_command", required=True)
    webull_subparsers.add_parser("auth", help="Authenticate — approve the request in your Webull mobile app when prompted")
    webull_subparsers.add_parser("status", help="Show auth/token state, selected account, and last sync (no secrets)")
    webull_subparsers.add_parser("accounts", help="List available Webull accounts")
    webull_select = webull_subparsers.add_parser("select", help="Select the default account for syncs")
    webull_select.add_argument("--account-id", required=True, help="Webull account id from `webull accounts`")
    webull_subparsers.add_parser("sync", help="Pull balances + positions (read-only) into the local snapshot")
    webull_subparsers.add_parser("context", help="Dry-run: print the sanitized AI portfolio context pack (never sends anything)")

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


def _run_nasa_wallpaper_command(args: argparse.Namespace) -> None:
    if args.wallpaper_command == "apply":
        result = apply_apod_wallpaper(date=args.date, refresh=bool(args.refresh))
        if args.json:
            print(json.dumps(result.to_json(), indent=2, sort_keys=True))
            return
        print(_wallpaper_result_line(result))
        return
    if args.wallpaper_command == "install-agent":
        plist = install_launch_agent(working_directory=Path.cwd())
        print(f"installed {plist}")
        return
    if args.wallpaper_command == "uninstall-agent":
        plist = uninstall_launch_agent()
        print(f"removed {plist}")
        return
    if args.wallpaper_command == "status":
        status = launch_agent_status()
        installed = "installed" if status["installed"] else "not installed"
        loaded = "loaded" if status["loaded"] else "not loaded"
        print(f"{installed}, {loaded}: {status['path']}")
        return
    raise SystemExit(f"Unknown NASA wallpaper command: {args.wallpaper_command}")


def _run_nasa_command(args: argparse.Namespace) -> None:
    if args.nasa_command == "wallpaper":
        _run_nasa_wallpaper_command(args)
        return
    raise SystemExit(f"Unknown NASA command: {args.nasa_command}")


def _wallpaper_result_line(result) -> str:
    if result.status == "applied" and result.date and result.title:
        return f"applied {result.date}: {result.title}"
    if result.status == "fallback_applied" and result.date and result.title:
        return f"today is a video; applied previous image {result.date}: {result.title}"
    if result.reason == "missing_api_key":
        return "NASA_API_KEY is not set"
    if result.reason == "unsupported_platform":
        return "unsupported platform: macOS required"
    if result.status == "skipped":
        return "NASA APOD not ready; kept existing wallpaper"
    if result.error:
        return result.error
    return "NASA APOD not ready; kept existing wallpaper"



def _run_webull_command(args) -> None:
    """Read-only Webull portfolio sync CLI. Never prints credentials or tokens."""
    import json as _json

    from copenet.core.market.webull.client import auth_status, select_account, selected_account
    from copenet.core.market.webull.config import load_webull_config
    from copenet.core.market.webull.sync import load_snapshot

    config = load_webull_config()
    if args.webull_command == "status":
        snapshot = load_snapshot()
        print("Webull configured:", "yes" if config else "no (set WEBULL_KEY / WEBULL_SECRET in .env)")
        if config:
            print("Environment:", config.env)
        state = auth_status()
        print("Auth:", state["status"], f"(token valid until {state['expires']})" if state.get("expires") else "")
        account = selected_account()
        print("Selected account:", account["accountId"] if account else "none — run `copenet webull accounts` then `select`")
        print("Last sync:", snapshot.get("synced_at") if snapshot else "never", f"({len(snapshot.get('positions', []))} positions)" if snapshot else "")
        return
    if config is None:
        print("Webull is not configured. Add WEBULL_KEY and WEBULL_SECRET to .env first.")
        return
    if args.webull_command == "auth":
        from copenet.core.market.webull.client import build_trade_client

        print("Starting Webull authentication…")
        print(">>> Open the Webull app on your PHONE and APPROVE the API access request (this polls up to ~5 minutes).")
        build_trade_client(config)
        state = auth_status()
        print("Auth:", state["status"], f"(token valid until {state['expires']})" if state.get("expires") else "")
        return
    if args.webull_command == "accounts":
        from copenet.core.market.webull.client import build_trade_client
        from copenet.core.market.webull.sync import list_accounts

        accounts = list_accounts(build_trade_client(config))
        if not accounts:
            print("No accounts returned.")
            return
        for account in accounts:
            print(f"  {account['accountId']}  {account.get('accountType', '')}  {account.get('brokerName', '')}  {account.get('currency', '')}")
        print("Select one with: uv run copenet webull select --account-id <id>")
        return
    if args.webull_command == "select":
        payload = select_account(args.account_id)
        print("Selected account:", payload["accountId"])
        return
    if args.webull_command == "sync":
        from copenet.core.market.webull.client import build_trade_client
        from copenet.core.market.webull.sync import fetch_snapshot

        account = selected_account()
        if account is None:
            print("No account selected — run `copenet webull accounts` then `copenet webull select --account-id <id>`.")
            return
        snapshot = fetch_snapshot(build_trade_client(config), account["accountId"])
        print(f"Fetched {len(snapshot.positions)} positions · equity {snapshot.total_equity} · synced {snapshot.synced_at}")
        for warning in snapshot.warnings:
            print("  warning:", warning)
        return
    if args.webull_command == "context":
        from copenet.core.market.webull.context_pack import build_portfolio_context_pack

        snapshot = load_snapshot()
        if snapshot is None:
            print("No snapshot yet — run `copenet webull sync` first.")
            return
        pack = build_portfolio_context_pack(snapshot)
        for needle in (config.app_key, config.app_secret):
            if needle and needle in pack:
                raise SystemExit("REDACTION FAILURE: a credential appeared in the context pack — aborting.")
        print(pack)
        print("\n--- dry run only: nothing was sent to any model; no secrets present (verified) ---")
        return
    print(_json.dumps({"error": f"unknown webull command {args.webull_command}"}))


def main() -> None:
    # Load `.env` first so secrets like NASA_API_KEY are present before any
    # Orchestrator (and its provider/store init) is constructed below.
    from copenet._env import load_project_env

    load_project_env()

    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "help":
        from copenet.host.cli_help import render_guide

        print(render_guide(parser))
        return
    if args.command == "auth":
        _run_auth_command(args)
        return
    if args.command == "chat":
        _run_chat_command(args)
        return
    if args.command == "nasa":
        _run_nasa_command(args)
        return
    if args.command == "webull":
        _run_webull_command(args)
        return

    host = _resolve_bind_host(os.environ.get("COPNET_HOST", "127.0.0.1"))
    port = int(os.environ.get("COPNET_PORT", "17123"))

    app = create_app()
    if host != "127.0.0.1":
        # Reachable beyond loopback — print the URL and a security reminder, since
        # CopeNet has no auth and (in full-access) real shell power.
        scope = "your tailnet" if host.startswith("100.") else "this network"
        print(f"\n  CopeNet is reachable from {scope} at:  http://{host}:{port}")
        if host == "0.0.0.0":
            print("  WARNING: 0.0.0.0 exposes CopeNet on ALL interfaces (incl. local wifi).")
            print("  Prefer COPNET_HOST=tailscale to keep it private to your tailnet.\n")
        else:
            print("  (only devices on your tailnet can reach it — keep it that way)\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
