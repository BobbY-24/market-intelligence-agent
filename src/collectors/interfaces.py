from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.models import Asset, MarketSnapshot, TreasurySnapshot


class MarketDataProvider(Protocol):
    def get_snapshot(self, asset: Asset, as_of: datetime) -> MarketSnapshot:
        """Return a market snapshot, preserving missing values when unavailable."""


class MacroDataProvider(Protocol):
    def get_treasury_curve(self, as_of: datetime) -> TreasurySnapshot:
        """Return the latest Treasury curve snapshot."""

