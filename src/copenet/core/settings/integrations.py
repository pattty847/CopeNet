"""Which optional data integrations this host is configured for.

Each check reports PRESENCE only. A key's value never leaves the process, so the Settings
panel can say "FRED: ready" without the browser ever holding a credential. Setup stays in
`.env` (or `.copenet.env`) because that is where every one of these is read from; the panel
tells the operator which variable to add rather than offering a field that writes secrets.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from importlib.util import find_spec

from copenet.core.market.economic_calendar import trading_economics_api_key
from copenet.core.market.fred import fred_api_key
from copenet.core.market.webull.config import load_webull_config
from copenet.core.messaging.telegram_delivery import telegram_transport_configured


@dataclass(frozen=True)
class IntegrationStatus:
    id: str
    label: str
    purpose: str
    ready: bool
    #: What to do when not ready: an env variable to set or a command to run.
    setup: str

    def to_public_dict(self) -> dict:
        return asdict(self)


def integration_statuses() -> list[IntegrationStatus]:
    return [
        IntegrationStatus(
            "sec", "SEC EDGAR", "Filings, fundamentals and insider trades in Market",
            find_spec("copetech_sec") is not None, "./scripts/setup.sh --with-sec",
        ),
        IntegrationStatus(
            "fred", "FRED", "Macro series for the brief and the agent's macro tools",
            fred_api_key() is not None, "FRED_API_KEY",
        ),
        IntegrationStatus(
            "trading-economics", "Trading Economics", "Economic calendar in the morning brief",
            trading_economics_api_key() is not None, "TRADING_ECONOMICS_API_KEY",
        ),
        IntegrationStatus(
            "webull", "Webull (read-only)", "Positions and fills for cost lines and scenarios",
            load_webull_config() is not None, "WEBULL_KEY and WEBULL_SECRET",
        ),
        IntegrationStatus(
            "telegram", "Telegram", "Alert delivery to your phone",
            telegram_transport_configured(), "COPNET_TELEGRAM_BOT_TOKEN",
        ),
        IntegrationStatus(
            "nasa", "NASA", "Picture of the Day on Home",
            bool(os.environ.get("NASA_API_KEY", "").strip()), "NASA_API_KEY",
        ),
    ]
