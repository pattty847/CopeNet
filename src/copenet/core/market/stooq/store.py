"""Locating, indexing and reading the offline Stooq daily archive."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Declared alongside every number derived from this archive. Deliberately NOT one of
# price_history's basis constants: those name bases the price cache can hold, and this
# one it must never hold. See the package docstring.
STOOQ_BASIS = "total_return"

_ENV_ROOT = "COPNET_STOOQ_ROOT"

# Probed only when the environment says nothing. An external volume is the realistic
# home for a two-gigabyte archive, but the operator's drive name is not a constant —
# any mounted volume is checked, and an absent archive is a normal, reportable state.
_RELATIVE_ROOT = Path("market-data/stooq/daily/data/daily/us")


class StooqUnavailable(RuntimeError):
    """The archive is not mounted or not where it was expected."""


def archive_root() -> Path | None:
    """The archive root, or None when it is not reachable right now."""
    configured = os.environ.get(_ENV_ROOT, "").strip()
    if configured:
        root = Path(configured).expanduser()
        return root if root.is_dir() else None
    volumes = Path("/Volumes")
    candidates = sorted(volumes.iterdir()) if volumes.is_dir() else []
    for volume in candidates:
        try:
            candidate = volume / _RELATIVE_ROOT
        except OSError:  # a stale mount point can raise on traversal
            continue
        if candidate.is_dir():
            return candidate
    return None


@dataclass(frozen=True)
class StooqBar:
    date: int  # unix seconds at UTC midnight, matching every other bar in CopeNet
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class StooqArchive:
    """A read-only index of the archive: symbol -> file, plus the equity/fund split.

    `equities` is folder-derived rather than heuristic — Stooq separates "<exchange>
    stocks" from "<exchange> etfs" itself, which is a cleaner common-stock filter than
    anything inferable from a price series.
    """

    root: Path
    paths: dict[str, Path]
    equities: frozenset[str]

    def __len__(self) -> int:
        return len(self.paths)

    def read(self, symbol: str, *, limit: int | None = None) -> list[StooqBar]:
        """Bars for one symbol, oldest first. Unparseable rows are skipped, not guessed."""
        path = self.paths.get(symbol.strip().upper())
        if path is None:
            return []
        try:
            with path.open() as handle:
                lines = handle.readlines()[1:]  # drop the <TICKER>,<PER>,... header
        except OSError:
            return []
        if limit is not None and len(lines) > limit:
            lines = lines[-limit:]
        bars: list[StooqBar] = []
        for line in lines:
            parts = line.split(",")
            if len(parts) < 9:
                continue
            try:
                stamp = parts[2].strip()
                bar = StooqBar(
                    date=_utc_midnight(stamp),
                    open=float(parts[4]),
                    high=float(parts[5]),
                    low=float(parts[6]),
                    close=float(parts[7]),
                    volume=float(parts[8]),
                )
            except (ValueError, IndexError):
                continue
            if bar.close <= 0:
                continue
            bars.append(bar)
        return bars


def _utc_midnight(stamp: str) -> int:
    """`YYYYMMDD` to unix seconds, without paying for a datetime parse 10 million times."""
    from datetime import date, datetime, timezone

    day = date(int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8]))
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def load_archive(root: Path | None = None) -> StooqArchive:
    """Index the archive. Raises StooqUnavailable when it is not mounted.

    A later duplicate symbol does not overwrite an earlier one: the same ticker can
    appear under more than one exchange folder, and silently preferring whichever the
    filesystem happened to yield last would make the universe non-deterministic.
    """
    resolved = root or archive_root()
    if resolved is None or not resolved.is_dir():
        raise StooqUnavailable(
            f"Stooq archive not found. Mount the drive or set {_ENV_ROOT} to the "
            "'data/daily/us' directory of an extracted d_us_txt.zip."
        )
    paths: dict[str, Path] = {}
    equities: set[str] = set()
    for group in sorted(resolved.iterdir()):
        if not group.is_dir():
            continue
        is_equity = "stocks" in group.name.lower()
        for path in sorted(group.rglob("*.txt")):
            symbol = path.name.removesuffix(".txt").removesuffix(".us").upper()
            if not symbol or symbol in paths:
                continue
            paths[symbol] = path
            if is_equity:
                equities.add(symbol)
    if not paths:
        raise StooqUnavailable(f"Stooq archive at {resolved} contains no ticker files")
    return StooqArchive(root=resolved, paths=paths, equities=frozenset(equities))
