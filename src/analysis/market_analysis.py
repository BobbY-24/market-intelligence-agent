from __future__ import annotations

from src.models import MarketSnapshot, TreasurySnapshot


def main_development(snapshot: MarketSnapshot) -> tuple[str, int]:
    if snapshot.latest_value is None:
        return ("Market data unavailable", 20)
    if snapshot.daily_change_pct is not None and abs(snapshot.daily_change_pct) >= 3:
        return (f"Large daily move: {snapshot.daily_change_pct:.1f}%", 65)
    high_volume = (
        snapshot.volume
        and snapshot.average_volume
        and snapshot.volume > snapshot.average_volume * 1.8
    )
    if high_volume:
        return ("Volume materially above recent average", 60)
    return ("No major price anomaly in available market data", 30)


def treasury_theme(snapshot: TreasurySnapshot | None) -> str:
    if snapshot is None:
        return "Treasury data unavailable."
    ten_year_change = snapshot.daily_changes_bp.get("10Y")
    if ten_year_change is None:
        return "Treasury data is available, but daily changes are incomplete."
    if abs(ten_year_change) >= 8:
        direction = "higher" if ten_year_change > 0 else "lower"
        return f"The 10-year Treasury yield moved sharply {direction} by {ten_year_change:.1f} bp."
    return "Treasury yield changes are not unusually large in the available data."
