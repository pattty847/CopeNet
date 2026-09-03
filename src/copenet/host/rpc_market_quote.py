"""Authenticated, connection-scoped ticker quote operations."""

import re

from copenet.core.market.live_quote import LiveQuoteSubscription
from .rpc_schema import ResponseFrame, make_response_frame

MARKET_QUOTE_METHODS = {"market.quote.subscribe", "market.quote.unsubscribe"}


async def handle_market_quote(req, send_json, subscription: LiveQuoteSubscription | None):
    if subscription is None:
        raise ValueError("Live quotes require an authenticated WebSocket connection")
    params = req.params or {}
    subscription_id = params.get("subscriptionId")
    if not isinstance(subscription_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", subscription_id):
        raise ValueError("subscriptionId must be a non-empty identifier")
    if req.method == "market.quote.subscribe":
        symbol = params.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,31}", symbol):
            raise ValueError("Choose one valid Yahoo ticker symbol")
        await subscription.subscribe(symbol, subscription_id)
    else:
        await subscription.unsubscribe(subscription_id)
    await send_json(make_response_frame(ResponseFrame(id=req.id, ok=True, payload={"subscriptionId": subscription_id})))
