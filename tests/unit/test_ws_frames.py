"""Pre-parse envelope bounds preserve existing metadata-only chat requests."""
import json

import pytest

from copenet.host import ws_frames


def test_large_frame_is_rejected_before_json_decoding(monkeypatch):
    monkeypatch.setattr(ws_frames, "MAX_RPC_FRAME_BYTES", 64)
    def should_not_parse(value):
        pytest.fail("An oversized frame reached the JSON decoder")
    monkeypatch.setattr(ws_frames.json, "loads", should_not_parse)
    with pytest.raises(ws_frames.RpcFrameTooLarge):
        ws_frames.decode_rpc_frame(" " * 65)
    with pytest.raises(ws_frames.RpcFrameTooLarge):
        ws_frames.decode_rpc_frame("🚀" * 17)


def test_attachment_ids_remain_valid_and_malformed_json_is_actionable():
    frame = {"type": "req", "id": "synthetic", "method": "chat.send", "params": {
        "sessionKey": "test", "message": "Inspect the attachment", "attachmentIds": ["synthetic-image"],
    }}
    assert ws_frames.decode_rpc_frame(json.dumps(frame)) == frame
    with pytest.raises(ValueError, match="valid JSON"):
        ws_frames.decode_rpc_frame('{"broken":')
