from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from src.collectors.http import CachedHttpClient
from src.models import Asset, MarketSnapshot


class StooqMarketDataProvider:
    """Free Stooq CSV-backed market data provider."""

    def __init__(self, http: CachedHttpClient) -> None:
        self.http = http

    def get_snapshot(self, asset: Asset, as_of: datetime) -> MarketSnapshot:
        try:
            rows = self._history(asset.symbol)
        except Exception as exc:
            return MarketSnapshot(
                symbol=asset.symbol,
                as_of=as_of,
                latest_value=None,
                data_quality=f"missing: {exc}",
                source="stooq",
            )

        if not rows:
            return MarketSnapshot(asset.symbol, as_of, None, data_quality="missing", source="stooq")

        latest = rows[-1]
        closes = [row["close"] for row in rows if row["close"] is not None]
        volumes = [row["volume"] for row in rows if row["volume"] is not None]
        latest_close = latest["close"]

        return MarketSnapshot(
            symbol=asset.symbol,
            as_of=latest["date"],
            latest_value=latest_close,
            daily_change_pct=_pct_change(closes, 1),
            five_day_change_pct=_pct_change(closes, 5),
            one_month_change_pct=_pct_change(closes, 21),
            ytd_change_pct=_ytd_change(rows),
            volume=latest["volume"],
            average_volume=_average(volumes[-20:]),
            fifty_day_ma=_average(closes[-50:]),
            two_hundred_day_ma=_average(closes[-200:]),
            fifty_two_week_high=max(closes[-252:]) if closes else None,
            fifty_two_week_low=min(closes[-252:]) if closes else None,
            data_quality="nav_prior_day" if asset.nav_only else "delayed_or_provider_dependent",
            source="stooq",
        )

    def _history(self, symbol: str) -> list[dict]:
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
        text = self.http.get_text(url)
        if not text.lstrip().startswith("Date,"):
            raise ValueError("provider returned non-CSV response")
        reader = csv.DictReader(StringIO(text))
        rows = []
        for row in reader:
            close = _float_or_none(row.get("Close"))
            if close is None:
                continue
            rows.append(
                {
                    "date": datetime.fromisoformat(str(row["Date"])),
                    "close": close,
                    "volume": _int_or_none(row.get("Volume")),
                }
            )
        return rows


def _pct_change(values: list[float], periods: int) -> float | None:
    if len(values) <= periods or values[-periods - 1] == 0:
        return None
    return (values[-1] / values[-periods - 1] - 1) * 100


def _ytd_change(rows: list[dict]) -> float | None:
    if not rows:
        return None
    latest_year = rows[-1]["date"].year
    first_this_year = next((row["close"] for row in rows if row["date"].year == latest_year), None)
    latest = rows[-1]["close"]
    if first_this_year in (None, 0) or latest is None:
        return None
    return (latest / first_this_year - 1) * 100


def _average(values: list[float | int]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None
