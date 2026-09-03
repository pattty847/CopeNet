"""Yahoo's quote wire format, decoded with yfinance's canonical protobuf schema."""

import base64
import json

from google.protobuf.json_format import MessageToDict

YAHOO_STREAM_URL = "wss://streamer.finance.yahoo.com/?version=2"


def decode_yahoo_stream_message(raw_message: str | bytes) -> dict:
    from yfinance.pricing_pb2 import PricingData

    envelope = json.loads(raw_message)
    encoded = envelope.get("message")
    if not encoded:
        raise ValueError("stream envelope did not contain a message")
    pricing_data = PricingData()
    pricing_data.ParseFromString(base64.b64decode(encoded))
    return MessageToDict(pricing_data, preserving_proto_field_name=True)
