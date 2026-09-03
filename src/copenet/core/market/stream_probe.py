"""Bounded Yahoo Finance WebSocket capture for market-data feasibility work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import random
from pathlib import Path
import time
from typing import Any

from websockets.asyncio.client import connect

from copenet.core._json_store import write_json_atomic

from .yahoo_stream import YAHOO_STREAM_URL, decode_yahoo_stream_message


@dataclass(frozen=True)
class StreamProbeConfig:
    symbols: tuple[str, ...]
    start_at: datetime
    end_at: datetime
    expected_date: str | None = None
    heartbeat_seconds: float = 15.0
    max_reconnects: int = 5


def validate_stream_probe_config(config: StreamProbeConfig) -> None:
    if not config.symbols:
        raise ValueError("at least one symbol is required")
    if config.start_at.tzinfo is None or config.end_at.tzinfo is None:
        raise ValueError("start_at and end_at must include timezone offsets")
    if config.end_at <= config.start_at:
        raise ValueError("end_at must be later than start_at")
    if config.heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")
    if config.max_reconnects < 0:
        raise ValueError("max_reconnects cannot be negative")


async def capture_yahoo_stream(
    config: StreamProbeConfig,
    *,
    output_directory: Path,
) -> dict[str, Any]:
    """Capture decoded stream messages and connection events until the hard stop."""
    validate_stream_probe_config(config)
    output_directory.mkdir(parents=True, exist_ok=True)
    run_name = config.start_at.strftime("%Y%m%dT%H%M%S%z")
    messages_path = output_directory / f"{run_name}-messages.jsonl"
    events_path = output_directory / f"{run_name}-events.jsonl"
    summary_path = output_directory / f"{run_name}-summary.json"
    stats = _new_stats(config)

    if config.expected_date and datetime.now(config.start_at.tzinfo).date().isoformat() != config.expected_date:
        stats["status"] = "skipped_wrong_date"
        stats["completed_at"] = datetime.now(UTC).isoformat()
        write_json_atomic(summary_path, stats)
        return stats

    await _wait_until(config.start_at)
    if datetime.now(UTC) >= config.end_at.astimezone(UTC):
        stats["status"] = "skipped_after_end"
        stats["completed_at"] = datetime.now(UTC).isoformat()
        write_json_atomic(summary_path, stats)
        return stats

    with messages_path.open("a", encoding="utf-8", buffering=1) as messages_file:
        with events_path.open("a", encoding="utf-8", buffering=1) as events_file:
            reconnect_index = 0
            while datetime.now(UTC) < config.end_at.astimezone(UTC):
                _write_jsonl(
                    events_file,
                    _connection_event("connecting", reconnect_index=reconnect_index),
                )
                try:
                    async with connect(
                        YAHOO_STREAM_URL,
                        open_timeout=15,
                        close_timeout=10,
                        ping_interval=20,
                        ping_timeout=20,
                    ) as websocket:
                        stats["connection_count"] += 1
                        _write_jsonl(
                            events_file,
                            _connection_event("connected", reconnect_index=reconnect_index),
                        )
                        await websocket.send(json.dumps({"subscribe": list(config.symbols)}))
                        await _capture_connection(
                            websocket,
                            config=config,
                            messages_file=messages_file,
                            events_file=events_file,
                            stats=stats,
                        )
                except Exception as exc:
                    stats["disconnect_count"] += 1
                    error = connection_error_record(exc)
                    stats["connection_errors"].append(error)
                    _write_jsonl(
                        events_file,
                        {
                            **_connection_event("disconnected", reconnect_index=reconnect_index),
                            **error,
                        },
                    )

                if datetime.now(UTC) >= config.end_at.astimezone(UTC):
                    break
                if reconnect_index >= config.max_reconnects:
                    stats["status"] = "reconnect_limit_reached"
                    break
                delay = reconnect_delay_seconds(reconnect_index)
                reconnect_index += 1
                stats["reconnect_count"] = reconnect_index
                _write_jsonl(
                    events_file,
                    {
                        **_connection_event("reconnect_backoff", reconnect_index=reconnect_index),
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(min(delay, _seconds_until(config.end_at)))

    if stats["status"] == "running":
        stats["status"] = "completed"
    stats["completed_at"] = datetime.now(UTC).isoformat()
    stats["message_path"] = str(messages_path)
    stats["event_path"] = str(events_path)
    stats["summary_path"] = str(summary_path)
    _finalize_stats(stats)
    write_json_atomic(summary_path, stats)
    return stats


async def _capture_connection(
    websocket: Any,
    *,
    config: StreamProbeConfig,
    messages_file: Any,
    events_file: Any,
    stats: dict[str, Any],
) -> None:
    next_heartbeat = time.monotonic() + config.heartbeat_seconds
    while datetime.now(UTC) < config.end_at.astimezone(UTC):
        seconds_to_heartbeat = max(next_heartbeat - time.monotonic(), 0.05)
        timeout = min(seconds_to_heartbeat, _seconds_until(config.end_at))
        try:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
        except TimeoutError:
            if datetime.now(UTC) >= config.end_at.astimezone(UTC):
                return
            await websocket.send(json.dumps({"subscribe": list(config.symbols)}))
            _write_jsonl(events_file, _connection_event("subscription_heartbeat"))
            next_heartbeat = time.monotonic() + config.heartbeat_seconds
            continue

        received_at = datetime.now(UTC)
        decoded = decode_yahoo_stream_message(raw_message)
        record = {
            "received_at": received_at.isoformat(),
            "vendor_lag_ms": vendor_message_lag_ms(decoded, received_at),
            "message": decoded,
        }
        _write_jsonl(messages_file, record)
        record_message_stats(stats, decoded, received_at)
        if time.monotonic() >= next_heartbeat:
            await websocket.send(json.dumps({"subscribe": list(config.symbols)}))
            _write_jsonl(events_file, _connection_event("subscription_heartbeat"))
            next_heartbeat = time.monotonic() + config.heartbeat_seconds


def record_message_stats(
    stats: dict[str, Any],
    message: dict[str, Any],
    received_at: datetime,
) -> None:
    stats["message_count"] += 1
    symbol = str(message.get("id") or "unknown").upper()
    symbol_stats = stats["symbols"].setdefault(symbol, _new_symbol_stats())
    symbol_stats["message_count"] += 1
    symbol_stats["first_received_at"] = symbol_stats["first_received_at"] or received_at.isoformat()
    symbol_stats["last_received_at"] = received_at.isoformat()
    symbol_stats["populated_fields"].update(
        key for key, value in message.items() if value is not None
    )
    vendor_time = message.get("time")
    if vendor_time is not None:
        symbol_stats["first_vendor_time"] = symbol_stats["first_vendor_time"] or str(vendor_time)
        symbol_stats["last_vendor_time"] = str(vendor_time)


def vendor_message_lag_ms(message: dict[str, Any], received_at: datetime) -> int | None:
    raw_value = message.get("time")
    if raw_value is None:
        return None
    try:
        timestamp = int(raw_value)
    except (TypeError, ValueError):
        return None
    vendor_seconds = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    return round(received_at.timestamp() * 1000 - vendor_seconds * 1000)


def connection_error_record(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    return {
        "error_type": type(exc).__name__,
        "error": str(exc)[:500],
        "http_status": getattr(response, "status_code", None),
        "close_code": getattr(exc, "code", None),
        "close_reason": getattr(exc, "reason", None),
    }


def reconnect_delay_seconds(reconnect_index: int) -> float:
    base_delays = (5, 30, 120, 300, 900)
    base = base_delays[min(reconnect_index, len(base_delays) - 1)]
    return round(base + random.uniform(0, base * 0.2), 2)


def _new_stats(config: StreamProbeConfig) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "running",
        "vendor": "yahoo_finance_websocket",
        "url": YAHOO_STREAM_URL,
        "symbols_requested": list(config.symbols),
        "start_at": config.start_at.isoformat(),
        "end_at": config.end_at.isoformat(),
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "message_count": 0,
        "connection_count": 0,
        "disconnect_count": 0,
        "reconnect_count": 0,
        "connection_errors": [],
        "symbols": {},
    }


def _new_symbol_stats() -> dict[str, Any]:
    return {
        "message_count": 0,
        "first_received_at": None,
        "last_received_at": None,
        "first_vendor_time": None,
        "last_vendor_time": None,
        "populated_fields": set(),
    }


def _finalize_stats(stats: dict[str, Any]) -> None:
    for symbol_stats in stats["symbols"].values():
        symbol_stats["populated_fields"] = sorted(symbol_stats["populated_fields"])


async def _wait_until(target: datetime) -> None:
    delay = _seconds_until(target)
    if delay > 0:
        await asyncio.sleep(delay)


def _seconds_until(target: datetime) -> float:
    return max((target.astimezone(UTC) - datetime.now(UTC)).total_seconds(), 0)


def _connection_event(event: str, **extra: Any) -> dict[str, Any]:
    return {"recorded_at": datetime.now(UTC).isoformat(), "event": event, **extra}


def _write_jsonl(file_handle: Any, record: dict[str, Any]) -> None:
    file_handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
