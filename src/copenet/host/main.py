"""CopeNet host and admin CLI entry.

From root directory run:
  uv run copenet
  uv run copenet auth status --provider openai-codex
"""

from __future__ import annotations

import argparse
import json
import os

import uvicorn

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



def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "auth":
        _run_auth_command(args)
        return

    host = os.environ.get("COPNET_HOST", "127.0.0.1")
    port = int(os.environ.get("COPNET_PORT", "17123"))

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
