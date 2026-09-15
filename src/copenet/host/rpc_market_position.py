"""Stored position and execution context for one ticker."""
import asyncio
import re

from copenet.core.market.positions import ticker_position
from copenet.core.market.runtime import resolve_market_runtime
from .rpc_schema import ResponseFrame, make_response_frame


async def handle_market_position_get(request_id, params, send_json, orchestrator):
    symbol = (params or {}).get('symbol')
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,19}', symbol):
        raise ValueError('A valid uppercase symbol is required')
    runtime = resolve_market_runtime(orchestrator)
    history = await asyncio.to_thread(runtime.prices.load, symbol)
    payload = await asyncio.to_thread(ticker_position, symbol, history)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
