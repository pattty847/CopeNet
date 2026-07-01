"""Webull SDK client construction + auth state — the only file that touches the SDK's auth.

Notes grounded in the SDK source (webull-openapi-python-sdk 2.0.12):
- `TradeClient(api_client)` runs the full token flow at construction: load local token → create/
  refresh on the server → if not yet approved, poll (default 300s @ 5s) while the user approves the
  request in the Webull mobile app. First-time auth therefore BLOCKS until approval — callers must
  run it in a thread and tell the user to open their Webull app.
- The SDK persists the token itself (token/expiry/status, token masked in its logs) under the
  directory given to `api_client.set_token_dir(...)` — we point that at ~/.copenet.
- TradeClient would otherwise install a file logger writing `webull_trade_sdk.log` into the CWD;
  we pre-set loggers so SDK logs land under ~/.copenet/logs at WARNING.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import WebullConfig

logger = logging.getLogger(__name__)


def webull_data_dir() -> Path:
    base = Path(os.environ.get("COPNET_HOME", Path.home() / ".copenet")) / "data" / "market" / "webull"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _token_dir() -> Path:
    path = webull_data_dir() / "token"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _account_file() -> Path:
    return webull_data_dir() / "account.json"


def build_trade_client(config: WebullConfig):
    """Construct the SDK trade client. BLOCKS during first-time app approval — call in a thread."""
    from webull.core.client import ApiClient
    from webull.trade.trade_client import TradeClient

    api_client = ApiClient(config.app_key, config.app_secret, "us")
    if config.uat_host:
        api_client.add_endpoint("us", config.uat_host)
    api_client.set_token_dir(str(_token_dir()))

    # Route SDK logging to ~/.copenet/logs at WARNING (never stdout, never the repo CWD).
    log_dir = Path(os.environ.get("COPNET_HOME", Path.home() / ".copenet")) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    api_client.set_file_logger(path=str(log_dir / "webull_sdk.log"), log_level=logging.WARNING)

    logger.info("Loaded Webull config (env=%s); building trade client", config.env)
    return TradeClient(api_client)


def _find_token_file() -> Path | None:
    root = _token_dir()
    candidates = sorted(root.rglob("*")) if root.exists() else []
    for path in candidates:
        if path.is_file():
            return path
    return None


def auth_status() -> dict[str, Any]:
    """Token state WITHOUT the token value: {authenticated, status, expires, tokenPath}."""
    path = _find_token_file()
    if path is None:
        return {"authenticated": False, "status": "no_token", "expires": None}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"authenticated": False, "status": "unreadable_token_file", "expires": None}
    # SDK token file format: line1 token, line2 expires, line3 status. NEVER return line 1.
    expires = lines[1].strip() if len(lines) > 1 else None
    status = lines[2].strip() if len(lines) > 2 else "unknown"
    return {
        "authenticated": status == "NORMAL",
        "status": status,
        "expires": int(expires) if expires and expires.isdigit() else expires,
    }


def selected_account() -> dict[str, Any] | None:
    path = _account_file()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("accountId") else None


def select_account(account_id: str, *, nickname: str | None = None) -> dict[str, Any]:
    payload = {"accountId": str(account_id), "nickname": nickname or ""}
    _account_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def mask_account_id(account_id: str) -> str:
    text = str(account_id)
    return f"***{text[-4:]}" if len(text) > 4 else "***"
