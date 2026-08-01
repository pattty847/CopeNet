"""Unit tests for the Webull read-only portfolio sync layer (no network, no SDK)."""

from __future__ import annotations

from copenet.core.market.webull.config import WebullConfig, load_webull_config
from copenet.core.market.webull.context_pack import MODEL_INSTRUCTION_HEADER, build_portfolio_context_pack
from copenet.core.market.webull.sync import WebullPosition, WebullSnapshot, finalize, normalize_balance, normalize_positions


def test_config_never_prints_secrets(monkeypatch):
    monkeypatch.setenv("WEBULL_KEY", "super-secret-key-123")
    monkeypatch.setenv("WEBULL_SECRET", "super-secret-secret-456")
    monkeypatch.delenv("WEBULL_ENV", raising=False)
    config = load_webull_config()
    assert config is not None
    assert config.env == "production"
    for rendered in (repr(config), str(config), f"{config}"):
        assert "super-secret" not in rendered
        assert "***" in rendered


def test_config_absent_returns_none(monkeypatch):
    monkeypatch.delenv("WEBULL_KEY", raising=False)
    monkeypatch.delenv("WEBULL_SECRET", raising=False)
    assert load_webull_config() is None


def test_normalize_positions_tolerates_vendor_key_variants():
    payload = {
        "data": [
            # Synthetic vendor-shaped fixtures: the P&L rate is a decimal fraction.
            {"symbol": "aaa", "quantity": "12.5", "cost_price": "100.00", "unrealized_profit_loss_rate": "-0.125"},
            {"ticker": "BBB", "qty": 4, "avgCost": 25.0},
            {"note": "row with no symbol should be skipped"},
        ]
    }
    positions, warnings = normalize_positions(payload)
    assert [p.symbol for p in positions] == ["AAA", "BBB"]
    assert positions[0].quantity == 12.5
    assert positions[0].avg_cost == 100.0
    assert positions[0].unrealized_pl_pct == -12.5  # fraction -> percent
    assert positions[1].avg_cost == 25.0
    assert len(warnings) == 1  # the skipped row is reported, not silently dropped


def test_normalize_balance_vendor_shape():
    # Synthetic values in the exact key structure returned by the vendor.
    payload = {
        "total_asset_currency": "USD",
        "total_net_liquidation_value": "10,000.00",
        "total_market_value": "9000.00",
        "total_cash_balance": "1,000.00",
        "account_currency_assets": [
            {"currency": "USD", "cash_balance": "1,000.00", "settled_cash": "900.00", "buying_power": "800.00"}
        ],
    }
    balance = normalize_balance(payload)
    assert balance["total_equity"] == 10000.0
    assert balance["cash"] == 1000.0
    assert balance["buying_power"] == 800.0
    assert balance["currency"] == "USD"
    empty = normalize_balance({})
    assert empty["total_equity"] is None  # missing data stays None, never fabricated


def test_finalize_derives_value_pnl_allocation():
    positions = [
        WebullPosition(symbol="GOOG", quantity=2.0, avg_cost=200.0, last_price=350.0),
        WebullPosition(symbol="SOFI", quantity=10.0, avg_cost=22.0, last_price=18.0),
    ]
    finalize(positions, total_equity=None)
    goog = positions[0]
    assert goog.market_value == 700.0
    assert goog.unrealized_pl == 300.0
    assert goog.unrealized_pl_pct == 75.0
    assert goog.allocation_pct is not None and goog.allocation_pct > 75  # 700 of 880


def test_context_pack_redaction_and_content():
    snapshot = WebullSnapshot(
        account_id_masked="***1234",
        synced_at="2026-07-01T00:00:00Z",
        total_equity=10000.0,
        cash=1000.0,
        buying_power=800.0,
        currency="USD",
        positions=[
            WebullPosition(symbol="AAA", quantity=30.0, avg_cost=100.0, last_price=150.0, market_value=4500.0, unrealized_pl=1500.0, unrealized_pl_pct=50.0, allocation_pct=45.0, price_source="yfinance"),
            WebullPosition(symbol="BBB", quantity=10.0, avg_cost=100.0, last_price=60.0, market_value=600.0, unrealized_pl=-400.0, unrealized_pl_pct=-40.0, allocation_pct=6.0, warnings=["thin volume"]),
        ],
        warnings=["one row skipped"],
    ).to_dict()
    # poison the dict with strings that must NEVER surface — proves whitelisting, not luck
    snapshot["app_key"] = "LEAKED-KEY"
    snapshot["access_token"] = "LEAKED-TOKEN"
    pack = build_portfolio_context_pack(snapshot)

    assert MODEL_INSTRUCTION_HEADER.splitlines()[0] in pack
    assert "***1234" in pack and "LEAKED" not in pack
    assert "AAA" in pack and "$150.00" in pack
    assert "oversized position: AAA" in pack
    assert "large unrealized winner: AAA" in pack
    assert "large unrealized loser: BBB" in pack
    assert "data gap" in pack  # warnings surface as flags
    assert "account data source: Webull" in pack


def test_context_pack_handles_missing_data():
    snapshot = WebullSnapshot(
        account_id_masked="***9",
        synced_at="2026-07-01T00:00:00Z",
        total_equity=None,
        cash=None,
        buying_power=None,
        currency=None,
        positions=[WebullPosition(symbol="CRWV", quantity=1.0, warnings=["no price available (webull + yfinance both missing)"])],
    ).to_dict()
    pack = build_portfolio_context_pack(snapshot)
    assert "n/a" in pack
    assert "no price available" in pack
