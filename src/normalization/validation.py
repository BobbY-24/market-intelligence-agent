from __future__ import annotations

import re

from src.models import Asset

VALID_ASSET_TYPES = {"equity", "etf", "mutual_fund"}
VALID_PRIORITIES = {"low", "medium", "high"}
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def validate_watchlist(assets: list[Asset]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for asset in assets:
        if not SYMBOL_RE.match(asset.symbol):
            errors.append(f"{asset.symbol}: invalid symbol format")
        if asset.asset_type not in VALID_ASSET_TYPES:
            errors.append(f"{asset.symbol}: invalid asset_type {asset.asset_type}")
        if asset.priority not in VALID_PRIORITIES:
            errors.append(f"{asset.symbol}: invalid priority {asset.priority}")
        if asset.symbol in seen:
            errors.append(f"{asset.symbol}: duplicate symbol")
        seen.add(asset.symbol)
        if asset.requires_identity_verification:
            message = f"{asset.symbol}: identity, asset class, and benchmark require verification"
            errors.append(message)
    return errors
