from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

AssetType = Literal["equity", "etf", "mutual_fund"]
Priority = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    asset_type: AssetType
    themes: list[str]
    priority: Priority = "medium"
    nav_only: bool = False
    requires_identity_verification: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketSnapshot:
    symbol: str
    as_of: datetime
    latest_value: float | None
    daily_change_pct: float | None = None
    five_day_change_pct: float | None = None
    one_month_change_pct: float | None = None
    ytd_change_pct: float | None = None
    volume: int | None = None
    average_volume: float | None = None
    fifty_day_ma: float | None = None
    two_hundred_day_ma: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    data_quality: str = "unknown"
    source: str = ""


@dataclass
class TreasurySnapshot:
    as_of: datetime
    yields: dict[str, float | None]
    daily_changes_bp: dict[str, float | None]
    spreads_bp: dict[str, float | None]
    source: str
    data_quality: str = "official_daily"


@dataclass(frozen=True)
class PricePoint:
    date: datetime
    close: float


@dataclass
class ReportBundle:
    generated_at: datetime
    market_snapshots: list[MarketSnapshot]
    treasury_snapshot: TreasurySnapshot | None
    warnings: list[str]
    price_histories: dict[str, list[PricePoint]] = field(default_factory=dict)
