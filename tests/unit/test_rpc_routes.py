"""The literal RPC inventory retains every route and its invocation contract."""
from pathlib import Path
import inspect
from unittest.mock import AsyncMock
import pytest
from copenet.host.rpc_route_context import RpcContext, RpcRoute, build_routes
from copenet.host.rpc_routes import RPC_ROUTES, CHART_RPC_METHODS
from copenet.host.rpc_schema import RequestFrame


def test_rpc_inventory_matches_pre_extraction_methods():
    expected = set(Path(__file__).with_name("rpc_method_inventory.txt").read_text().splitlines())
    assert set(RPC_ROUTES) == expected
    assert len(CHART_RPC_METHODS) == 8


def test_duplicate_rpc_registration_is_rejected():
    route = RpcRoute(AsyncMock(), "standard")
    with pytest.raises(ValueError, match="duplicate RPC method"):
        build_routes([("test", route), ("test", route)])


@pytest.mark.parametrize("method", sorted(RPC_ROUTES))
async def test_route_arguments_match_current_handler_signature(method):
    route = RPC_ROUTES[method]
    ctx = RpcContext(RequestFrame("id", method, {"test": True}), AsyncMock(), object(), set(), AsyncMock(), object())
    calls = []
    async def record(*args, **kwargs):
        inspect.signature(route.handler).bind(*args, **kwargs)
        calls.append((args, kwargs))
    await RpcRoute(record, route.style).invoke(ctx)
    assert len(calls) == 1
    args, kwargs = calls[0]
    if route.style in {"chat", "broadcast"}:
        assert kwargs["broadcast"] is ctx.broadcast
    if route.style in {"chat", "fleet"}:
        assert args[3] is ctx.tasks
    if route.style == "fleet":
        assert args[-1] is ctx.broadcast
    if route.style == "quote":
        assert args == (ctx.request, ctx.send_json, ctx.quote_subscription)
    elif route.style != "context":
        assert args[0] == "id" and ctx.send_json in args


@pytest.mark.parametrize("params", [None, {"sessionKey": "test"}])
async def test_runtime_context_selects_the_current_handler(monkeypatch, params):
    import copenet.host.rpc_route_context as module
    get, resolve = AsyncMock(), AsyncMock()
    monkeypatch.setattr(module, "handle_runtime_context_get", get)
    monkeypatch.setattr(module, "handle_runtime_context_resolve", resolve)
    ctx = RpcContext(RequestFrame("id", "runtime.context", params), AsyncMock(), object(), set(), AsyncMock())
    await RPC_ROUTES["runtime.context"].invoke(ctx)
    assert get.await_count == (0 if params else 1)
    assert resolve.await_count == (1 if params else 0)
