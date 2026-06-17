from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isnan

import yfinance as yf

from src.models import Asset, MarketSnapshot, PricePoint


@dataclass(frozen=True)
class CollectedMarketData:
    snapshot: MarketSnapshot
    price_history: list[PricePoint]


class YFinanceMarketDataProvider:
    """Yahoo Finance backed market data provider."""

    def __init__(self, delay_label: str = "yfinance_daily") -> None:
        self.delay_label = delay_label

    def collect(self, asset: Asset, as_of: datetime) -> CollectedMarketData:
        try:
            history = yf.Ticker(asset.symbol).history(period="1y", interval="1d", auto_adjust=False)
        except Exception as exc:
            return CollectedMarketData(
                snapshot=MarketSnapshot(
                    symbol=asset.symbol,
                    as_of=as_of,
                    latest_value=None,
                    data_quality=f"missing: {exc}",
                    source="yfinance",
                ),
                price_history=[],
            )

        closes = []
        price_history = []
        volumes = []
        rows = []
        for idx, row in history.iterrows():
            close = _float_or_none(row.get("Close"))
            if close is None:
                continue
            point_time = idx.to_pydatetime().replace(tzinfo=None)
            volume = _int_or_none(row.get("Volume"))
            rows.append({"date": point_time, "close": close, "volume": volume})
            closes.append(close)
            price_history.append(PricePoint(date=point_time, close=close))
            if volume is not None:
                volumes.append(volume)

        if not rows:
            return CollectedMarketData(
                snapshot=MarketSnapshot(
                    symbol=asset.symbol,
                    as_of=as_of,
                    latest_value=None,
                    data_quality="missing: provider returned empty history",
                    source="yfinance",
                ),
                price_history=[],
            )

        latest = rows[-1]
        data_quality = "nav_prior_day" if asset.nav_only else self.delay_label
        return CollectedMarketData(
            snapshot=MarketSnapshot(
                symbol=asset.symbol,
                as_of=latest["date"],
                latest_value=latest["close"],
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
                data_quality=data_quality,
                source="yfinance",
            ),
            price_history=_current_year_points(price_history, as_of.year),
        )


def _current_year_points(price_history: list[PricePoint], year: int) -> list[PricePoint]:
    return [point for point in price_history if point.date.year == year]


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


def _float_or_none(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        numeric = float(value)
        return None if isnan(numeric) else numeric
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        numeric = float(value)
        return None if isnan(numeric) else int(numeric)
    except (TypeError, ValueError):
        return None
