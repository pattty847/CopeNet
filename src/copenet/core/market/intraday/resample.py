"""Roll native grain bars up to a derived interval, anchored to the trading session.

The daily lane's `resample_bars` groups by calendar date. Intraday cannot: it has to group
within a session, and it has to agree with how the vendor already buckets. Yahoo anchors its
hourly bars to the regular open — 09:30, 10:30 … 15:30, seven per session with a 30-minute
stub — so derived bars anchor there too, and fetched and derived candles land on the same
boundaries.

THE INVARIANT THAT DECIDES THE ANCHOR: turning extended hours on must not move a
regular-session candle. So every bucket is measured from that session's 09:30, and premarket
bars bucket *backward* from it (08:30, 07:30 …) rather than forward from 04:00. Anchoring to
the extended open instead would silently re-cut every regular-hours candle the moment the
operator toggled the session mode — a chart redrawing its own past for a display setting.

Bars from different sessions can never share a bucket, because each bar is anchored to its
own session's open.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from ..models import MarketBar

EXCHANGE = ZoneInfo("America/New_York")
#: US equity regular open. The anchor for every derived intraday bucket.
REGULAR_OPEN = time(9, 30)


def session_anchor(timestamp: int) -> int:
    """Unix seconds of the regular open for the session a bar belongs to."""
    local = datetime.fromtimestamp(int(timestamp), tz=EXCHANGE)
    return int(datetime.combine(local.date(), REGULAR_OPEN, tzinfo=EXCHANGE).timestamp())


def bucket_start(timestamp: int, step_seconds: int) -> int:
    """The bucket a bar falls in, measured from its own session's regular open.

    Floor division is deliberate and load-bearing: premarket bars sit at a negative offset
    from 09:30, and Python floors toward negative infinity, so 08:45 lands in the 08:30
    bucket rather than the 09:30 one. Truncating toward zero would fold the whole premarket
    into the opening candle.
    """
    anchor = session_anchor(timestamp)
    return anchor + ((int(timestamp) - anchor) // step_seconds) * step_seconds


def resample_intraday(bars: list[MarketBar], step_seconds: int) -> list[MarketBar]:
    """Group bars into `step_seconds` buckets and roll each up to one candle.

    Open is the first bar's open, close the last bar's close, high and low the extremes, and
    volume the sum — the ordinary roll-up. A bucket with no volume at all sums to zero, which
    is the honest answer overnight rather than an absence.
    """
    if step_seconds <= 0:
        raise ValueError(f"step must be positive: {step_seconds}")
    if not bars:
        return []

    grouped: dict[int, list[MarketBar]] = {}
    for bar in sorted(bars, key=lambda row: int(row.t)):
        grouped.setdefault(bucket_start(int(bar.t), step_seconds), []).append(bar)

    return [
        MarketBar(
            t=start,
            o=group[0].o,
            h=max(row.h for row in group),
            l=min(row.l for row in group),
            c=group[-1].c,
            v=sum(int(row.v) for row in group),
        )
        for start, group in sorted(grouped.items())
    ]
