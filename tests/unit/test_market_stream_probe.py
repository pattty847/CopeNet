from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from copenet.core.market.stream_probe import (
    StreamProbeConfig,
    connection_error_record,
    record_message_stats,
    validate_stream_probe_config,
    vendor_message_lag_ms,
)


def _config(**overrides) -> StreamProbeConfig:
    values = {
        "symbols": ("AAPL", "SPY"),
        "start_at": datetime(2026, 7, 30, 13, 20, tzinfo=UTC),
        "end_at": datetime(2026, 7, 30, 20, 10, tzinfo=UTC),
    }
    values.update(overrides)
    return StreamProbeConfig(**values)


def test_validate_stream_probe_config_requires_a_bounded_aware_window() -> None:
    validate_stream_probe_config(_config())

    with pytest.raises(ValueError, match="later"):
        validate_stream_probe_config(
            _config(end_at=datetime(2026, 7, 30, 13, 20, tzinfo=UTC))
        )
    with pytest.raises(ValueError, match="timezone"):
        validate_stream_probe_config(
            _config(start_at=datetime(2026, 7, 30, 13, 20))
        )


def test_record_message_stats_keeps_field_and_vendor_time_evidence() -> None:
    stats = {"message_count": 0, "symbols": {}}
    received_at = datetime(2026, 7, 30, 13, 30, 1, tzinfo=UTC)

    record_message_stats(
        stats,
        {"id": "AAPL", "price": 210.25, "time": "1785418200000"},
        received_at,
    )

    assert stats["message_count"] == 1
    assert stats["symbols"]["AAPL"]["message_count"] == 1
    assert stats["symbols"]["AAPL"]["first_vendor_time"] == "1785418200000"
    assert stats["symbols"]["AAPL"]["populated_fields"] == {"id", "price", "time"}


def test_vendor_message_lag_supports_millisecond_and_second_timestamps() -> None:
    received_at = datetime(2026, 7, 30, 13, 30, 1, tzinfo=UTC)
    vendor_time = received_at - timedelta(seconds=1)

    assert vendor_message_lag_ms(
        {"time": str(round(vendor_time.timestamp() * 1000))},
        received_at,
    ) == 1000
    assert vendor_message_lag_ms(
        {"time": str(round(vendor_time.timestamp()))},
        received_at,
    ) == 1000
    assert vendor_message_lag_ms({}, received_at) is None


def test_connection_error_record_preserves_close_evidence() -> None:
    class ClosedConnection(Exception):
        code = 1008
        reason = "policy"

    record = connection_error_record(ClosedConnection("connection rejected"))

    assert record == {
        "error_type": "ClosedConnection",
        "error": "connection rejected",
        "http_status": None,
        "close_code": 1008,
        "close_reason": "policy",
    }
