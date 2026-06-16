from datetime import datetime

from src.collectors.market_data import StooqMarketDataProvider
from src.models import Asset


class FakeHttp:
    def get_text(self, url: str) -> str:
        return "\n".join(
            [
                "Date,Open,High,Low,Close,Volume",
                "2026-01-02,10,10,10,10,100",
                "2026-01-05,11,11,11,11,200",
                "2026-01-06,12,12,12,12,300",
                "2026-01-07,13,13,13,13,400",
                "2026-01-08,14,14,14,14,500",
                "2026-01-09,15,15,15,15,600",
            ]
        )


def test_market_provider_computes_basic_changes() -> None:
    provider = StooqMarketDataProvider(FakeHttp())  # type: ignore[arg-type]
    snapshot = provider.get_snapshot(Asset("TEST", "Test", "equity", []), datetime(2026, 1, 9))

    assert snapshot.latest_value == 15
    assert snapshot.daily_change_pct == 7.14285714285714
    assert snapshot.five_day_change_pct == 50
    assert snapshot.volume == 600

