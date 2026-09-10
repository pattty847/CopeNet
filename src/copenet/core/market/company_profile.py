"""What a ticker actually is: the business, the sector, the website.

A scanner surfaces names an operator has never heard of, and "SLI" tells you nothing about
whether it is a lithium miner or a shell. This is the answer to "what is this", cached
durably because it is the most static data in the whole Market lane — a company's industry
and business description change on the order of years, not minutes.

Coverage is honest about the asset type. Yahoo supplies a full profile for an equity, a
strategy blurb and a fund family for an ETF, a website for a crypto pair, and nothing at all
for an index. Absence is reported as absence; the UI must not render an empty card as though
the lookup merely had not finished.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import threading

from copenet.core._json_store import read_json, write_json_atomic

from .data_sources import yf_symbol

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
#: A business description does not change on a schedule worth polling. Long by design.
DEFAULT_MAX_AGE_DAYS = 30
SUMMARY_LIMIT = 2_000


@dataclass
class CompanyProfile:
    symbol: str
    #: EQUITY | ETF | CRYPTOCURRENCY | INDEX | MUTUALFUND | '' when the vendor is silent.
    quote_type: str = ""
    name: str = ""
    summary: str = ""
    sector: str = ""
    industry: str = ""
    website: str = ""
    country: str = ""
    employees: int | None = None
    #: ETF-only. An equity has a sector; a fund has a category and a family.
    category: str = ""
    fund_family: str = ""
    fetched_at: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when the vendor gave nothing worth showing — an index, typically."""
        return not any((self.summary, self.sector, self.industry, self.website, self.category))

    def to_wire(self) -> dict:
        return {
            "symbol": self.symbol,
            "quoteType": self.quote_type,
            "name": self.name,
            "summary": self.summary,
            "sector": self.sector,
            "industry": self.industry,
            "website": self.website,
            "country": self.country,
            "employees": self.employees,
            "category": self.category,
            "fundFamily": self.fund_family,
            "fetchedAt": self.fetched_at,
            "isEmpty": self.is_empty,
            "warnings": list(self.warnings),
        }


def _text(value: object, limit: int = 300) -> str:
    return str(value).strip()[:limit] if isinstance(value, str) and value.strip() else ""


def fetch_company_profile(symbol: str) -> CompanyProfile:
    """One vendor lookup. Never raises: an unreachable profile is a missing profile."""
    normalized = symbol.strip().upper()
    profile = CompanyProfile(symbol=normalized, fetched_at=datetime.now(timezone.utc).isoformat())
    try:
        import yfinance as yf

        info = yf.Ticker(yf_symbol(normalized)).info or {}
    except Exception as exc:
        logger.warning("market: %s profile lookup failed", normalized, exc_info=True)
        profile.warnings.append(f"Profile unavailable: {exc}"[:200])
        return profile

    profile.quote_type = _text(info.get("quoteType"), 40)
    profile.name = _text(info.get("longName") or info.get("shortName"))
    profile.summary = _text(info.get("longBusinessSummary"), SUMMARY_LIMIT)
    profile.sector = _text(info.get("sector"), 80)
    profile.industry = _text(info.get("industry"), 120)
    profile.website = _text(info.get("website"), 300)
    profile.country = _text(info.get("country"), 80)
    profile.category = _text(info.get("category"), 80)
    profile.fund_family = _text(info.get("fundFamily"), 120)
    employees = info.get("fullTimeEmployees")
    profile.employees = int(employees) if isinstance(employees, (int, float)) and employees > 0 else None
    return profile


class CompanyProfileStore:
    """One JSON file per symbol. Thread-safe, and stale rather than absent on a fetch failure."""

    def __init__(self, root_dir: Path, *, fetcher=None) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._fetch = fetcher or fetch_company_profile

    def path_for(self, symbol: str) -> Path:
        safe = "".join(char for char in symbol.upper() if char.isalnum() or char in "-._^")
        if not safe:
            raise ValueError(f"invalid symbol: {symbol!r}")
        return self._root / f"{safe}.json"

    def load(self, symbol: str) -> CompanyProfile | None:
        with self._lock:
            raw = read_json(self.path_for(symbol), fallback=None)
        if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
            return None
        stored = raw.get("profile")
        if not isinstance(stored, dict):
            return None
        known = {f for f in CompanyProfile.__dataclass_fields__}
        return CompanyProfile(**{k: v for k, v in stored.items() if k in known})

    def save(self, profile: CompanyProfile) -> CompanyProfile:
        with self._lock:
            write_json_atomic(self.path_for(profile.symbol), {
                "version": CACHE_VERSION, "profile": asdict(profile),
            })
        return profile

    def resolve(
        self, symbol: str, *, refresh: bool = False, max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        now: datetime | None = None,
    ) -> CompanyProfile:
        """Cached profile, refetched when missing, stale, or explicitly refreshed."""
        normalized = symbol.strip().upper()
        cached = self.load(normalized)
        if cached and not refresh and not _is_stale(cached, max_age_days, now):
            return cached

        fetched = self._fetch(normalized)
        # A failed refresh keeps whatever was cached: a description from last month beats an
        # empty panel, and the warning says which it is.
        if fetched.warnings and cached:
            cached.warnings = list(fetched.warnings)
            return cached
        return self.save(fetched)


def _is_stale(profile: CompanyProfile, max_age_days: int, now: datetime | None) -> bool:
    if not profile.fetched_at:
        return True
    try:
        stamp = datetime.fromisoformat(profile.fetched_at)
    except ValueError:
        return True
    stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - stamp > timedelta(days=max_age_days)
