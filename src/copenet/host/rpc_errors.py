"""Shared exception boundary for authenticated RPC dispatch."""

from .rpc_schema import ResponseFrame, RpcError, make_response_frame


async def respond_rpc_errors(request_id, send_json, operation):
    try:
        await operation
    except ValueError as exc:
        await send_json(make_response_frame(ResponseFrame(
            id=request_id, ok=False,
            error=RpcError(code="INVALID_REQUEST", message=str(exc) or "invalid request"),
        )))
    except Exception as exc:
        await send_json(make_response_frame(ResponseFrame(
            id=request_id, ok=False,
            error=RpcError(code="INTERNAL_ERROR", message=f"{exc.__class__.__name__}: {exc}"),
        )))
