"""Bound JSON allocation before decoding WebSocket request frames."""
import json

# Match the host transport's default envelope. Attachments use HTTP upload and
# chat.send carries attachment IDs, so the 20 MiB attachment limit is unchanged.
MAX_RPC_FRAME_BYTES = 16 * 1024 * 1024


class RpcFrameTooLarge(ValueError):
    pass


def decode_rpc_frame(text: str):
    if len(text) > MAX_RPC_FRAME_BYTES or len(text.encode("utf-8")) > MAX_RPC_FRAME_BYTES:
        raise RpcFrameTooLarge("RPC frame exceeds 16 MiB; reduce captured resources before retrying")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Request frame must contain valid JSON") from exc
