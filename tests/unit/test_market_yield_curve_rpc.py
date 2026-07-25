from __future__ import annotations

import pytest

from copenet.host.rpc_market_yield_curve import handle_market_yield_curve_get


async def test_yield_curve_rpc_rejects_invalid_range() -> None:
    async def send_json(frame):
        raise AssertionError(f"unexpected response: {frame}")

    with pytest.raises(ValueError, match="range must be one of"):
        await handle_market_yield_curve_get("curve", {"range": "quarter"}, send_json, object())
